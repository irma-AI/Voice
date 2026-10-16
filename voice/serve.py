"""The deployed web Channel: one page and a WebSocket, behind the login. `make up` serves it.

Pipecat's own runner (voice/web.py) stays for the eval Channel; Pipecat calls it a development tool.
"""

import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse
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
from voice.auth import BasicAuth
from voice.calls import NotLetStart
from voice.settings import describe_source
from voice.ticket import from_query, ticket_business

# What Gemini Live takes in and gives out; the page is served with these two numbers.
IN_RATE = 16000
OUT_RATE = 24000
# ponytail: a hard cap so a forgotten tab can't spend Gemini credit all night; make it a setting if calls legitimately run longer.
MAX_CALL_SECS = 600

PAGE = (Path(__file__).parent / "page.html").read_text("utf-8")


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

    The browser may send its cached Basic login with a cross-site WebSocket, so without this any page
    the logged-in Caller visits could start a paid call.
    """
    return bool(origin and host and urlsplit(origin).netloc == host)


def create_app(user: str, password: str, ticket_secret: str = "") -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(
        BasicAuth, user=user, password=password, ticket_secret=ticket_secret
    )

    @app.get("/")
    async def page() -> HTMLResponse:  # pyright: ignore[reportUnusedFunction]
        return HTMLResponse(
            PAGE.replace("__IN_RATE__", str(IN_RATE)).replace(
                "__OUT_RATE__", str(OUT_RATE)
            )
        )

    @app.websocket("/ws")
    async def call(websocket: WebSocket) -> None:  # pyright: ignore[reportUnusedFunction]
        origin, host = websocket.headers.get("origin"), websocket.headers.get("host")
        if not same_site(origin, host):
            logger.warning(
                "refused /ws: Origin {!r} does not match Host {!r}", origin, host
            )
            return await websocket.close(code=1008)
        # A ticket from the Portal names the Business this call is for; one that does not check out refuses the call,
        # even for the shared login, so a call never falls back to a Business the Caller did not ask for.
        business_id = None
        sent = from_query(
            websocket.scope["query_string"]
        )  # the same reading the login middleware made
        if sent is not None:
            business_id = ticket_business(sent, ticket_secret)
            if business_id is None:
                logger.warning("refused /ws: the call ticket is wrong or has expired")
                return await websocket.close(code=1008)
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

        try:
            await run_call(transport, business_id=business_id)
        except NotLetStart as refused:
            # The Portal said no before any model session opened: the page shows the reason as text and the socket closes.
            logger.warning("call not let start: {}", refused)
            await websocket.send_text(
                json.dumps({"type": "refused", "text": refused.text})
            )
            await websocket.close()

    return app


def main() -> None:
    load_dotenv()
    if not os.environ.get("GOOGLE_API_KEY", "").strip():
        sys.exit("GOOGLE_API_KEY is not set: put it in .env (see .env.example).")
    password = os.environ.get("VOICE_PASSWORD", "")
    if (
        not password.strip()
    ):  # fail closed: without a login anyone could start a paid call
        sys.exit("VOICE_PASSWORD is not set: put it in .env (see .env.example).")
    logger.info(
        describe_source()
    )  # a core with no settings source starts, and refuses every call
    app = create_app(
        os.environ.get("VOICE_USER", "voice"),
        password,
        os.environ.get("CORE_SECRET", ""),
    )
    uvicorn.run(
        app,
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "7860")),
        access_log=False,  # a Portal call ticket is in the request address: it must not reach the logs
    )


if __name__ == "__main__":
    main()
