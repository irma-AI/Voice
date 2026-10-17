"""The deployed web Channel: one page and a WebSocket, behind the Portal's call ticket. `make up` serves it.

Pipecat's own runner (voice/web.py) stays for the eval Channel; Pipecat calls it a development tool.
"""

import asyncio
import html
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import HTMLResponse, Response
from loguru import logger
from pipecat.frames.frames import (
    Frame,
    InputAudioRawFrame,
    InterruptionFrame,
    OutputAudioRawFrame,
)
from pipecat.serializers.base_serializer import FrameSerializer
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)

from voice.agent import run_call
from voice.auth import FONTS_PATH, REFUSAL_PAGE, TicketGate
from voice.settings import Settings, SettingsRefused, describe_source, load_settings
from voice.ticket import frame_ancestors, from_query, read_ticket

# What Gemini Live takes in and gives out; the page is served with these two numbers.
IN_RATE = 16000
OUT_RATE = 24000
# ponytail: a hard cap so a forgotten tab can't spend Gemini credit all night; make it a setting if calls legitimately run longer.
MAX_CALL_SECS = 600

PAGE = (Path(__file__).parent / "page.html").read_text("utf-8")
# The typefaces the call page uses: a copy of the Portal's, held equal by tests/test_design_tokens.py.
FONTS = {
    p.name: p.read_bytes()
    for p in (Path(__file__).parent / "static" / "fonts").glob("*.woff2")
}


def render_page(settings: Settings | None) -> str:
    """The call page for one Business, in its Theme; None (no settings to be had) is Voice's own look.

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
    return (
        PAGE.replace("__IN_RATE__", str(IN_RATE))
        .replace("__OUT_RATE__", str(OUT_RATE))
        .replace("__MAX_CALL_SECS__", str(MAX_CALL_SECS))
        .replace("__THEME__", css)
        .replace("__TITLE__", name)
        .replace("__BRAND__", brand)
    )


class RawPcmSerializer(FrameSerializer):
    """Mono 16-bit PCM both ways: bytes in are the Caller's microphone, bytes out are the agent."""

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
        return None

    async def deserialize(self, data: str | bytes) -> Frame | None:
        if isinstance(data, bytes):
            return InputAudioRawFrame(audio=data, sample_rate=IN_RATE, num_channels=1)
        return None


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


def create_app(ticket_secret: str) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    one_call = OneCallPerBusiness()
    app.add_middleware(TicketGate, ticket_secret=ticket_secret)

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
            render_page(settings), headers={"Content-Security-Policy": csp}
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
            transport = FastAPIWebsocketTransport(
                websocket,
                FastAPIWebsocketParams(
                    audio_in_enabled=True,
                    audio_out_enabled=True,
                    audio_in_sample_rate=IN_RATE,
                    audio_out_sample_rate=OUT_RATE,
                    serializer=RawPcmSerializer(),
                    session_timeout=MAX_CALL_SECS,
                ),
            )

            @transport.event_handler("on_session_timeout")
            async def _time_up(*_: object) -> None:  # pyright: ignore[reportUnusedFunction]
                await websocket.close()

            await run_call(transport, ticket=ticket)
        finally:
            one_call.release(ticket.business)

    return app


def main() -> None:
    load_dotenv()
    if not os.environ.get("GOOGLE_API_KEY", "").strip():
        sys.exit("GOOGLE_API_KEY is not set: put it in .env (see .env.example).")
    secret = os.environ.get("CORE_SECRET", "")
    if not secret.strip():  # fail closed: without it no call link can be checked
        sys.exit(
            "CORE_SECRET is not set: put the Portal's secret in .env (see .env.example)."
        )
    logger.info(
        describe_source()
    )  # a core with no settings source starts, and refuses every call
    app = create_app(secret)
    uvicorn.run(
        app,
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "7860")),
        access_log=False,  # a call ticket is in the request address: it must not reach the logs
    )


if __name__ == "__main__":
    main()
