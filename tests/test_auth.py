"""Seam 2: the login rule, free. Pure function on a header, like the cap rule beside it."""

import base64

import pytest
from starlette.types import Receive, Scope, Send

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
