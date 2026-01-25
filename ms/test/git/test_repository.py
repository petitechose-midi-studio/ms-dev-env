"""Tests for git/repository.py."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from ms.core.result import Err, Ok
from ms.git.repository import GitStatus, Repository, StatusEntry

if TYPE_CHECKING:
    pass


# =============================================================================
# StatusEntry Tests
# =============================================================================


class TestStatusEntry:
    """Tests for StatusEntry dataclass."""

    def test_staged_entry(self) -> None:
        """Test detection of staged changes."""
        entry = StatusEntry(xy="M ", path="file.py")
        assert entry.is_staged is True
        assert entry.is_unstaged is False
        assert entry.is_untracked is False

    def test_unstaged_entry(self) -> None:
        """Test detection of unstaged changes."""
        entry = StatusEntry(xy=" M", path="file.py")
        assert entry.is_staged is False
        assert entry.is_unstaged is True
        assert entry.is_untracked is False

    def test_both_staged_and_unstaged(self) -> None:
        """Test file with both staged and unstaged changes."""
        entry = StatusEntry(xy="MM", path="file.py")
        assert entry.is_staged is True
        assert entry.is_unstaged is True
        assert entry.is_untracked is False

    def test_untracked_entry(self) -> None:
        """Test detection of untracked files."""
        entry = StatusEntry(xy="??", path="new_file.py")
        assert entry.is_staged is False
        assert entry.is_unstaged is False
        assert entry.is_untracked is True

    def test_added_file(self) -> None:
        """Test newly added file."""
        entry = StatusEntry(xy="A ", path="new.py")
        assert entry.is_staged is True
        assert entry.is_unstaged is False

    def test_deleted_file(self) -> None:
        """Test deleted file."""
        entry = StatusEntry(xy="D ", path="old.py")
        assert entry.is_staged is True

    def test_renamed_file(self) -> None:
        """Test renamed file."""
        entry = StatusEntry(xy="R ", path="old.py -> new.py")
        assert entry.is_staged is True

    def test_pretty_xy(self) -> None:
        """Test pretty formatting of XY code."""
        assert StatusEntry(xy="M ", path="f").pretty_xy() == "M."
        assert StatusEntry(xy=" M", path="f").pretty_xy() == ".M"
        assert StatusEntry(xy="MM", path="f").pretty_xy() == "MM"
        assert StatusEntry(xy="??", path="f").pretty_xy() == "??"


# =============================================================================
# GitStatus Tests
# =============================================================================


class TestGitStatus:
    """Tests for GitStatus dataclass."""

    def test_clean_status(self) -> None:
        """Test clean repository status."""
        status = GitStatus(branch="main", upstream="origin/main")
        assert status.is_clean is True
        assert status.has_divergence is False
        assert status.staged_count == 0
        assert status.unstaged_count == 0
        assert status.untracked_count == 0

    def test_dirty_status(self) -> None:
        """Test repository with changes."""
        entries = (
            StatusEntry(xy="M ", path="staged.py"),
            StatusEntry(xy=" M", path="unstaged.py"),
            StatusEntry(xy="??", path="untracked.py"),
        )
        status = GitStatus(branch="main", upstream="origin/main", entries=entries)

        assert status.is_clean is False
        assert status.staged_count == 1
        assert status.unstaged_count == 1
        assert status.untracked_count == 1

    def test_divergence_ahead(self) -> None:
        """Test branch ahead of upstream."""
        status = GitStatus(branch="main", upstream="origin/main", ahead=3)
        assert status.has_divergence is True

    def test_divergence_behind(self) -> None:
        """Test branch behind upstream."""
        status = GitStatus(branch="main", upstream="origin/main", behind=2)
        assert status.has_divergence is True

    def test_divergence_no_upstream(self) -> None:
        """Test branch with no upstream."""
        status = GitStatus(branch="feature", upstream=None)
        assert status.has_divergence is True

    def test_no_divergence(self) -> None:
        """Test branch in sync with upstream."""
        status = GitStatus(branch="main", upstream="origin/main", ahead=0, behind=0)
        assert status.has_divergence is False

    def test_staged_list(self) -> None:
        """Test getting staged entries."""
        entries = (
            StatusEntry(xy="M ", path="staged1.py"),
            StatusEntry(xy=" M", path="unstaged.py"),
            StatusEntry(xy="A ", path="staged2.py"),
            StatusEntry(xy="??", path="untracked.py"),
        )
        status = GitStatus(branch="main", entries=entries)

        staged = status.staged
        assert len(staged) == 2
        assert staged[0].path == "staged1.py"
        assert staged[1].path == "staged2.py"

    def test_unstaged_list(self) -> None:
        """Test getting unstaged entries."""
        entries = (
            StatusEntry(xy="M ", path="staged.py"),
            StatusEntry(xy=" M", path="unstaged1.py"),
            StatusEntry(xy=" D", path="unstaged2.py"),
        )
        status = GitStatus(branch="main", entries=entries)

        unstaged = status.unstaged
        assert len(unstaged) == 2

    def test_untracked_list(self) -> None:
        """Test getting untracked entries."""
        entries = (
            StatusEntry(xy="??", path="new1.py"),
            StatusEntry(xy="??", path="new2.py"),
            StatusEntry(xy="M ", path="tracked.py"),
        )
        status = GitStatus(branch="main", entries=entries)

        untracked = status.untracked
        assert len(untracked) == 2


# =============================================================================
# Repository Tests - Mocked subprocess
# =============================================================================


def make_completed_process(
    stdout: str = "",
    stderr: str = "",
    returncode: int = 0,
) -> subprocess.CompletedProcess[str]:
    """Create a mock CompletedProcess."""
    return subprocess.CompletedProcess(
        args=["git"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


class TestRepository:
    """Tests for Repository class."""

    def test_exists_with_git_dir(self, tmp_path: Path) -> None:
        """Test exists() with .git directory."""
        (tmp_path / ".git").mkdir()
        repo = Repository(tmp_path)
        assert repo.exists() is True

    def test_exists_with_git_file(self, tmp_path: Path) -> None:
        """Test exists() with .git file (submodule)."""
        (tmp_path / ".git").write_text("gitdir: ../.git/modules/sub")
        repo = Repository(tmp_path)
        assert repo.exists() is True

    def test_exists_no_git(self, tmp_path: Path) -> None:
        """Test exists() with no .git."""
        repo = Repository(tmp_path)
        assert repo.exists() is False

    @patch("subprocess.run")
    def test_status_clean(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Test status() on clean repository."""
        mock_run.return_value = make_completed_process(stdout="## main...origin/main\n")

        repo = Repository(tmp_path)
        result = repo.status()

        assert isinstance(result, Ok)
        status = result.unwrap()
        assert status.branch == "main"
        assert status.upstream == "origin/main"
        assert status.is_clean is True

    @patch("subprocess.run")
    def test_status_with_changes(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Test status() with modified files."""
        mock_run.return_value = make_completed_process(
            stdout="## main...origin/main\nM  staged.py\n M unstaged.py\n?? new.py\n"
        )

        repo = Repository(tmp_path)
        result = repo.status()

        assert isinstance(result, Ok)
        status = result.unwrap()
        assert status.is_clean is False
        assert status.staged_count == 1
        assert status.unstaged_count == 1
        assert status.untracked_count == 1

    @patch("subprocess.run")
    def test_status_ahead_behind(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Test status() with ahead/behind counts."""
        mock_run.return_value = make_completed_process(
            stdout="## feature...origin/feature [ahead 3, behind 2]\n"
        )

        repo = Repository(tmp_path)
        result = repo.status()

        assert isinstance(result, Ok)
        status = result.unwrap()
        assert status.ahead == 3
        assert status.behind == 2
        assert status.has_divergence is True

    @patch("subprocess.run")
    def test_status_only_ahead(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Test status() with only ahead."""
        mock_run.return_value = make_completed_process(stdout="## main...origin/main [ahead 5]\n")

        repo = Repository(tmp_path)
        result = repo.status()

        assert isinstance(result, Ok)
        status = result.unwrap()
        assert status.ahead == 5
        assert status.behind == 0

    @patch("subprocess.run")
    def test_status_no_upstream(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Test status() with no upstream configured."""
        mock_run.return_value = make_completed_process(stdout="## feature\n")

        repo = Repository(tmp_path)
        result = repo.status()

        assert isinstance(result, Ok)
        status = result.unwrap()
        assert status.branch == "feature"
        assert status.upstream is None
        assert status.has_divergence is True

    @patch("subprocess.run")
    def test_status_error(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Test status() when git fails."""
        mock_run.return_value = make_completed_process(
            returncode=128,
            stderr="fatal: not a git repository",
        )

        repo = Repository(tmp_path)
        result = repo.status()

        assert isinstance(result, Err)
        error = result.unwrap_err()
        assert error.command == "status"
        assert "not a git repository" in error.message

    @patch("subprocess.run")
    def test_is_clean_true(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Test is_clean() on clean repository."""
        mock_run.return_value = make_completed_process(stdout="")

        repo = Repository(tmp_path)
        assert repo.is_clean() is True

    @patch("subprocess.run")
    def test_is_clean_false(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Test is_clean() on dirty repository."""
        mock_run.return_value = make_completed_process(stdout=" M file.py\n")

        repo = Repository(tmp_path)
        assert repo.is_clean() is False

    @patch("subprocess.run")
    def test_has_upstream_true(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Test has_upstream() when upstream exists."""
        mock_run.return_value = make_completed_process(
            stdout="origin/main",
            returncode=0,
        )

        repo = Repository(tmp_path)
        assert repo.has_upstream() is True

    @patch("subprocess.run")
    def test_has_upstream_false(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Test has_upstream() when no upstream."""
        mock_run.return_value = make_completed_process(
            returncode=128,
            stderr="fatal: no upstream configured",
        )

        repo = Repository(tmp_path)
        assert repo.has_upstream() is False

    @patch("subprocess.run")
    def test_current_branch(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Test current_branch() returns branch name."""
        mock_run.return_value = make_completed_process(stdout="feature-branch\n")

        repo = Repository(tmp_path)
        assert repo.current_branch() == "feature-branch"

    @patch("subprocess.run")
    def test_current_branch_detached(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Test current_branch() on detached HEAD."""
        mock_run.return_value = make_completed_process(stdout="HEAD\n")

        repo = Repository(tmp_path)
        assert repo.current_branch() is None

    @patch("subprocess.run")
    def test_pull_ff_success(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Test pull_ff() success."""
        mock_run.return_value = make_completed_process(stdout="Already up to date.\n")

        repo = Repository(tmp_path)
        result = repo.pull_ff()

        assert isinstance(result, Ok)
        assert "up to date" in result.unwrap()

    @patch("subprocess.run")
    def test_pull_ff_failure(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Test pull_ff() when fast-forward not possible."""
        mock_run.return_value = make_completed_process(
            returncode=1,
            stderr="fatal: Not possible to fast-forward, aborting.",
        )

        repo = Repository(tmp_path)
        result = repo.pull_ff()

        assert isinstance(result, Err)
        error = result.unwrap_err()
        assert "fast-forward" in error.message.lower()

    @patch("subprocess.run")
    def test_fetch_success(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Test fetch() success."""
        mock_run.return_value = make_completed_process(stdout="")

        repo = Repository(tmp_path)
        result = repo.fetch()

        assert isinstance(result, Ok)

    @patch("subprocess.run")
    def test_fetch_failure(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Test fetch() failure."""
        mock_run.return_value = make_completed_process(
            returncode=1,
            stderr="fatal: could not read from remote repository",
        )

        repo = Repository(tmp_path)
        result = repo.fetch()

        assert isinstance(result, Err)


# =============================================================================
# Parsing Tests
# =============================================================================


class TestParsing:
    """Tests for git output parsing."""

    @patch("subprocess.run")
    def test_parse_renamed_file(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Test parsing renamed file entry."""
        mock_run.return_value = make_completed_process(stdout="## main\nR  old.py -> new.py\n")

        repo = Repository(tmp_path)
        result = repo.status()

        assert isinstance(result, Ok)
        status = result.unwrap()
        assert len(status.entries) == 1
        assert "old.py -> new.py" in status.entries[0].path

    @patch("subprocess.run")
    def test_parse_copied_file(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Test parsing copied file entry."""
        mock_run.return_value = make_completed_process(stdout="## main\nC  src.py -> dst.py\n")

        repo = Repository(tmp_path)
        result = repo.status()

        assert isinstance(result, Ok)
        status = result.unwrap()
        assert len(status.entries) == 1

    @patch("subprocess.run")
    def test_parse_multiple_entries(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Test parsing multiple status entries."""
        output = """## main...origin/main
M  modified_staged.py
 M modified_unstaged.py
A  added.py
D  deleted.py
?? untracked1.py
?? untracked2.py
"""
        mock_run.return_value = make_completed_process(stdout=output)

        repo = Repository(tmp_path)
        result = repo.status()

        assert isinstance(result, Ok)
        status = result.unwrap()
        assert len(status.entries) == 6
        assert status.staged_count == 3  # M, A, D staged
        assert status.unstaged_count == 1
        assert status.untracked_count == 2

    @patch("subprocess.run")
    def test_parse_empty_output(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Test parsing empty status output."""
        mock_run.return_value = make_completed_process(stdout="")

        repo = Repository(tmp_path)
        result = repo.status()

        assert isinstance(result, Ok)
        status = result.unwrap()
        assert status.branch == ""
        assert status.is_clean is True

    @patch("subprocess.run")
    def test_parse_branch_only_ahead(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Test parsing branch line with only ahead."""
        mock_run.return_value = make_completed_process(stdout="## main...origin/main [ahead 10]\n")

        repo = Repository(tmp_path)
        result = repo.status()

        assert isinstance(result, Ok)
        status = result.unwrap()
        assert status.ahead == 10
        assert status.behind == 0

    @patch("subprocess.run")
    def test_parse_branch_only_behind(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Test parsing branch line with only behind."""
        mock_run.return_value = make_completed_process(stdout="## main...origin/main [behind 7]\n")

        repo = Repository(tmp_path)
        result = repo.status()

        assert isinstance(result, Ok)
        status = result.unwrap()
        assert status.ahead == 0
        assert status.behind == 7
