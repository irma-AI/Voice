"""Seam 2: the web Channel's pure rules, free. The audio converter, the same-site check, and the call page.

The call page's Theme comes from a real local server standing in for the Portal (tests/test_settings_port.py).
The Live transcript runs through a real Pipecat pipeline and socket, with a stand-in for the model.
"""

import asyncio
import contextlib
import json
import re
import time

import pytest
import uvicorn
import websockets
from fastapi import FastAPI, WebSocket
from loguru import logger
from pipecat.frames.frames import (
    Frame,
    InputAudioRawFrame,
    InterruptionFrame,
    LLMTextFrame,
    OutputAudioRawFrame,
    TextFrame,
    TranscriptionFrame,
    TTSTextFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineWorker
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams
from pipecat.utils.text.base_text_aggregator import AggregationType
from pipecat.workers.runner import WorkerRunner
from starlette.testclient import TestClient
from starlette.types import Receive, Scope, Send
from starlette.websockets import WebSocketDisconnect

from tests.test_settings_port import GOOD, fake_portal, portal_env
from voice import serve
from voice.auth import FONTS_PATH, REFUSAL, TICKET_PATHS
from voice.serve import (
    DrainingServer,
    OneCallPerBusiness,
    RawPcmSerializer,
    create_app,
    same_site,
)
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


def test_a_stop_lets_the_open_call_end_before_the_server_hangs_up() -> None:
    """A deploy stops the old copy with SIGTERM: a real server and a real WebSocket."""

    async def scenario() -> None:
        calls, over = OneCallPerBusiness(), asyncio.Event()

        async def app(scope: Scope, receive: Receive, send: Send) -> None:
            if scope["type"] != "websocket":
                return
            await receive()
            await send({"type": "websocket.accept"})
            assert calls.take(1)
            await over.wait()
            calls.release(1)
            await send({"type": "websocket.close", "code": 1000})

        config = uvicorn.Config(
            app, host="127.0.0.1", port=0, lifespan="off", log_level="warning"
        )
        server = DrainingServer(config, calls)
        serving = asyncio.create_task(server.serve())
        while not server.started:
            await asyncio.sleep(0.05)
        port = server.servers[0].sockets[0].getsockname()[1]
        async with websockets.connect(f"ws://127.0.0.1:{port}/") as call:
            while not calls.any_open():
                await asyncio.sleep(0.05)
            server.should_exit = True  # what uvicorn's SIGTERM handler sets; calling the handler would re-raise the signal at pytest
            await asyncio.sleep(1.5)
            assert not serving.done()
            await call.ping()  # still open: a hang-up would raise here
            with pytest.raises(OSError):  # and no new call gets in
                await websockets.connect(f"ws://127.0.0.1:{port}/")
            over.set()
            with pytest.raises(websockets.ConnectionClosedOK):
                await call.recv()
        await asyncio.wait_for(serving, 5)

    asyncio.run(scenario())


def test_the_call_page_opens_with_a_portal_ticket_and_refuses_everyone_else() -> None:
    client = TestClient(
        create_app("portal-secret"), base_url="https://voice.example.se"
    )
    page = f"/?ticket={sign('portal-secret', 7, 'test', int(time.time()) + 60)}"
    assert client.get(page).status_code == 200
    refused = client.get("/")
    assert refused.status_code == 403 and REFUSAL in refused.text


def test_every_response_says_https_only_no_sniffing_and_no_referrer_off_site() -> None:
    client = TestClient(
        create_app("portal-secret"), base_url="https://voice.example.se"
    )
    page = f"/?ticket={sign('portal-secret', 7, 'test', int(time.time()) + 60)}"
    for response in (
        client.get(page),
        client.get("/fonts/SchibstedGrotesk-Variable.woff2"),
        client.get("/"),  # the 403 refusal
    ):
        assert response.headers["strict-transport-security"] == "max-age=2592000"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["referrer-policy"] == "same-origin"


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


def test_the_call_page_links_the_business_privacy_notice_only_when_it_has_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    given = {**GOOD, "privacy_url": 'https://example.se/integritet?a=1&b="2"'}
    with fake_portal(body=given) as url:
        page = call_page(monkeypatch, portal_env(url))
    link = re.search(
        r'<p class="privacy"><a href="([^"]*)" ([^>]*)>Privacy notice</a>', page
    )  # the words were approved by Petter 2026-10-18
    assert link and link[1] == "https://example.se/integritet?a=1&amp;b=&quot;2&quot;"
    # The page is often framed in the Business's own website: the notice opens outside the call, which goes on.
    assert link[2] == 'target="_blank" rel="noopener"'
    assert page.index(DISCLOSURE) < page.index(
        'class="privacy"'
    )  # beside the disclosure, after it
    with fake_portal() as url:  # no notice given: no link at all
        assert 'class="privacy"' not in call_page(monkeypatch, portal_env(url))
    # An address that spells another page marker is filled in last, so it stays an address.
    with fake_portal(body={**GOOD, "privacy_url": "https://x.se/__BRAND__"}) as url:
        page = call_page(monkeypatch, portal_env(url))
    assert 'href="https://x.se/__BRAND__"' in page and page.count("<h1") == 1


def test_without_settings_the_call_page_shows_voices_own_look(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for env in ({}, portal_env("http://127.0.0.1:1")):  # no source; the Portal down
        page = call_page(monkeypatch, env)
        assert "<style></style>" in page  # no Theme
        # The name is the page's one heading, so a screen reader's heading list says who the Caller is talking to.
        assert '<h1 class="brand"><span class="name">Voice</span></h1>' in page
        assert page.count("<h1") == 1
        # Connecting marks the button aria-disabled and keeps it focusable: disabling it would drop the keyboard focus.
        assert 'go.setAttribute("aria-disabled"' in page and "go.disabled" not in page
        assert "<img" not in page
        assert DISCLOSURE in page
        # A screen reader finds the Live transcript as a log it can read, not announced over the agent's voice.
        assert 'role="log" aria-live="off" aria-label="Live transcript"' in page


def test_the_typefaces_are_open_and_nothing_else_under_them() -> None:
    client = TestClient(create_app("portal-secret"))
    font = client.get("/fonts/SchibstedGrotesk-Variable.woff2")  # no ticket needed
    assert font.status_code == 200
    assert font.headers["content-type"] == "font/woff2"
    assert font.content[:4] == b"wOF2"
    for path in (
        "/fonts/SchibstedGrotesk-OFL.txt",
        "/fonts/nope.woff2",
        "/fonts/../page.html",
    ):
        assert client.get(path).status_code in (403, 404), path


class StandInModel(FrameProcessor):
    """Stands in for Gemini Live: on the Caller's first audio it sends what Pipecat's service sends for a turn."""

    def __init__(self) -> None:
        super().__init__()  # pyright: ignore[reportUnknownMemberType]  # untyped kwargs upstream
        self.spoke = False

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        await self.push_frame(frame, direction)
        if isinstance(frame, InputAudioRawFrame) and not self.spoke:
            self.spoke = True
            await self.push_frame(
                TranscriptionFrame(CALLER_SAID, "", "now"), FrameDirection.UPSTREAM
            )
            await self.push_frame(LLMTextFrame(AGENT_SAID))  # the same words twice
            await self.push_frame(TTSTextFrame(AGENT_SAID, AggregationType.SENTENCE))


class TakesTheCallersWords(FrameProcessor):
    """Stands in for the context aggregator, which takes the Caller's transcript before it reaches the input."""

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if not isinstance(frame, TranscriptionFrame):
            await self.push_frame(frame, direction)


CALLER_SAID = "Hej, har ni öppet på lördag?"  # synthetic
AGENT_SAID = "Ja, mellan tio och tre."


def test_the_live_transcript_reaches_the_page_with_its_speaker_and_no_log() -> None:
    logged: list[str] = []
    sink = logger.add(lambda m: logged.append(str(m)), level="DEBUG")
    app = FastAPI()

    @app.websocket("/ws")
    async def call(websocket: WebSocket) -> None:  # pyright: ignore[reportUnusedFunction]
        await websocket.accept()
        transport = serve.CallTransport(
            websocket,
            FastAPIWebsocketParams(
                audio_in_enabled=True,
                audio_out_enabled=True,
                audio_in_sample_rate=serve.IN_RATE,
                audio_out_sample_rate=serve.OUT_RATE,
                serializer=RawPcmSerializer(),
            ),
        )
        steps = [
            transport.input(),
            TakesTheCallersWords(),
            StandInModel(),
            transport.output(),
        ]
        runner = WorkerRunner(handle_sigint=False)
        await runner.add_workers(PipelineWorker(Pipeline(steps)))

        @transport.event_handler("on_client_disconnected")
        async def _gone(*_: object) -> None:  # pyright: ignore[reportUnusedFunction]
            await runner.cancel()

        # The TestClient cancels the app right after its disconnect, mid-teardown: the normal end here.
        with contextlib.suppress(asyncio.CancelledError):
            await runner.run()

    try:
        with TestClient(app).websocket_connect("/ws") as ws:
            ws.send_bytes(b"\x00\x00" * 320)
            got = [json.loads(ws.receive_text()) for _ in range(2)]
    finally:
        logger.remove(sink)
    assert sorted(got, key=lambda m: m["speaker"]) == [
        {"type": "transcript", "speaker": "agent", "text": AGENT_SAID},
        {"type": "transcript", "speaker": "caller", "text": CALLER_SAID},
    ]
    assert logged, "nothing was logged, so the check below proves nothing"
    assert not [line for line in logged if CALLER_SAID in line or AGENT_SAID in line]


def test_transcript_messages_name_the_speaker() -> None:
    caller = TranscriptionFrame("Hej", "", "now")
    agent = TTSTextFrame("Hej hej", AggregationType.SENTENCE)
    assert json.loads(asyncio.run(RawPcmSerializer().serialize(caller)) or "") == {
        "type": "transcript",
        "speaker": "caller",
        "text": "Hej",
    }
    assert json.loads(asyncio.run(RawPcmSerializer().serialize(agent)) or "") == {
        "type": "transcript",
        "speaker": "agent",
        "text": "Hej hej",
    }
    # The agent's words also come as an LLMTextFrame; the page gets them once.
    assert asyncio.run(RawPcmSerializer().serialize(LLMTextFrame("Hej hej"))) is None
