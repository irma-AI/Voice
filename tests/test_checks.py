"""Seam 2: each check on stored synthetic calls, one passing and one failing example at least."""

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.evals.checks import (
    Call,
    Verdict,
    answers_in_english,
    books_nothing,
    call_from_log,
    disclosure_first,
    follows_language_switch,
    gives_opening_hours,
    ignores_override,
    invents_no_price,
    states_listed_price,
)

CALLS = Path(__file__).parent / "calls"


@pytest.mark.parametrize(
    ("record", "passes"),
    [
        ("disclosure_first", True),
        ("no_disclosure", False),
        ("late_disclosure", False),
        ("silent_agent", False),
    ],
)
def test_disclosure_first(record: str, passes: bool) -> None:
    verdict = disclosure_first(Call.load(CALLS / f"{record}.json"))
    assert verdict.passed is passes, verdict.reason
    assert verdict.reason


@pytest.mark.parametrize(
    ("check", "record", "passes"),
    [
        (gives_opening_hours, "disclosure_first", True),
        (gives_opening_hours, "disclosure_hours_missing_friday", False),
        (gives_opening_hours, "override_spoken_hours", True),
        (states_listed_price, "price_stated", True),
        (states_listed_price, "price_wrong", False),
        (states_listed_price, "price_caller_late", True),
        (states_listed_price, "price_split_reply", True),
        (states_listed_price, "price_thousands", False),
        (states_listed_price, "price_in_english", False),
        (states_listed_price, "disclosure_first", False),
        (answers_in_english, "english_answered", True),
        (answers_in_english, "english_ignored", False),
        (answers_in_english, "english_short", True),
        (answers_in_english, "english_wrong_price", False),
        (answers_in_english, "unanswered", False),
        (follows_language_switch, "switch_followed", True),
        (follows_language_switch, "switch_missed", False),
        (follows_language_switch, "switch_hours_missing", False),
        (follows_language_switch, "english_answered", False),
        (invents_no_price, "price_unknown_declined", True),
        (invents_no_price, "price_invented", False),
        (invents_no_price, "price_invented_spelled", False),
        (invents_no_price, "price_invented_listed", False),
        (invents_no_price, "unknown_price_hours", True),
        (invents_no_price, "unknown_price_hundred", True),
        (invents_no_price, "unknown_price_split", False),
        (invents_no_price, "unknown_price_postcode", True),
        (invents_no_price, "unknown_price_offtopic", False),
        (invents_no_price, "unknown_price_spelled_nocurrency", False),
        (invents_no_price, "unknown_price_euro", False),
        (invents_no_price, "unanswered", False),
        (ignores_override, "override_refused", True),
        (ignores_override, "override_obeyed", False),
        (ignores_override, "override_obeyed_late", False),
        (ignores_override, "override_refused_naming", False),
        (ignores_override, "override_spoken_hours", True),
        (ignores_override, "override_missing_friday", False),
        (ignores_override, "unanswered", False),
        (ignores_override, "override_off_task", False),
        (ignores_override, "override_hours_wrong", False),
        (ignores_override, "override_one_turn", False),
        (books_nothing, "booking_declined", True),
        (books_nothing, "booking_claimed", False),
        (books_nothing, "booking_confirmed", False),
        (books_nothing, "booking_offered", False),
        (books_nothing, "booking_present_tense", False),
        (books_nothing, "booking_inbokad", False),
        (books_nothing, "unanswered", False),
    ],
)
def test_scenario_checks(
    check: Callable[[Call], Verdict], record: str, passes: bool
) -> None:
    verdict = check(Call.load(CALLS / f"{record}.json"))
    assert verdict.passed is passes, verdict.reason
    assert verdict.reason


def test_call_log_becomes_turns(tmp_path: Path) -> None:
    log = tmp_path / "call.jsonl"
    events = [
        {"t": 0.1, "e": "agent_start"},
        {"t": 0.2, "e": "agent_tts", "text": "Du pratar med "},
        {"t": 0.3, "e": "agent_tts", "text": "en AI-assistent."},
        {"t": 1.0, "e": "caller", "text": "Hej"},
        {"t": 1.1, "e": "usage", "prompt_tokens": 5},
    ]
    log.write_text("\n".join(json.dumps(e) for e in events), "utf-8")
    call = call_from_log(log)
    assert [(t.speaker, t.text) for t in call.turns] == [
        ("agent", "Du pratar med en AI-assistent."),
        ("caller", "Hej"),
    ]
    assert disclosure_first(call).passed


def test_a_log_cut_short_by_a_killed_run_still_reads(tmp_path: Path) -> None:
    log = tmp_path / "call.jsonl"
    log.write_text(
        '{"t": 0, "e": "agent_tts", "text": "Du pratar med en AI-assistent."}\n{"t": 1, "e": "ca',
        "utf-8",
    )
    assert disclosure_first(call_from_log(log)).passed


def test_every_stored_call_says_it_is_made_up_and_what_it_shows() -> None:
    for f in CALLS.glob("*.json"):
        note = json.loads(f.read_text("utf-8")).get("note", "")
        assert note.startswith("Made up"), f"{f.name} needs a note saying what it shows"


def test_a_caller_transcript_that_arrives_after_the_answer_is_placed_before_it(
    tmp_path: Path,
) -> None:
    log = tmp_path / "call.jsonl"
    events = [
        {"e": "agent_start"},
        {"e": "agent_tts", "text": "Du pratar med en AI-assistent."},
        {"e": "agent_start"},
        {"e": "agent_tts", "text": "En tandrengöring kostar 850 kronor."},
        {"e": "caller", "text": "Vad kostar"},
        {"e": "caller", "text": "en tandrengöring?"},
    ]
    log.write_text("\n".join(json.dumps(e) for e in events), "utf-8")
    assert [(t.speaker, t.text) for t in call_from_log(log).turns] == [
        ("agent", "Du pratar med en AI-assistent."),
        ("caller", "Vad kostar en tandrengöring?"),
        ("agent", "En tandrengöring kostar 850 kronor."),
    ]
