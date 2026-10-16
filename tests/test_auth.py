"""Seam 2: the login rule, free. Pure function on a header, like the cap rule beside it."""

import asyncio
import base64
import time

import pytest
from starlette.types import Message, Receive, Scope, Send

from voice.auth import BasicAuth, allowed
from voice.ticket import sign


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


def run_asgi(
    scope_type: str,
    header: str | None,
    cookie: str | None = None,
    path: str = "/",
    query: str = "",
    ticket_secret: str = "",
) -> tuple[list[Message], bool]:
    """Sends one request or WebSocket through BasicAuth; returns what it sent and whether the app was reached."""
    sent: list[Message] = []
    reached: list[bool] = []

    async def inner(scope: Scope, receive: Receive, send: Send) -> None:
        reached.append(True)
        if scope["type"] == "http":
            await send({"type": "http.response.start", "status": 200, "headers": []})

    async def send(message: Message) -> None:
        sent.append(message)

    async def receive() -> Message:
        return {}

    headers = [(b"authorization", header.encode())] if header else []
    if cookie:
        headers.append((b"cookie", cookie.encode()))
    guarded = BasicAuth(inner, "voice", "s3cret", ticket_secret)
    scope: Scope = {
        "type": scope_type,
        "headers": headers,
        "path": path,
        "query_string": query.encode(),
    }
    asyncio.run(guarded(scope, receive, send))
    return sent, bool(reached)


def test_a_request_without_the_password_gets_401_and_never_reaches_the_app() -> None:
    sent, reached = run_asgi("http", None)
    assert sent[0]["status"] == 401 and not reached


def test_a_websocket_without_the_password_is_closed_and_never_reaches_the_app() -> None:
    sent, reached = run_asgi("websocket", basic("voice", "wrong"))
    assert sent == [{"type": "websocket.close", "code": 1008}] and not reached


def test_the_right_password_reaches_the_app_and_startup_needs_none() -> None:
    assert run_asgi("http", basic("voice", "s3cret"))[1]
    assert run_asgi("lifespan", None) == ([], True)


def login_cookie() -> str:
    """The cookie a browser keeps after logging in on the page."""
    sent, _ = run_asgi("http", basic("voice", "s3cret"))
    headers = dict(sent[0]["headers"])
    return headers[b"set-cookie"].decode().split(";")[0]


def test_logging_in_sets_a_cookie_the_browser_cannot_read_or_send_cross_site() -> None:
    sent, _ = run_asgi("http", basic("voice", "s3cret"))
    flags = dict(sent[0]["headers"])[b"set-cookie"].decode()
    assert "HttpOnly" in flags and "Secure" in flags and "SameSite=Strict" in flags
    assert "s3cret" not in flags


def test_a_websocket_with_the_login_cookie_is_let_in_without_the_basic_header() -> None:
    # Browsers don't reliably send the cached Basic login on a WebSocket handshake; they do send cookies.
    assert run_asgi("websocket", None, login_cookie()) == ([], True)


def test_a_wrong_or_unrelated_cookie_is_refused() -> None:
    for cookie in ("voice_session=wrong", "other=x", "voice_session="):
        sent, reached = run_asgi("websocket", None, cookie)
        assert sent == [{"type": "websocket.close", "code": 1008}] and not reached


def ticket_query(
    secret: str = "s3cret", business: int = 7, expires_in: int = 60
) -> str:
    return "ticket=" + sign(secret, business, int(time.time()) + expires_in)


def test_a_portal_ticket_opens_the_call_page_and_socket_without_the_login() -> None:
    for scope_type, path in (("http", "/"), ("websocket", "/ws")):
        _, reached = run_asgi(
            scope_type, None, path=path, query=ticket_query(), ticket_secret="s3cret"
        )
        assert reached, path


def test_a_bad_ticket_is_no_login_and_a_ticket_opens_nothing_else() -> None:
    for query, secret, path in (
        (ticket_query("other"), "s3cret", "/"),  # signed with another secret
        (ticket_query(expires_in=-1), "s3cret", "/"),  # expired
        (ticket_query(), "", "/"),  # the core has no secret: no ticket is valid
        (ticket_query(), "s3cret", "/elsewhere"),
    ):
        sent, reached = run_asgi(
            "http", None, path=path, query=query, ticket_secret=secret
        )
        assert sent[0]["status"] == 401 and not reached, (query, path)


def test_a_ticket_does_not_set_the_login_cookie() -> None:
    sent, _ = run_asgi("http", None, query=ticket_query(), ticket_secret="s3cret")
    assert b"set-cookie" not in dict(
        sent[0]["headers"]
    )  # only the Basic login earns the cookie
