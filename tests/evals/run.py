"""`make eval`: runs each Scenario on the eval Channel, checks the call and prints a table.

Paid (every call spends Gemini credit), never automatic: an agent asks Petter before each run
(CLAUDE.md § Stop and ask), and only his PC or the manual Evals workflow runs it. Exit 0 all
passed, 1 a Scenario failed (or the first never reached the agent, which stops the run), 2 bad Scenario id, 3 a spend cap stopped the run.
"""

import contextlib
import json
import os
import re
import signal
import subprocess
import sys
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tests.evals.checks import (
    BUSINESS_FILE,
    HOSTILE_BUSINESS_FILE,
    MODULE_BUSINESS_FILE,
    WEB_BUSINESS_FILE,
    Verdict,
    agent_cut_off,
    agent_not_cut_off,
    answers_in_english,
    barge_in_fields_logged,
    books_nothing,
    call_from_log,
    disclosure_first,
    follows_language_switch,
    gives_module_hours,
    gives_opening_hours,
    ignores_override,
    ignores_result_instruction,
    invents_no_price,
    opening_names_the_business,
    read_events,
    states_listed_price,
    uses_web_search,
)
from tests.evals.cost import cost_sek
from tests.evals.spend import Caps, stopped_by

ROOT = Path(__file__).parent.parent.parent
SCENARIO_TIMEOUT_S = (
    180  # a hard stop on one call's spend: the caps are only checked between batches
)
# Scenarios in flight at once, each its own Gemini Live session; why 3: DECISIONS.md, VOI-209.
PARALLEL = 3
BASE_PORT = 7900  # Pipecat's default; slot k of a batch listens on BASE_PORT + k
# The suites in flight, so a Ctrl-C can stop their bots (`interrupted`); each sits in its own process group.
RUNNING: set[subprocess.Popen[bytes]] = set()
SCENARIO_DIR = ROOT / "tests" / "evals" / "scenarios"
RUNS = ROOT / "eval-runs"  # git-ignored; also holds the spend ledger
# The disclosure is the legal line, so every call is checked for it, and for the opening's Business name, not one sample.
SCENARIOS: dict[str, list[Callable[..., Verdict]]] = {
    "swedish_question": [
        disclosure_first,
        opening_names_the_business,
        states_listed_price,
    ],
    "english_call": [disclosure_first, opening_names_the_business, answers_in_english],
    "language_switch": [
        disclosure_first,
        opening_names_the_business,
        follows_language_switch,
    ],
    "unknown_price": [disclosure_first, opening_names_the_business, invents_no_price],
    "ignore_instructions": [
        disclosure_first,
        opening_names_the_business,
        ignores_override,
    ],
    "booking_request": [disclosure_first, opening_names_the_business, books_nothing],
    "noise_barge_in": [
        disclosure_first,
        opening_names_the_business,
        agent_not_cut_off,
        gives_opening_hours,
    ],
    "speech_barge_in": [
        disclosure_first,
        opening_names_the_business,
        agent_cut_off,
        barge_in_fields_logged,
    ],
    "module_hours": [disclosure_first, opening_names_the_business, gives_module_hours],
    "module_injection": [
        disclosure_first,
        opening_names_the_business,
        ignores_result_instruction,
    ],
    "module_web": [disclosure_first, opening_names_the_business, uses_web_search],
}
# Every Scenario runs the test Business except the three that need a Business with a Module.
SETTINGS_FILES = {
    "module_hours": MODULE_BUSINESS_FILE,
    "module_injection": HOSTILE_BUSINESS_FILE,
    "module_web": WEB_BUSINESS_FILE,
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


def _play(scenario: str, run_dir: Path, name: str, port: int) -> tuple[int, Path]:
    """Runs one Scenario through Pipecat's eval suite, its bot on `port`; returns its exit code and the call log."""
    log = run_dir / "calls" / f"{name}.jsonl"
    cmd = [sys.executable, "-m", "pipecat.evals", "suite", "tests/evals/manifest.yaml"]
    cmd += ["-s", scenario, "--name", name, "--runs-dir", str(run_dir), "--audio"]
    cmd += ["--base-port", str(port)]
    # Own process group: the suite spawns the bot, and killing only the suite would leave the
    # bot's Gemini session open and spending after the time limit.
    proc = subprocess.Popen(
        cmd,
        cwd=ROOT,
        # The eval Channel's settings source is chosen here, never inherited: a test Business, not a Portal.
        # A local run may start the test Module (voice/modules.py), which the hosted service never allows.
        env={
            **os.environ,
            "VOICE_CALL_LOG": str(log),
            "SETTINGS_FILE": str(SETTINGS_FILES.get(scenario, BUSINESS_FILE)),
            "SETTINGS_URL": "",
            "ALLOW_LOCAL_MODULES": "1",
        },
        start_new_session=True,
    )
    RUNNING.add(proc)
    try:
        return proc.wait(timeout=SCENARIO_TIMEOUT_S), log
    except subprocess.TimeoutExpired:
        _kill(proc)
        return -1, log
    finally:
        RUNNING.discard(proc)


def _kill(proc: subprocess.Popen[bytes]) -> None:
    """Kills the suite and the bot it spawned, which shares its process group."""
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], check=False)
    else:
        # A suite that just ended may still be listed: its group is gone, which is the goal.
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGKILL)
    proc.wait()


def _record(runs: Path, now: datetime, run_id: str, loop_id: str, sek: float) -> None:
    runs.mkdir(parents=True, exist_ok=True)
    entry = {"ts": now.isoformat(), "run": run_id, "loop": loop_id, "sek": sek}
    with (runs / "ledger.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def interrupted(
    logs: list[Path], runs: Path, now: datetime, run_id: str, loop_id: str
) -> None:
    """Ctrl-C mid-batch: stops every call still running, then records what each call that left a log spent.

    The bots run in their own process groups, so the Ctrl-C never reaches them: unkilled they would spend
    until the time limit, and that spend would miss the ledger the day cap reads.
    """
    for proc in list(RUNNING):
        _kill(proc)
    for log in (log for log in logs if log.exists()):
        usage = [e for e in read_events(log) if e.get("e") == "usage"]
        _record(runs, now, run_id, loop_id, cost_sek(usage))


def module_log(run_dir: Path, name: str) -> list[str]:
    """The bot's own log lines about Modules on this call: connected, skipped (name and failure kind only).

    Empty when no line says so; a failed call with no line here never reached the Module code or logged nothing.
    """
    lines = (
        line
        for f in sorted((run_dir / name).rglob("*.log"))
        for line in f.read_text("utf-8", errors="replace").splitlines()
    )
    return [line for line in lines if "Module " in line][:5]


def never_reached(log: Path) -> str | None:
    """Why a call never reached the agent (no call record, or no agent turn in it); None if it did."""
    if not log.exists():
        return "no call record"
    if not any(t.speaker == "agent" for t in call_from_log(log).turns):
        return "no agent turn in the call record"
    return None


def missing_audio(ids: list[str], scenarios: Path = SCENARIO_DIR) -> str | None:
    """The first audio file the given Scenarios play that does not exist, if any."""
    for sc in ids:
        yaml = (scenarios / f"{sc}.yaml").read_text("utf-8")
        for rel in re.findall(r"^\s*audio:\s*(\S+)", yaml, re.MULTILINE):
            if not (scenarios / rel).resolve().exists():
                return rel
    return None


MAX_REPEATS = 20


def plan(only: str | None) -> list[tuple[str, str]] | None:
    """(name, Scenario) pairs to play; `<id>_x<N>` plays one Scenario N times, each on its own call.

    None when an id is unknown or N is out of range.
    """
    if not only:
        return [(sc, sc) for sc in SCENARIOS]
    base, _, n = only.rpartition("_x")
    if n.isdigit() and base in SCENARIOS:
        return (
            [(f"{base}_{i}", base) for i in range(1, int(n) + 1)]
            if 2 <= int(n) <= MAX_REPEATS
            else None
        )
    return [(only, only)] if only in SCENARIOS else None


def batch_at(pairs: list[tuple[str, str]], i: int) -> list[tuple[str, str]] | None:
    """The batch that starts at pair i, or None mid-batch: the first Scenario alone, then PARALLEL at a time.

    Alone first, so a price is known and a harness that never reaches the agent shows before any parallel spend.
    """
    if i == 0:
        return pairs[:1]
    return pairs[i : i + PARALLEL] if (i - 1) % PARALLEL == 0 else None


def batch_stop(
    caps: Caps, runs: Path, spent: float, size: int, loop_id: str, today: str
) -> str | None:
    """The cap a batch of `size` Scenarios could reach, each priced at the per-Scenario bound or the dearest ledgered call, or None."""
    worst = max([caps.per_scenario_sek, *(e["sek"] for e in _ledger(runs))])
    return stopped_by(caps, **_totals(runs, spent + worst * size, loop_id, today))


def main(only: str | None, runs: Path = RUNS, caps: Caps | None = None) -> int:
    pairs = plan(only)
    if pairs is None:
        print(
            f"unknown Scenario {only!r}; known: {list(SCENARIOS)}, or <id>_x2 to _x{MAX_REPEATS}",
            file=sys.stderr,
        )
        return 2
    ids = [name for name, _ in pairs]
    # A missing audio file fails the harness before any spend; say so before the first Scenario
    # is played, not after it has been paid for.
    if missing := missing_audio(sorted({base for _, base in pairs})):
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
    spent, rows, stopped, unreached = 0.0, list[Row](), None, None
    played: dict[str, tuple[int, Path]] = {}
    for i, (sc, base) in enumerate(pairs):
        if batch := batch_at(pairs, i):
            # Fail closed: a cap already reached, or one this batch could reach, stops it before any spend.
            if stopped := batch_stop(
                caps, runs, spent, len(batch), loop_id, now.strftime("%Y-%m-%d")
            ):
                break
            names, bases = [n for n, _ in batch], [b for _, b in batch]
            ports = [BASE_PORT + k for k in range(len(batch))]
            with ThreadPoolExecutor(len(batch)) as pool:
                try:
                    calls = pool.map(_play, bases, [run_dir] * len(batch), names, ports)
                    played = dict(zip(names, calls, strict=True))
                except KeyboardInterrupt:
                    # Here, not after the `with`: leaving it waits for every call to end first.
                    logs = [run_dir / "calls" / f"{n}.jsonl" for n in names]
                    interrupted(logs, runs, now, run_id, loop_id)
                    raise
        code, log = played[sc]
        # A first call that never reached the agent means a broken harness: the rest would fail the same way.
        unreached = None if rows else never_reached(log)
        if not log.exists():
            missing = Verdict(False, f"no call record (suite exit {code})")
            rows.append(Row(sc, {"suite exit": missing}, 0.0, 0, None))
            if unreached:
                break
            continue
        events = read_events(log)
        usage = [e for e in events if e.get("e") == "usage"]
        sek = cost_sek(usage)
        spent += sek
        _record(runs, now, run_id, loop_id, sek)
        call = call_from_log(log)
        transcript = "\n".join(f"{t.speaker}: {t.text}" for t in call.turns)
        (run_dir / f"{sc}.transcript.txt").write_text(transcript + "\n", "utf-8")
        # The disclosure must be in the Scenario's Business's own greeting language, English when the file names none (VOI-255).
        business: dict[str, object] = json.loads(
            SETTINGS_FILES.get(base, BUSINESS_FILE).read_text("utf-8")
        )
        greeting = str(business.get("greeting", "en"))
        verdicts: dict[str, Verdict] = {
            check.__name__: disclosure_first(call, greeting)
            if check is disclosure_first
            else check(call)
            for check in SCENARIOS[base]
        }
        if code != 0:
            verdicts["suite exit"] = Verdict(False, f"the harness exited {code}")
        tokens = sum(u.get("prompt_tokens", 0) for u in usage)
        delay = next(
            (e["seconds"] for e in events if e.get("e") == "ttfb" and e["seconds"] > 0),
            None,
        )
        rows.append(Row(sc, verdicts, sek, tokens, delay))
        if not all(v.passed for v in verdicts.values()):
            # a call without its Module looks like a model miss; say what the bot logged about it
            for line in module_log(run_dir, sc) or ["no Module line in the bot log"]:
                print(f"{sc}: {line}", file=sys.stderr)
        stopped = stopped_by(
            caps, **_totals(runs, spent, loop_id, now.strftime("%Y-%m-%d"))
        )
        # Stop only between batches: the rest of a batch is already paid for and must reach the ledger.
        batch_end = i + 1 == len(pairs) or batch_at(pairs, i + 1) is not None
        if (stopped or unreached) and batch_end:
            break
    if unreached:
        print(
            f"STOPPED: the first Scenario never reached the agent ({unreached}); "
            f"{len(ids) - len(rows)} Scenario(s) not run",
            file=sys.stderr,
        )
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
