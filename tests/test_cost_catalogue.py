"""Seam 2: the cost of a call from Google's price catalogue, free. A real server on localhost stands in for Google, and a stored sample catalogue reply (tests/catalogue/sample_skus.json) is what it answers.

Nothing of ours is mocked. The catalogue's price date and entry names are the sample's.
"""

import json
import threading
import time
from collections.abc import Generator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from loguru import logger

from voice import cost
from voice.cost import MODEL, CostReason, price, token_kinds

SAMPLE: dict[str, Any] = json.loads(
    (Path(__file__).parent / "catalogue/sample_skus.json").read_text()
)
KEY = "k3y-not-in-any-log"
TOTALS = {
    "prompt_tokens": 1200,
    "completion_tokens": 340,
    "input_audio_tokens": 1000,
    "output_audio_tokens": 300,
    "thinking_tokens": 10,
    "cached_tokens": 800,
}
# 1000 audio in at $3/M, 200 text in at $0.75/M, 300 audio out at $12/M, 40 + 10 thinking text out at $4.5/M.
COST = "0.00697500"


@pytest.fixture(autouse=True)
def fresh_catalogue() -> None:
    cost._kept = None  # pyright: ignore[reportPrivateUsage]


@contextmanager
def google(
    pages: list[Any] | None = None, status: int = 200
) -> Generator[tuple[str, list[dict[str, list[str]]]]]:
    """A real server answering the catalogue address with each page of `pages` (a dict, or raw bytes) in turn. Every request's query goes into the second value."""
    pages = pages if pages is not None else [SAMPLE]
    seen: list[dict[str, list[str]]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            seen.append(parse_qs(urlsplit(self.path).query))
            page = pages[min(len(seen), len(pages)) - 1]
            body = page if isinstance(page, bytes) else json.dumps(page).encode()
            self.send_response(status)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return None

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", seen
    finally:
        server.shutdown()
        server.server_close()


def split_in_two() -> list[dict[str, Any]]:
    half = len(SAMPLE["skus"]) // 2
    return [
        {"skus": SAMPLE["skus"][:half], "nextPageToken": "p2"},
        {"skus": SAMPLE["skus"][half:]},
    ]


def the_cost(base: str, totals: dict[str, int] = TOTALS) -> dict[str, str | None]:
    return price(totals, MODEL, KEY, base)


def test_tokens_are_split_by_kind() -> None:
    assert token_kinds(TOTALS) == {
        ("input", "audio"): 1000,
        ("input", "text"): 200,
        ("output", "audio"): 300,
        ("output", "text"): 50,
    }


def test_the_cost_is_worked_out_by_token_kind_from_the_catalogue() -> None:
    with google(split_in_two()) as (base, seen):
        # The newest matched price is 2026-10-01 (audio out); the page the key rides on is asked for in dollars.
        assert the_cost(base) == {
            "cost_usd": COST,
            "price_date": "2026-10-01",
            "cost_reason": None,
        }
    assert [q.get("pageToken") for q in seen] == [None, ["p2"]]
    assert all(q["key"] == [KEY] and q["currencyCode"] == ["USD"] for q in seen)


def test_the_catalogue_is_kept_for_a_day() -> None:
    with google() as (base, seen):
        the_cost(base)
        the_cost(base)
        assert len(seen) == 1
        cost._kept = (time.monotonic() - cost.KEPT_FOR_S - 1, cost._kept[1])  # pyright: ignore[reportPrivateUsage,reportOptionalSubscript]
        the_cost(base)
        assert len(seen) == 2


def test_a_call_without_tokens_costs_zero_dollars() -> None:
    with google() as (base, _):
        zero = the_cost(base, dict.fromkeys(TOTALS, 0))
    assert zero["cost_usd"] == "0.00000000" and zero["cost_reason"] is None


def without(kind_words: str) -> dict[str, Any]:
    return {"skus": [s for s in SAMPLE["skus"] if kind_words not in s["description"]]}


def twice(kind_words: str) -> dict[str, Any]:
    dup = [s for s in SAMPLE["skus"] if kind_words in s["description"]]
    return {"skus": [*SAMPLE["skus"], *dup]}


def flat_tiers() -> dict[str, Any]:
    tiers = json.loads(json.dumps(SAMPLE))
    rates = tiers["skus"][1]["pricingInfo"][0]["pricingExpression"]["tieredRates"]
    rates.append({**rates[0], "startUsageAmount": 100})
    return tiers


def reached(reason: CostReason) -> dict[str, str | None]:
    """Runs the one situation that gives this reason."""
    if reason is CostReason.NO_KEY:
        return price(TOTALS, MODEL, "")
    if reason is CostReason.UNREACHABLE:
        with google() as (base, _):
            pass  # closed again: nothing listens on this address
        return the_cost(base)
    if reason is CostReason.UNREADABLE:
        with google([b"<html>not a catalogue</html>"]) as (base, _):
            return the_cost(base)
    if reason is CostReason.NOT_MATCHED:
        with google([without("text output")]) as (base, _):
            return the_cost(base)
    if reason is CostReason.SHAPE_UNKNOWN:
        with google([flat_tiers()]) as (base, _):
            return the_cost(base)
    raise AssertionError(f"no situation for {reason}: add one in reached()")


@pytest.mark.parametrize("reason", list(CostReason))
def test_every_reason_gives_an_empty_cost_that_says_why(reason: CostReason) -> None:
    assert reached(reason) == {
        "cost_usd": None,
        "price_date": None,
        "cost_reason": reason.value,
    }


def test_reasons_are_codes_the_contract_accepts() -> None:
    pattern = json.loads(
        (Path(__file__).parents[1] / "contract/call-record.schema.json").read_text()
    )["properties"]["cost_reason"]["pattern"]
    import re

    assert all(re.fullmatch(pattern, r.value) for r in CostReason)


def test_an_answer_of_no_is_unreadable_and_two_matches_are_no_match() -> None:
    with google(status=403) as (base, _):
        assert the_cost(base)["cost_reason"] == "catalogue_unreadable"
    cost._kept = None  # pyright: ignore[reportPrivateUsage]
    with google([twice("audio output")]) as (base, _):
        assert the_cost(base)["cost_reason"] == "price_not_matched"


def test_the_log_names_the_entries_it_matched_and_never_the_key() -> None:
    lines: list[str] = []
    sink = logger.add(lambda m: lines.append(m.record["message"]), level="INFO")
    try:
        with google() as (base, _):
            the_cost(base)
        cost._kept = None  # pyright: ignore[reportPrivateUsage]
        with google(status=403) as (base, _):
            the_cost(base)
        with google([without("text output")]) as (base, _):
            cost._kept = None  # pyright: ignore[reportPrivateUsage]
            the_cost(base)
    finally:
        logger.remove(sink)
    assert any(
        l.startswith("price match: ['Gemini 3.8 Live audio input tokens'")
        for l in lines
    )
    assert any(
        "entries naming live" in l and "Gemini 3.8 Live video input" in l for l in lines
    )
    assert KEY not in "".join(lines)


def test_the_security_rule_lists_the_price_log_lines() -> None:
    rule = (Path(__file__).parents[1] / ".claude/rules/security.md").read_text()
    for line in ("price match", "price catalogue"):
        assert f"`{line}`" in rule, (
            f"add `{line}` to the Call record line in .claude/rules/security.md"
        )
