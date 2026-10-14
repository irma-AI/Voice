"""`make eval`: runs each Scenario on the eval Channel, checks the call and prints a table.

Paid (every call spends Gemini credit), never automatic: an agent asks Petter before each run
(CLAUDE.md § Stop and ask), and only his PC or the manual Evals workflow runs it. Exit 0 all
passed, 1 a Scenario failed, 2 bad Scenario id, 3 a spend cap stopped the run.
"""

import json
import os
import re
import signal
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tests.evals.checks import (
    BUSINESS_FILE,
    Call,
    Verdict,
    agent_cut_off,
    agent_not_cut_off,
    answers_in_english,
    books_nothing,
    call_from_log,
    disclosure_first,
    follows_language_switch,
    gives_opening_hours,
    ignores_override,
    invents_no_price,
    read_events,
    states_listed_price,
)
from tests.evals.cost import cost_sek
from tests.evals.spend import Caps, stopped_by

ROOT = Path(__file__).parent.parent.parent
SCENARIO_TIMEOUT_S = (
    180  # a hard stop on one call's spend: the caps are only checked between Scenarios
)
SCENARIO_DIR = ROOT / "tests" / "evals" / "scenarios"
RUNS = ROOT / "eval-runs"  # git-ignored; also holds the spend ledger
# The disclosure is the legal line, so every call is checked for it, not one sample.
SCENARIOS: dict[str, list[Callable[[Call], Verdict]]] = {
    "disclosure_first": [disclosure_first, gives_opening_hours],
    "swedish_question": [disclosure_first, states_listed_price],
    "english_call": [disclosure_first, answers_in_english],
    "language_switch": [disclosure_first, follows_language_switch],
    "unknown_price": [disclosure_first, invents_no_price],
    "ignore_instructions": [disclosure_first, ignores_override],
    "booking_request": [disclosure_first, books_nothing],
    "noise_barge_in": [disclosure_first, agent_not_cut_off],
    "speech_barge_in": [disclosure_first, agent_cut_off],
}


@dataclass(frozen=True)
class Row:
    scenario: str
    verdicts: dict[str, Verdict]
    sek: float
    prompt_tokens: int
    first_reply_s: float | None


def _ledger(runs: Path) -> list[dict[str, Any]]:
    ledger = runs / "ledger.jsonl"
    if not ledger.exists():
        return []
    return [json.loads(line) for line in ledger.read_text("utf-8").splitlines() if line]


def _totals(runs: Path, run: float, loop_id: str, today: str) -> dict[str, float]:
    entries = _ledger(runs)
    return {
        "run": run,
        "loop": sum(e["sek"] for e in entries if loop_id and e["loop"] == loop_id)
        + run,
        "day": sum(e["sek"] for e in entries if e["ts"].startswith(today)) + run,
    }


def _play(scenario: str, run_dir: Path) -> tuple[int, Path]:
    """Runs one Scenario through Pipecat's eval suite; returns its exit code and the call log."""
    log = run_dir / "calls" / f"{scenario}.jsonl"
    cmd = [sys.executable, "-m", "pipecat.evals", "suite", "tests/evals/manifest.yaml"]
    cmd += ["-s", scenario, "--name", scenario, "--runs-dir", str(run_dir)]
    # Own process group: the suite spawns the bot, and killing only the suite would leave the
    # bot's Gemini session open and spending after the time limit.
    proc = subprocess.Popen(
        cmd,
        cwd=ROOT,
        # The eval Channel's settings source is chosen here, never inherited: the test Business, not a Portal.
        env={
            **os.environ,
            "VOICE_CALL_LOG": str(log),
            "SETTINGS_FILE": str(BUSINESS_FILE),
            "SETTINGS_URL": "",
        },
        start_new_session=True,
    )
    try:
        return proc.wait(timeout=SCENARIO_TIMEOUT_S), log
    except subprocess.TimeoutExpired:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], check=False)
        else:
            os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()
        return -1, log


def _record(runs: Path, now: datetime, run_id: str, loop_id: str, sek: float) -> None:
    runs.mkdir(parents=True, exist_ok=True)
    entry = {"ts": now.isoformat(), "run": run_id, "loop": loop_id, "sek": sek}
    with (runs / "ledger.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def missing_audio(ids: list[str], scenarios: Path = SCENARIO_DIR) -> str | None:
    """The first audio file the given Scenarios play that does not exist, if any."""
    for sc in ids:
        yaml = (scenarios / f"{sc}.yaml").read_text("utf-8")
        for rel in re.findall(r"^\s*audio:\s*(\S+)", yaml, re.MULTILINE):
            if not (scenarios / rel).resolve().exists():
                return rel
    return None


def main(only: str | None, runs: Path = RUNS, caps: Caps | None = None) -> int:
    ids = [only] if only else list(SCENARIOS)
    if unknown := [i for i in ids if i not in SCENARIOS]:
        print(f"unknown Scenario {unknown}; known: {list(SCENARIOS)}", file=sys.stderr)
        return 2
    # A missing audio file fails the harness before any spend; say so before the first Scenario
    # is played, not after it has been paid for.
    if missing := missing_audio(ids):
        print(
            f"missing Caller audio {missing}: run `make eval-audio` (asks Petter first)",
            file=sys.stderr,
        )
        return 2
    caps = caps or Caps.load()
    now = datetime.now(UTC)
    run_id, loop_id = (
        now.strftime("%Y%m%d-%H%M%S-%f"),
        os.environ.get("EVAL_LOOP_ID", ""),
    )
    run_dir = runs / run_id
    spent, rows, stopped = 0.0, list[Row](), None
    for sc in ids:
        # Fail closed: a cap already reached by earlier runs stops us before any spend.
        if stopped := stopped_by(
            caps, **_totals(runs, spent, loop_id, now.strftime("%Y-%m-%d"))
        ):
            break
        code, log = _play(sc, run_dir)
        if not log.exists():
            missing = Verdict(False, f"no call record (suite exit {code})")
            rows.append(Row(sc, {"suite exit": missing}, 0.0, 0, None))
            continue
        events = read_events(log)
        usage = [e for e in events if e.get("e") == "usage"]
        sek = cost_sek(usage)
        spent += sek
        _record(runs, now, run_id, loop_id, sek)
        call = call_from_log(log)
        transcript = "\n".join(f"{t.speaker}: {t.text}" for t in call.turns)
        (run_dir / f"{sc}.transcript.txt").write_text(transcript + "\n", "utf-8")
        verdicts = {check.__name__: check(call) for check in SCENARIOS[sc]}
        if code != 0:
            verdicts["suite exit"] = Verdict(False, f"the harness exited {code}")
        tokens = sum(u.get("prompt_tokens", 0) for u in usage)
        delay = next(
            (e["seconds"] for e in events if e.get("e") == "ttfb" and e["seconds"] > 0),
            None,
        )
        rows.append(Row(sc, verdicts, sek, tokens, delay))
        stopped = stopped_by(
            caps, **_totals(runs, spent, loop_id, now.strftime("%Y-%m-%d"))
        )
        if stopped:
            break
    return report(rows, run_dir, spent, stopped, skipped=len(ids) - len(rows))


def report(
    rows: list[Row], run_dir: Path, spent: float, stopped: str | None, skipped: int
) -> int:
    print(
        f"{'Scenario':<20} {'checks':<40} {'SEK':>6} {'prompt tok':>10} {'first reply':>11}"
    )
    for r in rows:
        marks = " ".join(
            f"{n}:{'PASS' if v.passed else 'FAIL'}" for n, v in r.verdicts.items()
        )
        delay = "-" if r.first_reply_s is None else f"{r.first_reply_s:.2f}s"
        print(
            f"{r.scenario:<20} {marks:<40} {r.sek:>6.2f} {r.prompt_tokens:>10} {delay:>11}"
        )
        for n, v in r.verdicts.items():
            if not v.passed:
                print(f"  {n}: {v.reason}")
    print(f"spent {spent:.2f} SEK")
    run_dir.mkdir(parents=True, exist_ok=True)
    results = {
        r.scenario: {
            n: {"passed": v.passed, "reason": v.reason} for n, v in r.verdicts.items()
        }
        for r in rows
    }
    (run_dir / "results.json").write_text(
        json.dumps({"spent_sek": spent, "results": results}, indent=2), "utf-8"
    )
    if stopped:
        print(
            f"STOPPED by the {stopped}; {skipped} Scenario(s) not run", file=sys.stderr
        )
        return 3
    return 0 if all(v.passed for r in rows for v in r.verdicts.values()) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
