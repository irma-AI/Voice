# pyright: basic
# (django-stubs types model fields for mypy's plugin; strict pyright cannot read them)
"""Sign-in with a click (VOI-119): the Portal is the OAuth 2.1 authorization server for its own agent endpoint, so claude.ai,
ChatGPT and other assistants connect without a pasted token. Authlib (DECISIONS.md, Petter 2026-10-20) runs the flows; the
storage is ours, so a sign-in's Access tokens are ordinary hashed AccessToken rows and the endpoint checks them as it checks
a pasted one.

- Discovery: protected-resource metadata (RFC 9728) and authorization-server metadata (RFC 8414).
- Registration: open dynamic client registration (RFC 7591); the consent page names the client and where it sends you back.
- Authorize: the consent page, behind the Portal login: the owner picks read-only or full for their Business.
- Token: authorization code with PKCE S256 (required), and refresh, whose token changes at every use.
- Revoke (RFC 7009), and every connection is listed on the Access tokens page, where the owner revokes it.
- Audience: a `resource` other than this endpoint is refused at authorize and token.
"""

import hashlib
import hmac
import secrets
from datetime import timedelta
from typing import Any, ClassVar
from urllib.parse import urlsplit

from authlib.common.urls import add_params_to_uri
from authlib.integrations.django_oauth2 import AuthorizationServer
from authlib.oauth2 import OAuth2Error
from authlib.oauth2.rfc6749 import ClientMixin, InvalidRequestError, grants
from authlib.oauth2.rfc6750 import BearerTokenGenerator
from authlib.oauth2.rfc7009 import RevocationEndpoint
from authlib.oauth2.rfc7591 import (
    ClientMetadataClaims,
    ClientRegistrationEndpoint,
    InvalidClientMetadataError,
)
from authlib.oauth2.rfc7636 import CodeChallenge
from authlib.oauth2.rfc9207 import IssuerParameter
from django import forms
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, connection, transaction
from django.db.models.functions import Now
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from portal.accounts import tokens
from portal.accounts.models import (
    OAUTH_AUTH_METHODS,
    AccessToken,
    Business,
    OAuthClient,
    OAuthCode,
    OAuthConnection,
)

# An Access token from a sign-in works for an hour; the client renews it with its refresh token.
ACCESS_SECONDS = 3600
# A refresh token used again within this long of its swap is refused without ending the connection (see OAuthConnection).
REFRESH_GRACE_SECONDS = 30
# A code is exchanged within 10 minutes of the approval, once.
CODE_SECONDS = 600
# Open registration writes a row per request: at most this many clients an hour, across everyone.
# shortcut: one global cap, so a flood refuses real clients for the rest of the hour; add a per-address limit if it is ever hit.
REGISTRATIONS_PER_HOUR = 100
SCOPES = list(tokens.SCOPES)  # "read", "full"


def issuer() -> str:
    return settings.PORTAL_URL.rstrip("/")


def resource() -> str:
    """The one resource tokens are for: the agent endpoint."""
    return issuer() + reverse("agent_endpoint")


def same_resource(asked: str | None) -> bool:
    """A client may leave `resource` out; one that names it must name this endpoint (with or without its last slash)."""
    return asked is None or asked.rstrip("/") == resource().rstrip("/")


def resource_metadata_url() -> str:
    return (
        issuer() + "/.well-known/oauth-protected-resource" + reverse("agent_endpoint")
    )


def hashed(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


class Client(ClientMixin):
    """A registered client, as Authlib asks about it."""

    def __init__(self, row: OAuthClient) -> None:
        self.row = row
        self.client_id = row.client_id

    def get_client_id(self) -> str:
        return self.row.client_id

    def get_default_redirect_uri(self) -> str | None:
        uris = self.row.redirect_uris
        return uris[0] if len(uris) == 1 else None

    def get_allowed_scope(self, scope: str) -> str:
        return (
            ""  # the owner picks read-only or full on the consent page, not the client
        )

    def check_redirect_uri(self, redirect_uri: str) -> bool:
        return redirect_uri in self.row.redirect_uris

    def check_client_secret(self, client_secret: str) -> bool:
        return bool(self.row.secret_hash) and hmac.compare_digest(
            self.row.secret_hash, hashed(client_secret)
        )

    def check_endpoint_auth_method(self, method: str, endpoint: str) -> bool:
        return method == self.row.auth_method

    def check_response_type(self, response_type: str) -> bool:
        return response_type == "code"

    def check_grant_type(self, grant_type: str) -> bool:
        return grant_type in ("authorization_code", "refresh_token")


class Code:
    """A code as Authlib asks about it; `row` is already spent (used_at set) when Authlib holds one."""

    def __init__(self, row: OAuthCode) -> None:
        self.row = row

    def get_redirect_uri(self) -> str:
        return self.row.redirect_uri

    def get_scope(self) -> str:
        return self.row.scope


class Refresh:
    """A live connection, found by its current refresh token."""

    def __init__(self, row: OAuthConnection, presented: str) -> None:
        self.row = row
        self.presented = presented

    def check_client(self, client: Client) -> bool:
        return self.row.client.pk == client.row.pk

    def get_scope(self) -> str:
        return self.row.scope

    def get_expires_in(self) -> int:
        return 0

    def is_expired(self) -> bool:
        return False

    def is_revoked(self) -> bool:
        return self.row.revoked_at is not None


AUTH_METHODS = list(OAUTH_AUTH_METHODS)


def refuse_another_resource(request: Any) -> None:
    if not same_resource(request.form.get("resource")):
        raise OAuth2Error(
            error="invalid_target",
            description="Tokens here are for the agent endpoint only.",
        )


class CodeGrant(grants.AuthorizationCodeGrant):
    TOKEN_ENDPOINT_AUTH_METHODS = AUTH_METHODS

    def save_authorization_code(self, code: str, request: Any) -> None:
        business, scope = request.user
        OAuthCode.objects.create(
            code_hash=hashed(code),
            client=request.client.row,
            business=business,
            scope=scope,
            redirect_uri=request.payload.redirect_uri or "",
            code_challenge=request.payload.data["code_challenge"],
        )

    def query_authorization_code(self, code: str, client: Client) -> Code | None:
        """Spends the code as it is read: a second exchange, or one after CODE_SECONDS, finds nothing."""
        row = OAuthCode.objects.filter(
            code_hash=hashed(code),
            client=client.row,
            used_at__isnull=True,
            created_at__gt=Now() - timedelta(seconds=CODE_SECONDS),
        ).first()
        if row is None or not OAuthCode.objects.filter(
            pk=row.pk, used_at__isnull=True
        ).update(used_at=Now()):
            return None
        return Code(row)

    def delete_authorization_code(self, authorization_code: Code) -> None:
        pass  # spent when read; the row stays as the record of the approval

    def authenticate_user(self, authorization_code: Code) -> tuple[Business, str]:
        return authorization_code.row.business, authorization_code.row.scope

    def validate_token_request(self) -> None:
        refuse_another_resource(self.request)
        super().validate_token_request()


class S256Only(CodeChallenge):
    """PKCE with S256 for every client (OAuth 2.1, the MCP spec): Authlib alone lets a request without a challenge through."""

    SUPPORTED_CODE_CHALLENGE_METHOD: ClassVar[list[str]] = ["S256"]

    def validate_code_challenge(self, grant: Any, redirect_uri: str) -> None:
        data = grant.request.payload.data
        if (
            not data.get("code_challenge")
            or data.get("code_challenge_method") != "S256"
        ):
            raise InvalidRequestError(
                "PKCE with code_challenge_method S256 is required."
            )
        super().validate_code_challenge(grant, redirect_uri)

    def get_authorization_code_challenge(self, authorization_code: Code) -> str:
        return authorization_code.row.code_challenge

    def get_authorization_code_challenge_method(self, authorization_code: Code) -> str:
        return "S256"


class RefreshGrant(grants.RefreshTokenGrant):
    TOKEN_ENDPOINT_AUTH_METHODS = AUTH_METHODS
    INCLUDE_NEW_REFRESH_TOKEN = True

    def authenticate_refresh_token(self, refresh_token: str) -> Refresh | None:
        live = OAuthConnection.objects.select_related("client").filter(
            revoked_at__isnull=True
        )
        row = live.filter(refresh_hash=hashed(refresh_token)).first()
        if row is None:
            # The one before, again, after the grace: whoever else holds the chain stole it, so the connection ends
            # (RFC 9700 §4.14.2). Within the grace it is a retry or a race of the client's own, refused only (Petter, 2026-10-20).
            for stolen in live.filter(
                previous_refresh_hash=hashed(refresh_token),
                refreshed_at__lt=Now() - timedelta(seconds=REFRESH_GRACE_SECONDS),
            ):
                stolen.revoke()
            return None
        return Refresh(row, refresh_token)

    def authenticate_user(self, refresh_token: Refresh) -> tuple[Business, str]:
        return refresh_token.row.business, refresh_token.row.scope

    def revoke_old_credential(self, refresh_token: Refresh) -> None:
        pass  # save_token swaps the refresh token in the same transaction

    def validate_token_request(self) -> None:
        refuse_another_resource(self.request)
        super().validate_token_request()


class Server(AuthorizationServer):
    """Authlib's Django server on our tables."""

    def __init__(self) -> None:
        super().__init__(OAuthClient, AccessToken)
        self.register_token_generator(
            "default",
            BearerTokenGenerator(
                access_token_generator=lambda **_: tokens.new_secret(),
                refresh_token_generator=lambda **_: secrets.token_urlsafe(48),
                expires_generator=lambda client, grant_type: ACCESS_SECONDS,
            ),
        )

    def query_client(self, client_id: str) -> Client | None:
        row = OAuthClient.objects.filter(client_id=client_id).first()
        return Client(row) if row is not None else None

    def save_token(self, token: dict[str, Any], request: Any) -> None:
        """The one way a sign-in's Access token is made: a new connection for a code, the same one, its refresh token
        swapped, for a refresh. A refresh token already swapped by a request in flight finds nothing, so it fails."""
        business, scope = request.user
        client = request.client.row
        with transaction.atomic():
            old = getattr(request, "refresh_token", None)
            if old is None:
                connection = OAuthConnection.objects.create(
                    business=business,
                    client=client,
                    scope=scope,
                    refresh_hash=hashed(token["refresh_token"]),
                )
            else:
                connection = old.row
                if not OAuthConnection.objects.filter(
                    pk=connection.pk,
                    refresh_hash=hashed(old.presented),
                    revoked_at__isnull=True,
                ).update(
                    refresh_hash=hashed(token["refresh_token"]),
                    previous_refresh_hash=hashed(old.presented),
                    refreshed_at=Now(),
                ):
                    raise OAuth2Error(
                        error="invalid_grant",
                        description="That refresh token was already used.",
                    )
            AccessToken.objects.create(
                business=business,
                label=client.client_name[: tokens.LABEL_MAX],
                scope=scope,
                is_operator=False,  # the operator's powers go only with a token the operator pastes knowingly
                token_hash=tokens.hash_of(token["access_token"]),
                connection=connection,
                expires_at=Now()
                + timedelta(
                    seconds=ACCESS_SECONDS
                ),  # the database's clock, as its trigger reads it
            )
        token["scope"] = scope


class Revoke(RevocationEndpoint):
    CLIENT_AUTH_METHODS = AUTH_METHODS

    def query_token(self, token_string: str, token_type_hint: str | None) -> Any:
        found = AccessToken.objects.filter(
            token_hash=tokens.hash_of(token_string), connection__isnull=False
        ).first()
        if found is not None:
            return Revocable(found.connection)
        connection = OAuthConnection.objects.filter(
            refresh_hash=hashed(token_string)
        ).first()
        return Revocable(connection) if connection is not None else None

    def revoke_token(self, token: "Revocable", request: Any) -> None:
        token.connection.revoke()


class Revocable:
    """Either of a connection's tokens: revoking one ends the connection (RFC 7009 lets a server revoke more than asked)."""

    def __init__(self, connection: OAuthConnection) -> None:
        self.connection = connection

    def check_client(self, client: Client) -> bool:
        return self.connection.client.pk == client.row.pk


def redirect_problem(uri: str) -> str | None:
    """Why a client may not send people back to this address, or None: https, or http only to this machine (RFC 8252 §7.3)."""
    parts = urlsplit(uri)
    if parts.fragment or not parts.hostname:
        return "a redirect_uri is an absolute address with no fragment"
    if parts.scheme == "https":
        return None
    if parts.scheme == "http" and parts.hostname in ("localhost", "127.0.0.1", "::1"):
        return None
    return "a redirect_uri is https, or http to localhost"


class Register(ClientRegistrationEndpoint):
    def extract_client_metadata(self, request: Any) -> dict[str, Any]:
        uris = request.payload.data.get("redirect_uris")
        if not isinstance(uris, list) or not all(isinstance(u, str) for u in uris):
            raise InvalidClientMetadataError("redirect_uris is a list of addresses.")
        return super().extract_client_metadata(request)

    def authenticate_token(self, request: Any) -> bool:
        return True  # open registration: a client gets nothing until a Business approves it on the consent page

    def get_server_metadata(self) -> dict[str, Any]:
        return authorization_server_metadata()

    def generate_client_info(self, request: Any) -> dict[str, Any]:
        info = super().generate_client_info(request)
        if request.payload.data.get("token_endpoint_auth_method") == "none":
            del info["client_secret"], info["client_secret_expires_at"]
        return info

    def save_client(
        self, client_info: dict[str, Any], client_metadata: dict[str, Any], request: Any
    ) -> OAuthClient:
        uris = client_metadata.get("redirect_uris") or []
        if (
            not uris
            or len(uris) > 5
            or any(len(u) > 2000 or redirect_problem(u) for u in uris)
        ):
            raise OAuth2Error(
                error="invalid_redirect_uri",
                description="Give one to five redirect_uris, each https or http to localhost.",
            )
        method = client_metadata.get(
            "token_endpoint_auth_method", "client_secret_basic"
        )
        secret = client_info.get("client_secret")
        # One registration at a time, so the cap holds under a burst.
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext('oauth_register'))")
            if (
                OAuthClient.objects.filter(
                    created_at__gt=Now() - timedelta(hours=1)
                ).count()
                >= REGISTRATIONS_PER_HOUR
            ):
                raise OAuth2Error(
                    error="temporarily_unavailable",
                    description="Too many registrations. Try again later.",
                    status_code=503,
                )
            try:
                with transaction.atomic():
                    return OAuthClient.objects.create(
                        client_id=client_info["client_id"],
                        secret_hash=hashed(secret)
                        if method != "none" and secret
                        else "",
                        client_name=(
                            str(client_metadata.get("client_name") or "").strip()
                            or "An AI assistant"
                        )[:100],
                        redirect_uris=uris,
                        auth_method=method,
                    )
            except IntegrityError:  # the store's own rule for an address (migration 0031), stricter than the check above
                raise OAuth2Error(
                    error="invalid_redirect_uri",
                    description="Give one to five redirect_uris, each https or http to localhost.",
                ) from None


def authorization_server_metadata() -> dict[str, Any]:
    base = issuer()
    return {
        "issuer": base,
        "authorization_endpoint": base + reverse("oauth_authorize"),
        "token_endpoint": base + reverse("oauth_token"),
        "registration_endpoint": base + reverse("oauth_register"),
        "revocation_endpoint": base + reverse("oauth_revoke"),
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": AUTH_METHODS,
        "revocation_endpoint_auth_methods_supported": AUTH_METHODS,
        "scopes_supported": SCOPES,
        "authorization_response_iss_parameter_supported": True,
    }


class Issuer(IssuerParameter):
    """RFC 9207: the answer names this server, so a client talking to several cannot be mixed up."""

    def get_issuer(self) -> str:
        return issuer()

    def add_issuer_parameter(self, authorization_server: Any, response: Any) -> None:
        # Authlib's own reads a Flask-style `location`; a Django response keeps it as a header.
        if response.has_header("Location"):
            response["Location"] = add_params_to_uri(
                response["Location"], [("iss", issuer())]
            )


server = Server()
server.register_extension(Issuer())
server.register_grant(CodeGrant, [S256Only(required=True)])
server.register_grant(RefreshGrant)
server.register_endpoint(Revoke)
server.register_endpoint(Register(claims_classes=[ClientMetadataClaims]))


@require_GET
def protected_resource(request: HttpRequest) -> JsonResponse:
    """RFC 9728: which server signs people in for the agent endpoint."""
    return JsonResponse(
        {
            "resource": resource(),
            "authorization_servers": [issuer()],
            "scopes_supported": SCOPES,
            "bearer_methods_supported": ["header"],
        }
    )


@require_GET
def authorization_server(request: HttpRequest) -> JsonResponse:
    """RFC 8414."""
    return JsonResponse(authorization_server_metadata())


@csrf_exempt  # a client posts here, never a browser with a session
@require_POST
def register(request: HttpRequest) -> Any:
    return server.create_endpoint_response("client_registration", request)


@csrf_exempt
@require_POST
def token(request: HttpRequest) -> Any:
    return server.create_token_response(request)


@csrf_exempt
@require_POST
def revoke(request: HttpRequest) -> Any:
    return server.create_endpoint_response("revocation", request)


@never_cache
@login_required
def authorize(request: HttpRequest) -> Any:
    """The consent page: the Business owner sees which assistant asks, where it sends them back, and picks read-only or full."""
    business = get_object_or_404(Business, account=request.user)
    if not same_resource(request.GET.get("resource")):
        return refused(
            request,
            "This assistant asked for access to something other than this Portal's agent endpoint.",
        )
    try:
        grant = server.get_consent_grant(request=request, end_user=business)
    except OAuth2Error as error:
        return refused(request, str(error.description or error.error))
    client: OAuthClient = grant.client.row
    if request.method == "POST":
        consent = Consent(request.POST)
        if not consent.is_valid():
            return refused(
                request, "Pick read-only or full, then Connect or Don't connect."
            )
        choice = consent.cleaned_data["access"]
        if consent.cleaned_data["decision"] != "approve":
            return server.create_authorization_response(
                request, grant_user=None, grant=grant
            )
        return server.create_authorization_response(
            request, grant_user=(business, choice), grant=grant
        )
    return render(
        request,
        "accounts/oauth_consent.html",
        {
            "client": client,
            "back_to": urlsplit(
                grant.request.payload.redirect_uri or client.redirect_uris[0]
            ).hostname,
            "business": business,
            "scopes": list(tokens.SCOPES.items()),
        },
    )


class Consent(forms.Form):
    # Not named scope: Authlib reads a POST's fields as the request's own parameters.
    access = forms.ChoiceField(choices=list(tokens.SCOPES.items()))
    decision = forms.ChoiceField(
        choices=[("approve", "Connect"), ("deny", "Don't connect")]
    )


def refused(request: HttpRequest, why: str) -> HttpResponse:
    return render(request, "accounts/oauth_refused.html", {"why": why}, status=400)
