# SPDX-License-Identifier: MIT
"""Tests for ToolsChecker."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ms.platform.detection import LinuxDistro, Platform
from ms.services.checkers.base import CheckStatus
from ms.services.checkers.common import Hints
from ms.services.checkers.tools import ToolsChecker


class MockCommandRunner:
    """Mock command runner for testing."""

    def __init__(self, responses: dict[tuple[str, ...], tuple[int, str, str]] | None = None):
        """Initialize with canned responses.

        Args:
            responses: Dict mapping command tuples to (returncode, stdout, stderr)
        """
        self.responses = responses or {}
        self.calls: list[list[str]] = []

    def run(
        self, args: list[str], *, capture: bool = True, cwd: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        """Return canned response for command."""
        self.calls.append(args)
        key = tuple(args)
        if key in self.responses:
            rc, stdout, stderr = self.responses[key]
            return subprocess.CompletedProcess(args, rc, stdout, stderr)
        # Default: command not found
        raise FileNotFoundError(f"Command not found: {args[0]}")


class TestToolsCheckerSystemTool:
    """Tests for check_system_tool method."""

    def test_tool_found_with_version(self, tmp_path: Path) -> None:
        runner = MockCommandRunner(
            {
                ("git", "--version"): (0, "git version 2.43.0", ""),
            }
        )
        checker = ToolsChecker(
            platform=Platform.LINUX,
            tools_dir=tmp_path / "tools",
            runner=runner,
        )
        with patch("shutil.which", return_value="/usr/bin/git"):
            result = checker.check_system_tool("git", ["--version"])

        assert result.status == CheckStatus.OK
        assert "git version 2.43.0" in result.message

    def test_tool_not_found_required(self, tmp_path: Path) -> None:
        hints = Hints(tools={"git": {"debian": "sudo apt install git"}})
        checker = ToolsChecker(
            platform=Platform.LINUX,
            tools_dir=tmp_path / "tools",
            hints=hints,
            distro=LinuxDistro.DEBIAN,
        )
        with patch("shutil.which", return_value=None):
            result = checker.check_system_tool("git", ["--version"])

        assert result.status == CheckStatus.ERROR
        assert result.hint == "sudo apt install git"

    def test_tool_not_found_optional(self, tmp_path: Path) -> None:
        hints = Hints(tools={"gh": {"debian": "sudo apt install gh"}})
        checker = ToolsChecker(
            platform=Platform.LINUX,
            tools_dir=tmp_path / "tools",
            hints=hints,
            distro=LinuxDistro.DEBIAN,
        )
        with patch("shutil.which", return_value=None):
            result = checker.check_system_tool("gh", ["--version"], required=False)

        assert result.status == CheckStatus.WARNING
        assert "optional" in result.message
        assert result.hint == "sudo apt install gh"

    def test_tool_found_no_version_args(self, tmp_path: Path) -> None:
        checker = ToolsChecker(
            platform=Platform.LINUX,
            tools_dir=tmp_path / "tools",
        )
        with patch("shutil.which", return_value="/usr/bin/git"):
            result = checker.check_system_tool("git", None)

        assert result.status == CheckStatus.OK
        assert result.message == "ok"


class TestToolsCheckerBundledTool:
    """Tests for check_bundled_tool method."""

    def test_bundled_tool_found(self, tmp_path: Path) -> None:
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()

        # Create mock binary
        cmake_dir = tools_dir / "cmake" / "bin"
        cmake_dir.mkdir(parents=True)
        cmake_bin = cmake_dir / "cmake.exe"
        cmake_bin.write_text("mock")

        runner = MockCommandRunner(
            {
                (str(cmake_bin), "--version"): (0, "cmake version 3.28.0", ""),
            }
        )

        checker = ToolsChecker(
            platform=Platform.WINDOWS,
            tools_dir=tools_dir,
            runner=runner,
        )

        # Create mock tool
        tool = MagicMock()
        tool.spec.id = "cmake"
        tool.bin_path.return_value = cmake_bin

        result = checker.check_bundled_tool(tool, ["--version"])

        assert result.status == CheckStatus.OK
        assert "cmake version 3.28.0" in result.message

    def test_bundled_tool_not_found_falls_back_to_path(self, tmp_path: Path) -> None:
        runner = MockCommandRunner(
            {
                ("cmake", "--version"): (0, "cmake version 3.27.0", ""),
            }
        )

        checker = ToolsChecker(
            platform=Platform.LINUX,
            tools_dir=tmp_path / "tools",
            runner=runner,
        )

        tool = MagicMock()
        tool.spec.id = "cmake"
        tool.bin_path.return_value = None

        with patch("shutil.which", return_value="/usr/bin/cmake"):
            result = checker.check_bundled_tool(tool, ["--version"])

        assert result.status == CheckStatus.OK
        assert "cmake version 3.27.0" in result.message

    def test_bundled_tool_not_found_required(self, tmp_path: Path) -> None:
        hints = Hints(tools={"cmake": {"debian": "sudo apt install cmake"}})
        checker = ToolsChecker(
            platform=Platform.LINUX,
            tools_dir=tmp_path / "tools",
            hints=hints,
            distro=LinuxDistro.DEBIAN,
        )

        tool = MagicMock()
        tool.spec.id = "cmake"
        tool.bin_path.return_value = None

        with patch("shutil.which", return_value=None):
            result = checker.check_bundled_tool(tool, ["--version"])

        assert result.status == CheckStatus.ERROR
        assert result.hint == "sudo apt install cmake"

    def test_bundled_tool_not_found_optional(self, tmp_path: Path) -> None:
        checker = ToolsChecker(
            platform=Platform.LINUX,
            tools_dir=tmp_path / "tools",
        )

        tool = MagicMock()
        tool.spec.id = "bun"
        tool.bin_path.return_value = None

        with patch("shutil.which", return_value=None):
            result = checker.check_bundled_tool(tool, ["--version"], required=False)

        assert result.status == CheckStatus.WARNING
        assert "optional" in result.message


class TestToolsCheckerCargo:
    """Tests for check_cargo method."""

    def test_cargo_found(self, tmp_path: Path) -> None:
        runner = MockCommandRunner(
            {
                ("cargo", "--version"): (0, "cargo 1.75.0 (1d8b05cdd 2023-11-20)", ""),
            }
        )
        checker = ToolsChecker(
            platform=Platform.LINUX,
            tools_dir=tmp_path / "tools",
            runner=runner,
        )
        with patch("shutil.which", return_value="/home/user/.cargo/bin/cargo"):
            result = checker.check_cargo()

        assert result.status == CheckStatus.OK
        assert "cargo 1.75.0" in result.message

    def test_cargo_not_found(self, tmp_path: Path) -> None:
        hints = Hints(tools={"cargo": {"debian": "curl ... rustup.rs"}})
        checker = ToolsChecker(
            platform=Platform.LINUX,
            tools_dir=tmp_path / "tools",
            hints=hints,
            distro=LinuxDistro.DEBIAN,
        )
        with patch("shutil.which", return_value=None):
            result = checker.check_cargo()

        assert result.status == CheckStatus.WARNING
        assert "curl ... rustup.rs" in (result.hint or "")


class TestToolsCheckerGhAuth:
    """Tests for check_gh_auth method."""

    def test_gh_not_installed(self, tmp_path: Path) -> None:
        checker = ToolsChecker(
            platform=Platform.LINUX,
            tools_dir=tmp_path / "tools",
        )
        with patch("shutil.which", return_value=None):
            result = checker.check_gh_auth()

        assert result.status == CheckStatus.WARNING
        assert "gh not installed" in result.message

    def test_gh_authenticated(self, tmp_path: Path) -> None:
        runner = MockCommandRunner(
            {
                ("gh", "auth", "status"): (0, "Logged in to github.com", ""),
            }
        )
        checker = ToolsChecker(
            platform=Platform.LINUX,
            tools_dir=tmp_path / "tools",
            runner=runner,
        )
        with patch("shutil.which", return_value="/usr/bin/gh"):
            result = checker.check_gh_auth()

        assert result.status == CheckStatus.OK
        assert "authenticated" in result.message

    def test_gh_not_authenticated(self, tmp_path: Path) -> None:
        runner = MockCommandRunner(
            {
                ("gh", "auth", "status"): (1, "", "not logged in"),
            }
        )
        checker = ToolsChecker(
            platform=Platform.LINUX,
            tools_dir=tmp_path / "tools",
            runner=runner,
        )
        with patch("shutil.which", return_value="/usr/bin/gh"):
            result = checker.check_gh_auth()

        assert result.status == CheckStatus.WARNING
        assert "gh auth login" in (result.hint or "")


class TestToolsCheckerPythonDeps:
    """Tests for check_python_deps method."""

    def test_uv_not_installed(self, tmp_path: Path) -> None:
        checker = ToolsChecker(
            platform=Platform.LINUX,
            tools_dir=tmp_path / "tools",
        )
        with patch("shutil.which", return_value=None):
            result = checker.check_python_deps()

        assert result.status == CheckStatus.WARNING
        assert "uv not installed" in result.message

    def test_deps_synced(self, tmp_path: Path) -> None:
        runner = MockCommandRunner(
            {
                ("uv", "sync", "--check", "--extra", "dev"): (0, "", ""),
            }
        )
        checker = ToolsChecker(
            platform=Platform.LINUX,
            tools_dir=tmp_path / "tools",
            runner=runner,
        )
        with patch("shutil.which", return_value="/usr/bin/uv"):
            result = checker.check_python_deps()

        assert result.status == CheckStatus.OK
        assert "synced" in result.message

    def test_deps_not_synced(self, tmp_path: Path) -> None:
        runner = MockCommandRunner(
            {
                ("uv", "sync", "--check", "--extra", "dev"): (1, "", "Would update: foo"),
            }
        )
        checker = ToolsChecker(
            platform=Platform.LINUX,
            tools_dir=tmp_path / "tools",
            runner=runner,
        )
        with patch("shutil.which", return_value="/usr/bin/uv"):
            result = checker.check_python_deps()

        assert result.status == CheckStatus.WARNING
        assert "uv sync" in (result.hint or "")


class TestToolsCheckerHints:
    """Tests for hint lookup by platform."""

    def test_hint_lookup_linux_debian(self, tmp_path: Path) -> None:
        hints = Hints(
            tools={
                "git": {
                    "debian": "sudo apt install git",
                    "fedora": "sudo dnf install git",
                }
            }
        )
        checker = ToolsChecker(
            platform=Platform.LINUX,
            tools_dir=tmp_path / "tools",
            hints=hints,
            distro=LinuxDistro.DEBIAN,
        )
        with patch("shutil.which", return_value=None):
            result = checker.check_system_tool("git", ["--version"])

        assert result.hint == "sudo apt install git"

    def test_hint_lookup_linux_fedora(self, tmp_path: Path) -> None:
        hints = Hints(
            tools={
                "git": {
                    "debian": "sudo apt install git",
                    "fedora": "sudo dnf install git",
                }
            }
        )
        checker = ToolsChecker(
            platform=Platform.LINUX,
            tools_dir=tmp_path / "tools",
            hints=hints,
            distro=LinuxDistro.FEDORA,
        )
        with patch("shutil.which", return_value=None):
            result = checker.check_system_tool("git", ["--version"])

        assert result.hint == "sudo dnf install git"

    def test_hint_lookup_windows(self, tmp_path: Path) -> None:
        hints = Hints(tools={"git": {"windows": "Download from https://git-scm.com"}})
        checker = ToolsChecker(
            platform=Platform.WINDOWS,
            tools_dir=tmp_path / "tools",
            hints=hints,
        )
        with patch("shutil.which", return_value=None):
            result = checker.check_system_tool("git", ["--version"])

        assert result.hint == "Download from https://git-scm.com"


class TestToolsCheckerFrozen:
    """Tests for dataclass immutability."""

    def test_frozen(self, tmp_path: Path) -> None:
        checker = ToolsChecker(
            platform=Platform.LINUX,
            tools_dir=tmp_path / "tools",
        )
        with pytest.raises(AttributeError):
            checker.platform = Platform.WINDOWS  # type: ignore[misc]
