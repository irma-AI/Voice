"""The decisions archive (scripts/archive-decisions.js), run as `make archive-decisions` runs it, on a stored synthetic log."""

import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "archive-decisions.js"
LOG = """# Decisions

Header text stays.

[2026-09-01] Old decision: why.
[2026-09-02] ESCALATED: answered question -> Petter
[2026-09-03] RESOLVED 2026-09-02: the answer.
[2026-09-10] ESCALATED: still waiting -> Petter
[2026-10-01] Another old one in a new month: why.
[2026-10-15] This week: why.
"""


def run(tmp_path: Path) -> str:
    (tmp_path / "DECISIONS.md").write_text(LOG)
    env = {**os.environ, "ARCHIVE_ROOT": str(tmp_path), "ARCHIVE_TODAY": "2026-10-19"}
    subprocess.run(["node", str(SCRIPT)], env=env, check=True, capture_output=True)
    return (tmp_path / "DECISIONS.md").read_text()


def test_old_lines_move_to_their_month_and_the_week_and_open_questions_stay(
    tmp_path: Path,
) -> None:
    kept = run(tmp_path)
    assert kept.startswith("# Decisions\n\nHeader text stays.\n")
    assert "still waiting" in kept and "This week" in kept
    assert "Old decision" not in kept and "answered question" not in kept
    september = (tmp_path / "docs/decisions/2026-09.md").read_text()
    assert "Old decision" in september and "the answer." in september
    assert "still waiting" not in september
    assert "Another old one" in (tmp_path / "docs/decisions/2026-10.md").read_text()


def test_a_second_run_moves_nothing_more_and_still_sees_the_archived_answers(
    tmp_path: Path,
) -> None:
    first = run(tmp_path)
    env = {**os.environ, "ARCHIVE_ROOT": str(tmp_path), "ARCHIVE_TODAY": "2026-10-19"}
    subprocess.run(["node", str(SCRIPT)], env=env, check=True, capture_output=True)
    assert (tmp_path / "DECISIONS.md").read_text() == first
    assert (tmp_path / "docs/decisions/2026-09.md").read_text().count(
        "Old decision"
    ) == 1
