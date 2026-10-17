"""Seam 2: the web Channel's pure rules, free. The audio converter, the same-site check, and the call page.

The call page's Theme comes from a real local server standing in for the Portal (tests/test_settings_port.py).
"""

import asyncio
import time

import pytest
from pipecat.frames.frames import (
    InputAudioRawFrame,
    InterruptionFrame,
    OutputAudioRawFrame,
    TextFrame,
)
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from tests.test_settings_port import GOOD, fake_portal, portal_env
from voice import serve
from voice.auth import FONTS_PATH, REFUSAL, TICKET_PATHS
from voice.serve import OneCallPerBusiness, RawPcmSerializer, create_app, same_site
from voice.ticket import sign


def test_microphone_bytes_become_a_caller_audio_frame() -> None:
    frame = asyncio.run(RawPcmSerializer().deserialize(b"\x01\x00\x02\x00"))
    assert isinstance(frame, InputAudioRawFrame)
    assert (frame.audio, frame.sample_rate, frame.num_channels) == (
        b"\x01\x00\x02\x00",
        16000,
        1,
    )


def test_text_from_the_browser_is_ignored() -> None:
    assert asyncio.run(RawPcmSerializer().deserialize("hello")) is None


def test_agent_audio_goes_out_as_plain_bytes() -> None:
    audio = OutputAudioRawFrame(audio=b"\x03\x00", sample_rate=24000, num_channels=1)
    assert asyncio.run(RawPcmSerializer().serialize(audio)) == b"\x03\x00"


def test_audio_at_the_wrong_rate_is_refused_not_played_garbled() -> None:
    audio = OutputAudioRawFrame(audio=b"\x03\x00", sample_rate=16000, num_channels=1)
    with pytest.raises(ValueError):
        asyncio.run(RawPcmSerializer().serialize(audio))


def test_an_interruption_tells_the_page_to_stop_playing() -> None:
    sent = asyncio.run(RawPcmSerializer().serialize(InterruptionFrame()))
    assert sent == '{"type": "interrupt"}'


def test_other_frames_send_nothing() -> None:
    assert asyncio.run(RawPcmSerializer().serialize(TextFrame("hi"))) is None


def test_only_this_site_may_open_the_call_socket() -> None:
    assert same_site("https://voice.example.se", "voice.example.se")
    assert same_site("http://localhost:7860", "localhost:7860")
    assert not same_site("https://evil.example", "voice.example.se")
    assert not same_site("https://voice.example.se.evil.example", "voice.example.se")
    assert not same_site(None, "voice.example.se")  # fail closed: no Origin, no call
    assert not same_site("https://voice.example.se", None)


def test_a_business_has_one_call_at_a_time_and_other_businesses_are_unaffected() -> (
    None
):
    calls = OneCallPerBusiness()
    assert calls.take(7)
    assert not calls.take(7)  # a second call for the same Business is refused
    assert calls.take(8)  # another Business is not
    calls.release(7)
    assert calls.take(7)  # free again once the first call has ended
    calls.release(7)
    calls.release(7)  # releasing twice is harmless


def test_the_call_page_opens_with_a_portal_ticket_and_refuses_everyone_else() -> None:
    client = TestClient(
        create_app("portal-secret"), base_url="https://voice.example.se"
    )
    page = f"/?ticket={sign('portal-secret', 7, 'test', int(time.time()) + 60)}"
    assert client.get(page).status_code == 200
    refused = client.get("/")
    assert refused.status_code == 403 and REFUSAL in refused.text


def test_the_call_page_says_which_site_may_frame_it() -> None:
    client = TestClient(
        create_app("portal-secret"), base_url="https://voice.example.se"
    )
    expires = int(time.time()) + 60

    def page(kind: str, domain: str) -> str:
        ticket = sign("portal-secret", 7, kind, expires, domain)
        return client.get(f"/?ticket={ticket}").headers.get(
            "content-security-policy", ""
        )

    assert page("test", "") == "frame-ancestors 'none'"
    assert (
        page("call_link", "example.se")
        == "frame-ancestors https://example.se https://*.example.se"
    )


def test_a_call_link_ticket_without_a_clean_domain_opens_no_page() -> None:
    client = TestClient(
        create_app("portal-secret"), base_url="https://voice.example.se"
    )
    expires = int(time.time()) + 60
    for domain in ("", "example.se;", "https://example.se", "exa mple.se"):
        ticket = sign("portal-secret", 7, "call_link", expires, domain)
        refused = client.get(f"/?ticket={ticket}")
        assert refused.status_code == 403, domain
        assert "content-security-policy" not in refused.headers, domain


def test_the_socket_refuses_a_missing_or_bad_ticket() -> None:
    client = TestClient(
        create_app("portal-secret"), base_url="https://voice.example.se"
    )
    same_origin = {"Origin": "https://voice.example.se"}
    for query in (
        "",
        "ticket=7.1.abc",
        f"ticket={sign('other', 7, 'test', int(time.time()) + 60)}",
    ):
        with (
            pytest.raises(WebSocketDisconnect) as refused,
            client.websocket_connect(f"/ws?{query}", headers=same_origin),
        ):
            pass
        assert refused.value.code == 1008


def test_the_web_channel_will_not_start_without_the_portal_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        serve, "load_dotenv", lambda: None
    )  # a developer's .env must not leak in
    monkeypatch.setenv("GOOGLE_API_KEY", "key")
    monkeypatch.setenv("CORE_SECRET", " ")
    with pytest.raises(SystemExit, match="CORE_SECRET"):
        serve.main()


def test_a_ticket_opens_exactly_the_pages_the_app_has() -> None:
    # A new route is outside the ticket until this list is edited on purpose (voice/auth.py TICKET_PATHS).
    routes = {getattr(r, "path", None) for r in create_app("s3cret").routes}
    assert routes == {*TICKET_PATHS, FONTS_PATH + "{name}"}


DISCLOSURE = "You are talking to an AI assistant."  # approved by Petter 2026-10-17
THEMED = {
    **GOOD,
    "theme": {
        "accent": "#2f6b4f",
        "accent_text": "#ffffff",
        "logo_url": 'https://portal.example.se/logo/ab"c.png',
    },
}


def call_page(monkeypatch: pytest.MonkeyPatch, env: dict[str, str]) -> str:
    for key in ("SETTINGS_URL", "SETTINGS_FILE", "CORE_SECRET"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    client = TestClient(
        create_app("portal-secret"), base_url="https://voice.example.se"
    )
    reply = client.get(
        f"/?ticket={sign('portal-secret', 7, 'test', int(time.time()) + 60)}"
    )
    assert reply.status_code == 200
    return reply.text


def test_the_call_page_wears_the_business_theme_and_says_it_is_an_ai(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[str] = []
    with fake_portal(body=THEMED, paths=asked) as url:
        page = call_page(monkeypatch, portal_env(url))
    assert asked == ["/api/settings/7/"]  # the Business the ticket names
    assert "--action: #2f6b4f; --on-action: #ffffff" in page
    assert "--live: #2f6b4f" in page
    assert 'src="https://portal.example.se/logo/ab&quot;c.png"' in page  # escaped
    assert 'alt="Anna&#x27;s Salon"' in page
    assert DISCLOSURE in page


def test_without_settings_the_call_page_shows_voices_own_look(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for env in ({}, portal_env("http://127.0.0.1:1")):  # no source; the Portal down
        page = call_page(monkeypatch, env)
        assert "<style></style>" in page  # no Theme
        assert '<span class="name">Voice</span>' in page
        assert "<img" not in page
        assert DISCLOSURE in page


def test_the_typefaces_are_open_and_nothing_else_under_them() -> None:
    client = TestClient(create_app("portal-secret"))
    font = client.get("/fonts/Geist-Variable.woff2")  # no ticket needed
    assert font.status_code == 200
    assert font.headers["content-type"] == "font/woff2"
    assert font.content[:4] == b"wOF2"
    for path in ("/fonts/Geist-OFL.txt", "/fonts/nope.woff2", "/fonts/../page.html"):
        assert client.get(path).status_code in (403, 404), path
