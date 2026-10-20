"""Seam 1 without spend: a cap already reached stops `make eval` before anything is played."""

import io
import json
import re
import wave
from datetime import UTC, datetime
from pathlib import Path

from pipecat.evals.scenario import EvalScenarioFile
from pipecat.evals.script import EvalScriptScenario

from tests.evals.checks import (
    HOSTILE_BUSINESS_FILE,
    MODULE_BUSINESS_FILE,
    WEB_BUSINESS_FILE,
    Verdict,
)
from tests.evals.render_audio import LINES, frames
from tests.evals.run import (
    MAX_REPEATS,
    PARALLEL,
    ROOT,
    SCENARIOS,
    SETTINGS_FILES,
    Row,
    batch_at,
    batch_stop,
    main,
    missing_audio,
    module_log,
    never_reached,
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
    caps = Caps(per_run_sek=10, per_loop_sek=30, per_day_sek=0.5, per_scenario_sek=0.5)

    assert main("swedish_question", runs=tmp_path, caps=caps) == 3
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


def test_the_module_scenarios_each_play_their_own_business() -> None:
    # the hostile and the plain Module answer the same Action name, so only the Business file tells them apart
    assert SETTINGS_FILES == {
        "module_hours": MODULE_BUSINESS_FILE,
        "module_injection": HOSTILE_BUSINESS_FILE,
        "module_web": WEB_BUSINESS_FILE,
    }
    assert "example_hostile" in HOSTILE_BUSINESS_FILE.read_text("utf-8")
    assert "example_hostile" not in MODULE_BUSINESS_FILE.read_text("utf-8")


def test_the_module_scenarios_end_on_the_speech_after_the_tool_result() -> None:
    # A holding line before the Action is speech too: stopping on its end would cut off the answer (VOI-206).
    for sc in SETTINGS_FILES:
        path = ROOT / "tests" / "evals" / "scenarios" / f"{sc}.yaml"
        (scenario,) = EvalScenarioFile.load(path).scenarios
        assert isinstance(scenario, EvalScriptScenario)
        last = [e.event for e in scenario.turns[-1].expect]
        assert last == [
            "function_call_stopped",
            "bot_started_speaking",
            "bot_stopped_speaking",
        ], f"{sc}'s last turn must wait for the tool result, then the speech after it"


def test_missing_audio_is_found_before_any_scenario_is_played(tmp_path: Path) -> None:
    (tmp_path / "a.yaml").write_text(
        "turns:\n  - user: hej\n    audio: ../audio/x.wav\n", "utf-8"
    )
    assert missing_audio(["a"], tmp_path) == "../audio/x.wav"
    (tmp_path.parent / "audio").mkdir(exist_ok=True)
    (tmp_path.parent / "audio" / "x.wav").write_bytes(b"")
    assert missing_audio(["a"], tmp_path) is None


def test_a_module_line_in_the_bot_log_is_found(tmp_path: Path) -> None:
    logs = tmp_path / "module_hours_1" / "deeper"
    logs.mkdir(parents=True)
    (logs / "bot.log").write_text(
        "ok\nModule 'hours' skipped: TimeoutError\nok\n", "utf-8"
    )
    assert module_log(tmp_path, "module_hours_1") == [
        "Module 'hours' skipped: TimeoutError"
    ]
    assert module_log(tmp_path, "module_hours_2") == []


def test_the_first_scenario_plays_alone_then_parallel_at_a_time() -> None:
    pairs = plan(None)
    assert pairs
    got = [b for i in range(len(pairs)) if (b := batch_at(pairs, i)) is not None]
    assert got[0] == pairs[:1]
    assert all(len(b) <= PARALLEL for b in got)
    assert [p for b in got for p in b] == pairs  # every Scenario once, in order


def test_a_batch_starts_only_if_its_worst_case_fits_under_the_caps(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / "ledger.jsonl"
    entry = {"ts": "2026-10-19T08:00:00+00:00", "run": "earlier", "loop": ""}
    caps = Caps(per_run_sek=2, per_loop_sek=30, per_day_sek=50, per_scenario_sek=0.5)
    # each Scenario is priced at the per-Scenario bound when no ledgered call cost more
    ledger.write_text(json.dumps({**entry, "sek": 0.2}) + "\n", "utf-8")
    assert batch_stop(caps, tmp_path, 0.5, 3, "", "2026-10-20") == "run cap 2 SEK"
    assert batch_stop(caps, tmp_path, 0.5, 2, "", "2026-10-20") is None
    # and at the dearest ledgered call when one cost more than the bound
    ledger.write_text(json.dumps({**entry, "sek": 0.8}) + "\n", "utf-8")
    assert batch_stop(caps, tmp_path, 0.5, 2, "", "2026-10-20") == "run cap 2 SEK"
    # an empty ledger still prices the first Scenario at the bound
    ledger.unlink()
    assert batch_stop(caps, tmp_path, 1.6, 1, "", "2026-10-20") == "run cap 2 SEK"


def test_a_tts_reply_that_is_already_a_wav_keeps_only_its_frames() -> None:
    pcm = b"\x01\x00" * 240
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(pcm)
    assert frames(buf.getvalue()) == pcm  # no second header played as sound
    assert frames(pcm) == pcm  # bare PCM passes through


def test_a_call_that_never_reached_the_agent_is_named(tmp_path: Path) -> None:
    # main() stops the run on this after the first Scenario, so a broken harness spends nothing more
    log = tmp_path / "call.jsonl"
    assert never_reached(log) == "no call record"
    log.write_text('{"e": "usage", "prompt_tokens": 0}\n', "utf-8")
    assert never_reached(log) == "no agent turn in the call record"
    log.write_text(
        '{"e": "caller", "text": "hej"}\n{"e": "agent_llm", "text": "Hej!"}\n', "utf-8"
    )
    assert never_reached(log) is None
