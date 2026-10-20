"""The call reports port: what the core tells the Portal about one finished call (VOI-41), and its Call log (VOI-153).

At call end the core prices the call (voice/cost.py), builds one Call record (contract/call-record.schema.json),
writes it to its server log as one line, and only then sends it to the Portal's record address, all in the background,
retrying the send for up to a minute. The log line is the copy that survives a Portal that stays down or a restart
mid-retry; the raw usage reports are logged as they arrive, so the tokens survive a restart before it. Nothing here
delays or cuts a call.

The Call log (contract/call-log.schema.json) is the call's barge-in lines (voice/bargein.py), read here as they reach
the log, so the stored copy is exactly what the server log holds; it is sent beside the record, the same way.
"""

import asyncio
import json
import os
from collections import defaultdict
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any

from loguru import logger
from pipecat.frames.frames import Frame, MetricsFrame
from pipecat.metrics.metrics import LLMUsageMetricsData
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from voice.cost import MODEL, price
from voice.portal_client import post
from voice.ticket import Ticket

# Records retrying against a down Portal wait here, never on asyncio's default threads that call starts read settings on.
# shortcut: a fifth record waits for a free thread, raise max_workers if the give-up line is ever seen for a queued record.
SENDER = ThreadPoolExecutor(max_workers=4, thread_name_prefix="call-record")
# Call logs retry on their own threads, so a down Portal never makes a record (and its log line, the billing copy) wait behind them.
LOG_SENDER = ThreadPoolExecutor(max_workers=4, thread_name_prefix="call-log")
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
sending: set[asyncio.Future[bool]] = set()
BARGE_IN_PREFIX = "barge-in "
# The barge-in events of each call still running, by call id, as logged; report_call takes a call's out at its end.
# shortcut: a call that never reaches report_call (the eval Channel, a pipeline that fails to build), or a line logged after it (not seen), stays here until the process ends; bound it if a long-lived core ever runs those.
EVENTS: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)


def keep_barge_in_line(record: Any) -> None:
    """A loguru patcher: keeps each barge-in line the recorder logs. Reads the log, not the recorder, whose module is an eval-required path."""
    message: str = record["message"]
    if message.startswith(BARGE_IN_PREFIX):
        try:
            event = json.loads(message.removeprefix(BARGE_IN_PREFIX))
            EVENTS[event["call"]].append(event)
        except (ValueError, KeyError, TypeError):  # never fail the code that logs
            pass


# A patcher, not a sink: run_call removes every sink at each call start, and patchers survive that.
logger.configure(patcher=keep_barge_in_line)


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


def build_log(
    call_id: str,
    ticket: Ticket,
    started_at: datetime,
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    """The Call log, in the shape of contract/call-log.schema.json."""
    return {
        "call_id": call_id,
        "business": ticket.business,
        "kind": ticket.kind,
        "started_at": started_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "events": events,
    }


def finish(
    call_id: str,
    ticket: Ticket,
    started_at: datetime,
    length_seconds: int,
    totals: Mapping[str, int],
    env: Mapping[str, str],
) -> bool:
    """Prices the call, logs its record, then sends it. Blocks, so it runs in a thread."""
    cost = price(totals, MODEL, env.get("BILLING_API_KEY", "").strip())
    record = build_record(call_id, ticket, started_at, length_seconds, totals, cost)
    logger.info("call record {}", json.dumps(record))
    return post("/api/calls/", record, "record", env)


def send_log(log: Mapping[str, Any], env: Mapping[str, str]) -> bool:
    """Sends the Call log, whose lines the server log already holds. Blocks, so it runs in a thread."""
    return post("/api/call-logs/", log, "Call log", env)


def report_call(
    call_id: str,
    ticket: Ticket,
    started_at: datetime,
    length_seconds: int,
    totals: Mapping[str, int],
    env: Mapping[str, str] = os.environ,
) -> None:
    """Starts pricing, logging and sending the call's record, and sending its Call log, and returns: the caller never waits on Google or the Portal. Needs a running loop."""
    loop = asyncio.get_running_loop()
    log = build_log(call_id, ticket, started_at, EVENTS.pop(call_id, []))
    for task in (
        loop.run_in_executor(
            SENDER, finish, call_id, ticket, started_at, length_seconds, totals, env
        ),
        loop.run_in_executor(LOG_SENDER, send_log, log, env),
    ):
        sending.add(task)
        task.add_done_callback(sending.discard)
