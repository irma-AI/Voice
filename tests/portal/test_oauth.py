"""Sign-in with a click: the Portal as OAuth authorization server for its agent endpoint (VOI-119, make test-db).

A client registers, the owner approves on the consent page, the client exchanges the code with PKCE and calls the endpoint
with the token, the way claude.ai or ChatGPT does. Authlib refuses plain http, so every request here is https (secure=True).
The Commands run on the SDK's worker threads with their own database connection, so these tests commit (transaction=True).
"""

# pyright: basic
# (django-stubs types model fields for mypy's plugin; strict pyright cannot read them)

import base64
import hashlib
import html
import json
import secrets
from datetime import timedelta
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest
from authlib.oauth2.rfc8414 import AuthorizationServerMetadata
from django.db import IntegrityError, connection, transaction
from django.test import Client
from django.utils import timezone

from portal.accounts.models import (
    AccessToken,
    OAuthClient,
    OAuthCode,
    OAuthConnection,
)
from tests.portal.helpers import business_with_login
from tests.portal.test_agent_endpoint import ask, tool_names

pytestmark = [pytest.mark.db, pytest.mark.django_db(transaction=True)]

PORTAL = "https://portal.example.se"
BACK = "http://localhost:33418/callback"


@pytest.fixture(autouse=True)
def portal_url(settings: Any) -> None:
    settings.PORTAL_URL = PORTAL
    settings.SUPER_ADMIN_EMAIL = ""


def register(**extra: Any) -> dict[str, Any]:
    answer = Client().post(
        "/oauth/register/",
        json.dumps(
            {
                "client_name": "Claude",
                "redirect_uris": [BACK],
                "token_endpoint_auth_method": "none",
                **extra,
            }
        ),
        content_type="application/json",
        secure=True,
    )
    assert answer.status_code == 201, answer.content
    return answer.json()


def pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    return verifier, challenge


def authorize_url(client_id: str, challenge: str | None, **extra: str) -> str:
    query = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": BACK,
        "state": "s-1",
        **extra,
    }
    if challenge is not None:
        query |= {"code_challenge": challenge, "code_challenge_method": "S256"}
    return "/oauth/authorize/?" + urlencode(query)


def approve(
    owner: Client, url: str, access: str = "full", decision: str = "approve"
) -> dict[str, list[str]]:
    answer = owner.post(url, {"access": access, "decision": decision}, secure=True)
    assert answer.status_code == 302, answer.content
    assert answer["Location"].startswith(BACK)
    return parse_qs(urlsplit(answer["Location"]).query)


def exchange(form: dict[str, str]) -> Any:
    return Client().post("/oauth/token/", form, secure=True)


def signed_in(owner: Client, access: str = "full") -> tuple[str, dict[str, Any]]:
    """A full sign-in, as an assistant does it: the client id and the token answer."""
    client_id = register()["client_id"]
    verifier, challenge = pkce()
    code = approve(owner, authorize_url(client_id, challenge), access)["code"][0]
    answer = exchange(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": BACK,
            "client_id": client_id,
            "code_verifier": verifier,
        }
    )
    assert answer.status_code == 200, answer.content
    return client_id, answer.json()


def test_a_401_names_the_resource_metadata_and_both_documents_hold_to_their_rfcs() -> (
    None
):
    answer = Client().post("/mcp/", "{}", content_type="application/json")
    assert answer.status_code == 401
    assert (
        f'resource_metadata="{PORTAL}/.well-known/oauth-protected-resource/mcp/"'
        in answer["WWW-Authenticate"]
    )
    resource = Client().get("/.well-known/oauth-protected-resource/mcp/").json()
    assert resource["resource"] == PORTAL + "/mcp/" and resource[
        "authorization_servers"
    ] == [PORTAL]
    metadata = Client().get("/.well-known/oauth-authorization-server").json()
    AuthorizationServerMetadata(metadata).validate()  # RFC 8414, as Authlib reads it
    assert metadata["code_challenge_methods_supported"] == ["S256"]


def test_a_sign_in_gives_a_token_the_endpoint_takes_with_the_scope_the_owner_picked() -> (
    None
):
    business, owner = business_with_login("user-a@example.com", "Owner A's Salon")
    client_id = register()["client_id"]
    _, challenge = pkce()
    page = html.unescape(
        owner.get(authorize_url(client_id, challenge), secure=True).content.decode()
    )
    assert (
        "Connect “Claude”?" in page
        and "Owner A's Salon" in page
        and "localhost" in page
    )
    assert "Read-only" in page and "Full" in page
    _, read = signed_in(owner, "read")
    assert (
        read["scope"] == "read"
        and read["expires_in"] == 3600
        and read["access_token"].startswith("voice_")
    )
    assert "add_module" not in tool_names(
        ask("tools/list", secret=read["access_token"])
    )
    _, full = signed_in(owner, "full")
    assert "add_module" in tool_names(ask("tools/list", secret=full["access_token"]))
    assert {c.business for c in OAuthConnection.objects.all()} == {business}


def test_refresh_gives_new_tokens_and_the_old_refresh_token_stops() -> None:
    _, owner = business_with_login("user-a@example.com", "Owner A's Salon")
    client_id, first = signed_in(owner)
    renew = {
        "grant_type": "refresh_token",
        "refresh_token": first["refresh_token"],
        "client_id": client_id,
    }
    second = exchange(renew)
    assert second.status_code == 200, second.content
    assert second.json()["refresh_token"] != first["refresh_token"]
    assert tool_names(ask("tools/list", secret=second.json()["access_token"]))
    assert exchange(renew).json()["error"] == "invalid_grant"  # already used


def test_pkce_is_required_and_checked() -> None:
    _, owner = business_with_login("user-a@example.com", "Owner A's Salon")
    client_id = register()["client_id"]
    assert owner.get(authorize_url(client_id, None), secure=True).status_code == 400
    _, challenge = pkce()
    code = approve(owner, authorize_url(client_id, challenge))["code"][0]
    wrong = exchange(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": BACK,
            "client_id": client_id,
            "code_verifier": secrets.token_urlsafe(48),
        }
    )
    assert wrong.status_code == 400 and wrong.json()["error"] == "invalid_grant"
    assert not AccessToken.objects.exists()


def test_a_token_for_another_resource_is_refused() -> None:
    _, owner = business_with_login("user-a@example.com", "Owner A's Salon")
    client_id = register()["client_id"]
    verifier, challenge = pkce()
    other = owner.get(
        authorize_url(client_id, challenge, resource="https://elsewhere.example/mcp"),
        secure=True,
    )
    assert other.status_code == 400
    code = approve(
        owner, authorize_url(client_id, challenge, resource=PORTAL + "/mcp")
    )["code"][0]
    answer = exchange(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": BACK,
            "client_id": client_id,
            "code_verifier": verifier,
            "resource": "https://elsewhere.example/mcp",
        }
    )
    assert (
        answer.json()["error"] == "invalid_target" and not AccessToken.objects.exists()
    )


def test_a_code_works_once() -> None:
    _, owner = business_with_login("user-a@example.com", "Owner A's Salon")
    client_id = register()["client_id"]
    verifier, challenge = pkce()
    code = approve(owner, authorize_url(client_id, challenge))["code"][0]
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": BACK,
        "client_id": client_id,
        "code_verifier": verifier,
    }
    assert exchange(form).status_code == 200
    assert exchange(form).json()["error"] == "invalid_grant"


def test_saying_no_connects_nothing() -> None:
    _, owner = business_with_login("user-a@example.com", "Owner A's Salon")
    client_id = register()["client_id"]
    _, challenge = pkce()
    back = approve(owner, authorize_url(client_id, challenge), decision="deny")
    assert back["error"] == ["access_denied"] and back["state"] == ["s-1"]
    assert not OAuthCode.objects.exists()


def test_the_consent_page_needs_the_login() -> None:
    client_id = register()["client_id"]
    _, challenge = pkce()
    answer = Client().get(authorize_url(client_id, challenge), secure=True)
    assert answer.status_code == 302 and answer["Location"].startswith("/login/")


def test_revoking_a_connection_stops_its_token_and_its_refresh_and_only_its_owner_may() -> (
    None
):
    _, owner = business_with_login("user-a@example.com", "Owner A's Salon")
    _, other = business_with_login("user-b@example.com", "Owner B's Bikes")
    client_id, tokens = signed_in(owner)
    page = owner.get("/tokens/").content.decode()
    assert "Signed-in assistants" in page and "Claude" in page
    connection = OAuthConnection.objects.get()
    assert other.post(f"/tokens/connections/{connection.pk}/revoke/").status_code == 404
    assert owner.post(f"/tokens/connections/{connection.pk}/revoke/").status_code == 302
    assert ask("tools/list", secret=tokens["access_token"]).status_code == 401
    renew = exchange(
        {
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
            "client_id": client_id,
        }
    )
    assert renew.json()["error"] == "invalid_grant"


def test_the_client_revokes_through_rfc_7009() -> None:
    _, owner = business_with_login("user-a@example.com", "Owner A's Salon")
    client_id, tokens = signed_in(owner)
    answer = Client().post(
        "/oauth/revoke/",
        {"token": tokens["refresh_token"], "client_id": client_id},
        secure=True,
    )
    assert answer.status_code == 200
    assert OAuthConnection.objects.get().revoked_at is not None
    assert ask("tools/list", secret=tokens["access_token"]).status_code == 401


def test_an_expired_token_is_refused() -> None:
    _, owner = business_with_login("user-a@example.com", "Owner A's Salon")
    _, tokens = signed_in(owner)
    # A token made an hour ago: the database clock decides, so make one with its expiry passed.
    made = AccessToken.objects.get()
    AccessToken.objects.create(
        business=made.business,
        label="old",
        scope="full",
        token_hash=hashlib.sha256(b"voice_expired").hexdigest(),
        connection=made.connection,
        expires_at=timezone.now() - timedelta(seconds=1),
    )
    assert ask("tools/list", secret="voice_expired").status_code == 401
    assert ask("tools/list", secret=tokens["access_token"]).status_code == 200


def test_registration_refuses_an_address_it_could_be_tricked_into() -> None:
    for uris in (
        ["http://evil.example/cb"],
        ["javascript:alert(1)"],
        ["https://a.example/cb#x"],
        [],
        ["https://a.example/"] * 6,
    ):
        answer = Client().post(
            "/oauth/register/",
            json.dumps(
                {
                    "client_name": "X",
                    "redirect_uris": uris,
                    "token_endpoint_auth_method": "none",
                }
            ),
            content_type="application/json",
            secure=True,
        )
        assert answer.status_code == 400, uris
    assert not OAuthClient.objects.exists()


def test_a_confidential_client_authenticates_with_its_secret() -> None:
    _, owner = business_with_login("user-a@example.com", "Owner A's Salon")
    registered = register(token_endpoint_auth_method="client_secret_post")
    assert registered["client_secret"]
    assert (
        OAuthClient.objects.get().secret_hash != registered["client_secret"]
    )  # only its hash is kept
    verifier, challenge = pkce()
    code = approve(owner, authorize_url(registered["client_id"], challenge))["code"][0]
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": BACK,
        "client_id": registered["client_id"],
        "code_verifier": verifier,
    }
    assert exchange({**form, "client_secret": "wrong"}).status_code == 401
    code = approve(owner, authorize_url(registered["client_id"], challenge))["code"][0]
    assert (
        exchange(
            {**form, "code": code, "client_secret": registered["client_secret"]}
        ).status_code
        == 200
    )


def refused(statement: str, rule: str) -> None:
    with (
        pytest.raises(IntegrityError, match=rule),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute(statement)


def test_the_database_keeps_codes_connections_clients_and_tokens_as_made() -> None:
    _, owner = business_with_login("user-a@example.com", "Owner A's Salon")
    signed_in(owner)
    refused("UPDATE accounts_oauthcode SET used_at = NULL", "oauth_code_is_used_once")
    refused("UPDATE accounts_oauthcode SET scope = 'full'", "oauth_code_is_used_once")
    refused(
        "DELETE FROM accounts_oauthconnection",
        "oauth_connection_is_revoked_never_deleted",
    )
    refused(
        "UPDATE accounts_oauthconnection SET scope = 'read'",
        "oauth_connection_is_fixed",
    )
    refused(
        "UPDATE accounts_oauthclient SET client_name = 'Someone else'",
        "oauth_client_is_fixed",
    )
    refused(
        "UPDATE accounts_accesstoken SET expires_at = now() + interval '1 year'",
        "access_token_is_fixed",
    )
    refused(
        "UPDATE accounts_accesstoken SET connection_id = NULL", "access_token_is_fixed"
    )
    OAuthConnection.objects.get().revoke()
    refused(
        "UPDATE accounts_oauthconnection SET refresh_hash = repeat('a', 64)",
        "oauth_connection_is_fixed",
    )


def test_offboarding_ends_a_sign_in(settings: Any) -> None:
    from tests.portal.test_offboard import EMAIL, offboard

    settings.ENVIRONMENT = "local"
    _, owner = business_with_login(EMAIL, "Owner A's Salon")
    client_id, tokens = signed_in(owner)
    offboard()
    assert OAuthConnection.objects.get().revoked_at is not None
    renew = exchange(
        {
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
            "client_id": client_id,
        }
    )
    assert renew.json()["error"] == "invalid_grant"
