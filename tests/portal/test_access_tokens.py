"""A Business makes and revokes Access tokens on its Portal page, and the database holds only hashes (make test-db). No mocks of our own code."""

# pyright: basic
# (django-stubs types model fields for mypy's plugin; strict pyright cannot read them)

import re
from typing import Any

import pytest
from django.db import IntegrityError, connection, transaction
from django.test import Client
from django.utils import timezone

from portal.accounts import tokens
from portal.accounts.models import AccessToken, Business
from tests.portal.helpers import business_with_login

pytestmark = [pytest.mark.db, pytest.mark.django_db]

EMAIL = "petter.testsson@example.com"  # synthetic


def make(client: Client, label: str = "Claude Code", scope: str = "read") -> Any:
    return client.post("/tokens/", {"label": label, "scope": scope})


def secret_in(page: str) -> str:
    found = re.search(rf"{tokens.PREFIX}[A-Za-z0-9_-]+", page)
    assert found, "the page shows the secret"
    return found.group()


def stored(business: Business, label: str = "Claude Code") -> AccessToken:
    return AccessToken.objects.get(business=business, label=label)


def test_the_secret_shows_once_and_the_database_holds_only_its_hash() -> None:
    business, client = business_with_login()
    answer = make(client)
    assert (
        "no-store" in answer["Cache-Control"]
    )  # the browser keeps no copy of the secret
    secret = secret_in(answer.content.decode())
    assert stored(business).token_hash == tokens.hash_of(secret)
    assert secret not in client.get("/tokens/").content.decode()
    with connection.cursor() as cursor:  # the secret is in no column of any row
        cursor.execute("SELECT row_to_json(t)::text FROM accounts_accesstoken t")
        assert secret not in cursor.fetchone()[0]


def test_the_page_lists_label_scope_made_and_last_used_times_and_a_new_token_is_unused() -> (
    None
):
    business, client = business_with_login()
    make(client, "Claude Code", "full")
    page = client.get("/tokens/").content.decode()
    assert "Claude Code" in page and "Full" in page and "Never used" in page
    token = stored(business)
    assert token.scope == "full" and not token.is_operator
    assert token.created_at and token.last_used_at is None and token.revoked_at is None


def test_the_new_secret_has_a_copy_button_and_each_revoke_names_its_token_and_asks_first() -> (
    None
):
    _, client = business_with_login()
    page = make(client, "Claude Code").content.decode()
    secret = secret_in(page)
    assert (
        f'<pre id="new-token" tabindex="0" autofocus><code>{secret}</code></pre>'
        in page
    )
    assert 'data-copy="new-token"' in page
    make(client, "Reporting agent")
    page = client.get("/tokens/").content.decode()
    # Revoke opens a second step; the button that revokes says so and names the token, for a screen reader too.
    for label in ("Claude Code", "Reporting agent"):
        assert f'<summary>Revoke<span class="sr-only"> {label}</span></summary>' in page
        assert f'Revoke for good<span class="sr-only"> {label}</span>' in page


def test_a_refused_form_makes_no_token_and_shows_no_secret() -> None:
    business, client = business_with_login()
    for label, scope in (
        ("", "read"),
        ("   ", "read"),
        ("x" * 61, "read"),
        ("ok", "admin"),
        ("ok", ""),
    ):
        page = make(client, label, scope).content.decode()
        assert tokens.PREFIX not in page, (label, scope)
    assert not AccessToken.objects.filter(business=business).exists()


def test_revoking_marks_the_token_and_it_cannot_be_revoked_again_or_undone() -> None:
    business, client = business_with_login()
    make(client)
    token = stored(business)
    assert client.post(f"/tokens/{token.pk}/revoke/")["Location"] == "/tokens/"
    token.refresh_from_db()
    first = token.revoked_at
    assert first is not None
    assert "Revoked" in client.get("/tokens/").content.decode()
    token.revoke()  # a second revoke changes nothing
    token.refresh_from_db()
    assert token.revoked_at == first
    with (
        pytest.raises(IntegrityError, match="access_token_revoked_at_is_set_once"),
        transaction.atomic(),
    ):
        AccessToken.objects.filter(pk=token.pk).update(revoked_at=None)


def test_a_business_sees_and_revokes_only_its_own_tokens() -> None:
    business_a, client_a = business_with_login()
    _, client_b = business_with_login()
    make(client_a, "Owner A's agent")
    token = stored(business_a, "Owner A's agent")
    assert "Owner A's agent" not in client_b.get("/tokens/").content.decode()
    assert client_b.post(f"/tokens/{token.pk}/revoke/").status_code == 404
    token.refresh_from_db()
    assert token.revoked_at is None


def test_a_visitor_is_sent_to_the_login_and_a_get_of_revoke_does_nothing() -> None:
    business, client = business_with_login()
    make(client)
    token = stored(business)
    visitor = Client()
    assert visitor.post("/tokens/", {"label": "x", "scope": "read"})[
        "Location"
    ].startswith("/login/")
    assert visitor.post(f"/tokens/{token.pk}/revoke/")["Location"].startswith("/login/")
    assert client.get(f"/tokens/{token.pk}/revoke/")["Location"] == "/tokens/"
    token.refresh_from_db()
    assert token.revoked_at is None


def test_only_the_super_admin_account_makes_operator_tokens(settings: Any) -> None:
    settings.SUPER_ADMIN_EMAIL = EMAIL
    petter, petter_client = business_with_login(EMAIL, "Petter's Business")
    business_a, client_a = business_with_login()
    make(petter_client)
    make(client_a)
    assert stored(petter).is_operator and not stored(business_a).is_operator
    assert "Operator" in petter_client.get("/tokens/").content.decode()
    assert "Operator" not in client_a.get("/tokens/").content.decode()
    settings.SUPER_ADMIN_EMAIL = ""  # unset: nobody gets an operator token
    make(petter_client, "second")
    assert not stored(petter, "second").is_operator


def test_the_database_refuses_a_scope_outside_read_and_full() -> None:
    business, _ = business_with_login()
    with (
        pytest.raises(IntegrityError, match="access_token_scope_must_be_read_or_full"),
        transaction.atomic(),
    ):
        AccessToken.objects.create(
            business=business, label="x", scope="admin", token_hash="a" * 64
        )


def test_the_database_refuses_a_repeated_hash() -> None:
    business, _ = business_with_login()
    AccessToken.objects.create(
        business=business, label="x", scope="read", token_hash="a" * 64
    )
    with pytest.raises(IntegrityError, match="token_hash"), transaction.atomic():
        AccessToken.objects.create(
            business=business, label="y", scope="full", token_hash="a" * 64
        )


@pytest.mark.parametrize("bad", ["voice_" + "A" * 43, "A" * 64, "a" * 63, ""])
def test_the_database_refuses_anything_but_a_lower_case_sha256_in_place_of_the_hash(
    bad: str,
) -> None:
    business, _ = business_with_login()
    with (
        pytest.raises(IntegrityError, match="access_token_must_hold_a_sha256_hash"),
        transaction.atomic(),
    ):
        AccessToken.objects.create(
            business=business, label="x", scope="read", token_hash=bad
        )


def test_the_database_refuses_a_blank_label() -> None:
    business, _ = business_with_login()
    with (
        pytest.raises(IntegrityError, match="access_token_label_must_not_be_blank"),
        transaction.atomic(),
    ):
        AccessToken.objects.create(
            business=business, label=" ", scope="read", token_hash="a" * 64
        )


def test_a_made_token_changes_only_in_its_last_use_and_its_first_revoke() -> None:
    business, _ = business_with_login()
    token, _ = AccessToken.make(business, "x", "read", False)
    for change in (
        {"scope": "full"},
        {"is_operator": True},
        {"token_hash": "b" * 64},
    ):
        with (
            pytest.raises(IntegrityError, match="access_token_is_fixed"),
            transaction.atomic(),
        ):
            AccessToken.objects.filter(pk=token.pk).update(**change)
    with (
        pytest.raises(IntegrityError, match="access_token_revoked_at_is_set_once"),
        transaction.atomic(),
    ):
        AccessToken.objects.filter(pk=token.pk).update(revoked_at=timezone.now())
    AccessToken.objects.filter(pk=token.pk).update(last_used_at=timezone.now())
    token.refresh_from_db()
    assert token.last_used_at and token.scope == "read" and token.revoked_at is None


def test_a_token_is_never_deleted_only_revoked() -> None:
    business, _ = business_with_login()
    token, _ = AccessToken.make(business, "x", "read", False)
    refused = "access_token_is_revoked_never_deleted"
    with pytest.raises(IntegrityError, match=refused), transaction.atomic():
        token.delete()
    with (
        pytest.raises(IntegrityError, match=refused),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute("DELETE FROM accounts_accesstoken")
    with pytest.raises(IntegrityError, match=refused), transaction.atomic():
        business.delete()  # a Business's CASCADE takes no token with it
    assert AccessToken.objects.filter(pk=token.pk).exists()


def test_a_label_is_changed_only_when_offboarding_blanks_a_revoked_token() -> None:
    business, _ = business_with_login()
    token, _ = AccessToken.make(business, "Owner A's laptop", "read", False)
    refused = "access_token_label_is_blanked_only_by_offboarding"
    placeholder = f"Token {token.pk}"

    def update_label(label: str, switch: bool) -> None:
        with connection.cursor() as cursor:
            if switch:
                cursor.execute(
                    "SELECT set_config('voice.offboard_token_labels', 'on', true)"
                )
            AccessToken.objects.filter(pk=token.pk).update(label=label)

    for label, switch in ((placeholder, False), ("y", False), (placeholder, True)):
        # A plain update, and the switch on a token still live.
        with pytest.raises(IntegrityError, match=refused), transaction.atomic():
            update_label(label, switch)
    token.revoke()
    for label, switch in ((placeholder, False), ("Owner B's laptop", True)):
        with pytest.raises(IntegrityError, match=refused), transaction.atomic():
            update_label(label, switch)
    token.refresh_from_db()
    assert token.label == "Owner A's laptop"


def test_a_new_token_comes_with_the_line_that_connects_claude_code(
    settings: Any,
) -> None:
    settings.PORTAL_URL = "https://portal.example.se"
    _, client = business_with_login()
    page = make(client).content.decode()
    secret = secret_in(page)
    line = f"claude mcp add --transport http voice https://portal.example.se/mcp/ --header &quot;Authorization: Bearer {secret}&quot;"
    assert line in page
    later = client.get("/tokens/").content.decode()
    assert (
        "https://portal.example.se/mcp/" in later
    )  # the address for a sign-in, and for a script
    assert (
        "claude mcp add" not in later
    )  # the line holds the secret, so it shows once with it
