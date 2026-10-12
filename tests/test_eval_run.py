"""Seam 1 without spend: a cap already reached stops `make eval` before anything is played."""

import json
from datetime import UTC, datetime
from pathlib import Path

from evals.run import main
from evals.spend import Caps


def test_a_reached_day_cap_stops_with_exit_3_before_any_spend(tmp_path: Path) -> None:
    entry = {
        "ts": datetime.now(UTC).isoformat(),
        "run": "earlier",
        "loop": "",
        "sek": 0.5,
    }
    (tmp_path / "ledger.jsonl").write_text(json.dumps(entry) + "\n", "utf-8")
    caps = Caps(per_run_sek=10, per_loop_sek=30, per_day_sek=0.5)

    assert main(None, runs=tmp_path, caps=caps) == 3
    assert (
        not (tmp_path / "ledger.jsonl").read_text("utf-8").count("\n") > 1
    )  # nothing new was spent


def test_an_unknown_scenario_is_refused(tmp_path: Path) -> None:
    assert main("nope", runs=tmp_path) == 2
