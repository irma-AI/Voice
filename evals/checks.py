"""The checks: pure functions from a call record to a verdict. No model, no network, no spend."""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from voice.agent import DISCLOSURE


@dataclass(frozen=True)
class Turn:
    speaker: Literal["caller", "agent"]
    text: str


@dataclass(frozen=True)
class Call:
    """What was said on one call, in order."""

    turns: tuple[Turn, ...]

    @classmethod
    def load(cls, path: Path) -> "Call":
        data = json.loads(path.read_text("utf-8"))
        return cls(tuple(Turn(t["speaker"], t["text"]) for t in data["turns"]))


@dataclass(frozen=True)
class Verdict:
    passed: bool
    reason: str


def _words(text: str) -> str:
    return " ".join(re.findall(r"\w+", text.lower()))


def disclosure_first(call: Call) -> Verdict:
    """The first thing said on the call is the approved disclosure line."""
    if not call.turns or call.turns[0].speaker != "agent":
        return Verdict(False, "the agent did not speak first")
    first = call.turns[0].text
    if _words(first).startswith(_words(DISCLOSURE)):
        return Verdict(True, "the first turn starts with the disclosure")
    return Verdict(
        False, f"the first turn does not start with the disclosure: {first!r}"
    )


def call_from_log(path: Path) -> Call:
    """Builds the call record from the JSONL the agent wrote (voice/record.py).

    Caller pieces join into one turn until an agent response starts; agent pieces join into one
    turn per response. Agent text comes from the speech events when there are any, else the model's.
    """
    events = [json.loads(line) for line in path.read_text("utf-8").splitlines() if line]
    agent_kind = (
        "agent_tts" if any(e["e"] == "agent_tts" for e in events) else "agent_llm"
    )
    turns: list[Turn] = []
    new_agent_turn = True
    for e in events:
        if e["e"] == "agent_start":
            new_agent_turn = True
        elif e["e"] == "caller":
            if turns and turns[-1].speaker == "caller":
                turns[-1] = Turn("caller", f"{turns[-1].text} {e['text']}".strip())
            else:
                turns.append(Turn("caller", e["text"].strip()))
        elif e["e"] == agent_kind:
            if new_agent_turn or not turns or turns[-1].speaker != "agent":
                turns.append(Turn("agent", e["text"]))
                new_agent_turn = False
            else:
                turns[-1] = Turn("agent", turns[-1].text + e["text"])
    return Call(tuple(turns))
