"""Integration tests for Phase 3: Git & App.

These tests verify that the git and app modules work together correctly.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from ms.core.app import App, list_all, resolve
from ms.core.result import Ok
from ms.git import (
    GitStatus,
    Repository,
    StatusEntry,
    find_workspace_repos,
    status_all,
)


# =============================================================================
# Workspace Simulation
# =============================================================================


def create_workspace(tmp_path: Path) -> Path:
    """Create a mock workspace structure."""
    workspace = tmp_path / "workspace"

    # Create workspace .git
    (workspace / ".git").mkdir(parents=True)
    (workspace / "config.toml").touch()
    (workspace / "commands").mkdir()

    # Create open-control repos
    oc = workspace / "open-control"
    (oc / "bridge" / ".git").mkdir(parents=True)
    (oc / "ui-lvgl" / ".git").mkdir(parents=True)

    # Create midi-studio repos with apps
    ms = workspace / "midi-studio"

    # Core with Teensy and SDL
    core = ms / "core"
    core.mkdir(parents=True)
    (core / ".git").mkdir()
    (core / "platformio.ini").touch()
    (core / "sdl").mkdir(parents=True)
    (core / "sdl" / "app.cmake").write_text("# CMake")

    # Bitwig plugin with Teensy (uses core SDL)
    bitwig = ms / "plugin-bitwig"
    bitwig.mkdir(parents=True)
    (bitwig / ".git").mkdir()
    (bitwig / "platformio.ini").touch()

    return workspace


# =============================================================================
# Integration Tests
# =============================================================================


class TestWorkspaceDiscovery:
    """Test discovering repos and apps in a workspace."""

    def test_find_all_repos_in_workspace(self, tmp_path: Path) -> None:
        """Test finding all git repos in workspace."""
        workspace = create_workspace(tmp_path)

        repos = find_workspace_repos(workspace)

        # Should find: workspace root, bridge, ui-lvgl, core, plugin-bitwig
        assert len(repos) == 5
        names = [r.name for r in repos]
        assert "workspace" in names  # Root repo
        assert "bridge" in names
        assert "ui-lvgl" in names
        assert "core" in names
        assert "plugin-bitwig" in names

    def test_list_all_apps(self, tmp_path: Path) -> None:
        """Test listing all apps."""
        workspace = create_workspace(tmp_path)

        apps = list_all(workspace)

        assert apps == ["core", "bitwig"]

    def test_resolve_core_app(self, tmp_path: Path) -> None:
        """Test resolving core app."""
        workspace = create_workspace(tmp_path)

        result = resolve("core", workspace)

        assert isinstance(result, Ok)
        app = result.unwrap()
        assert app.name == "core"
        assert app.has_teensy is True
        assert app.has_sdl is True
        assert app.sdl_path == workspace / "midi-studio" / "core" / "sdl"

    def test_resolve_bitwig_uses_core_sdl(self, tmp_path: Path) -> None:
        """Test that bitwig plugin uses core SDL."""
        workspace = create_workspace(tmp_path)

        result = resolve("bitwig", workspace)

        assert isinstance(result, Ok)
        app = result.unwrap()
        assert app.name == "bitwig"
        assert app.has_teensy is True
        assert app.has_sdl is True
        # Uses shared SDL from core
        assert app.sdl_path == workspace / "midi-studio" / "core" / "sdl"


def make_git_output(
    branch: str = "main",
    upstream: str | None = "origin/main",
    ahead: int = 0,
    behind: int = 0,
    entries: list[str] | None = None,
) -> str:
    """Create mock git status output."""
    parts: list[str] = [f"## {branch}"]
    if upstream:
        parts[0] += f"...{upstream}"
    if ahead or behind:
        info: list[str] = []
        if ahead:
            info.append(f"ahead {ahead}")
        if behind:
            info.append(f"behind {behind}")
        parts[0] += f" [{', '.join(info)}]"

    parts.append("")  # Empty line after branch
    if entries:
        parts.extend(entries)

    return "\n".join(parts)


class TestStatusWorkflow:
    """Test the status workflow across repos."""

    @patch("subprocess.run")
    def test_status_all_repos(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Test getting status of all repos."""
        workspace = create_workspace(tmp_path)
        repos = find_workspace_repos(workspace)

        # Mock git status for each repo
        mock_run.return_value = subprocess.CompletedProcess(
            args=["git"],
            returncode=0,
            stdout=make_git_output(),
            stderr="",
        )

        statuses = status_all(repos)

        assert len(statuses) == 5
        assert all(s.ok for s in statuses)
        assert all(s.is_clean for s in statuses)

    @patch("subprocess.run")
    def test_find_dirty_repos(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Test finding dirty repos in workspace."""
        workspace = create_workspace(tmp_path)
        repos = find_workspace_repos(workspace)

        # Make some repos dirty
        def status_side_effect(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
            if "core" in str(args):
                return subprocess.CompletedProcess(
                    args=["git"],
                    returncode=0,
                    stdout=make_git_output(entries=["M  file.py"]),
                    stderr="",
                )
            return subprocess.CompletedProcess(
                args=["git"],
                returncode=0,
                stdout=make_git_output(),
                stderr="",
            )

        mock_run.side_effect = status_side_effect

        statuses = status_all(repos)
        dirty = [s for s in statuses if s.is_dirty]

        # Only core should be dirty
        assert len(dirty) == 1


class TestAppGitIntegration:
    """Test integration between app and git modules."""

    @patch("subprocess.run")
    def test_app_repo_status(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Test getting git status for a app repo."""
        workspace = create_workspace(tmp_path)

        # Resolve app
        result = resolve("core", workspace)
        assert isinstance(result, Ok)
        app = result.unwrap()

        # Get git status for app
        mock_run.return_value = subprocess.CompletedProcess(
            args=["git"],
            returncode=0,
            stdout=make_git_output(
                branch="feature",
                upstream="origin/feature",
                ahead=2,
                entries=["M  src/main.cpp"],
            ),
            stderr="",
        )

        repo = Repository(app.path)
        status_result = repo.status()

        assert isinstance(status_result, Ok)
        status = status_result.unwrap()
        assert status.branch == "feature"
        assert status.ahead == 2
        assert not status.is_clean


class TestHintsLoading:
    """Test that hints.toml can be loaded."""

    def test_hints_file_exists(self) -> None:
        """Test that hints.toml was created."""
        from pathlib import Path

        # Path from ms/test/ to ms/data/
        hints_path = Path(__file__).parent.parent / "data" / "hints.toml"
        assert hints_path.exists(), f"hints.toml not found at {hints_path}"

    def test_hints_file_valid_toml(self) -> None:
        """Test that hints.toml is valid TOML."""
        import tomllib
        from pathlib import Path

        hints_path = Path(__file__).parent.parent / "data" / "hints.toml"
        content = hints_path.read_text(encoding="utf-8")

        # Should not raise
        data = tomllib.loads(content)

        # Check structure
        assert "tools" in data
        assert "cmake" in data["tools"]
        assert "fedora" in data["tools"]["cmake"]


# =============================================================================
# Summary
# =============================================================================


class TestPhase3Summary:
    """Summary tests for Phase 3 completion."""

    def test_all_modules_importable(self) -> None:
        """Test that all Phase 3 modules can be imported."""
        # Git module - verify imports work
        import ms.git as git_module

        assert hasattr(git_module, "GitError")
        assert hasattr(git_module, "GitStatus")
        assert hasattr(git_module, "PullResult")
        assert hasattr(git_module, "RepoStatus")
        assert hasattr(git_module, "Repository")
        assert hasattr(git_module, "StatusEntry")
        assert hasattr(git_module, "filter_dirty")
        assert hasattr(git_module, "filter_diverged")
        assert hasattr(git_module, "find_repos")
        assert hasattr(git_module, "find_workspace_repos")
        assert hasattr(git_module, "get_summary")
        assert hasattr(git_module, "pull_all")
        assert hasattr(git_module, "status_all")

        # App module (app resolution) - verify imports work
        import ms.core.app as app_module

        assert hasattr(app_module, "App")
        assert hasattr(app_module, "AppError")
        assert hasattr(app_module, "list_all")
        assert hasattr(app_module, "resolve")

    def test_git_status_dataclasses(self) -> None:
        """Test that git dataclasses work correctly."""
        entry = StatusEntry(xy="M ", path="file.py")
        assert entry.is_staged

        status = GitStatus(
            branch="main",
            upstream="origin/main",
            entries=(entry,),
        )
        assert not status.is_clean
        assert status.staged_count == 1

    def test_app_dataclasses(self, tmp_path: Path) -> None:
        """Test that app dataclasses work correctly."""
        app = App(
            name="test",
            path=tmp_path,
            has_teensy=True,
            has_sdl=True,
            sdl_path=tmp_path / "sdl",
        )

        assert app.name == "test"
        assert app.has_teensy
        assert app.has_sdl
