"""The call reports port: what the core tells the Portal about one finished call (VOI-41).

At call end the core prices the call (voice/cost.py), builds one Call record (contract/call-record.schema.json),
writes it to its server log as one line, and only then sends it to the Portal's record address, all in the background,
retrying the send for up to a minute. The log line is the copy that survives a Portal that stays down or a restart
mid-retry; the raw usage reports are logged as they arrive, so the tokens survive a restart before it. Nothing here
delays or cuts a call.
"""

import asyncio
import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from loguru import logger
from pipecat.frames.frames import Frame, MetricsFrame
from pipecat.metrics.metrics import LLMUsageMetricsData
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from voice.cost import MODEL, price
from voice.settings import PORTAL_TIMEOUT_S, NoRedirect
from voice.ticket import Ticket

# ponytail: a fixed pause between tries; back off if the Portal is ever seen struggling under them.
RETRY_WINDOW_S = 60
RETRY_PAUSE_S = 5
# Record field <- Pipecat's usage report field. Both sides name the same count; the contract is the record's one definition.
TOKEN_FIELDS = {
    "prompt_tokens": "prompt_tokens",
    "completion_tokens": "completion_tokens",
    "input_audio_tokens": "input_audio_tokens",
    "output_audio_tokens": "output_audio_tokens",
    "thinking_tokens": "reasoning_tokens",
    "cached_tokens": "cache_read_input_tokens",
}
# Held so a send in flight is not collected before it finishes.
sending: set[asyncio.Task[bool]] = set()


class UsageTally(FrameProcessor):
    """Passes every frame on, adds up the model's usage reports and logs each one (numbers only) for the one-real-call check."""

    def __init__(self, call_id: str) -> None:
        super().__init__()  # pyright: ignore[reportUnknownMemberType]  # untyped kwargs upstream
        self._call_id = call_id
        self.totals = dict.fromkeys(TOKEN_FIELDS, 0)

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, MetricsFrame) and direction == FrameDirection.DOWNSTREAM:
            for d in frame.data:
                if isinstance(d, LLMUsageMetricsData):
                    report = d.value.model_dump(exclude_none=True)
                    logger.info(
                        "usage {}", json.dumps({"call": self._call_id, **report})
                    )
                    for field, source in TOKEN_FIELDS.items():
                        self.totals[field] += report.get(source, 0)
        await self.push_frame(frame, direction)


def build_record(
    call_id: str,
    ticket: Ticket,
    started_at: datetime,
    length_seconds: int,
    totals: Mapping[str, int],
    cost: Mapping[str, str | None],
) -> dict[str, Any]:
    """The Call record, in the shape of contract/call-record.schema.json. `cost` is `voice.cost.price`'s three fields."""
    return {
        "call_id": call_id,
        "business": ticket.business,
        "kind": ticket.kind,
        "started_at": started_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "length_seconds": length_seconds,
        **totals,
        **cost,
    }


def deliver(
    record: Mapping[str, Any],
    portal_url: str,
    secret: str,
    window_s: float = RETRY_WINDOW_S,
    pause_s: float = RETRY_PAUSE_S,
) -> bool:
    """Posts the record to the Portal, trying again for up to `window_s` seconds. Blocks, so it runs in a thread."""
    host = urlsplit(
        portal_url
    ).hostname  # the address could hold a password: the log names the host only
    call = record["call_id"]
    body = json.dumps(record).encode()
    deadline = time.monotonic() + window_s
    while True:
        try:
            request = urllib.request.Request(
                f"{portal_url.rstrip('/')}/api/calls/",
                body,
                {
                    "Authorization": f"Bearer {secret}",
                    "Content-Type": "application/json",
                },
            )
            with urllib.request.build_opener(NoRedirect).open(
                request, timeout=PORTAL_TIMEOUT_S
            ):
                logger.info("call {}: record delivered to the Portal", call)
                return True
        except urllib.error.HTTPError as e:
            why = f"answered {e.code}"
        except Exception as e:  # noqa: BLE001  the kind only: a message could hold the secret
            why = type(e).__name__
        if time.monotonic() + pause_s > deadline:
            logger.error(
                "call {}: gave up sending the record to the Portal at {} ({}); the log line above is the only copy",
                call,
                host,
                why,
            )
            return False
        logger.warning(
            "call {}: record not delivered to the Portal at {} ({}), trying again",
            call,
            host,
            why,
        )
        time.sleep(pause_s)


def finish(
    call_id: str,
    ticket: Ticket,
    started_at: datetime,
    length_seconds: int,
    totals: Mapping[str, int],
    env: Mapping[str, str],
) -> bool:
    """Prices the call, logs its record, then sends it. Blocks, so it runs in a thread."""
    cost = price(totals, MODEL, env.get("GOOGLE_API_KEY", "").strip())
    record = build_record(call_id, ticket, started_at, length_seconds, totals, cost)
    logger.info("call record {}", json.dumps(record))
    portal, secret = env.get("SETTINGS_URL", "").strip(), env.get("CORE_SECRET", "")
    if not (portal and secret):
        logger.error(
            "call {}: record not sent, SETTINGS_URL or CORE_SECRET is not set", call_id
        )
        return False
    return deliver(record, portal, secret)


def report_call(
    call_id: str,
    ticket: Ticket,
    started_at: datetime,
    length_seconds: int,
    totals: Mapping[str, int],
    env: Mapping[str, str] = os.environ,
) -> None:
    """Starts pricing, logging and sending the call's record and returns: the caller never waits on Google or the Portal. Needs a running loop."""
    task = asyncio.get_running_loop().create_task(
        asyncio.to_thread(
            finish, call_id, ticket, started_at, length_seconds, totals, env
        )
    )
    sending.add(task)
    task.add_done_callback(sending.discard)
