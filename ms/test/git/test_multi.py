"""Tests for git/multi.py."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from ms.git.multi import (
    PullResult,
    RepoStatus,
    filter_dirty,
    filter_diverged,
    find_repos,
    find_workspace_repos,
    get_summary,
    pull_all,
    status_all,
)
from ms.git.repository import GitError, GitStatus, StatusEntry

# =============================================================================
# RepoStatus Tests
# =============================================================================


class TestRepoStatus:
    """Tests for RepoStatus dataclass."""

    def test_ok_with_status(self, tmp_path: Path) -> None:
        """Test ok property with status."""
        status = GitStatus(branch="main")
        repo_status = RepoStatus(path=tmp_path, status=status)
        assert repo_status.ok is True

    def test_not_ok_with_error(self, tmp_path: Path) -> None:
        """Test ok property with error."""
        error = GitError(command="status", message="failed", returncode=1)
        repo_status = RepoStatus(path=tmp_path, error=error)
        assert repo_status.ok is False

    def test_is_clean(self, tmp_path: Path) -> None:
        """Test is_clean with clean status."""
        status = GitStatus(branch="main")
        repo_status = RepoStatus(path=tmp_path, status=status)
        assert repo_status.is_clean is True
        assert repo_status.is_dirty is False

    def test_is_dirty(self, tmp_path: Path) -> None:
        """Test is_dirty with dirty status."""
        entries = (StatusEntry(xy="M ", path="file.py"),)
        status = GitStatus(branch="main", entries=entries)
        repo_status = RepoStatus(path=tmp_path, status=status)
        assert repo_status.is_clean is False
        assert repo_status.is_dirty is True

    def test_has_divergence(self, tmp_path: Path) -> None:
        """Test has_divergence."""
        status = GitStatus(branch="main", upstream="origin/main", ahead=2)
        repo_status = RepoStatus(path=tmp_path, status=status)
        assert repo_status.has_divergence is True

    def test_error_is_not_clean(self, tmp_path: Path) -> None:
        """Test that error state is not considered clean."""
        error = GitError(command="status", message="failed", returncode=1)
        repo_status = RepoStatus(path=tmp_path, error=error)
        assert repo_status.is_clean is False
        assert repo_status.is_dirty is False  # Not dirty, just error


# =============================================================================
# PullResult Tests
# =============================================================================


class TestPullResult:
    """Tests for PullResult dataclass."""

    def test_ok_with_output(self, tmp_path: Path) -> None:
        """Test ok property with output."""
        result = PullResult(path=tmp_path, output="Already up to date.")
        assert result.ok is True

    def test_not_ok_with_error(self, tmp_path: Path) -> None:
        """Test ok property with error."""
        error = GitError(command="pull", message="failed", returncode=1)
        result = PullResult(path=tmp_path, error=error)
        assert result.ok is False

    def test_skipped(self, tmp_path: Path) -> None:
        """Test skipped pull."""
        result = PullResult(path=tmp_path, skipped=True, skip_reason="dirty")
        assert result.ok is False
        assert result.skipped is True
        assert result.skip_reason == "dirty"


# =============================================================================
# find_repos Tests
# =============================================================================


class TestFindRepos:
    """Tests for find_repos function."""

    def test_find_repos_in_directory(self, tmp_path: Path) -> None:
        """Test finding repos in a directory."""
        # Create some repos
        (tmp_path / "repo1" / ".git").mkdir(parents=True)
        (tmp_path / "repo2" / ".git").mkdir(parents=True)
        (tmp_path / "not_a_repo").mkdir(parents=True)
        (tmp_path / "file.txt").touch()

        repos = find_repos(tmp_path)

        assert len(repos) == 2
        assert repos[0].name == "repo1"
        assert repos[1].name == "repo2"

    def test_find_repos_empty_directory(self, tmp_path: Path) -> None:
        """Test finding repos in empty directory."""
        repos = find_repos(tmp_path)
        assert repos == []

    def test_find_repos_nonexistent_directory(self, tmp_path: Path) -> None:
        """Test finding repos in nonexistent directory."""
        repos = find_repos(tmp_path / "nonexistent")
        assert repos == []

    def test_find_repos_sorted_case_insensitive(self, tmp_path: Path) -> None:
        """Test repos are sorted case-insensitively."""
        (tmp_path / "Zebra" / ".git").mkdir(parents=True)
        (tmp_path / "alpha" / ".git").mkdir(parents=True)
        (tmp_path / "Beta" / ".git").mkdir(parents=True)

        repos = find_repos(tmp_path)

        assert len(repos) == 3
        assert repos[0].name == "alpha"
        assert repos[1].name == "Beta"
        assert repos[2].name == "Zebra"


class TestFindWorkspaceRepos:
    """Tests for find_workspace_repos function."""

    def test_find_workspace_repos(self, tmp_path: Path) -> None:
        """Test finding repos in workspace structure."""
        # Create workspace structure
        (tmp_path / ".git").mkdir()  # Workspace root is a repo
        (tmp_path / "open-control" / "bridge" / ".git").mkdir(parents=True)
        (tmp_path / "open-control" / "ui-lvgl" / ".git").mkdir(parents=True)
        (tmp_path / "midi-studio" / "core" / ".git").mkdir(parents=True)

        repos = find_workspace_repos(tmp_path)

        assert len(repos) == 4
        assert repos[0] == tmp_path  # Workspace root first
        # Then sorted repos from open-control and midi-studio

    def test_find_workspace_repos_no_root_repo(self, tmp_path: Path) -> None:
        """Test workspace where root is not a repo."""
        (tmp_path / "open-control" / "bridge" / ".git").mkdir(parents=True)

        repos = find_workspace_repos(tmp_path)

        assert len(repos) == 1
        assert repos[0].name == "bridge"


# =============================================================================
# status_all Tests
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


class TestStatusAll:
    """Tests for status_all function."""

    @patch("subprocess.run")
    def test_status_all_success(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Test getting status of multiple repos."""
        mock_run.return_value = make_completed_process(stdout="## main...origin/main\n")

        repo1 = tmp_path / "repo1"
        repo2 = tmp_path / "repo2"
        repo1.mkdir()
        repo2.mkdir()

        statuses = status_all([repo1, repo2])

        assert len(statuses) == 2
        assert all(s.ok for s in statuses)
        assert statuses[0].path == repo1
        assert statuses[1].path == repo2

    @patch("subprocess.run")
    def test_status_all_with_error(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Test status_all with a failing repo."""
        mock_run.side_effect = [
            make_completed_process(stdout="## main\n"),
            make_completed_process(returncode=128, stderr="not a repo"),
        ]

        repo1 = tmp_path / "repo1"
        repo2 = tmp_path / "repo2"
        repo1.mkdir()
        repo2.mkdir()

        statuses = status_all([repo1, repo2])

        assert len(statuses) == 2
        assert statuses[0].ok is True
        assert statuses[1].ok is False
        assert statuses[1].error is not None


# =============================================================================
# pull_all Tests
# =============================================================================


class TestPullAll:
    """Tests for pull_all function."""

    @patch("subprocess.run")
    def test_pull_all_success(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Test pulling multiple repos."""
        mock_run.side_effect = [
            # is_clean check
            make_completed_process(stdout=""),
            # has_upstream check
            make_completed_process(stdout="origin/main"),
            # pull
            make_completed_process(stdout="Already up to date."),
            # Second repo
            make_completed_process(stdout=""),
            make_completed_process(stdout="origin/main"),
            make_completed_process(stdout="Fast-forward"),
        ]

        repo1 = tmp_path / "repo1"
        repo2 = tmp_path / "repo2"
        repo1.mkdir()
        repo2.mkdir()

        results = pull_all([repo1, repo2])

        assert len(results) == 2
        assert all(r.ok for r in results)

    @patch("subprocess.run")
    def test_pull_all_skip_dirty(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Test skipping dirty repos."""
        mock_run.return_value = make_completed_process(stdout=" M file.py")

        repo = tmp_path / "repo"
        repo.mkdir()

        results = pull_all([repo], skip_dirty=True)

        assert len(results) == 1
        assert results[0].skipped is True
        assert results[0].skip_reason == "dirty"

    @patch("subprocess.run")
    def test_pull_all_skip_no_upstream(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Test skipping repos without upstream."""
        mock_run.side_effect = [
            make_completed_process(stdout=""),  # is_clean - clean
            make_completed_process(returncode=128),  # has_upstream - no
        ]

        repo = tmp_path / "repo"
        repo.mkdir()

        results = pull_all([repo], skip_no_upstream=True)

        assert len(results) == 1
        assert results[0].skipped is True
        assert results[0].skip_reason == "no upstream"

    @patch("subprocess.run")
    def test_pull_all_failure(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Test pull failure."""
        mock_run.side_effect = [
            make_completed_process(stdout=""),  # is_clean
            make_completed_process(stdout="origin/main"),  # has_upstream
            make_completed_process(returncode=1, stderr="Merge conflict"),  # pull
        ]

        repo = tmp_path / "repo"
        repo.mkdir()

        results = pull_all([repo])

        assert len(results) == 1
        assert results[0].ok is False
        assert results[0].error is not None


# =============================================================================
# Helper Functions Tests
# =============================================================================


class TestGetSummary:
    """Tests for get_summary function."""

    def test_get_summary(self, tmp_path: Path) -> None:
        """Test summary generation."""
        statuses = [
            RepoStatus(
                path=tmp_path / "clean", status=GitStatus(branch="main", upstream="origin/main")
            ),
            RepoStatus(
                path=tmp_path / "dirty",
                status=GitStatus(
                    branch="main",
                    upstream="origin/main",
                    entries=(StatusEntry(xy="M ", path="f"),),
                ),
            ),
            RepoStatus(
                path=tmp_path / "diverged",
                status=GitStatus(
                    branch="main",
                    upstream="origin/main",
                    ahead=2,
                ),
            ),
            RepoStatus(
                path=tmp_path / "error",
                error=GitError(
                    command="status",
                    message="failed",
                ),
            ),
        ]

        summary = get_summary(statuses)

        assert summary["total"] == 4
        assert summary["clean"] == 2  # clean + diverged (no entries = clean worktree)
        assert summary["dirty"] == 1
        assert summary["diverged"] == 1  # only diverged (dirty has no ahead/behind)
        assert summary["errors"] == 1


class TestFilters:
    """Tests for filter functions."""

    def test_filter_dirty(self, tmp_path: Path) -> None:
        """Test filtering dirty repos."""
        statuses = [
            RepoStatus(path=tmp_path / "clean", status=GitStatus(branch="main")),
            RepoStatus(
                path=tmp_path / "dirty",
                status=GitStatus(
                    branch="main",
                    entries=(StatusEntry(xy="M ", path="f"),),
                ),
            ),
        ]

        dirty = filter_dirty(statuses)

        assert len(dirty) == 1
        assert dirty[0].path.name == "dirty"

    def test_filter_diverged(self, tmp_path: Path) -> None:
        """Test filtering diverged repos."""
        statuses = [
            RepoStatus(
                path=tmp_path / "synced",
                status=GitStatus(
                    branch="main",
                    upstream="origin/main",
                ),
            ),
            RepoStatus(
                path=tmp_path / "ahead",
                status=GitStatus(
                    branch="main",
                    upstream="origin/main",
                    ahead=3,
                ),
            ),
            RepoStatus(
                path=tmp_path / "no_upstream",
                status=GitStatus(
                    branch="feature",
                ),
            ),
        ]

        diverged = filter_diverged(statuses)

        assert len(diverged) == 2
