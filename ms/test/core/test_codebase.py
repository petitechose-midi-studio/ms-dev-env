"""Tests for core/codebase.py."""

from __future__ import annotations

from pathlib import Path

from ms.core.codebase import Codebase, CodebaseError, list_all, resolve
from ms.core.result import Err, Ok


# =============================================================================
# Codebase Tests
# =============================================================================


class TestCodebase:
    """Tests for Codebase dataclass."""

    def test_codebase_properties(self, tmp_path: Path) -> None:
        """Test codebase dataclass."""
        codebase = Codebase(
            name="core",
            path=tmp_path / "core",
            sdl_path=tmp_path / "core" / "sdl",
            has_teensy=True,
            has_sdl=True,
        )

        assert codebase.name == "core"
        assert codebase.has_teensy is True
        assert codebase.has_sdl is True
        assert codebase.sdl_path is not None

    def test_codebase_no_sdl(self, tmp_path: Path) -> None:
        """Test codebase without SDL."""
        codebase = Codebase(
            name="test",
            path=tmp_path,
            has_teensy=True,
        )

        assert codebase.has_sdl is False
        assert codebase.sdl_path is None

    def test_codebase_immutable(self, tmp_path: Path) -> None:
        """Test that codebase is immutable."""
        codebase = Codebase(name="test", path=tmp_path)

        # Should raise on modification attempt
        try:
            codebase.name = "other"  # type: ignore
            assert False, "Should have raised"
        except AttributeError:
            pass


# =============================================================================
# CodebaseError Tests
# =============================================================================


class TestCodebaseError:
    """Tests for CodebaseError dataclass."""

    def test_error_with_available(self) -> None:
        """Test error with available codebases."""
        error = CodebaseError(
            name="unknown",
            message="Not found",
            available=("core", "bitwig"),
        )

        assert error.name == "unknown"
        assert "core" in error.available
        assert "bitwig" in error.available

    def test_error_without_available(self) -> None:
        """Test error without available codebases."""
        error = CodebaseError(
            name="test",
            message="Not found",
        )

        assert error.available == ()


# =============================================================================
# resolve Tests
# =============================================================================


class TestResolve:
    """Tests for resolve function."""

    def test_resolve_core(self, tmp_path: Path) -> None:
        """Test resolving core codebase."""
        # Create workspace structure
        (tmp_path / "midi-studio" / "core").mkdir(parents=True)

        result = resolve("core", tmp_path)

        assert isinstance(result, Ok)
        codebase = result.unwrap()
        assert codebase.name == "core"
        assert codebase.path == tmp_path / "midi-studio" / "core"

    def test_resolve_plugin(self, tmp_path: Path) -> None:
        """Test resolving plugin codebase."""
        # Create workspace structure
        (tmp_path / "midi-studio" / "plugin-bitwig").mkdir(parents=True)

        result = resolve("bitwig", tmp_path)

        assert isinstance(result, Ok)
        codebase = result.unwrap()
        assert codebase.name == "bitwig"
        assert codebase.path == tmp_path / "midi-studio" / "plugin-bitwig"

    def test_resolve_not_found(self, tmp_path: Path) -> None:
        """Test resolving nonexistent codebase."""
        (tmp_path / "midi-studio" / "core").mkdir(parents=True)

        result = resolve("unknown", tmp_path)

        assert isinstance(result, Err)
        error = result.unwrap_err()
        assert error.name == "unknown"
        assert "core" in error.available

    def test_resolve_with_teensy(self, tmp_path: Path) -> None:
        """Test resolving codebase with platformio.ini."""
        core = tmp_path / "midi-studio" / "core"
        core.mkdir(parents=True)
        (core / "platformio.ini").touch()

        result = resolve("core", tmp_path)

        assert isinstance(result, Ok)
        assert result.unwrap().has_teensy is True

    def test_resolve_without_teensy(self, tmp_path: Path) -> None:
        """Test resolving codebase without platformio.ini."""
        core = tmp_path / "midi-studio" / "core"
        core.mkdir(parents=True)

        result = resolve("core", tmp_path)

        assert isinstance(result, Ok)
        assert result.unwrap().has_teensy is False

    def test_resolve_with_own_sdl(self, tmp_path: Path) -> None:
        """Test resolving codebase with its own SDL."""
        core = tmp_path / "midi-studio" / "core"
        sdl = core / "sdl"
        sdl.mkdir(parents=True)
        (sdl / "app.cmake").touch()

        result = resolve("core", tmp_path)

        assert isinstance(result, Ok)
        codebase = result.unwrap()
        assert codebase.has_sdl is True
        assert codebase.sdl_path == sdl

    def test_resolve_with_shared_sdl(self, tmp_path: Path) -> None:
        """Test resolving codebase using shared core SDL."""
        # Create plugin without SDL
        plugin = tmp_path / "midi-studio" / "plugin-bitwig"
        plugin.mkdir(parents=True)

        # Create core with SDL
        core_sdl = tmp_path / "midi-studio" / "core" / "sdl"
        core_sdl.mkdir(parents=True)
        (core_sdl / "app.cmake").touch()

        result = resolve("bitwig", tmp_path)

        assert isinstance(result, Ok)
        codebase = result.unwrap()
        assert codebase.has_sdl is True
        assert codebase.sdl_path == core_sdl

    def test_resolve_without_sdl(self, tmp_path: Path) -> None:
        """Test resolving codebase without any SDL."""
        core = tmp_path / "midi-studio" / "core"
        core.mkdir(parents=True)

        result = resolve("core", tmp_path)

        assert isinstance(result, Ok)
        assert result.unwrap().has_sdl is False
        assert result.unwrap().sdl_path is None

    def test_resolve_empty_workspace(self, tmp_path: Path) -> None:
        """Test resolving in empty workspace."""
        result = resolve("core", tmp_path)

        assert isinstance(result, Err)
        error = result.unwrap_err()
        assert error.available == ()


# =============================================================================
# list_all Tests
# =============================================================================


class TestListAll:
    """Tests for list_all function."""

    def test_list_all_with_codebases(self, tmp_path: Path) -> None:
        """Test listing all codebases."""
        (tmp_path / "midi-studio" / "core").mkdir(parents=True)
        (tmp_path / "midi-studio" / "plugin-bitwig").mkdir(parents=True)
        (tmp_path / "midi-studio" / "plugin-test").mkdir(parents=True)

        codebases = list_all(tmp_path)

        assert codebases == ["core", "bitwig", "test"]

    def test_list_all_empty(self, tmp_path: Path) -> None:
        """Test listing codebases in empty workspace."""
        codebases = list_all(tmp_path)

        assert codebases == []

    def test_list_all_only_core(self, tmp_path: Path) -> None:
        """Test listing with only core."""
        (tmp_path / "midi-studio" / "core").mkdir(parents=True)

        codebases = list_all(tmp_path)

        assert codebases == ["core"]

    def test_list_all_only_plugins(self, tmp_path: Path) -> None:
        """Test listing with only plugins."""
        (tmp_path / "midi-studio" / "plugin-foo").mkdir(parents=True)
        (tmp_path / "midi-studio" / "plugin-bar").mkdir(parents=True)

        codebases = list_all(tmp_path)

        assert codebases == ["bar", "foo"]

    def test_list_all_ignores_files(self, tmp_path: Path) -> None:
        """Test that files are ignored."""
        (tmp_path / "midi-studio" / "core").mkdir(parents=True)
        (tmp_path / "midi-studio" / "plugin-bitwig").mkdir(parents=True)
        (tmp_path / "midi-studio" / "README.md").touch()

        codebases = list_all(tmp_path)

        assert codebases == ["core", "bitwig"]

    def test_list_all_ignores_non_plugin_dirs(self, tmp_path: Path) -> None:
        """Test that non-plugin directories are ignored."""
        (tmp_path / "midi-studio" / "core").mkdir(parents=True)
        (tmp_path / "midi-studio" / "shared").mkdir(parents=True)
        (tmp_path / "midi-studio" / "docs").mkdir(parents=True)

        codebases = list_all(tmp_path)

        assert codebases == ["core"]

    def test_list_all_sorted(self, tmp_path: Path) -> None:
        """Test that plugins are sorted alphabetically."""
        (tmp_path / "midi-studio" / "plugin-zebra").mkdir(parents=True)
        (tmp_path / "midi-studio" / "plugin-alpha").mkdir(parents=True)
        (tmp_path / "midi-studio" / "plugin-beta").mkdir(parents=True)

        codebases = list_all(tmp_path)

        assert codebases == ["alpha", "beta", "zebra"]
