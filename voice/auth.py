"""The login in front of the web Channel: one shared name and password (HTTP Basic), or a Portal ticket.

It sits in front of every route, so nobody without one can start a call and spend Gemini credit.
"""

import base64
import hashlib
import hmac
from http.cookies import CookieError, SimpleCookie

from loguru import logger
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from voice.ticket import from_query, ticket_business

COOKIE = "voice_session"
# The only pages a Portal ticket opens: the call page and its WebSocket.
TICKET_PATHS = ("/", "/ws")


def allowed(header: str | None, user: str, password: str) -> bool:
    """True only for a well-formed `Authorization: Basic ...` header with exactly this name and password."""
    if not header or not password:
        return False
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "basic":
        return False
    try:
        got = base64.b64decode(token, validate=True)
    except ValueError:
        return False
    return hmac.compare_digest(got, f"{user}:{password}".encode())


def session_value(password: str) -> str:
    """What the login cookie holds: derived from the password, so changing the password logs everyone out."""
    return hmac.new(password.encode(), b"voice-session", hashlib.sha256).hexdigest()


def has_session(cookie_header: str | None, password: str) -> bool:
    """True only for a `Cookie` header carrying the login cookie for this password."""
    if not cookie_header or not password:
        return False
    jar: SimpleCookie = SimpleCookie()
    try:
        jar.load(cookie_header)
    except CookieError:  # a malformed Cookie header is just not a login
        return False
    morsel = jar.get(COOKIE)
    return morsel is not None and hmac.compare_digest(
        morsel.value.encode(), session_value(password).encode()
    )


# ponytail: one shared password, no rate limit or lockout; per-person login (Pocket ID) and throttling when more than a few people use it.
class BasicAuth:
    """ASGI middleware: refuses every request and WebSocket without the Basic login or the cookie it sets."""

    def __init__(
        self, app: ASGIApp, user: str, password: str, ticket_secret: str = ""
    ) -> None:
        if not password:  # fail closed: an empty password must never mean an open page
            raise ValueError("VOICE_PASSWORD is empty")
        self.app, self.user, self.password = app, user, password
        self.ticket_secret = ticket_secret  # empty: no ticket is ever valid

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            return await self.app(scope, receive, send)
        headers = dict(scope["headers"])
        header = headers.get(b"authorization", b"").decode("latin-1")
        if allowed(header, self.user, self.password):
            return await self.app(scope, receive, self.remember(scope, send))
        # A Portal ticket (voice/ticket.py) opens the call page for the one Business it names; the call itself checks it again.
        if (
            scope.get("path") in TICKET_PATHS
            and ticket_business(
                from_query(scope.get("query_string", b"")), self.ticket_secret
            )
            is not None
        ):
            return await self.app(scope, receive, send)
        # Browsers don't reliably send the cached Basic login on a WebSocket handshake, but they send cookies.
        if has_session(headers.get(b"cookie", b"").decode("latin-1"), self.password):
            return await self.app(scope, receive, send)
        if scope["type"] == "websocket":
            logger.warning(
                "refused {}: no valid login (Basic header or cookie)",
                scope.get("path", "websocket"),
            )
            return await send({"type": "websocket.close", "code": 1008})
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"www-authenticate", b'Basic realm="voice"'),
                    (b"content-length", b"0"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": b""})

    def remember(self, scope: Scope, send: Send) -> Send:
        """Wraps `send` so a page served after a Basic login also sets the login cookie."""
        if scope["type"] != "http":
            return send
        cookie = f"{COOKIE}={session_value(self.password)}; Path=/; HttpOnly; Secure; SameSite=Strict"

        async def with_cookie(message: Message) -> None:
            if message["type"] == "http.response.start":
                message["headers"] = [
                    *message.get("headers", []),
                    (b"set-cookie", cookie.encode()),
                ]
            await send(message)

        return with_cookie
