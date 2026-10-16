"""Seam 1 without spend: a cap already reached stops `make eval` before anything is played."""

import json
import re
from datetime import UTC, datetime
from pathlib import Path

from tests.evals.checks import Verdict
from tests.evals.render_audio import LINES
from tests.evals.run import (
    MAX_REPEATS,
    ROOT,
    SCENARIOS,
    Row,
    main,
    missing_audio,
    plan,
    report,
)
from tests.evals.spend import Caps


def test_a_reached_day_cap_stops_with_exit_3_before_any_spend(tmp_path: Path) -> None:
    entry = {
        "ts": datetime.now(UTC).isoformat(),
        "run": "earlier",
        "loop": "",
        "sek": 0.5,
    }
    (tmp_path / "ledger.jsonl").write_text(json.dumps(entry) + "\n", "utf-8")
    caps = Caps(per_run_sek=10, per_loop_sek=30, per_day_sek=0.5)

    assert main("disclosure_first", runs=tmp_path, caps=caps) == 3
    assert (
        not (tmp_path / "ledger.jsonl").read_text("utf-8").count("\n") > 1
    )  # nothing new was spent


def test_an_unknown_scenario_is_refused(tmp_path: Path) -> None:
    assert main("nope", runs=tmp_path) == 2


def test_x_n_plays_one_scenario_n_times_on_separate_calls(tmp_path: Path) -> None:
    pairs = plan("module_hours_x3")
    assert pairs == [(f"module_hours_{i}", "module_hours") for i in (1, 2, 3)]
    assert plan("module_hours") == [("module_hours", "module_hours")]
    for bad in ("nope_x3", "module_hours_x1", f"module_hours_x{MAX_REPEATS + 1}"):
        assert plan(bad) is None
        assert main(bad, runs=tmp_path) == 2


def test_the_table_and_exit_code_follow_the_verdicts(tmp_path: Path) -> None:
    ok, bad = Verdict(True, "ok"), Verdict(False, "no")
    assert report([Row("a", {"c": ok}, 0.5, 100, 1.2)], tmp_path, 0.5, None, 0) == 0
    assert report([Row("a", {"c": bad}, 0.5, 100, None)], tmp_path, 0.5, None, 0) == 1
    assert report([], tmp_path, 10, "run cap 10 SEK", 1) == 3


def test_every_scenario_is_in_the_runner_the_manifest_and_the_audio_list() -> None:
    evals = ROOT / "tests" / "evals"
    files = {p.stem for p in (evals / "scenarios").glob("*.yaml")}
    manifest = (evals / "manifest.yaml").read_text("utf-8")
    listed = re.search(r"scenarios: \[(.*)\]", manifest)
    assert listed
    assert set(SCENARIOS) == files == set(re.split(r",\s*", listed.group(1)))
    for f in files:
        yaml = (evals / "scenarios" / f"{f}.yaml").read_text("utf-8")
        for audio in re.findall(r"audio: \.\./audio/(\w+)\.wav", yaml):
            licence = evals / "audio" / f"{audio}.licence.md"
            assert audio in LINES or licence.exists(), (
                f"{f} plays {audio}: make eval-audio does not render it and {licence.name} is missing"
            )


def test_missing_audio_is_found_before_any_scenario_is_played(tmp_path: Path) -> None:
    (tmp_path / "a.yaml").write_text(
        "turns:\n  - user: hej\n    audio: ../audio/x.wav\n", "utf-8"
    )
    assert missing_audio(["a"], tmp_path) == "../audio/x.wav"
    (tmp_path.parent / "audio").mkdir(exist_ok=True)
    (tmp_path.parent / "audio" / "x.wav").write_bytes(b"")
    assert missing_audio(["a"], tmp_path) is None
