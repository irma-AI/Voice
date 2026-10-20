"""Seam 2: the web Channel's pure rules, free. The audio converter, the same-site check, and the call page.

The call page's Theme comes from a real local server standing in for the Portal (tests/test_settings_port.py).
The Live transcript runs through a real Pipecat pipeline and socket, with a stand-in for the model.
"""

import asyncio
import contextlib
import json
import re
import threading
import time
from collections.abc import Callable, Generator
from pathlib import Path

import pytest
import uvicorn
import websockets
from fastapi import FastAPI, WebSocket
from loguru import logger
from pipecat.frames.frames import (
    Frame,
    InputAudioRawFrame,
    InputTransportMessageFrame,
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
from pipecat.tests.utils import run_test
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams
from pipecat.utils.text.base_text_aggregator import AggregationType
from pipecat.workers.runner import WorkerRunner
from starlette.testclient import TestClient
from starlette.types import Receive, Scope, Send
from starlette.websockets import WebSocketDisconnect, WebSocketState

from tests.test_settings_port import GOOD, fake_portal, portal_env
from voice import serve
from voice.auth import FONTS_PATH, REFUSAL, TICKET_PATHS
from voice.bargein import BargeInRecorder
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


def test_a_call_that_never_ends_lets_the_stop_finish_after_the_ceiling_and_says_so() -> (
    None
):
    """A call whose slot is never released (its finally never ran) must not hold the old copy until Docker kills it."""

    async def scenario() -> list[str]:
        calls, lines = OneCallPerBusiness(), list[str]()
        sink = logger.add(lambda m: lines.append(m.record["message"]), level="WARNING")

        async def app(scope: Scope, receive: Receive, send: Send) -> None:
            if scope["type"] != "websocket":
                return
            await receive()
            await send({"type": "websocket.accept"})
            assert calls.take(3)
            await asyncio.Event().wait()  # never releases

        config = uvicorn.Config(
            app, host="127.0.0.1", port=0, lifespan="off", log_level="warning"
        )
        server = DrainingServer(config, calls, ceiling_s=0.5)
        serving = asyncio.create_task(server.serve())
        while not server.started:
            await asyncio.sleep(0.05)
        port = server.servers[0].sockets[0].getsockname()[1]
        async with websockets.connect(f"ws://127.0.0.1:{port}/"):
            while not calls.any_open():
                await asyncio.sleep(0.05)
            server.should_exit = True
            await asyncio.wait_for(
                serving, 10
            )  # the ceiling, then uvicorn's 5 s to cancel the stuck call
        logger.remove(sink)
        return lines

    lines = asyncio.run(scenario())
    assert any("gave up" in line and "[3]" in line for line in lines), lines


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


def test_the_socket_refuses_a_call_with_no_ticket() -> None:
    client = TestClient(
        create_app("portal-secret"), base_url="https://voice.example.se"
    )
    same_origin = {"Origin": "https://voice.example.se"}
    with (
        pytest.raises(WebSocketDisconnect) as refused,
        client.websocket_connect("/ws", headers=same_origin),
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
    assert 'alt="Owner A&#x27;s Salon"' in page
    assert DISCLOSURE in page


def test_the_call_page_links_the_business_privacy_notice_only_when_it_has_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    given = {**GOOD, "privacy_url": 'https://example.se/integritet?a=1&b="2"'}
    with fake_portal(body=given) as url:
        page = call_page(monkeypatch, portal_env(url))
    link = re.search(
        r'<p class="privacy"><a href="([^"]*)" ([^>]*)>Privacy notice'
        r'<span class="sr-only"> \(opens in a new tab\)</span></a>',
        page,
    )  # the words were approved by Petter 2026-10-18; the hidden new-tab note 2026-10-19
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


# What voice/page.html sends at call start: an iPhone, which skips the loopback route (VOI-222).
FACTS = {
    "echo_cancellation": True,
    "noise_suppression": True,
    "auto_gain_control": "remote-only",
    "loopback": "skipped",
    "sample_rate": 48000,
    "base_latency_ms": 5.3,
    "output_latency_ms": 0,
    "browser": "safari",
    "os": "ios",
    "os_version": 18,
}
USER_AGENT = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)"  # synthetic


@contextlib.contextmanager
def warnings() -> Generator[list[str]]:
    lines: list[str] = []
    sink = logger.add(lambda m: lines.append(m.record["message"]), level="WARNING")
    try:
        yield lines
    finally:
        logger.remove(sink)


def test_the_browser_facts_go_to_the_log_checked_or_not_at_all() -> None:
    assert serve.page_facts(json.dumps({"type": "browser", **FACTS})) == {
        "page_facts": "sent",
        **FACTS,
    }
    assert serve.page_facts(json.dumps({"type": "browser"})) == {"page_facts": "sent"}
    # In the database's field order whatever order the page sent, so the Portal's log file matches the server log.
    shuffled = json.dumps({"type": "browser", **dict(reversed(FACTS.items()))})
    assert list(serve.page_facts(shuffled)) == ["page_facts", *serve.PAGE_FACTS]
    assert serve.page_facts(None) == {"page_facts": "not_sent"}
    refused = {
        "a user-agent string": {"browser": USER_AGENT},
        "a field nobody listed": {"user_agent": USER_AGENT},
        "a version that is not a major number": {"os_version": "18.0.1"},
        "true for a number": {"sample_rate": True},
        "1 for true": {"echo_cancellation": 1},
        "an unknown loopback": {"loopback": "maybe"},
        "a list": {"os": ["ios"]},
    }
    with warnings() as logged:
        for name, bad in refused.items():
            message = json.dumps({"type": "browser", **FACTS, **bad})
            assert serve.page_facts(message) == {"page_facts": "refused"}, name
        for message, kind in (
            ("x" * (serve.PAGE_MESSAGE_MAX + 1), "oversized"),
            ("{not json", "not_json"),
            ('["browser"]', "no_type"),
            ('{"type": "playback_gaps", "count": 1}', "bad_playback_gaps"),
            (json.dumps({"type": USER_AGENT}), "unknown_type"),
        ):
            assert serve.page_facts(message) == {"page_facts": "refused"}, kind
            assert logged[-1].endswith(f": {kind}")
    # Logged by kind, never by what the page sent.
    assert logged and not [line for line in logged if "Mozilla" in line]


def test_the_page_may_say_only_what_the_call_log_contract_lists() -> None:
    schema = json.loads(
        (Path(__file__).parents[1] / "contract/call-log.schema.json").read_text()
    )
    event = schema["$defs"]["event"]["properties"]
    assert {"page_facts", *serve.PAGE_FACTS} <= set(event), (
        "a browser fact voice/serve.py accepts is not in contract/call-log.schema.json: add it there (and to the security rule) first"
    )
    for name, values in (
        ("browser", serve.BROWSERS),
        ("os", serve.SYSTEMS),
        ("loopback", serve.LOOPBACK),
    ):
        assert tuple(event[name]["enum"]) == values, (
            f"voice/serve.py and contract/call-log.schema.json list different values for {name}: edit whichever is wrong"
        )
    switch = schema["$defs"]["switch"]["anyOf"]
    assert (True, False, *switch[1]["enum"]) == serve.SWITCH, (
        "voice/serve.py SWITCH and the contract's switch differ: edit whichever is wrong"
    )
    said = {
        serve.page_facts(text)["page_facts"]
        for text in ('{"type": "browser"}', None, "not json")
    }
    assert said == set(event["page_facts"]["enum"]), (
        "voice/serve.py page_facts and the contract's page_facts enum differ: edit whichever is wrong"
    )


def test_the_page_count_of_playback_gaps_is_passed_on_and_anything_else_ignored() -> (
    None
):
    frame = asyncio.run(
        RawPcmSerializer().deserialize('{"type": "playback_gaps", "count": 3}')
    )
    assert isinstance(frame, InputTransportMessageFrame)
    assert frame.message == {"type": "playback_gaps", "count": 3}
    page = RawPcmSerializer()  # one call's
    with warnings() as logged:
        for message in (
            '{"type": "playback_gaps", "count": -1}',
            '{"type": "playback_gaps", "count": 2, "note": "hej"}',
            '{"type": "browser"}',  # facts come once, first: these missed the wait
            *["x" * (serve.PAGE_MESSAGE_MAX + 1)] * 50,  # a page sending junk in a loop
        ):
            assert asyncio.run(page.deserialize(message)) is None
    # Once per kind and call, so a loop cannot flood the log.
    assert logged == [
        "ignored a message from the call page: bad_playback_gaps",
        "ignored a message from the call page: late_browser",
        "ignored a message from the call page: oversized",
    ]


class HangsUpOnTheLastCount(FrameProcessor):
    """Stands in for the Caller hanging up: ends the call once the page's second gap count has passed the recorder."""

    def __init__(self, worker: Callable[[], PipelineWorker]) -> None:
        super().__init__()  # pyright: ignore[reportUnknownMemberType]  # untyped kwargs upstream
        self._worker = worker

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        await self.push_frame(frame, direction)
        if (
            isinstance(frame, InputTransportMessageFrame)
            and frame.message["count"] == 2
        ):
            await self._worker().stop_when_done()


def test_a_call_logs_the_browser_facts_and_its_playback_gaps_and_survives_a_bad_message(
    tmp_path: Path,
) -> None:
    """The page's messages through a real socket and Pipecat pipeline into the barge-in log, as on a call."""
    log = tmp_path / "call.jsonl"
    app = FastAPI()

    @app.websocket("/ws")
    async def call(websocket: WebSocket) -> None:  # pyright: ignore[reportUnusedFunction]
        await websocket.accept()
        page = await serve.receive_page_facts(websocket)
        assert page is not None
        transport = serve.CallTransport(
            websocket,
            FastAPIWebsocketParams(
                audio_in_enabled=True,
                audio_in_sample_rate=serve.IN_RATE,
                serializer=RawPcmSerializer(),
            ),
        )
        recorder = BargeInRecorder("c0ffee0123456789", log, page)
        worker = PipelineWorker(
            Pipeline(
                [transport.input(), recorder, HangsUpOnTheLastCount(lambda: worker)]
            )
        )
        runner = WorkerRunner(handle_sigint=False)
        await runner.add_workers(worker)
        try:
            await runner.run()
            # Pipecat's transport closes the socket itself when its input stops; closing twice raises.
            if websocket.application_state != WebSocketState.DISCONNECTED:
                await websocket.close()
        finally:
            ended.set()

    # Pipecat closes the socket before its runner has stopped. Leaving the client then cancels the
    # runner mid-teardown, and the CancelledError that comes out is a Pipecat child task's, which
    # the TestClient's cancel scope does not take as its own, so it fails the test (VOI-176).
    # So the client waits for the call to end first.
    ended = threading.Event()
    with warnings() as logged, TestClient(app).websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "browser", **FACTS}))
        ws.send_text(json.dumps({"type": "user_agent", "ua": USER_AGENT}))
        ws.send_text("x" * 5000)
        ws.send_bytes(b"\x00\x00" * 320)
        ws.send_text('{"type": "playback_gaps", "count": 1}')
        ws.send_text('{"type": "playback_gaps", "count": 2}')
        with pytest.raises(WebSocketDisconnect):
            ws.receive_text()  # the call ends from its side, so the end event is written
        assert ended.wait(10), "the call did not end within 10 s of closing the socket"
    events = [json.loads(line) for line in log.read_text("utf-8").splitlines()]
    config, end = events[0], events[-1]
    assert config == {**config, "e": "config", "page_facts": "sent", **FACTS}
    # Both bad messages were refused and the call went on to count the gaps after them.
    assert end["e"] == "end" and end["playback_gaps"] == 2, end
    assert "Mozilla" not in log.read_text("utf-8") + str(logged)


def test_a_page_that_sends_no_facts_first_leaves_the_reason_and_no_gap_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(serve, "PAGE_FACTS_WAIT_S", 0.2)
    got: list[dict[str, object] | None] = []
    app = FastAPI()

    @app.websocket("/ws")
    async def call(websocket: WebSocket) -> None:  # pyright: ignore[reportUnusedFunction]
        await websocket.accept()
        got.append(await serve.receive_page_facts(websocket))
        await websocket.close()

    with TestClient(app).websocket_connect("/ws") as ws:
        ws.send_bytes(b"\x00\x00" * 320)  # audio first
        with pytest.raises(WebSocketDisconnect):
            ws.receive_text()
    # nothing at all
    with (
        TestClient(app).websocket_connect("/ws") as ws,
        pytest.raises(WebSocketDisconnect),
    ):
        ws.receive_text()
    assert got == [{"page_facts": "not_sent"}] * 2
    recorder = BargeInRecorder("c0ffee0123456789", tmp_path / "call.jsonl", got[0])
    asyncio.run(run_test(Pipeline([recorder]), frames_to_send=[]))
    events = [
        json.loads(line)
        for line in (tmp_path / "call.jsonl").read_text("utf-8").splitlines()
    ]
    assert events[0]["page_facts"] == "not_sent"
    assert "playback_gaps" not in events[-1], "a gap count nobody counted"
