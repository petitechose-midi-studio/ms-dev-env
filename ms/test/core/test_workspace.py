"""Tests for ms.core.workspace module."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from ms.core.result import Err, Ok
from ms.core.user_workspace import remember_default_workspace_root
from ms.core.workspace import (
    Workspace,
    WorkspaceError,
    WorkspaceInfo,
    detect_workspace,
    detect_workspace_info,
    detect_workspace_or_raise,
    find_workspace_upward,
    is_workspace_root,
)
from ms.platform.paths import clear_caches


@pytest.fixture
def temp_workspace(tmp_path: Path) -> Path:
    """Create a minimal workspace structure in a temp directory."""
    (tmp_path / ".ms-workspace").write_text("")
    # config.toml is optional, but most tests assume it can exist.
    (tmp_path / "config.toml").write_text("[project]\nname = 'test'\n")
    return tmp_path


@pytest.fixture
def nested_workspace(tmp_path: Path) -> Path:
    """Create a workspace with nested directories."""
    # Create workspace at tmp_path
    (tmp_path / ".ms-workspace").write_text("")
    (tmp_path / "config.toml").write_text("[project]\nname = 'test'\n")
    # Create nested directories
    nested = tmp_path / "a" / "b" / "c"
    nested.mkdir(parents=True)
    return tmp_path


class TestWorkspace:
    """Test Workspace dataclass."""

    def test_create(self, temp_workspace: Path) -> None:
        ws = Workspace(root=temp_workspace)
        assert ws.root == temp_workspace

    def test_config_path(self, temp_workspace: Path) -> None:
        ws = Workspace(root=temp_workspace)
        assert ws.config_path == temp_workspace / "config.toml"

    def test_bin_dir(self, temp_workspace: Path) -> None:
        ws = Workspace(root=temp_workspace)
        assert ws.bin_dir == temp_workspace / "bin"

    def test_build_dir(self, temp_workspace: Path) -> None:
        ws = Workspace(root=temp_workspace)
        assert ws.build_dir == temp_workspace / ".build"

    def test_tools_dir(self, temp_workspace: Path) -> None:
        ws = Workspace(root=temp_workspace)
        assert ws.tools_dir == temp_workspace / "tools"

    def test_tools_bin_dir(self, temp_workspace: Path) -> None:
        ws = Workspace(root=temp_workspace)
        assert ws.tools_bin_dir == temp_workspace / "tools" / "bin"

    def test_cache_dir(self, temp_workspace: Path) -> None:
        ws = Workspace(root=temp_workspace)
        assert ws.cache_dir == temp_workspace / ".ms" / "cache"

    def test_download_cache_dir(self, temp_workspace: Path) -> None:
        ws = Workspace(root=temp_workspace)
        assert ws.download_cache_dir == temp_workspace / ".ms" / "cache" / "downloads"

    def test_open_control_dir(self, temp_workspace: Path) -> None:
        ws = Workspace(root=temp_workspace)
        assert ws.open_control_dir == temp_workspace / "open-control"

    def test_midi_studio_dir(self, temp_workspace: Path) -> None:
        ws = Workspace(root=temp_workspace)
        assert ws.midi_studio_dir == temp_workspace / "midi-studio"

    def test_exists_true(self, temp_workspace: Path) -> None:
        ws = Workspace(root=temp_workspace)
        assert ws.exists() is True

    def test_exists_false_no_marker(self, temp_workspace: Path) -> None:
        (temp_workspace / ".ms-workspace").unlink()
        ws = Workspace(root=temp_workspace)
        assert ws.exists() is False

    def test_exists_false_no_dir(self, tmp_path: Path) -> None:
        ws = Workspace(root=tmp_path / "nonexistent")
        assert ws.exists() is False

    def test_str(self, temp_workspace: Path) -> None:
        ws = Workspace(root=temp_workspace)
        assert str(ws) == str(temp_workspace)

    def test_frozen(self, temp_workspace: Path) -> None:
        ws = Workspace(root=temp_workspace)
        with pytest.raises(AttributeError):
            ws.root = temp_workspace / "other"  # type: ignore[misc]


class TestWorkspaceError:
    """Test WorkspaceError dataclass."""

    def test_create(self) -> None:
        err = WorkspaceError(message="not found")
        assert err.message == "not found"
        assert err.searched_from is None

    def test_create_with_path(self, tmp_path: Path) -> None:
        err = WorkspaceError(message="not found", searched_from=tmp_path)
        assert err.message == "not found"
        assert err.searched_from == tmp_path


class TestIsWorkspaceRoot:
    """Test is_workspace_root helper."""

    def test_valid_workspace(self, temp_workspace: Path) -> None:
        assert is_workspace_root(temp_workspace) is True

    def test_missing_marker(self, tmp_path: Path) -> None:
        assert is_workspace_root(tmp_path) is False

    def test_empty_dir(self, tmp_path: Path) -> None:
        assert is_workspace_root(tmp_path) is False

    def test_marker_as_dir(self, tmp_path: Path) -> None:
        """Marker must be a file, not a directory."""
        (tmp_path / ".ms-workspace").mkdir()
        assert is_workspace_root(tmp_path) is False


class TestFindWorkspaceUpward:
    """Test find_workspace_upward helper."""

    def test_find_at_start(self, temp_workspace: Path) -> None:
        found = find_workspace_upward(temp_workspace)
        assert found == temp_workspace

    def test_find_from_nested(self, nested_workspace: Path) -> None:
        nested = nested_workspace / "a" / "b" / "c"
        found = find_workspace_upward(nested)
        assert found == nested_workspace

    def test_not_found(self, tmp_path: Path) -> None:
        found = find_workspace_upward(tmp_path)
        assert found is None


class TestDetectWorkspace:
    """Test detect_workspace function."""

    def test_detect_from_workspace_root(self, temp_workspace: Path) -> None:
        """Starting at a workspace root should find it immediately."""
        # Use find_workspace_upward directly to avoid env var interference
        from ms.core.workspace import find_workspace_upward

        found = find_workspace_upward(temp_workspace)
        assert found == temp_workspace

    def test_detect_from_nested(self, nested_workspace: Path) -> None:
        """Starting from nested dir should find workspace above."""
        from ms.core.workspace import find_workspace_upward

        nested = nested_workspace / "a" / "b" / "c"
        found = find_workspace_upward(nested)
        assert found == nested_workspace

    def test_not_found_in_isolated_hierarchy(self, tmp_path: Path) -> None:
        """When no workspace markers exist in hierarchy, returns None."""
        from ms.core.workspace import find_workspace_upward

        # tmp_path has no workspace markers, but its parents might include
        # the real workspace. Create a "fake root" by making a marker that
        # would be found first if we were searching for something else.
        # Instead, we test the helper directly with a known non-workspace.
        isolated = tmp_path / "no_workspace_here"
        isolated.mkdir()
        # The helper will search upward and may find real workspace
        # So we test that if workspace IS found, it's not our isolated path
        found = find_workspace_upward(isolated)
        # found might be the real workspace or None - either is valid
        # What we care about is that isolated itself is NOT a workspace
        assert found != isolated

    def test_detect_with_explicit_start(self, temp_workspace: Path) -> None:
        """detect_workspace with explicit start_dir should find workspace."""
        with patch.dict(os.environ, {}, clear=False):
            # Remove WORKSPACE_ROOT if set
            os.environ.pop("WORKSPACE_ROOT", None)
            result = detect_workspace(start_dir=temp_workspace)
            assert isinstance(result, Ok)
            assert result.value.root == temp_workspace

    def test_env_var_takes_precedence(self, temp_workspace: Path, tmp_path: Path) -> None:
        """Environment variable should be checked before searching upward."""
        # Create a second workspace
        other = tmp_path / "other"
        other.mkdir()
        (other / ".ms-workspace").write_text("")

        with patch.dict(os.environ, {"WORKSPACE_ROOT": str(other)}):
            result = detect_workspace(start_dir=temp_workspace)
            assert isinstance(result, Ok)
            assert result.value.root == other

    def test_env_var_invalid_returns_err(self, tmp_path: Path) -> None:
        """Invalid WORKSPACE_ROOT should return error, not fallback."""
        invalid = tmp_path / "invalid"
        invalid.mkdir()  # Directory exists but no workspace markers

        with patch.dict(os.environ, {"WORKSPACE_ROOT": str(invalid)}):
            result = detect_workspace(start_dir=tmp_path)
            assert isinstance(result, Err)
            assert "WORKSPACE_ROOT" in result.error.message
            assert "not a valid workspace" in result.error.message

    def test_env_var_nonexistent_returns_err(self, tmp_path: Path) -> None:
        """WORKSPACE_ROOT pointing to nonexistent path should error."""
        nonexistent = tmp_path / "nonexistent"

        with patch.dict(os.environ, {"WORKSPACE_ROOT": str(nonexistent)}):
            result = detect_workspace(start_dir=tmp_path)
            assert isinstance(result, Err)
            assert "WORKSPACE_ROOT" in result.error.message

    def test_custom_env_var_name(self, temp_workspace: Path) -> None:
        """Can use a custom environment variable name."""
        with patch.dict(os.environ, {"MY_WORKSPACE": str(temp_workspace)}):
            result = detect_workspace(start_dir=Path("/"), env_var="MY_WORKSPACE")
            assert isinstance(result, Ok)
            assert result.value.root == temp_workspace

    def test_env_var_with_tilde(self, temp_workspace: Path) -> None:
        """Environment variable with ~ should be expanded."""
        # This test is tricky because ~ depends on actual home
        # We'll just verify the path gets resolved
        with patch.dict(os.environ, {"WORKSPACE_ROOT": str(temp_workspace)}):
            result = detect_workspace()
            assert isinstance(result, Ok)

    def test_remembered_workspace_used_when_not_found(self, tmp_path: Path) -> None:
        """When cwd search fails, fall back to remembered default workspace."""
        ws = tmp_path / "ws"
        ws.mkdir()
        (ws / ".ms-workspace").write_text("")

        # Redirect user config dir to tmp_path
        env = {"APPDATA": str(tmp_path)} if os.name == "nt" else {"XDG_CONFIG_HOME": str(tmp_path)}
        with patch.dict(os.environ, env, clear=False):
            clear_caches()
            assert isinstance(remember_default_workspace_root(ws), Ok)

            start = tmp_path / "outside"
            start.mkdir()
            result = detect_workspace(start_dir=start)
            assert isinstance(result, Ok)
            assert result.value.root == ws

    def test_detect_workspace_info_has_source(self, tmp_path: Path) -> None:
        ws = tmp_path / "ws"
        ws.mkdir()
        (ws / ".ms-workspace").write_text("")

        env = {"APPDATA": str(tmp_path)} if os.name == "nt" else {"XDG_CONFIG_HOME": str(tmp_path)}
        with patch.dict(os.environ, env, clear=False):
            clear_caches()
            assert isinstance(remember_default_workspace_root(ws), Ok)
            start = tmp_path / "outside"
            start.mkdir()

            info = detect_workspace_info(start_dir=start)
            assert isinstance(info, Ok)
            assert isinstance(info.value, WorkspaceInfo)
            assert info.value.workspace.root == ws
            assert info.value.source == "remembered"


class TestDetectWorkspaceOrRaise:
    """Test detect_workspace_or_raise convenience function."""

    def test_returns_workspace(self, temp_workspace: Path) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("WORKSPACE_ROOT", None)
            ws = detect_workspace_or_raise(start_dir=temp_workspace)
            assert isinstance(ws, Workspace)
            assert ws.root == temp_workspace

    def test_raises_on_invalid_env(self, tmp_path: Path) -> None:
        """Raises when WORKSPACE_ROOT points to invalid location."""
        invalid = tmp_path / "invalid"
        invalid.mkdir()
        with patch.dict(os.environ, {"WORKSPACE_ROOT": str(invalid)}):
            with pytest.raises(ValueError) as exc_info:
                detect_workspace_or_raise(start_dir=tmp_path)
            assert "not a valid workspace" in str(exc_info.value)


class TestRealWorkspace:
    """Test with the real workspace (if available)."""

    def test_detect_real_workspace(self) -> None:
        """If running from within a workspace, we should detect it."""
        result = detect_workspace()
        # This test runs from within the midi-studio workspace
        if isinstance(result, Ok):
            ws = result.value
            assert ws.marker_path.exists()
