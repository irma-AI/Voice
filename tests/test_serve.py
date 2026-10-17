"""Seam 2: the web Channel's pure rules, free. The audio converter and the same-site check."""

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

from voice import serve
from voice.auth import REFUSAL, TICKET_PATHS
from voice.serve import RawPcmSerializer, create_app, same_site
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


def test_the_call_page_opens_with_a_portal_ticket_and_refuses_everyone_else() -> None:
    client = TestClient(
        create_app("portal-secret"), base_url="https://voice.example.se"
    )
    page = f"/?ticket={sign('portal-secret', 7, 'test', int(time.time()) + 60)}"
    assert client.get(page).status_code == 200
    refused = client.get("/")
    assert refused.status_code == 403 and REFUSAL in refused.text


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
    assert routes == set(TICKET_PATHS)
