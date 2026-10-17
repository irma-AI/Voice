"""The gate in front of the web Channel: only a valid Portal call ticket (voice/ticket.py) opens a call.

It sits in front of every route, so nobody without a Business's call link can start a call and spend Gemini credit.
"""

from loguru import logger
from starlette.types import ASGIApp, Receive, Scope, Send

from voice.ticket import from_query, read_ticket

# The only pages a ticket opens: the call page and its WebSocket.
TICKET_PATHS = ("/", "/ws")
# What a visitor without a valid link reads (Swedish: it is what the Caller hears and reads, like the disclosure line).
REFUSAL = (
    "Det här samtalet kan inte öppnas. Starta det igen från företagets samtalslänk."
)
REFUSAL_PAGE = f'<!doctype html><html lang="sv"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Samtalet kan inte öppnas</title><p>{REFUSAL}</p></html>'.encode()


class TicketGate:
    """ASGI middleware: refuses every request and WebSocket that has no valid, unexpired ticket for a page it opens."""

    def __init__(self, app: ASGIApp, ticket_secret: str) -> None:
        if (
            not ticket_secret
        ):  # fail closed: without the Portal secret no ticket can be checked
            raise ValueError("CORE_SECRET is empty")
        self.app, self.ticket_secret = app, ticket_secret

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            return await self.app(scope, receive, send)
        if (
            scope.get("path") in TICKET_PATHS
            and read_ticket(
                from_query(scope.get("query_string", b"")), self.ticket_secret
            )
            is not None
        ):
            return await self.app(scope, receive, send)  # the call checks it again
        if scope["type"] == "websocket":
            logger.warning(
                "refused {}: no valid call ticket", scope.get("path", "websocket")
            )
            return await send({"type": "websocket.close", "code": 1008})
        await send(
            {
                "type": "http.response.start",
                "status": 403,
                "headers": [
                    (b"content-type", b"text/html; charset=utf-8"),
                    (b"content-length", str(len(REFUSAL_PAGE)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": REFUSAL_PAGE})
