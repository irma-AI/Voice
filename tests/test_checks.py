"""Seam 2: each check on stored synthetic calls, one passing and one failing example at least."""

import json
from pathlib import Path

import pytest

from evals.checks import Call, call_from_log, disclosure_first

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
