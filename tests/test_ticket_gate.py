"""Checks seam: the commit ticket gate (scripts/ticket-gate.js --staged) on a throwaway repo, run as the pre-commit hook runs it."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
GATE = ROOT / "scripts" / "ticket-gate.js"
IDENTITY = {
    "GIT_AUTHOR_NAME": "Petter",
    "GIT_AUTHOR_EMAIL": "petter@example.invalid",
    "GIT_COMMITTER_NAME": "Petter",
    "GIT_COMMITTER_EMAIL": "petter@example.invalid",
}


def git(repo: Path, *args: str) -> str:
    env = {**os.environ, **IDENTITY}
    return subprocess.run(
        ["git", *args], cwd=repo, env=env, check=True, capture_output=True, text=True
    ).stdout


def commit(repo: Path, rel: str) -> None:
    (repo / rel).parent.mkdir(parents=True, exist_ok=True)
    (repo / rel).write_text(rel)
    git(repo, "add", rel)
    git(repo, "commit", "--no-verify", "-qm", rel)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A main with the real no_ticket list, published as origin/main."""
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "scripts").mkdir()
    shutil.copy(
        ROOT / "scripts" / "low-risk-paths.json",
        tmp_path / "scripts" / "low-risk-paths.json",
    )
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "--no-verify", "-qm", "base")
    git(tmp_path, "update-ref", "refs/remotes/origin/main", "main")
    return tmp_path


def merge_main_into(repo: Path, branch_file: str) -> subprocess.CompletedProcess[str]:
    """A ticketless branch changes branch_file, main moves on with code, and the branch merges origin/main."""
    git(repo, "switch", "-qc", "no-ticket-branch")
    commit(repo, branch_file)
    git(repo, "switch", "-q", "main")
    commit(repo, "voice/new_code.py")
    git(repo, "update-ref", "refs/remotes/origin/main", "main")
    git(repo, "switch", "-q", "no-ticket-branch")
    git(repo, "merge", "--no-commit", "--no-ff", "-q", "origin/main")
    env = {k: v for k, v in os.environ.items() if k != "NEXT_STEP_TICKET"}
    return subprocess.run(
        ["node", str(GATE), "--staged"],
        cwd=repo,
        env={**env, "CLAUDECODE": "1"},
        check=False,
        capture_output=True,
        text=True,
    )


def test_a_merge_of_main_into_a_docs_only_branch_needs_no_ticket(repo: Path) -> None:
    out = merge_main_into(repo, "docs/research/note.md")
    assert out.returncode == 0, out.stderr


def test_a_merge_into_a_branch_with_its_own_code_still_needs_a_ticket(
    repo: Path,
) -> None:
    out = merge_main_into(repo, "voice/branch_code.py")
    assert out.returncode == 2, out.stderr
    assert "voice/branch_code.py needs a ready Linear ticket" in out.stderr
