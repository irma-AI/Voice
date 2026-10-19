"""Seam 2: each check on stored synthetic calls, one passing and one failing example at least."""

import asyncio
import json
from collections.abc import Callable
from pathlib import Path

import pytest
from pipecat.frames.frames import FunctionCallInProgressFrame
from pipecat.processors.frame_processor import FrameDirection
from pipecat.tests.utils import run_test

from tests.evals.checks import (
    Call,
    Verdict,
    agent_cut_off,
    agent_not_cut_off,
    answers_in_english,
    books_nothing,
    call_from_log,
    disclosure_first,
    events_from_record,
    false_barge_ins,
    follows_language_switch,
    gives_module_hours,
    gives_opening_hours,
    ignores_override,
    ignores_result_instruction,
    invents_no_price,
    read_events,
    states_listed_price,
    uses_web_search,
)
from voice.record import CallRecorder

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
        (books_nothing, "booking_laid_in", False),
        (books_nothing, "booking_noted", False),
        (books_nothing, "booking_declined_confirm", True),
        (books_nothing, "booking_declined_goes_not", True),
        (books_nothing, "booking_inbokad", False),
        (books_nothing, "unanswered", False),
        (gives_module_hours, "module_hours_used", True),
        (gives_module_hours, "module_hours_not_called", False),
        (gives_module_hours, "module_hours_wrong_tool", False),
        (gives_module_hours, "module_hours_wrong_times", False),
        (gives_module_hours, "unanswered", False),
        (ignores_result_instruction, "module_injection_ignored", True),
        (ignores_result_instruction, "module_injection_obeyed", False),
        (ignores_result_instruction, "module_injection_obeyed_no_hours", False),
        (ignores_result_instruction, "module_injection_obeyed_inflected", False),
        (ignores_result_instruction, "module_injection_obeyed_greeting", False),
        (ignores_result_instruction, "module_hours_not_called", False),
        (ignores_result_instruction, "unanswered", False),
        (uses_web_search, "module_web_used", True),
        (uses_web_search, "module_web_not_called", False),
        (uses_web_search, "module_web_wrong_tool", False),
        (uses_web_search, "module_web_wrong_figure", False),
        (uses_web_search, "unanswered", False),
    ],
)
def test_scenario_checks(
    check: Callable[[Call], Verdict], record: str, passes: bool
) -> None:
    verdict = check(Call.load(CALLS / f"{record}.json"))
    assert verdict.passed is passes, verdict.reason
    assert verdict.reason


@pytest.mark.parametrize(
    ("record", "passes"),
    [
        ("words_follow", True),
        ("noise_only", False),
        ("loud_no_words", True),
        ("agent_silent", True),
        ("words_too_late", False),
    ],
)
def test_false_barge_ins(record: str, passes: bool) -> None:
    verdict = false_barge_ins(events_from_record(CALLS / f"barge_in_{record}.json"))
    assert verdict.passed is passes, verdict.reason
    assert verdict.reason


@pytest.mark.parametrize(
    ("check", "record", "passes"),
    [
        (agent_not_cut_off, "none", True),
        (agent_not_cut_off, "short_reply", False),
        (agent_not_cut_off, "agent_silent", False),
        (agent_not_cut_off, "noise_only", False),
        (agent_not_cut_off, "loud_no_words", False),
        (agent_cut_off, "words_follow", True),
        (agent_cut_off, "noise_only", True),
        (agent_cut_off, "none", False),
        (agent_cut_off, "agent_silent", False),
    ],
)
def test_cut_off_checks(
    check: Callable[[Call], Verdict], record: str, passes: bool
) -> None:
    verdict = check(Call.load(CALLS / f"barge_in_{record}.json"))
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


def test_the_recorder_writes_a_tool_call_by_name_and_never_its_arguments(
    tmp_path: Path,
) -> None:
    log = tmp_path / "call.jsonl"
    call = FunctionCallInProgressFrame(
        function_name="opening_hours",
        tool_call_id="t1",
        arguments={"phone": "+46700000000"},
    )
    asyncio.run(run_test(CallRecorder(log), frames_to_send=[call]))
    assert [e["name"] for e in read_events(log) if e["e"] == "tool_call"] == [
        "opening_hours"
    ]
    assert "46700000000" not in log.read_text("utf-8")
    # The model service broadcasts the frame both ways; only the downstream copy is a record.
    upstream = tmp_path / "up.jsonl"
    asyncio.run(
        run_test(
            CallRecorder(upstream),
            frames_to_send=[call],
            frames_to_send_direction=FrameDirection.UPSTREAM,
        )
    )
    assert not [e for e in read_events(upstream) if e["e"] == "tool_call"]
