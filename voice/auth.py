"""The login in front of the web Channel: one shared name and password (HTTP Basic).

It sits in front of every route, so nobody without it can start a call and spend Gemini credit.
"""

import base64
import hmac

from starlette.types import ASGIApp, Receive, Scope, Send


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


# ponytail: one shared password, no rate limit or lockout; per-person login (Pocket ID) and throttling when more than a few people use it.
class BasicAuth:
    """ASGI middleware: refuses every request and WebSocket that doesn't pass `allowed`."""

    def __init__(self, app: ASGIApp, user: str, password: str) -> None:
        if not password:  # fail closed: an empty password must never mean an open page
            raise ValueError("VOICE_PASSWORD is empty")
        self.app, self.user, self.password = app, user, password

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            return await self.app(scope, receive, send)
        header = dict(scope["headers"]).get(b"authorization", b"").decode("latin-1")
        if allowed(header, self.user, self.password):
            return await self.app(scope, receive, send)
        if scope["type"] == "websocket":
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
