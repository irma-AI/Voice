"""Seam 2: the cost of a call from Google's price catalogue, free. A real server on localhost stands in for Google, and stored sample replies (tests/catalogue/) are what it answers.

Nothing of ours is mocked. The catalogue's entry names and prices are the samples'.
"""

import json
import re
import threading
import time
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from loguru import logger

from voice import cost
from voice.cost import MODEL, CostReason, price, token_kinds

ROOT = Path(__file__).parents[1]
SKUS: list[dict[str, Any]] = json.loads(
    (ROOT / "tests/catalogue/sample_skus.json").read_text()
)["skus"]
PRICES: dict[str, Any] = json.loads(
    (ROOT / "tests/catalogue/sample_prices.json").read_text()
)["prices"]
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
# A stored copy of the official rates with synthetic numbers (the real copy is voice/prices.json): 1000 x $2 + 200 x $1 + 300 x $8 + 50 x $4 per M.
STORED = ROOT / "tests/cost/synthetic_prices.json"
STORED_COST = "0.00480000"


@pytest.fixture(autouse=True)
def fresh_catalogue() -> None:
    cost._kept = None  # pyright: ignore[reportPrivateUsage]


@contextmanager
def google(
    skus: list[Any] | None = None,
    prices: dict[str, Any] | None = None,
    status: int = 200,
    body: bytes | None = None,
) -> Generator[tuple[str, list[tuple[str, dict[str, list[str]]]]]]:
    """A real server: the SKU list answers with each page of `skus` in turn (a list of entries per page), a price with `prices[skuId]`.

    `status` and `body` replace every answer. Every request's path and query goes into the second value.
    """
    pages = skus if skus is not None else [SKUS]
    sold = prices if prices is not None else PRICES
    seen: list[tuple[str, dict[str, list[str]]]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            url = urlsplit(self.path)
            seen.append((url.path, parse_qs(url.query)))
            if body is not None:
                answer = body
            elif url.path == "/v2beta/skus":
                number = sum(p == "/v2beta/skus" for p, _ in seen)
                page: dict[str, Any] = {"skus": pages[min(number, len(pages)) - 1]}
                if number < len(pages):
                    page["nextPageToken"] = f"p{number + 1}"
                answer = json.dumps(page).encode()
            else:
                match = re.fullmatch(r"/v1beta/skus/([A-Z0-9-]+)/price", url.path)
                answer = json.dumps(sold[match.group(1)] if match else {}).encode()
            self.send_response(status)
            self.end_headers()
            self.wfile.write(answer)

        def log_message(self, format: str, *args: object) -> None:
            return None

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", seen
    finally:
        server.shutdown()
        server.server_close()


def the_cost(base: str, totals: dict[str, int] = TOTALS) -> dict[str, str | None]:
    """The live catalogue alone: no stored copy to fall back on."""
    return price(totals, MODEL, KEY, base, stored=None)


def without(words: str) -> list[Any]:
    return [[s for s in SKUS if words not in s["displayName"]]]


def test_tokens_are_split_by_kind() -> None:
    assert token_kinds(TOTALS) == {
        ("input", "audio"): 1000,
        ("input", "text"): 200,
        ("output", "audio"): 300,
        ("output", "text"): 50,
    }


def test_the_cost_is_worked_out_by_token_kind_from_the_catalogue() -> None:
    half = len(SKUS) // 2
    with google([SKUS[:half], SKUS[half:]]) as (base, seen):
        assert the_cost(base) == {
            "cost_usd": COST,
            "price_date": datetime.now(UTC).date().isoformat(),
            "cost_reason": None,
        }
    listed = [q for p, q in seen if p == "/v2beta/skus"]
    assert [q.get("pageToken") for q in listed] == [None, ["p2"]]
    assert all(q["filter"] == [f'service="{cost.GEMINI_SERVICE}"'] for q in listed)
    priced = [(p, q) for p, q in seen if p != "/v2beta/skus"]
    assert sorted(p for p, _ in priced) == [
        f"/v1beta/skus/AAAA-000{n}/price" for n in (2, 3, 5, 6)
    ]
    assert all(q["currencyCode"] == ["USD"] for _, q in priced)
    assert all(q["key"] == [KEY] for _, q in seen)


def test_the_prices_are_kept_for_a_day() -> None:
    with google() as (base, seen):
        the_cost(base)
        assert len(seen) == 5
        the_cost(base)
        assert len(seen) == 5
        kept = cost._kept  # pyright: ignore[reportPrivateUsage]
        assert kept
        cost._kept = (time.monotonic() - cost.KEPT_FOR_S - 1, *kept[1:])  # pyright: ignore[reportPrivateUsage]
        the_cost(base)
        assert len(seen) == 10


def test_a_call_without_tokens_costs_zero_dollars() -> None:
    with google() as (base, _):
        zero = the_cost(base, dict.fromkeys(TOTALS, 0))
    assert zero["cost_usd"] == "0.00000000" and zero["cost_reason"] is None


def two_tiers() -> dict[str, Any]:
    tiered = json.loads(json.dumps(PRICES))
    rate = tiered["AAAA-0002"]["rate"]
    rate["tiers"].append({**rate["tiers"][0]})
    return tiered


def reached(reason: CostReason, stored: Path | None = None) -> dict[str, str | None]:
    """Runs the one situation that gives this reason, falling back on `stored` if given."""
    if reason is CostReason.NO_KEY:
        return price(TOTALS, MODEL, "", stored=stored)
    if reason is CostReason.UNREACHABLE:
        with google() as (base, _):
            pass  # closed again: nothing listens on this address
        return price(TOTALS, MODEL, KEY, base, stored=stored)
    if reason is CostReason.UNREADABLE:
        with google(body=b"<html>not a catalogue</html>") as (base, _):
            return price(TOTALS, MODEL, KEY, base, stored=stored)
    if reason is CostReason.NOT_MATCHED:
        with google(without("text output")) as (base, _):
            return price(TOTALS, MODEL, KEY, base, stored=stored)
    if reason is CostReason.SHAPE_UNKNOWN:
        with google(prices=two_tiers()) as (base, _):
            return price(TOTALS, MODEL, KEY, base, stored=stored)
    raise AssertionError(f"no situation for {reason}: add one in reached()")


@pytest.mark.parametrize("reason", list(CostReason))
def test_every_reason_gives_an_empty_cost_that_says_why(reason: CostReason) -> None:
    assert reached(reason) == {
        "cost_usd": None,
        "price_date": None,
        "cost_reason": reason.value,
    }


@pytest.mark.parametrize("reason", list(CostReason))
def test_a_failed_lookup_prices_the_tokens_at_the_stored_official_rates(
    reason: CostReason,
) -> None:
    """VOI-216: known tokens are priced exactly from the stored copy, dated by it, and the log says so."""
    lines: list[str] = []
    sink = logger.add(lambda m: lines.append(m.record["message"]), level="INFO")
    try:
        assert reached(reason, STORED) == {
            "cost_usd": STORED_COST,
            "price_date": "2026-01-01",
            "cost_reason": None,
        }
    finally:
        logger.remove(sink)
    assert (
        f"price catalogue failed ({reason.value}): priced from the stored rates of 2026-01-01"
        in lines
    )


@pytest.mark.parametrize(
    "reply",
    [
        {"body": b"[]"},
        {"skus": [[{k: v for k, v in s.items() if k != "skuId"} for s in SKUS]]},
        {"skus": [[{**s, "displayName": None} for s in SKUS]]},
    ],
    ids=["a list", "no skuId", "a null name"],
)
def test_a_catalogue_reply_of_the_wrong_shape_prices_from_the_stored_rates(
    reply: dict[str, Any],
) -> None:
    """VOI-228: a reply our parsing trips on must not lose the Call record."""
    with google(**reply) as (base, _):
        assert price(TOTALS, MODEL, KEY, base, stored=STORED) == {
            "cost_usd": STORED_COST,
            "price_date": "2026-01-01",
            "cost_reason": None,
        }
        assert the_cost(base)["cost_reason"] == "catalogue_unreadable"


def test_a_stored_copy_for_another_model_prices_nothing() -> None:
    assert price(TOTALS, "models/another-live", "", stored=STORED) == {
        "cost_usd": None,
        "price_date": None,
        "cost_reason": "no_billing_key",
    }


@pytest.mark.parametrize(
    "broken",
    [
        {"text_out": "n/a"},
        {"text_out": float("nan")},
        {"audio_in": -1.0},
        {"audio_in": 0.0},  # a zeroed kind would undercount every call
        {"as_of": "soon"},
    ],
)
def test_a_broken_stored_copy_leaves_the_cost_empty_with_the_reason(
    broken: dict[str, Any], tmp_path: Path
) -> None:
    copy = json.loads(STORED.read_text())
    if "as_of" in broken:
        copy.update(broken)
    else:
        copy["usd_per_million_tokens"].update(broken)
    bad = tmp_path / "prices.json"
    bad.write_text(json.dumps(copy))
    assert price(TOTALS, MODEL, "", stored=bad) == {
        "cost_usd": None,
        "price_date": None,
        "cost_reason": "no_billing_key",
    }


def test_the_stored_official_rates_are_for_the_model_the_core_runs() -> None:
    stored = json.loads(cost.STORED_PRICES.read_text())
    assert stored["model"] == MODEL, (
        f"voice/prices.json holds rates for {stored['model']}: copy Google's official rates for {MODEL} into it"
    )


def test_reasons_are_codes_the_contract_accepts() -> None:
    pattern = json.loads((ROOT / "contract/call-record.schema.json").read_text())[
        "properties"
    ]["cost_reason"]["pattern"]
    assert all(re.fullmatch(pattern, r.value) for r in CostReason)


def test_two_matching_entries_are_no_match() -> None:
    twice = [[*SKUS, *(s for s in SKUS if "audio output" in s["displayName"])]]
    with google(twice) as (base, _):
        assert the_cost(base)["cost_reason"] == "price_not_matched"


def test_the_log_says_what_google_said_and_what_matched_and_never_the_key() -> None:
    lines: list[str] = []
    sink = logger.add(lambda m: lines.append(m.record["message"]), level="INFO")
    refused = json.dumps(
        {
            "error": {
                "status": "UNAUTHENTICATED",
                "message": f"key {KEY} is no good",
                "details": [{"reason": "API_KEYS_NOT_SUPPORTED"}],
            }
        }
    ).encode()
    try:
        with google() as (base, _):
            the_cost(base)
        cost._kept = None  # pyright: ignore[reportPrivateUsage]
        with google(status=401, body=refused) as (base, _):
            assert the_cost(base)["cost_reason"] == "catalogue_unreadable"
        with google(without("text output")) as (base, _):
            the_cost(base)
    finally:
        logger.remove(sink)
    assert any(
        line.startswith(
            "price match: ['Bidi_generate_content audio input token count for gemini-3.8-live'"
        )
        for line in lines
    )
    assert (
        "price catalogue answered 401 UNAUTHENTICATED API_KEYS_NOT_SUPPORTED" in lines
    )
    assert any(
        "0 entries for output text" in line
        and "video input token count for gemini-3.8-live" in line
        for line in lines
    )
    assert KEY not in "".join(lines)


def test_the_security_rule_lists_the_price_log_lines() -> None:
    rule = (ROOT / ".claude/rules/security.md").read_text()
    record = next(l for l in rule.splitlines() if l.startswith("- The Call record log"))
    for line in ("price match", "price catalogue"):
        assert f"`{line}`" in record, (
            f"add `{line}` to the Call record line in .claude/rules/security.md"
        )
