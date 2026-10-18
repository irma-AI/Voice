"""Checks seam: the usage gate (scripts/usage-gate.js) on stored example readings, run as the hook Claude Code runs."""

import json
import os
import subprocess
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
GATE = ROOT / "scripts" / "usage-gate.js"
CASES = json.loads((Path(__file__).parent / "usage" / "cases.json").read_text())


def run_gate(
    shared: Path, stdin: str, *args: str, remote: bool = True
) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "PROJECT_FILES": str(shared),
        "CLAUDE_CODE_REMOTE": "true" if remote else "false",
    }
    return subprocess.run(
        ["node", str(GATE), *args],
        check=False,
        input=stdin,
        env=env,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def write_reading(shared: Path, case: dict[str, object]) -> None:
    if "reading" in case:
        if case["reading"] is None:
            return
        reading = case["reading"]
    else:
        now = time.time()
        reset = now + float(case.get("reset_in_s", 3600))  # type: ignore[arg-type]
        reading = {
            "five_hour": {"utilization": case["five_hour"], "resets_at": reset},
            "seven_day": {"utilization": case["seven_day"], "resets_at": reset},
            "read_at": now - float(case.get("age_s", 5)),  # type: ignore[arg-type]
        }
    (shared / ".usage").mkdir()
    (shared / ".usage" / "state.json").write_text(json.dumps(reading))


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_gate_decides(tmp_path: Path, case: dict[str, object]) -> None:
    write_reading(tmp_path, case)
    hook_input = {
        "hook_event_name": "PreToolUse",
        "tool_name": case["tool"],
        "tool_input": {"command": case.get("command")},
    }
    out = run_gate(tmp_path, json.dumps(hook_input))
    expect = case["expect"]
    if expect == "deny":
        assert out.returncode == 2, out
        assert str(case.get("says", "Usage gate")) in out.stderr
    else:
        assert out.returncode == 0, out
        warned = "additionalContext" in out.stdout
        assert warned == (expect == "warn"), out.stdout


def test_record_writes_a_fresh_reading_the_gate_accepts(tmp_path: Path) -> None:
    out = run_gate(tmp_path, "", "record", "0.5", "1792337400", "0.4", "1792843200")
    assert out.returncode == 0, out.stderr
    reading = json.loads((tmp_path / ".usage" / "state.json").read_text())
    assert reading["five_hour"] == {"utilization": 0.5, "resets_at": 1792337400}
    assert not list((tmp_path / ".usage").glob("*.tmp"))
    edit = json.dumps(
        {"hook_event_name": "PreToolUse", "tool_name": "Edit", "tool_input": {}}
    )
    assert run_gate(tmp_path, edit).returncode == 0


def test_record_refuses_a_bad_reading(tmp_path: Path) -> None:
    assert (
        run_gate(
            tmp_path, "", "record", "82", "1792337400", "0.4", "1792843200"
        ).returncode
        == 1
    )
    assert not (tmp_path / ".usage" / "state.json").exists()


def test_gate_leaves_non_cloud_sessions_alone(tmp_path: Path) -> None:
    edit = json.dumps(
        {"hook_event_name": "PreToolUse", "tool_name": "Edit", "tool_input": {}}
    )
    assert run_gate(tmp_path, edit, remote=False).returncode == 0


def test_prompt_hook_only_adds_context(tmp_path: Path) -> None:
    write_reading(tmp_path, {"five_hour": 0.97, "seven_day": 0.1})
    out = run_gate(
        tmp_path, json.dumps({"hook_event_name": "UserPromptSubmit", "prompt": "go on"})
    )
    assert out.returncode == 0
    assert "five-hour usage at 97%" in out.stdout
