"""scripts/check-no-data.sh, run for real against a throwaway git repository.

The guard is what stands between a local board file and a public commit (ADR-0006), and a
shell pattern that silently matches nothing looks exactly like one that works. So each case
stages a file in a temporary repo and asserts the exit code the hook and CI would see.

Nothing here is provider data. The sheet id is 44 repeated characters, and every
credential-shaped string is assembled at runtime, so this file never matches the patterns
it tests -- a literal would make it fail the `--tracked` run it asserts below.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "check-no-data.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None or shutil.which("bash") is None, reason="needs git and bash"
)

SHEET_KEY = "DRAFT_SHEET_ID"
FAKE_ID = "Z" * 44
SHEETS = "https://docs.google.com/spreadsheets/d/"


def git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q")
    (tmp_path / "scripts").mkdir()
    shutil.copy2(SCRIPT, tmp_path / "scripts" / "check-no-data.sh")
    return tmp_path


def stage(repo: Path, rel: str, text: str = "synthetic\n") -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    # -f: a global excludes file on the machine running the tests must not decide the case.
    git(repo, "add", "-f", "--", rel)


def guard(repo: Path, mode: str = "--staged") -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", "scripts/check-no-data.sh", mode], cwd=repo, capture_output=True, text=True
    )


@pytest.mark.parametrize(
    "rel",
    [
        "scripts/draft-board/Data.gs",
        "board - 2026-01-01.json",
        "docs/board - 2026-01-01.json",
        "draft-state.json",
        "tests/fixtures/draft-state.mock.json",
        "draft-state.json.lock",
        "draft-state.20260101T000000.bak.json",
        "notes/anything.bak.json",
        "data/draft-board/pulls/2026-01-01T000000Z live.json",
    ],
)
def test_local_board_files_are_blocked_anywhere(repo, rel):
    stage(repo, rel)
    result = guard(repo)
    assert result.returncode == 1, result.stdout
    assert rel in result.stdout


@pytest.mark.parametrize(
    "rel",
    [
        "scripts/draft-board/board_layout.json",
        "scripts/draft-board/board.py",
        "scripts/draft-board/Build.gs",
        "tests/test_board_state.py",
        "docs/draft-board/cheat-sheet.md",
    ],
)
def test_committed_board_files_pass(repo, rel):
    stage(repo, rel)
    assert guard(repo).returncode == 0


@pytest.mark.parametrize(
    "text",
    [
        SHEET_KEY + "=" + FAKE_ID + "\n",
        SHEET_KEY + ": " + FAKE_ID + "\n",
        "FANTASYPROS_API_KEY" + "=" + "abc123\n",
        SHEETS + FAKE_ID + "/edit\n",
        "fetch('" + SHEETS + FAKE_ID + "/gviz/tq?tqx=out:json')\n",
    ],
)
def test_ids_and_keys_in_content_are_blocked(repo, text):
    stage(repo, "docs/procedure.md", text)
    result = guard(repo)
    assert result.returncode == 1, result.stdout
    assert "docs/procedure.md" in result.stdout


def test_a_blocked_sheet_id_is_not_echoed(repo):
    stage(repo, "docs/procedure.md", "intro\n" + SHEETS + FAKE_ID + "/edit\n")
    result = guard(repo)
    assert result.returncode == 1
    assert "line 2" in result.stdout
    assert FAKE_ID not in result.stdout + result.stderr


@pytest.mark.parametrize(
    "text",
    [
        SHEET_KEY + "=\n",
        SHEET_KEY + "=<SHEET_ID>\n",
        "Read the id from `" + SHEET_KEY + "` in .env.\n",
        "| `.env.example` | `" + SHEET_KEY + "=`. |\n",
        SHEETS + "<SHEET_ID>/edit\n",
        SHEETS + "{id}/gviz/tq?tqx=out:json\n",
        SHEETS + "d/short/edit\n",
    ],
)
def test_placeholders_pass(repo, text):
    stage(repo, "docs/procedure.md", text)
    result = guard(repo)
    assert result.returncode == 0, result.stdout


def test_env_example_with_an_empty_sheet_id_passes(repo):
    stage(repo, ".env.example", "# the draft sheet\n" + SHEET_KEY + "=\n")
    assert guard(repo).returncode == 0


def test_the_guard_passes_its_own_patterns(repo):
    git(repo, "add", "-f", "--", "scripts/check-no-data.sh")
    assert guard(repo).returncode == 0


def test_nothing_staged_passes(repo):
    assert guard(repo).returncode == 0


@pytest.mark.skipif(not (REPO / ".git").exists(), reason="not a git checkout")
def test_every_tracked_file_in_this_repository_passes():
    result = subprocess.run(
        ["bash", str(SCRIPT), "--tracked"], cwd=REPO, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout
