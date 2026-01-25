"""Tests for tools/state.py - Tool state tracking."""

import json
from pathlib import Path

from ms.tools.state import (
    ToolState,
    get_installed_version,
    load_state,
    save_state,
    set_installed_version,
)


class TestToolState:
    """Tests for ToolState dataclass."""

    def test_create(self) -> None:
        """Create ToolState."""
        state = ToolState(version="1.12.1", installed_at="2025-01-25T10:00:00")
        assert state.version == "1.12.1"
        assert state.installed_at == "2025-01-25T10:00:00"

    def test_now(self) -> None:
        """Create ToolState with current timestamp."""
        state = ToolState.now("1.12.1")
        assert state.version == "1.12.1"
        assert state.installed_at  # Should have a timestamp


class TestLoadSaveState:
    """Tests for load_state and save_state."""

    def test_load_empty(self, tmp_path: Path) -> None:
        """Load from non-existent file returns empty dict."""
        state = load_state(tmp_path)
        assert state == {}

    def test_save_and_load(self, tmp_path: Path) -> None:
        """Save and load roundtrip."""
        state = {
            "ninja": ToolState(version="1.12.1", installed_at="2025-01-25T10:00:00"),
            "cmake": ToolState(version="3.31.0", installed_at="2025-01-25T11:00:00"),
        }
        save_state(tmp_path, state)

        loaded = load_state(tmp_path)
        assert loaded["ninja"].version == "1.12.1"
        assert loaded["cmake"].version == "3.31.0"

    def test_state_file_location(self, tmp_path: Path) -> None:
        """State is saved to state.json."""
        state = {"ninja": ToolState.now("1.12.1")}
        save_state(tmp_path, state)

        state_file = tmp_path / "state.json"
        assert state_file.exists()

        # Verify it's valid JSON
        data = json.loads(state_file.read_text())
        assert "ninja" in data

    def test_load_corrupted(self, tmp_path: Path) -> None:
        """Load corrupted state returns empty dict."""
        state_file = tmp_path / "state.json"
        state_file.write_text("not valid json")

        state = load_state(tmp_path)
        assert state == {}


class TestGetSetInstalledVersion:
    """Tests for get/set installed version helpers."""

    def test_get_not_installed(self, tmp_path: Path) -> None:
        """Get version for non-installed tool returns None."""
        version = get_installed_version(tmp_path, "ninja")
        assert version is None

    def test_set_and_get(self, tmp_path: Path) -> None:
        """Set and get version."""
        set_installed_version(tmp_path, "ninja", "1.12.1")

        version = get_installed_version(tmp_path, "ninja")
        assert version == "1.12.1"

    def test_update_version(self, tmp_path: Path) -> None:
        """Update version for already installed tool."""
        set_installed_version(tmp_path, "ninja", "1.12.0")
        set_installed_version(tmp_path, "ninja", "1.12.1")

        version = get_installed_version(tmp_path, "ninja")
        assert version == "1.12.1"

    def test_multiple_tools(self, tmp_path: Path) -> None:
        """Track multiple tools."""
        set_installed_version(tmp_path, "ninja", "1.12.1")
        set_installed_version(tmp_path, "cmake", "3.31.0")

        assert get_installed_version(tmp_path, "ninja") == "1.12.1"
        assert get_installed_version(tmp_path, "cmake") == "3.31.0"
