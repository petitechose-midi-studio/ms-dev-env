"""Tests for tools/state.py - Tool state tracking."""

import json
from pathlib import Path

from ms.core.result import Err, Ok
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
        """Load from non-existent file returns Ok({})."""
        result = load_state(tmp_path)
        assert isinstance(result, Ok)
        assert result.value == {}

    def test_save_and_load(self, tmp_path: Path) -> None:
        """Save and load roundtrip."""
        state = {
            "ninja": ToolState(version="1.12.1", installed_at="2025-01-25T10:00:00"),
            "cmake": ToolState(version="3.31.0", installed_at="2025-01-25T11:00:00"),
        }
        save_state(tmp_path, state)

        result = load_state(tmp_path)
        assert isinstance(result, Ok)
        assert result.value["ninja"].version == "1.12.1"
        assert result.value["cmake"].version == "3.31.0"

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
        """Load corrupted state starts fresh."""
        state_file = tmp_path / "state.json"
        state_file.write_text("not valid json")

        result = load_state(tmp_path)
        assert isinstance(result, Ok)
        assert result.value == {}

    def test_load_json_array_starts_fresh(self, tmp_path: Path) -> None:
        """A JSON array root is not a valid state table."""
        (tmp_path / "state.json").write_text("[]")

        result = load_state(tmp_path)
        assert isinstance(result, Ok)
        assert result.value == {}

    def test_load_invalid_encoding_is_error(self, tmp_path: Path) -> None:
        """Non-UTF-8 bytes are an I/O error, not a fresh state."""
        (tmp_path / "state.json").write_bytes(b"\xff\xfe\x00{")

        result = load_state(tmp_path)
        assert isinstance(result, Err)
        assert "cannot read tool state" in result.error.message

    def test_load_unreadable_is_error(self, tmp_path: Path) -> None:
        """An unreadable state file is an I/O error, not a fresh state."""
        (tmp_path / "state.json").mkdir()

        result = load_state(tmp_path)
        assert isinstance(result, Err)


class TestGetSetInstalledVersion:
    """Tests for get/set installed version helpers."""

    def test_get_not_installed(self, tmp_path: Path) -> None:
        """Get version for non-installed tool returns Ok(None)."""
        result = get_installed_version(tmp_path, "ninja")
        assert isinstance(result, Ok)
        assert result.value is None

    def test_set_and_get(self, tmp_path: Path) -> None:
        """Set and get version."""
        written = set_installed_version(tmp_path, "ninja", "1.12.1")
        assert isinstance(written, Ok)

        result = get_installed_version(tmp_path, "ninja")
        assert isinstance(result, Ok)
        assert result.value == "1.12.1"

    def test_update_version(self, tmp_path: Path) -> None:
        """Update version for already installed tool."""
        set_installed_version(tmp_path, "ninja", "1.12.0")
        set_installed_version(tmp_path, "ninja", "1.12.1")

        result = get_installed_version(tmp_path, "ninja")
        assert isinstance(result, Ok)
        assert result.value == "1.12.1"

    def test_multiple_tools(self, tmp_path: Path) -> None:
        """Track multiple tools."""
        set_installed_version(tmp_path, "ninja", "1.12.1")
        set_installed_version(tmp_path, "cmake", "3.31.0")

        ninja = get_installed_version(tmp_path, "ninja")
        cmake = get_installed_version(tmp_path, "cmake")
        assert isinstance(ninja, Ok) and ninja.value == "1.12.1"
        assert isinstance(cmake, Ok) and cmake.value == "3.31.0"

    def test_get_on_unreadable_state_is_error(self, tmp_path: Path) -> None:
        """Unreadable state must not be reported as 'not installed'."""
        (tmp_path / "state.json").mkdir()

        result = get_installed_version(tmp_path, "ninja")
        assert isinstance(result, Err)

    def test_set_on_unreadable_state_is_error(self, tmp_path: Path) -> None:
        """Refuse to overwrite an unreadable state file."""
        (tmp_path / "state.json").mkdir()

        result = set_installed_version(tmp_path, "ninja", "1.12.1")
        assert isinstance(result, Err)
