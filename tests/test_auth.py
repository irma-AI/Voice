"""Seam 2: the login rule, free. Pure function on a header, like the cap rule beside it."""

import asyncio
import base64

import pytest
from starlette.types import Message, Receive, Scope, Send

from voice.auth import BasicAuth, allowed


async def app(scope: Scope, receive: Receive, send: Send) -> None:
    return None


def basic(user: str, password: str) -> str:
    return "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()


def test_right_name_and_password_is_let_in() -> None:
    assert allowed(basic("voice", "s3cret"), "voice", "s3cret")


def test_everything_else_is_refused() -> None:
    assert not allowed(None, "voice", "s3cret")
    assert not allowed("", "voice", "s3cret")
    assert not allowed(basic("voice", "wrong"), "voice", "s3cret")
    assert not allowed(basic("other", "s3cret"), "voice", "s3cret")
    assert not allowed("Bearer s3cret", "voice", "s3cret")
    assert not allowed("Basic !!!not-base64", "voice", "s3cret")


def test_an_empty_password_never_opens_the_page() -> None:
    assert not allowed(basic("voice", ""), "voice", "")
    with pytest.raises(ValueError):
        BasicAuth(app, "voice", "")


def run_asgi(scope_type: str, header: str | None) -> tuple[list[Message], bool]:
    """Sends one request or WebSocket through BasicAuth; returns what it sent and whether the app was reached."""
    sent: list[Message] = []
    reached: list[bool] = []

    async def inner(scope: Scope, receive: Receive, send: Send) -> None:
        reached.append(True)

    async def send(message: Message) -> None:
        sent.append(message)

    async def receive() -> Message:
        return {}

    headers = [(b"authorization", header.encode())] if header else []
    guarded = BasicAuth(inner, "voice", "s3cret")
    asyncio.run(guarded({"type": scope_type, "headers": headers}, receive, send))
    return sent, bool(reached)


def test_a_request_without_the_password_gets_401_and_never_reaches_the_app() -> None:
    sent, reached = run_asgi("http", None)
    assert sent[0]["status"] == 401 and not reached


def test_a_websocket_without_the_password_is_closed_and_never_reaches_the_app() -> None:
    sent, reached = run_asgi("websocket", basic("voice", "wrong"))
    assert sent == [{"type": "websocket.close", "code": 1008}] and not reached


def test_the_right_password_reaches_the_app_and_startup_needs_none() -> None:
    assert run_asgi("http", basic("voice", "s3cret")) == ([], True)
    assert run_asgi("lifespan", None) == ([], True)
