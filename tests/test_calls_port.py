"""Seam 2: the calls port, free. The core asks the Portal to let a call start and reports its end.

A real HTTP server on localhost stands in for the Portal; nothing of ours is mocked.
tests/portal/test_calls.py holds the real Portal and this code together.
"""

import json
import time
from collections.abc import Generator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from typing import Any

import pytest

from voice.calls import REFUSED, Call, NotLetStart, finish, start
from voice.settings import Settings, SettingsRefused

FROM_PORTAL = Settings("Anna's Salon", "", ("sv",), business_id="7")


@contextmanager
def fake_portal(
    status: int = 201,
    body: object = None,
    seen: list[tuple[str, dict[str, Any]]] | None = None,
) -> Generator[dict[str, str]]:
    """A server that answers every POST with `status` and `body` when the Bearer secret is `s3cret`, else 401; the env the core would use."""
    got: list[tuple[str, dict[str, Any]]] = [] if seen is None else seen
    reply = {"call": 41} if body is None else body

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            got.append((self.path, json.loads(self.rfile.read(length) or b"{}")))
            ok = self.headers.get("Authorization") == "Bearer s3cret"
            self.send_response(status if ok else 401)
            if status == 302:
                self.send_header("Location", "http://127.0.0.1:1/elsewhere")
            self.end_headers()
            self.wfile.write(json.dumps(reply if ok else {"error": "no"}).encode())

        def log_message(self, format: str, *args: object) -> None:
            return None

    server = HTTPServer(("127.0.0.1", 0), Handler)
    Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield {
            "SETTINGS_URL": f"http://127.0.0.1:{server.server_port}",
            "CORE_SECRET": "s3cret",
        }
    finally:
        server.shutdown()


def test_an_address_with_spaces_or_a_trailing_slash_works_as_the_settings_port_reads_it() -> (
    None
):
    with fake_portal() as env:
        env["SETTINGS_URL"] = f" {env['SETTINGS_URL']}/ "
        call = start(FROM_PORTAL, env)
        assert call is not None
        finish(call, env)


def test_the_portal_lets_a_call_start_and_the_core_asks_for_that_business() -> None:
    seen: list[tuple[str, dict[str, Any]]] = []
    with fake_portal(seen=seen) as env:
        call = start(FROM_PORTAL, env)
    assert call is not None and call.id == 41
    assert seen == [("/api/businesses/7/calls/", {})]


@pytest.mark.parametrize("reason", sorted(REFUSED))
def test_a_refusal_from_the_portal_carries_the_text_the_caller_is_shown(
    reason: str,
) -> None:
    with fake_portal(403, {"refused": reason}) as env, pytest.raises(NotLetStart) as e:
        start(FROM_PORTAL, env)
    assert e.value.text == REFUSED[reason]


def test_every_reason_has_a_sentence_for_the_caller() -> None:
    assert set(REFUSED) == {"off", "limit"}  # a new reason is added here on purpose
    assert all(text.strip() for text in REFUSED.values())


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (403, {"refused": "a-reason-this-core-has-never-heard-of"}),
        (403, {"refused": ["off"]}),
        (403, {}),
        (201, {}),
        (201, {"call": "41"}),
        (200, {"call": 41}),
        (302, {}),
        (500, {"call": 41}),
    ],
)
def test_anything_but_a_clear_yes_or_a_known_no_refuses_the_call(
    status: int, body: object
) -> None:
    with fake_portal(status, body) as env, pytest.raises(SettingsRefused):
        start(FROM_PORTAL, env)


def test_a_wrong_secret_and_a_portal_that_is_down_refuse_the_call() -> None:
    with fake_portal() as env, pytest.raises(SettingsRefused):
        start(FROM_PORTAL, {**env, "CORE_SECRET": "wrong"})
    with pytest.raises(SettingsRefused):
        start(
            FROM_PORTAL, {"SETTINGS_URL": "http://127.0.0.1:1", "CORE_SECRET": "s3cret"}
        )


def test_the_refusal_names_the_host_never_the_secret() -> None:
    with fake_portal(500) as env, pytest.raises(SettingsRefused) as e:
        start(FROM_PORTAL, env)
    assert "s3cret" not in str(e.value) and "127.0.0.1" in str(e.value)


def test_settings_that_did_not_come_from_the_portal_have_nothing_to_count_against() -> (
    None
):
    assert start(Settings("Anna's Salon", "", ("sv",)), {}) is None


def test_the_end_of_a_call_is_reported_with_its_length() -> None:
    seen: list[tuple[str, dict[str, Any]]] = []
    with fake_portal(200, {}, seen) as env:
        finish(Call(41, began=time.monotonic() - 30), env)
    path, body = seen[0]
    assert path == "/api/calls/41/end/" and body["seconds"] in (30, 31)


def test_a_report_that_cannot_be_delivered_blocks_nothing() -> None:
    finish(
        Call(41, began=0.0),
        {"SETTINGS_URL": "http://127.0.0.1:1", "CORE_SECRET": "s3cret"},
    )
    with fake_portal(500) as env:
        finish(Call(41, began=0.0), env)
