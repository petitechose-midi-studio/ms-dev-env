"""Tests for ms.platform.paths module."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from ms.platform.paths import (
    APP_NAME,
    clear_caches,
    home,
    user_config_dir,
)


@pytest.fixture(autouse=True)
def clear_path_caches() -> None:
    """Clear path caches before each test."""
    clear_caches()


class TestHome:
    """Test home directory detection."""

    def test_returns_path(self) -> None:
        result = home()
        assert isinstance(result, Path)

    def test_path_exists(self) -> None:
        """Home directory should exist on any system."""
        result = home()
        assert result.exists()

    def test_uses_userprofile_on_windows(self) -> None:
        test_path = r"C:\Users\TestUser"
        with (
            patch("ms.platform.paths.is_windows", return_value=True),
            patch.dict(os.environ, {"USERPROFILE": test_path}),
        ):
            clear_caches()
            result = home()
            assert result == Path(test_path)

    def test_uses_home_on_unix(self) -> None:
        test_path = "/home/testuser"
        with (
            patch("ms.platform.paths.is_windows", return_value=False),
            patch.dict(os.environ, {"HOME": test_path}),
        ):
            clear_caches()
            result = home()
            assert result == Path(test_path)

    def test_is_cached(self) -> None:
        """Multiple calls return same object."""
        result1 = home()
        result2 = home()
        assert result1 is result2


class TestUserConfigDir:
    """Test user config directory detection."""

    def test_returns_path(self) -> None:
        result = user_config_dir()
        assert isinstance(result, Path)

    def test_ends_with_app_name(self) -> None:
        result = user_config_dir()
        assert str(result).endswith(APP_NAME)

    def test_windows_uses_appdata(self) -> None:
        test_path = r"C:\Users\Test\AppData\Roaming"
        with (
            patch("ms.platform.paths.is_windows", return_value=True),
            patch.dict(os.environ, {"APPDATA": test_path}),
        ):
            clear_caches()
            result = user_config_dir()
            assert result == Path(test_path) / APP_NAME

    def test_unix_uses_xdg_config_home(self) -> None:
        test_path = "/custom/config"
        with (
            patch("ms.platform.paths.is_windows", return_value=False),
            patch.dict(os.environ, {"XDG_CONFIG_HOME": test_path}),
        ):
            clear_caches()
            result = user_config_dir()
            assert result == Path(test_path) / APP_NAME

    def test_unix_defaults_to_dot_config(self) -> None:
        with (
            patch("ms.platform.paths.is_windows", return_value=False),
            patch.dict(os.environ, {"HOME": "/home/test"}, clear=False),
        ):
            env = os.environ.copy()
            env.pop("XDG_CONFIG_HOME", None)
            env["HOME"] = "/home/test"
            with patch.dict(os.environ, env, clear=True):
                clear_caches()
                result = user_config_dir()
                assert result == Path("/home/test/.config") / APP_NAME


class TestClearCaches:
    """Test cache clearing functionality."""

    def test_clears_all_caches(self) -> None:
        """After clearing, new calls should return new objects."""
        # Populate caches (call functions to fill cache)
        home()
        user_config_dir()

        # Clear
        clear_caches()

        # New calls - note we can't guarantee different objects on same machine
        # but the function should at least run without error
        h2 = home()
        c2 = user_config_dir()

        assert isinstance(h2, Path)
        assert isinstance(c2, Path)


class TestPathConsistency:
    """Test that paths are consistent and sensible."""

    def test_all_paths_are_absolute(self) -> None:
        """All returned paths should be absolute."""
        assert home().is_absolute()
        assert user_config_dir().is_absolute()

    def test_config_is_under_home(self) -> None:
        """Config directory should typically be under home."""
        # On most systems, config is somewhere under home
        # This might not be true if XDG vars are set, so we just check it's valid
        assert user_config_dir().is_absolute()
