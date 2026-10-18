"""Seam 2: the call-ticket gate, free. Pure rule on a request path and query, like the cap rule beside it."""

import asyncio
import time

import pytest
from starlette.types import Message, Receive, Scope, Send

from voice.auth import REFUSAL, TicketGate
from voice.ticket import sign

SECRET = "portal-secret"


async def app(scope: Scope, receive: Receive, send: Send) -> None:
    return None


def ticket_query(secret: str = SECRET, business: int = 7, expires_in: int = 60) -> str:
    return "ticket=" + sign(secret, business, "test", int(time.time()) + expires_in)


def run_asgi(
    scope_type: str, path: str = "/", query: str = ""
) -> tuple[list[Message], bool]:
    """Sends one request or WebSocket through the gate; returns what it sent and whether the app was reached."""
    sent: list[Message] = []
    reached: list[bool] = []

    async def inner(scope: Scope, receive: Receive, send: Send) -> None:
        reached.append(True)

    async def send(message: Message) -> None:
        sent.append(message)

    async def receive() -> Message:
        return {}

    scope: Scope = {
        "type": scope_type,
        "path": path,
        "query_string": query.encode(),
    }
    asyncio.run(TicketGate(inner, SECRET)(scope, receive, send))
    return sent, bool(reached)


def test_a_gate_with_no_secret_cannot_be_built() -> None:
    with pytest.raises(ValueError):  # fail closed: no secret, no way to check a link
        TicketGate(app, "")


def test_a_valid_ticket_opens_the_call_page_and_socket() -> None:
    for scope_type, path in (("http", "/"), ("websocket", "/ws")):
        assert run_asgi(scope_type, path, ticket_query()) == ([], True), path


def test_startup_needs_no_ticket() -> None:
    assert run_asgi("lifespan") == ([], True)


def test_no_ticket_or_a_bad_one_is_refused_and_never_reaches_the_app() -> None:
    for query in (
        "",
        "ticket=",  # blank
        ticket_query("other"),  # signed with another secret
        ticket_query(expires_in=-1),  # expired
        "ticket=7.9999999999.abc",  # tampered
    ):
        sent, reached = run_asgi("http", "/", query)
        assert sent[0]["status"] == 403 and not reached, query
        assert REFUSAL.encode() in sent[1]["body"], query
        # A page a screen reader can find its way in: its language, a main landmark, the sentence as its heading.
        assert sent[1]["body"].startswith(b'<!doctype html><html lang="sv">'), query
        assert f"<main><h1>{REFUSAL}</h1></main>".encode() in sent[1]["body"], query
        sent, reached = run_asgi("websocket", "/ws", query)
        assert sent == [{"type": "websocket.close", "code": 1008}] and not reached


def test_a_ticket_opens_nothing_but_the_call_page_and_socket() -> None:
    sent, reached = run_asgi("http", "/elsewhere", ticket_query())
    assert sent[0]["status"] == 403 and not reached
