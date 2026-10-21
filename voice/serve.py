"""The deployed web Channel: one page and a WebSocket, behind the Portal's call ticket. `make up` serves it.

Pipecat's own runner (voice/web.py) stays for the eval Channel; Pipecat calls it a development tool.
"""

import asyncio
import hashlib
import hmac
import html
import json
import math
import os
import secrets
import socket
import sys
import time
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import HTMLResponse, Response
from loguru import logger
from pipecat.frames.frames import (
    Frame,
    InputAudioRawFrame,
    InputTransportMessageFrame,
    InterruptionFrame,
    OutputAudioRawFrame,
    TranscriptionFrame,
    TTSTextFrame,
)
from pipecat.observers.base_observer import BaseObserver, FramePushed
from pipecat.processors.frame_processor import FrameProcessorSetup
from pipecat.serializers.base_serializer import FrameSerializer
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketOutputTransport,
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from voice.agent import run_call
from voice.auth import FONTS_PATH, REFUSAL_PAGE, TicketGate
from voice.portal_client import core_secret
from voice.settings import Settings, SettingsRefused, describe_source, load_settings
from voice.ticket import frame_ancestors, from_query, read_ticket

# What Gemini Live takes in and gives out; the page is served with these two numbers.
IN_RATE = 16000
OUT_RATE = 24000
# ponytail: a hard cap so a forgotten tab can't spend Gemini credit all night; make it a setting if calls legitimately run longer.
# Per kind: a demo call from the landing page gets 3 minutes (Petter, 2026-10-20, VOI-243). tests/test_serve.py fails for a kind of
# voice/ticket.py KINDS with no cap here.
CALL_SECS = {"test": 600, "call_link": 600, "demo": 180, "agent_test": 600}
# The longest call of any kind: the Portal's worst-case rate (tests/portal/test_call_link.py) and the drain wait are sized to it.
MAX_CALL_SECS = max(CALL_SECS.values())
# A stop waits this long at most for open calls: every call ends within MAX_CALL_SECS, and Dokploy kills at 660 s.
DRAIN_CEILING_S = MAX_CALL_SECS + 30

PAGE = (Path(__file__).parent / "page.html").read_text("utf-8")
# Caller-facing wording, approved by Petter 2026-10-18 (CLAUDE.md § Stop and ask): a change here waits for his answer.
PRIVACY_LINK = "Privacy notice"
# What a test call's page says before Start, since its words are kept (VOI-160). Caller wording: a DRAFT from
# docs/research/call-log-legal-ground.md § 7, cut to words only; not to merge before Petter approves it (DECISIONS.md, ESCALATED).
TEST_CALL_NOTICE = (
    "This is a test call. We keep what you say, and what the assistant says, as text for 30 days "
    "to find and fix faults in the service. Only the Voice team can read it. Call where only you can be heard."
)
# The typefaces the call page uses: a copy of the Portal's, held equal by tests/test_design_tokens.py.
FONTS = {
    p.name: p.read_bytes()
    for p in (Path(__file__).parent / "static" / "fonts").glob("*.woff2")
}


# What the call page tells the core about the browser (voice/page.html): untrusted, so each field is checked here.
# The browser family and its OS come from fixed lists, so a user-agent string or a device name has no field to land
# in; contract/call-log.schema.json lists the same values (tests/test_serve.py fails when they differ).
BROWSERS = ("chrome", "edge", "firefox", "safari", "samsung", "other")
SYSTEMS = ("android", "ios", "macos", "windows", "linux", "chromeos", "other")
LOOPBACK = ("set_up", "fell_back", "skipped")  # skipped: iOS plays without it (VOI-222)
# getSettings() reports an audio setting as true or false, or (newer browsers) which audio echo cancelling covers.
SWITCH = (True, False, "all", "remote-only")
PAGE_MESSAGE_MAX = 1024  # characters; the page's messages are a few hundred
# The page sends its facts before its microphone; one that has not by then is taken to send none.
PAGE_FACTS_WAIT_S = 3.0


def _number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and 0 <= value <= 1_000_000
    )


def _count(value: object, below: int = 1_000_000) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value < below


def _one_of(*allowed: object) -> Callable[[object], bool]:
    # By type as well as value: True == 1 in Python, and a list or object is never one of them.
    return lambda value: any(type(value) is type(a) and value == a for a in allowed)


PAGE_FACTS: dict[str, Callable[[object], bool]] = {
    "echo_cancellation": _one_of(*SWITCH),
    "noise_suppression": _one_of(*SWITCH),
    "auto_gain_control": _one_of(*SWITCH),
    "loopback": _one_of(*LOOPBACK),
    "sample_rate": _number,
    "base_latency_ms": _number,
    "output_latency_ms": _number,
    "browser": _one_of(*BROWSERS),
    "os": _one_of(*SYSTEMS),
    "os_version": lambda value: _count(value, 1000),  # the major version only
}


def read_page_message(text: str) -> dict[str, Any] | str:
    """One text message from the call page, a JSON object with a `type`; else why not, as a code (never its content)."""
    if len(text) > PAGE_MESSAGE_MAX:
        return "oversized"
    try:
        message: object = json.loads(text)
    except ValueError:
        return "not_json"
    if not isinstance(message, dict) or not isinstance(message.get("type"), str):  # pyright: ignore[reportUnknownMemberType]
        return "no_type"
    return message  # pyright: ignore[reportUnknownVariableType]


def _kind(message: dict[str, Any] | str) -> str:
    """What a refused page message was, for the log: our code, or a type the page knows, never the page's text."""
    if isinstance(message, str):
        return message
    known = message["type"] in ("browser", "playback_gaps")
    return f"bad_{message['type']}" if known else "unknown_type"


def page_facts(text: str | None) -> dict[str, object]:
    """The browser facts for the call's config event, with `page_facts` saying whether they came: never a guess."""
    if text is None:
        return {"page_facts": "not_sent"}
    message = read_page_message(text)
    if isinstance(message, dict) and message["type"] == "browser":
        facts = {k: v for k, v in message.items() if k != "type"}
        if all(k in PAGE_FACTS and PAGE_FACTS[k](v) for k, v in facts.items()):
            # PAGE_FACTS's order is the database's field list's, which the Portal's Call log pages show fields in.
            return {
                "page_facts": "sent",
                **{k: facts[k] for k in PAGE_FACTS if k in facts},
            }
    logger.warning("refused the call page's browser facts: {}", _kind(message))
    return {"page_facts": "refused"}


async def receive_page_facts(websocket: WebSocket) -> dict[str, object] | None:
    """The page's first message, its browser facts, waited for briefly; None when the page has already gone."""
    try:
        message = await asyncio.wait_for(websocket.receive(), PAGE_FACTS_WAIT_S)
    except TimeoutError:
        return page_facts(None)
    if message["type"] == "websocket.disconnect":
        return None
    # Audio first is a page that sends no facts; that one block of microphone, before the agent speaks, is dropped.
    return page_facts(message.get("text"))


def render_page(settings: Settings | None, call_secs: int, kept: bool = False) -> str:
    """The call page for one Business, in its Theme, with its ring sized to this call's cap; None (no settings to be had) is Voice's own look.

    Text from the settings is escaped; the colours were checked as `#` and six hex digits by the settings port.
    """
    theme = settings.theme if settings else None
    css = ""
    if theme and theme.accent and theme.accent_text:
        css = (
            f":root {{ --action: {theme.accent}; --on-action: {theme.accent_text}; "
            f"--action-hover: {theme.accent}; --live: {theme.accent}; }}"
        )
    name = html.escape(settings.name if settings else "Voice")
    brand = f'<span class="name">{name}</span>'
    if theme and theme.logo_url:  # a logo that fails to load gives way to the name
        brand = (
            f'<img src="{html.escape(theme.logo_url)}" alt="{name}" '
            'onerror="this.hidden=true;this.nextElementSibling.hidden=false">'
            f'<span class="name" hidden>{name}</span>'
        )
    privacy = ""
    if (
        settings and settings.privacy_url
    ):  # the Business's own notice, beside the disclosure; it opens outside the call's frame
        privacy = (
            f'<p class="privacy"><a href="{html.escape(settings.privacy_url)}" '
            f'target="_blank" rel="noopener">{PRIVACY_LINK}<span class="sr-only"> (opens in a new tab)</span></a></p>'
        )
    if kept:  # a test call, whose words are kept: said before the Caller presses Start
        privacy = f'<p class="privacy">{TEST_CALL_NOTICE}</p>' + privacy
    return (
        PAGE.replace("__IN_RATE__", str(IN_RATE))
        .replace("__OUT_RATE__", str(OUT_RATE))
        .replace("__MAX_CALL_SECS__", str(call_secs))
        .replace("__DEMO_CAPPED__", str(DEMO_CAPPED))
        .replace(
            "__SERVED_AT__", str(int(time.time()))
        )  # the page tells an expired ticket by the core's clock
        .replace("__THEME__", css)
        .replace("__TITLE__", name)
        .replace("__BRAND__", brand)
        .replace(
            "__PRIVACY__", privacy
        )  # last: the Business's address could spell another marker
    )


class RawPcmSerializer(FrameSerializer):
    """Mono 16-bit PCM both ways: bytes in are the Caller's microphone, bytes out are the agent.

    Text out is JSON: the interrupt, and the Live transcript (GLOSSARY.md), which is shown on the page only:
    nothing here keeps or logs it.
    """

    async def serialize(self, frame: Frame) -> str | bytes | None:
        if isinstance(frame, OutputAudioRawFrame):
            if frame.sample_rate != OUT_RATE or frame.num_channels != 1:
                raise ValueError(
                    "agent audio is not 24 kHz mono, so it would play garbled"
                )
            return frame.audio
        if isinstance(
            frame, InterruptionFrame
        ):  # the Caller spoke over the agent: drop queued audio
            return json.dumps({"type": "interrupt"})
        # Gemini Live's transcription: a sentence the Caller said, or a piece of what the agent says
        # (its text also comes as an LLMTextFrame, which is left out so the page gets it once).
        if isinstance(frame, TranscriptionFrame):
            return json.dumps(
                {"type": "transcript", "speaker": "caller", "text": frame.text}
            )
        if isinstance(frame, TTSTextFrame):
            return json.dumps(
                {"type": "transcript", "speaker": "agent", "text": frame.text}
            )
        return None

    def __init__(self) -> None:
        super().__init__()  # pyright: ignore[reportUnknownMemberType]  # untyped kwargs upstream
        self._warned: set[str] = (
            set()
        )  # kinds of page message already logged on this call

    async def deserialize(self, data: str | bytes) -> Frame | None:
        if isinstance(data, bytes):
            return InputAudioRawFrame(audio=data, sample_rate=IN_RATE, num_channels=1)
        # Text is the page's count of playback gaps so far, for the barge-in log's end event (voice/bargein.py);
        # anything else is ignored and logged by kind, and the call goes on.
        message = read_page_message(data)
        if (
            isinstance(message, dict)
            and message["type"] == "playback_gaps"
            and set(message) == {"type", "count"}
            and _count(message["count"])
        ):
            return InputTransportMessageFrame(
                message={"type": "playback_gaps", "count": message["count"]}
            )
        kind = _kind(message)
        if kind == "bad_browser":
            kind = (
                "late_browser"  # facts come first or not at all; these missed the wait
            )
        if (
            kind not in self._warned
        ):  # once per kind and call: a page sending junk in a loop must not flood the log
            self._warned.add(kind)
            logger.warning("ignored a message from the call page: {}", kind)
        return None


class _TranscriptOutput(FastAPIWebsocketOutputTransport):
    """The socket's output, which also sends the Live transcript to the page through the serializer.

    The agent's words come downstream and wait in the output's queue behind the audio before them, so they show as
    they are heard and are dropped with it on an interruption. The Caller's words go upstream from the model and are
    taken by the context aggregator before they reach the input, so an observer of the pipeline (Pipecat's own way
    to watch frames) picks them up; the pipeline itself is the agent's (voice/agent.py) and is left as it is.
    """

    async def setup(self, setup: FrameProcessorSetup) -> None:
        await super().setup(setup)
        setup.pipeline_worker.add_observer(_CallerWords(self))

    async def write_transport_frame(self, frame: Frame) -> None:
        if isinstance(frame, TTSTextFrame):
            # ponytail: Pipecat's private sender (pinned 1.12.0); move to a public one if it gets one.
            await self._write_frame(frame)  # pyright: ignore[reportPrivateUsage]


class _CallerWords(BaseObserver):
    """Hands each sentence the Caller said to the socket's output, once (its first push)."""

    def __init__(self, output: _TranscriptOutput) -> None:
        super().__init__(observe_every_push=False)  # pyright: ignore[reportUnknownMemberType]  # untyped kwargs upstream
        self._output = output

    async def on_push_frame(self, data: FramePushed) -> None:
        if isinstance(data.frame, TranscriptionFrame):
            await self._output._write_frame(data.frame)  # pyright: ignore[reportPrivateUsage]


class CallTransport(FastAPIWebsocketTransport):
    """Pipecat's FastAPI WebSocket transport, with an output that also sends the Live transcript."""

    def __init__(self, websocket: WebSocket, params: FastAPIWebsocketParams) -> None:
        super().__init__(websocket, params)
        # ponytail: replaces Pipecat's output after it is built (pinned 1.12.0); it takes no output class to use instead.
        self._output = _TranscriptOutput(
            self, self._client, self._params, name=self._output_name
        )


def call_params(kind: str) -> FastAPIWebsocketParams:
    """How the socket carries one call: raw PCM at the model's rates, ended by Pipecat at the kind's cap (tests/test_serve.py)."""
    return FastAPIWebsocketParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        audio_in_sample_rate=IN_RATE,
        audio_out_sample_rate=OUT_RATE,
        serializer=RawPcmSerializer(),
        session_timeout=CALL_SECS[kind],
    )


def same_site(origin: str | None, host: str | None) -> bool:
    """True only when the WebSocket was opened from this site's own page.

    A call link in the address is all a cross-site page needs to open a socket, so without this any page
    the Caller visits could start a paid call from a link it has seen.
    """
    return bool(origin and host and urlsplit(origin).netloc == host)


class OneCallPerBusiness:
    """Which Businesses have a call open. A link anyone can open would otherwise let one visitor run many paid calls at once.

    shortcut: counts in this process's memory, so it holds only while the core runs as one process; move it to shared storage before a second one.
    """

    def __init__(self) -> None:
        self._open: set[int] = set()

    def take(self, business: int) -> bool:
        """True and the Business is marked open, or False when a call for it is already open."""
        if business in self._open:
            return False
        self._open.add(business)
        return True

    def release(self, business: int) -> None:
        self._open.discard(business)

    def any_open(self) -> bool:
        return bool(self._open)

    def open_ones(self) -> list[int]:
        return sorted(self._open)


# The landing page's demo (VOI-244; Petter, 2026-10-20): one visitor's address may start this many demo calls a day. Counted here,
# when a call starts, so opening and closing the Call button's panel counts nothing (Petter, 2026-10-20).
DEMO_CALLS_PER_ADDRESS = 2
# The close code that tells the call page the visitor's demo calls are used up for today (voice/page.html reads it).
DEMO_CAPPED = 4003


class DemoCalls:
    """Each visitor address's demo calls today. An address is kept only as HMAC-SHA-256 of it and the day under a key made per
    process, so it cannot be turned back by trying addresses; it is never logged. The counts go at midnight on TIME_ZONE.

    shortcut: counts in this process's memory, so a restart clears them and a second process would count apart; move them to shared storage before a second one.
    """

    def __init__(self) -> None:
        self._key = secrets.token_bytes(32)
        self._day: date | None = None
        self._counts: dict[str, int] = {}

    def take(self, address: str, today: date) -> bool:
        """True and one call counted, or False when this address has started its demo calls for today."""
        if today != self._day:
            self._day, self._counts = today, {}
        code = hmac.new(
            self._key, f"{address}\n{today}".encode(), hashlib.sha256
        ).hexdigest()
        if self._counts.get(code, 0) >= DEMO_CALLS_PER_ADDRESS:
            return False
        self._counts[code] = self._counts.get(code, 0) + 1
        return True


def local_today() -> date:
    """Today on TIME_ZONE (the Portal's setting of the same name; UTC when unset), the day the demo counts go by."""
    return datetime.now(
        ZoneInfo(os.environ.get("TIME_ZONE", "UTC").strip() or "UTC")
    ).date()


def client_address(websocket: WebSocket) -> str:
    """Where the call comes from: behind the one proxy (Traefik on Dokploy) the last X-Forwarded-For entry is the address it saw;
    entries before it are whatever the client wrote. Without the header, the socket's own peer."""
    forwarded = websocket.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[-1].strip() or (
        websocket.client.host if websocket.client else ""
    )


class DrainingServer(uvicorn.Server):
    """uvicorn, except that a stop (a deploy) waits for the open calls to end before it hangs up on anyone.

    uvicorn closes every open WebSocket with code 1012 when it is told to stop. Calls end by themselves within MAX_CALL_SECS, and the platform's stop wait must be longer than that (see the Dockerfile).
    A call still open after DRAIN_CEILING_S never released its slot (a bug): the stop gives up on it and says which Business.
    """

    def __init__(
        self,
        config: uvicorn.Config,
        calls: OneCallPerBusiness,
        ceiling_s: float = DRAIN_CEILING_S,
    ) -> None:
        super().__init__(config)
        self.calls, self.ceiling_s = calls, ceiling_s

    async def shutdown(self, sockets: list[socket.socket] | None = None) -> None:
        for server in self.servers:
            server.close()  # no new call; the open ones keep their connections
        give_up = time.monotonic() + self.ceiling_s
        while self.calls.any_open():
            if time.monotonic() >= give_up:
                logger.error(
                    "stop: gave up after {} s waiting for the calls of Businesses {}; they are cut now",
                    self.ceiling_s,
                    self.calls.open_ones(),
                )
                self.config.timeout_graceful_shutdown = (
                    5  # else uvicorn waits on the stuck call's task for ever
                )
                break
            await asyncio.sleep(min(1, self.ceiling_s))
        await super().shutdown(sockets)


SECURITY_HEADERS = [
    (b"strict-transport-security", b"max-age=2592000"),
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"same-origin"),
]


class SecurityHeaders:
    """ASGI middleware: every HTTP response, the gate's refusal included, says HTTPS only, no sniffing, no referrer off the site."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                message["headers"] = [*message.get("headers", []), *SECURITY_HEADERS]
            await send(message)

        await self.app(scope, receive, with_headers)


def create_app(ticket_secret: str) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    one_call = app.state.one_call = OneCallPerBusiness()
    demo_calls = app.state.demo_calls = DemoCalls()
    app.add_middleware(TicketGate, ticket_secret=ticket_secret)
    app.add_middleware(SecurityHeaders)  # added last, so it wraps the gate

    @app.get("/")
    async def page(request: Request) -> HTMLResponse:  # pyright: ignore[reportUnusedFunction]
        # The gate has checked the ticket; the domain it names is re-checked as the header is written (fail closed).
        ticket = read_ticket(from_query(request.scope["query_string"]), ticket_secret)
        try:
            if ticket is None:
                raise ValueError("no valid ticket")
            csp = frame_ancestors(ticket.domain)
        except ValueError:
            logger.warning("refused /: the call ticket has no usable domain")
            return HTMLResponse(REFUSAL_PAGE, status_code=403)
        # The Theme comes through the settings port the call uses. Without settings the page shows Voice's
        # own look; the call itself is then refused when it starts (voice/agent.py).
        try:
            settings = await asyncio.to_thread(
                load_settings, os.environ, str(ticket.business)
            )
        except SettingsRefused as e:
            logger.warning("call page in Voice's own look: {}", e)
            settings = None
        return HTMLResponse(
            render_page(settings, CALL_SECS[ticket.kind], kept=ticket.kind == "test"),
            headers={"Content-Security-Policy": csp},
        )

    @app.get(FONTS_PATH + "{name}")
    async def font(name: str) -> Response:  # pyright: ignore[reportUnusedFunction]
        if name not in FONTS:
            return Response(status_code=404)
        return Response(
            FONTS[name],
            media_type="font/woff2",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    @app.websocket("/ws")
    async def call(websocket: WebSocket) -> None:  # pyright: ignore[reportUnusedFunction]
        origin, host = websocket.headers.get("origin"), websocket.headers.get("host")
        if not same_site(origin, host):
            logger.warning(
                "refused /ws: Origin {!r} does not match Host {!r}", origin, host
            )
            return await websocket.close(code=1008)
        # The ticket names the Business this call is for and what started it; the gate already checked it, and a call never runs without one.
        ticket = read_ticket(from_query(websocket.scope["query_string"]), ticket_secret)
        if ticket is None:
            logger.warning("refused /ws: the call ticket is wrong or has expired")
            return await websocket.close(code=1008)
        # One call at a time per Business, whatever started it (Petter, VOI-59); the slot is taken before anything awaits.
        if not one_call.take(ticket.business):
            logger.warning(
                "refused /ws: Business {} already has a call open", ticket.business
            )
            return await websocket.close(code=1008)
        try:
            await websocket.accept()
            page = await receive_page_facts(websocket)
            if page is None:
                return
            # A demo call counts when it starts. The page keeps the close code from the moment the socket opens, so it shows a used-up day even when it was slow to send its facts.
            if ticket.kind == "demo" and not demo_calls.take(
                client_address(websocket), local_today()
            ):
                logger.warning(
                    "refused /ws: Business {} demo cap per_address", ticket.business
                )
                return await websocket.close(code=DEMO_CAPPED)
            transport = CallTransport(websocket, call_params(ticket.kind))

            @transport.event_handler("on_session_timeout")
            async def _time_up(*_: object) -> None:  # pyright: ignore[reportUnusedFunction]
                await websocket.close()

            await run_call(transport, ticket=ticket, page=page)
        finally:
            one_call.release(ticket.business)

    return app


def main() -> None:
    load_dotenv()
    if not os.environ.get("GOOGLE_API_KEY", "").strip():
        sys.exit("GOOGLE_API_KEY is not set: put it in .env (see .env.example).")
    secret = core_secret()
    if not secret.strip():  # fail closed: without it no call link can be checked
        sys.exit(
            "CORE_SECRET is not set: put the Portal's secret in .env (see .env.example)."
        )
    try:  # read on every demo call: a bad name would break each one, so it stops the core here (fail closed, with the reason)
        local_today()
    except (ZoneInfoNotFoundError, ValueError):
        sys.exit(
            "TIME_ZONE is not a tz database name, like Europe/Stockholm (see .env.example)."
        )
    logger.info(
        describe_source()
    )  # a core with no settings source starts, and refuses every call
    app = create_app(secret)
    config = uvicorn.Config(
        app,
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "7860")),
        access_log=False,  # a call ticket is in the request address: it must not reach the logs
    )
    DrainingServer(config, app.state.one_call).run()


if __name__ == "__main__":
    main()
