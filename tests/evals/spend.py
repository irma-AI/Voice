"""Spend caps. Read only from caps.json: no flag or env var raises them (CLAUDE.md § Stop and ask)."""

import json
from dataclasses import dataclass
from pathlib import Path

CAPS_FILE = Path(__file__).parent / "caps.json"


@dataclass(frozen=True)
class Caps:
    per_run_sek: float
    per_loop_sek: float
    per_day_sek: float
    per_scenario_sek: (
        float  # the least a batch prices each Scenario at, before it starts
    )

    @classmethod
    def load(cls, path: Path = CAPS_FILE) -> "Caps":
        data = json.loads(path.read_text("utf-8"))
        return cls(
            data["per_run_sek"],
            data["per_loop_sek"],
            data["per_day_sek"],
            data["per_scenario_sek"],
        )


def stopped_by(caps: Caps, *, run: float, loop: float, day: float) -> str | None:
    """Which cap the spend so far has reached (the running totals include this run), or None."""
    if run >= caps.per_run_sek:
        return f"run cap {caps.per_run_sek} SEK"
    if loop >= caps.per_loop_sek:
        return f"loop cap {caps.per_loop_sek} SEK"
    if day >= caps.per_day_sek:
        return f"day cap {caps.per_day_sek} SEK"
    return None
