"""Seam 2: the call reports port, free. The Call record and Call log the core builds after a call, and their delivery to a real HTTP server on localhost standing in for the Portal.

Nothing of ours is mocked. The shapes are the contract files' (contract/call-record.schema.json, contract/call-log.schema.json).
"""

import asyncio
import json
import threading
import time
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from loguru import logger
from pipecat.frames.frames import EndFrame, MetricsFrame
from pipecat.metrics.metrics import LLMTokenUsage, LLMUsageMetricsData
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineWorker
from pipecat.workers.runner import WorkerRunner

from voice import report
from voice.bargein import BargeInRecorder
from voice.portal_client import post
from voice.report import UsageTally, build_record, report_call
from voice.ticket import Ticket

ROOT = Path(__file__).parents[1]
SCHEMA: dict[str, Any] = json.loads(
    (ROOT / "contract/call-record.schema.json").read_text()
)
LOG_SCHEMA: dict[str, Any] = json.loads(
    (ROOT / "contract/call-log.schema.json").read_text()
)
SECRET = "s3cret"
STARTED = datetime(2026, 10, 17, 7, 30, 5, 123456, tzinfo=UTC)
TICKET = Ticket(7, "call_link")
TOTALS = {
    "prompt_tokens": 1200,
    "completion_tokens": 340,
    "input_audio_tokens": 1000,
    "output_audio_tokens": 300,
    "thinking_tokens": 0,
    "cached_tokens": 800,
}


# No Google key in these tests' environment: the record is priced as far as the key (the pricing itself is tests/test_cost_catalogue.py).
NO_KEY = {"cost_usd": None, "price_date": None, "cost_reason": "no_billing_key"}


def a_record() -> dict[str, Any]:
    return build_record("c0ffee0123456789", TICKET, STARTED, 184, TOTALS, NO_KEY)


@contextmanager
def fake_portal(
    answers: list[int], seen: list[Any], hold: threading.Event | None = None
) -> Generator[str]:
    """A real server that answers the record address with each status in `answers` in turn, then 201.

    Every request it gets goes into `seen` as (path, Authorization, parsed body); with `hold`, it waits for the event before answering.
    """

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            body = self.rfile.read(int(self.headers["Content-Length"]))
            seen.append(
                (self.path, self.headers.get("Authorization"), json.loads(body))
            )
            if hold:
                hold.wait(10)
            self.send_response(answers.pop(0) if answers else 201)
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            return None

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()


def portal_env(url: str) -> dict[str, str]:
    return {"SETTINGS_URL": url, "CORE_SECRET": SECRET}


@contextmanager
def log_lines() -> Generator[list[str]]:
    lines: list[str] = []
    sink = logger.add(lambda m: lines.append(m.record["message"]), level="INFO")
    try:
        yield lines
    finally:
        logger.remove(sink)


def test_a_finished_call_makes_a_record_the_contract_accepts() -> None:
    record = a_record()
    validator: Any = Draft202012Validator(SCHEMA)
    assert list(validator.iter_errors(record)) == []
    assert record["started_at"] == "2026-10-17T07:30:05.123456Z"
    assert (record["business"], record["kind"], record["length_seconds"]) == (
        7,
        "call_link",
        184,
    )
    assert record["cost_usd"] is None and record["cost_reason"] == "no_billing_key"


def test_the_tally_adds_up_every_usage_report_of_a_call() -> None:
    def usage(**tokens: int) -> MetricsFrame:
        value = LLMTokenUsage(total_tokens=0, **{"prompt_tokens": 0, **tokens})  # pyright: ignore[reportArgumentType]
        return MetricsFrame(data=[LLMUsageMetricsData(processor="llm", value=value)])

    tally = UsageTally("c0ffee0123456789")

    async def play() -> None:
        worker = PipelineWorker(Pipeline([tally]))
        await worker.queue_frames(
            [
                usage(
                    prompt_tokens=100,
                    completion_tokens=10,
                    input_audio_tokens=80,
                    output_audio_tokens=8,
                    cache_read_input_tokens=50,
                ),
                usage(prompt_tokens=120, completion_tokens=20, reasoning_tokens=5),
                EndFrame(),
            ]
        )
        runner = WorkerRunner()
        await runner.add_workers(worker)
        await runner.run()

    with log_lines() as lines:
        asyncio.run(play())

    assert tally.totals == {
        "prompt_tokens": 220,
        "completion_tokens": 30,
        "input_audio_tokens": 80,
        "output_audio_tokens": 8,
        "thinking_tokens": 5,
        "cached_tokens": 50,
    }
    # Each raw report is kept for the one-real-call check, numbers only.
    assert [line for line in lines if line.startswith("usage ")] == [
        (
            'usage {"call": "c0ffee0123456789", "prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 0, '
            '"cache_read_input_tokens": 50, "input_audio_tokens": 80, "output_audio_tokens": 8}'
        ),
        (
            'usage {"call": "c0ffee0123456789", "prompt_tokens": 120, "completion_tokens": 20, "total_tokens": 0, '
            '"reasoning_tokens": 5}'
        ),
    ]


def test_a_record_is_delivered_with_the_secret() -> None:
    seen: list[Any] = []
    with fake_portal([], seen) as portal:
        assert (
            post("/api/calls/", a_record(), "record", portal_env(portal + "/")) is True
        )
    assert seen == [("/api/calls/", f"Bearer {SECRET}", a_record())]


def test_delivery_tries_again_while_the_portal_fails() -> None:
    seen: list[Any] = []
    with fake_portal([503, 503], seen) as portal, log_lines() as lines:
        assert (
            post(
                "/api/calls/",
                a_record(),
                "record",
                portal_env(portal),
                window_s=5,
                pause_s=0.01,
            )
            is True
        )
    assert len(seen) == 3
    assert sum("trying again" in line for line in lines) == 2


def test_delivery_gives_up_when_the_window_ends_and_says_so() -> None:
    seen: list[Any] = []
    with fake_portal([503] * 1000, seen) as portal, log_lines() as lines:
        started = time.monotonic()
        assert (
            post(
                "/api/calls/",
                a_record(),
                "record",
                portal_env(portal),
                window_s=0.3,
                pause_s=0.05,
            )
            is False
        )
        assert time.monotonic() - started < 3  # the window, not forever
    assert len(seen) >= 2
    assert "gave up sending the record" in lines[-1] and "answered 503" in lines[-1]
    assert SECRET not in "".join(lines)


def test_a_portal_that_is_down_is_the_same_as_one_that_fails() -> None:
    with fake_portal([], []) as portal:
        pass  # the server is closed again: nothing listens on this address
    with log_lines() as lines:
        assert (
            post(
                "/api/calls/",
                a_record(),
                "record",
                portal_env(portal),
                window_s=0.2,
                pause_s=0.05,
            )
            is False
        )
    assert "gave up" in lines[-1] and portal not in "".join(lines)


def test_the_record_is_logged_before_any_send_and_the_call_never_waits_on_it() -> None:
    seen: list[Any] = []
    hold = threading.Event()
    env: dict[str, str] = {}
    with fake_portal([], seen, hold) as portal, log_lines() as lines:
        env = portal_env(portal)

        async def end_of_call() -> tuple[float, int]:
            began = time.monotonic()
            report_call("c0ffee0123456789", TICKET, STARTED, 184, TOTALS, env)
            took = time.monotonic() - began
            # The Portal is stuck; the call is already over. Let the record reach the log, then let the Portal answer.
            await asyncio.sleep(0.2)
            logged_before_send = len(lines)
            hold.set()
            await asyncio.gather(*report.sending)
            return took, logged_before_send

        took, logged_before_send = asyncio.run(end_of_call())

    assert took < 0.1  # the Portal held its answer; the call did not
    assert lines[0] == "call record " + json.dumps(a_record())
    assert logged_before_send == 1  # the line was written when the send had not started
    assert [s[2] for s in seen if s[0] == "/api/calls/"] == [a_record()]
    assert any("record delivered" in line for line in lines)


def test_records_stuck_on_a_down_portal_leave_the_default_threads_to_call_starts() -> (
    None
):
    hold = threading.Event()
    with fake_portal([], [], hold) as portal:
        env = portal_env(portal)

        async def six_calls_end_then_one_starts() -> tuple[float, int]:
            # asyncio's default executor on a 2 vCPU host: min(32, cpu + 4) threads.
            asyncio.get_running_loop().set_default_executor(
                ThreadPoolExecutor(max_workers=6)
            )
            began = time.monotonic()
            for _ in range(6):
                report_call("c0ffee0123456789", TICKET, STARTED, 184, TOTALS, env)
            took = time.monotonic() - began
            await asyncio.sleep(0)  # each record is on its thread
            try:  # a call start reading its settings
                return took, await asyncio.wait_for(asyncio.to_thread(lambda: 1), 1)
            finally:
                hold.set()
                await asyncio.gather(*report.sending)

        took, started = asyncio.run(six_calls_end_then_one_starts())

    assert took < 0.1
    assert started == 1


def test_no_portal_to_send_to_is_logged_not_ignored() -> None:
    async def end_of_call() -> None:
        report_call("c0ffee0123456789", TICKET, STARTED, 1, TOTALS, {})
        await asyncio.gather(*report.sending)

    with log_lines() as lines:
        asyncio.run(end_of_call())
    assert any(line.startswith("call record ") for line in lines)
    assert sum("not sent" in line for line in lines) == 2  # the record and the Call log


def test_the_security_rule_lists_every_field_a_production_log_line_may_hold() -> None:
    """A new field in the record or in Pipecat's usage report fails here until `.claude/rules/security.md` lists it."""
    rule = (ROOT / ".claude/rules/security.md").read_text()
    line = next(l for l in rule.splitlines() if l.startswith("- The Call record log"))
    for field in [*SCHEMA["properties"], "call", *LLMTokenUsage.model_fields]:
        assert f"`{field}`" in line, (
            f"add `{field}` to the Call record line in .claude/rules/security.md"
        )


def test_a_call_s_barge_in_lines_reach_the_portal_as_its_call_log_and_the_call_never_waits() -> (
    None
):
    """The lines are in the server log first; the Portal holds its answer, and the call's end does not wait for it."""
    call = "c0ffee0123456789"
    seen: list[Any] = []
    hold = threading.Event()
    with fake_portal([], seen, hold) as portal, log_lines() as lines:
        env = portal_env(portal)

        async def a_call_ends() -> float:
            worker = PipelineWorker(Pipeline([BargeInRecorder(call)]))
            await worker.queue_frames([EndFrame()])
            runner = WorkerRunner()
            await runner.add_workers(worker)
            await runner.run()
            began = time.monotonic()
            report_call(call, TICKET, STARTED, 2, TOTALS, env)
            took = time.monotonic() - began
            await asyncio.sleep(0.2)
            hold.set()
            await asyncio.gather(*report.sending)
            return took

        took = asyncio.run(a_call_ends())

    assert took < 0.1
    logged = [
        json.loads(line.removeprefix("barge-in "))
        for line in lines
        if line.startswith("barge-in ")
    ]
    assert [e["e"] for e in logged] == ["config", "end"]
    [(_, auth, log)] = [s for s in seen if s[0] == "/api/call-logs/"]
    assert auth == f"Bearer {SECRET}"
    assert log == {
        "call_id": call,
        "business": 7,
        "kind": "call_link",
        "started_at": "2026-10-17T07:30:05.123456Z",
        "events": logged,
    }
    validator: Any = Draft202012Validator(LOG_SCHEMA)
    assert list(validator.iter_errors(log)) == []
    assert call not in report.EVENTS  # taken out at the call's end, not kept


def test_a_hung_up_call_keeps_its_end_line_and_ends_at_once_while_the_portal_hangs() -> (
    None
):
    """The Caller hangs up (the runner is cancelled, as the web Channel does) while the Portal answers nothing."""
    call = "deadbeef01234567"
    seen: list[Any] = []
    hold = threading.Event()
    with fake_portal([], seen, hold) as portal, log_lines() as lines:
        env = portal_env(portal)

        async def a_call_is_hung_up() -> float:
            worker = PipelineWorker(Pipeline([BargeInRecorder(call)]))
            runner = WorkerRunner()
            await runner.add_workers(worker)

            async def hang_up() -> None:
                await asyncio.sleep(0.2)
                await runner.cancel()

            caller = asyncio.create_task(hang_up())
            await runner.run()
            await caller
            began = time.monotonic()
            report_call(call, TICKET, STARTED, 1, TOTALS, env)
            took = time.monotonic() - began
            await asyncio.sleep(0.2)
            hold.set()
            await asyncio.gather(*report.sending)
            return took

        took = asyncio.run(a_call_is_hung_up())
    assert took < 0.1
    logged = [
        json.loads(line.removeprefix("barge-in "))
        for line in lines
        if line.startswith("barge-in ")
    ]
    assert [e["e"] for e in logged] == ["config", "end"]
    assert logged[-1]["reason"] == "cancel"
    [(_, _, log)] = [s for s in seen if s[0] == "/api/call-logs/"]
    assert log["events"] == logged


def test_a_call_log_the_portal_never_takes_is_given_up_and_said() -> None:
    with fake_portal([], []) as portal:
        pass  # nothing listens here any more
    with log_lines() as lines:
        assert (
            post(
                "/api/call-logs/",
                {"call_id": "c0ffee0123456789"},
                "Call log",
                portal_env(portal),
                window_s=0.2,
                pause_s=0.05,
            )
            is False
        )
    assert "gave up sending the Call log" in lines[-1]
