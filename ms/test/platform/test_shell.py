"""Tests for shell activation script generation."""

import sys
from pathlib import Path

import pytest

from ms.platform.detection import Platform
from ms.platform.shell import (
    generate_activation_scripts,
    generate_bash_activate,
    generate_cmd_activate,
    generate_powershell_activate,
)


@pytest.fixture
def env_vars() -> dict[str, str]:
    """Sample environment variables."""
    return {
        "JAVA_HOME": "/tools/jdk",
        "M2_HOME": "/tools/maven",
    }


@pytest.fixture
def path_additions() -> list[Path]:
    """Sample path additions."""
    return [
        Path("/tools/ninja"),
        Path("/tools/cmake/bin"),
    ]


class TestGenerateBashActivate:
    """Tests for generate_bash_activate."""

    def test_has_shebang(self, env_vars: dict[str, str], path_additions: list[Path]) -> None:
        """Script has bash shebang."""
        content = generate_bash_activate(Path("/tools"), env_vars, path_additions)

        assert content.startswith("#!/usr/bin/env bash")

    def test_uses_lf_endings(self, env_vars: dict[str, str], path_additions: list[Path]) -> None:
        """Script uses LF line endings."""
        content = generate_bash_activate(Path("/tools"), env_vars, path_additions)

        assert "\r\n" not in content
        assert "\n" in content

    def test_exports_env_vars(self, env_vars: dict[str, str], path_additions: list[Path]) -> None:
        """Script exports environment variables."""
        content = generate_bash_activate(Path("/tools"), env_vars, path_additions)

        assert 'export JAVA_HOME="/tools/jdk"' in content
        assert 'export M2_HOME="/tools/maven"' in content

    def test_adds_to_path(self, env_vars: dict[str, str], path_additions: list[Path]) -> None:
        """Script adds directories to PATH."""
        content = generate_bash_activate(Path("/tools"), env_vars, path_additions)

        assert "PATH=" in content
        assert "$PATH" in content

    def test_has_deactivate_function(
        self, env_vars: dict[str, str], path_additions: list[Path]
    ) -> None:
        """Script has deactivate function."""
        content = generate_bash_activate(Path("/tools"), env_vars, path_additions)

        assert "ms_deactivate()" in content
        assert "unset JAVA_HOME" in content

    def test_saves_old_path(self, env_vars: dict[str, str], path_additions: list[Path]) -> None:
        """Script saves original PATH for deactivation."""
        content = generate_bash_activate(Path("/tools"), env_vars, path_additions)

        assert "_MS_OLD_PATH" in content

    def test_empty_env_vars(self, path_additions: list[Path]) -> None:
        """Script handles empty env vars."""
        content = generate_bash_activate(Path("/tools"), {}, path_additions)

        assert "#!/usr/bin/env bash" in content

    def test_empty_path_additions(self, env_vars: dict[str, str]) -> None:
        """Script handles empty path additions."""
        content = generate_bash_activate(Path("/tools"), env_vars, [])

        assert "#!/usr/bin/env bash" in content


class TestGeneratePowershellActivate:
    """Tests for generate_powershell_activate."""

    def test_uses_crlf_endings(self, env_vars: dict[str, str], path_additions: list[Path]) -> None:
        """Script uses CRLF line endings."""
        content = generate_powershell_activate(Path("/tools"), env_vars, path_additions)

        assert "\r\n" in content

    def test_sets_env_vars(self, env_vars: dict[str, str], path_additions: list[Path]) -> None:
        """Script sets environment variables."""
        content = generate_powershell_activate(Path("/tools"), env_vars, path_additions)

        assert "$env:JAVA_HOME" in content
        assert "$env:M2_HOME" in content

    def test_adds_to_path(self, env_vars: dict[str, str], path_additions: list[Path]) -> None:
        """Script adds directories to PATH."""
        content = generate_powershell_activate(Path("/tools"), env_vars, path_additions)

        assert "$env:PATH" in content

    def test_has_deactivate_function(
        self, env_vars: dict[str, str], path_additions: list[Path]
    ) -> None:
        """Script has deactivate function."""
        content = generate_powershell_activate(Path("/tools"), env_vars, path_additions)

        assert "function global:ms_deactivate" in content

    def test_saves_old_values(self, env_vars: dict[str, str], path_additions: list[Path]) -> None:
        """Script saves original values for deactivation."""
        content = generate_powershell_activate(Path("/tools"), env_vars, path_additions)

        assert "_MS_OLD_PATH" in content
        assert "_MS_OLD_JAVA_HOME" in content


class TestGenerateCmdActivate:
    """Tests for generate_cmd_activate."""

    def test_starts_with_echo_off(
        self, env_vars: dict[str, str], path_additions: list[Path]
    ) -> None:
        """Script starts with @echo off."""
        content = generate_cmd_activate(Path("/tools"), env_vars, path_additions)

        assert content.startswith("@echo off")

    def test_uses_crlf_endings(self, env_vars: dict[str, str], path_additions: list[Path]) -> None:
        """Script uses CRLF line endings."""
        content = generate_cmd_activate(Path("/tools"), env_vars, path_additions)

        assert "\r\n" in content

    def test_sets_env_vars(self, env_vars: dict[str, str], path_additions: list[Path]) -> None:
        """Script sets environment variables."""
        content = generate_cmd_activate(Path("/tools"), env_vars, path_additions)

        assert 'set "JAVA_HOME' in content
        assert 'set "M2_HOME' in content

    def test_adds_to_path(self, env_vars: dict[str, str], path_additions: list[Path]) -> None:
        """Script adds directories to PATH."""
        content = generate_cmd_activate(Path("/tools"), env_vars, path_additions)

        assert 'set "PATH=' in content
        assert "%PATH%" in content


class TestGenerateActivationScripts:
    """Tests for generate_activation_scripts."""

    def test_creates_bash_on_linux(
        self,
        tmp_path: Path,
        env_vars: dict[str, str],
        path_additions: list[Path],
    ) -> None:
        """Creates bash script on Linux."""
        result = generate_activation_scripts(tmp_path, env_vars, path_additions, Platform.LINUX)

        assert "bash" in result
        assert result["bash"].exists()
        assert result["bash"].name == "activate.sh"

    def test_creates_bash_on_macos(
        self,
        tmp_path: Path,
        env_vars: dict[str, str],
        path_additions: list[Path],
    ) -> None:
        """Creates bash script on macOS."""
        result = generate_activation_scripts(tmp_path, env_vars, path_additions, Platform.MACOS)

        assert "bash" in result

    def test_creates_all_on_windows(
        self,
        tmp_path: Path,
        env_vars: dict[str, str],
        path_additions: list[Path],
    ) -> None:
        """Creates all scripts on Windows."""
        result = generate_activation_scripts(tmp_path, env_vars, path_additions, Platform.WINDOWS)

        assert "bash" in result
        assert "powershell" in result
        assert "cmd" in result

    def test_creates_directory(
        self,
        tmp_path: Path,
        env_vars: dict[str, str],
        path_additions: list[Path],
    ) -> None:
        """Creates tools directory if needed."""
        tools_dir = tmp_path / "tools"
        generate_activation_scripts(tools_dir, env_vars, path_additions, Platform.LINUX)

        assert tools_dir.exists()

    @pytest.mark.skipif(sys.platform == "win32", reason="chmod doesn't work on Windows")
    def test_bash_executable_on_unix(
        self,
        tmp_path: Path,
        env_vars: dict[str, str],
        path_additions: list[Path],
    ) -> None:
        """Bash script is executable on Unix."""
        result = generate_activation_scripts(tmp_path, env_vars, path_additions, Platform.LINUX)

        bash_path = result["bash"]
        assert bash_path.stat().st_mode & 0o111

    def test_powershell_has_ps1_extension(
        self,
        tmp_path: Path,
        env_vars: dict[str, str],
        path_additions: list[Path],
    ) -> None:
        """PowerShell script has .ps1 extension."""
        result = generate_activation_scripts(tmp_path, env_vars, path_additions, Platform.WINDOWS)

        assert result["powershell"].suffix == ".ps1"

    def test_cmd_has_bat_extension(
        self,
        tmp_path: Path,
        env_vars: dict[str, str],
        path_additions: list[Path],
    ) -> None:
        """Cmd script has .bat extension."""
        result = generate_activation_scripts(tmp_path, env_vars, path_additions, Platform.WINDOWS)

        assert result["cmd"].suffix == ".bat"
