# SPDX-License-Identifier: MIT
"""Tools checker.

Validates that required build tools are installed:
- System tools: git, gh, uv, rustc, cargo
- Bundled tools: cmake, ninja, bun, jdk, maven, platformio
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from ms.core.versions import RUST_MIN_VERSION, RUST_MIN_VERSION_TEXT
from ms.services.checkers.base import CheckResult
from ms.services.checkers.common import (
    CommandRunner,
    DefaultCommandRunner,
    Hints,
    first_line,
    format_version_triplet,
    get_platform_key,
    parse_version_triplet,
)

if TYPE_CHECKING:
    from ms.platform.detection import LinuxDistro, Platform
    from ms.tools.base import Tool


@dataclass(frozen=True, slots=True)
class ToolsChecker:
    """Check that build tools are installed.

    Attributes:
        platform: Current platform for platform-specific checks
        tools_dir: Path to bundled tools directory
        hints: Installation hints
        distro: Linux distribution (for hint lookup)
        runner: Command runner for version checks
    """

    platform: Platform
    tools_dir: Path
    hints: Hints = field(default_factory=Hints.empty)
    distro: LinuxDistro | None = None
    runner: CommandRunner = field(default_factory=DefaultCommandRunner)

    def check_all(self) -> list[CheckResult]:
        """Run all tool checks."""
        results: list[CheckResult] = []

        # System tools (must be in PATH)
        results.append(self.check_system_tool("git", ["--version"]))
        results.append(self.check_system_tool("gh", ["--version"], required=False))
        results.append(self.check_system_tool("uv", ["--version"]))
        results.append(self.check_rustc(required=False))
        results.append(self.check_cargo(required=False))
        results.append(self.check_gh_auth())
        results.append(self.check_python_deps())

        # Bundled tools
        from ms.tools.definitions import (
            BunTool,
            CMakeTool,
            JdkTool,
            MavenTool,
            NinjaTool,
            PlatformioTool,
        )

        results.append(self.check_bundled_tool(CMakeTool(), ["--version"]))
        results.append(self.check_bundled_tool(NinjaTool(), ["--version"]))
        results.append(self.check_bundled_tool(BunTool(), ["--version"], required=False))
        results.append(self.check_bundled_tool(JdkTool(), ["-version"]))
        results.append(self.check_bundled_tool(MavenTool(), ["-version"]))
        results.append(self.check_bundled_tool(PlatformioTool(), ["--version"]))

        return results

    def check_system_tool(
        self,
        name: str,
        version_args: list[str] | None = None,
        *,
        required: bool = True,
    ) -> CheckResult:
        """Check a system tool is available in PATH."""
        path = shutil.which(name)
        if not path:
            hint = self._get_tool_hint(name)
            if required:
                return CheckResult.error(name, "missing", hint=hint)
            return CheckResult.warning(name, "missing (optional)", hint=hint)

        version = self._get_version(name, version_args)
        msg = version if version else "ok"
        return CheckResult.success(name, msg)

    def check_bundled_tool(
        self,
        tool: Tool,
        version_args: list[str] | None = None,
        *,
        required: bool = True,
    ) -> CheckResult:
        """Check a bundled tool is installed."""
        name = tool.spec.id

        # Check bundled location first
        bin_path = tool.bin_path(self.tools_dir, self.platform)
        if bin_path and bin_path.exists():
            version = self._get_version_from_path(bin_path, version_args)
            msg = version if version else "ok"
            return CheckResult.success(name, msg)

        # Check PATH fallback
        system_path = shutil.which(name)
        if system_path:
            version = self._get_version(name, version_args)
            msg = version if version else "ok"
            return CheckResult.success(name, msg)

        hint = self._get_tool_hint(name)
        if required:
            return CheckResult.error(name, "missing", hint=hint)
        return CheckResult.warning(name, "missing (optional)", hint=hint)

    def check_rustc(self, *, required: bool = False) -> CheckResult:
        """Check rustc is installed and meets the minimum version."""
        if not shutil.which("rustc"):
            hint = self._rust_hint()
            if required:
                return CheckResult.error(
                    "rustc",
                    f"missing (>= {RUST_MIN_VERSION_TEXT} required)",
                    hint=hint,
                )
            return CheckResult.warning(
                "rustc",
                "missing (optional)",
                hint=hint,
            )

        version_line = self._get_version("rustc", ["--version"])
        return self._check_min_version("rustc", version_line, required=required)

    def check_cargo(self, *, required: bool = False) -> CheckResult:
        """Check cargo is installed and meets the minimum version."""
        if not shutil.which("cargo"):
            hint = self._rust_hint()
            if required:
                return CheckResult.error(
                    "cargo",
                    f"missing (>= {RUST_MIN_VERSION_TEXT} required)",
                    hint=hint,
                )
            return CheckResult.warning(
                "cargo",
                "missing (optional)",
                hint=hint,
            )

        version_line = self._get_version("cargo", ["--version"])
        return self._check_min_version("cargo", version_line, required=required)

    def _check_min_version(self, name: str, version_line: str, *, required: bool) -> CheckResult:
        """Validate that a Rust tool meets the minimum version."""
        if not version_line:
            return CheckResult.success(name, "ok")

        actual = parse_version_triplet(version_line)
        if actual is None:
            return CheckResult.success(name, version_line)

        if actual < RUST_MIN_VERSION:
            hint = self._rust_hint()
            found = format_version_triplet(actual)
            if required:
                return CheckResult.error(
                    name,
                    f"too old (found {found}, need >= {RUST_MIN_VERSION_TEXT})",
                    hint=hint,
                )
            return CheckResult.warning(
                name,
                f"too old (found {found}, need >= {RUST_MIN_VERSION_TEXT})",
                hint=hint,
            )

        return CheckResult.success(name, version_line)

    def _rust_hint(self) -> str:
        hint = self._get_tool_hint("cargo")
        return hint or "Install rustup: https://rustup.rs"

    def check_gh_auth(self) -> CheckResult:
        """Check GitHub CLI authentication status."""
        if not shutil.which("gh"):
            return CheckResult.warning("gh auth", "gh not installed")

        try:
            result = self.runner.run(["gh", "auth", "status"])
            if result.returncode == 0:
                return CheckResult.success("gh auth", "authenticated")
            return CheckResult.warning(
                "gh auth",
                "not logged in",
                hint="Run: gh auth login",
            )
        except OSError:
            return CheckResult.warning("gh auth", "check failed")

    def check_python_deps(self) -> CheckResult:
        """Check Python dependencies are synced."""
        if not shutil.which("uv"):
            return CheckResult.warning("python deps", "uv not installed")

        try:
            workspace_root = self.tools_dir.parent
            # Keep dev tooling (pytest/pyright) in sync too.
            result = self.runner.run(
                ["uv", "sync", "--check", "--extra", "dev"], cwd=workspace_root
            )
            if result.returncode == 0:
                return CheckResult.success("python deps", "synced (.venv)")
            return CheckResult.warning(
                "python deps",
                "not synced",
                hint="Run: uv sync --frozen --extra dev",
            )
        except OSError:
            return CheckResult.warning("python deps", "check failed")

    def _get_version(self, name: str, version_args: list[str] | None) -> str:
        """Get version string by running command."""
        if not version_args:
            return ""
        try:
            result = self.runner.run([name, *version_args])
            if result.returncode == 0:
                return first_line(result.stdout + result.stderr)
        except OSError:
            pass
        return ""

    def _get_version_from_path(self, path: Path, version_args: list[str] | None) -> str:
        """Get version string by running specific binary."""
        if not version_args:
            return ""
        try:
            result = self.runner.run([str(path), *version_args])
            if result.returncode == 0:
                return first_line(result.stdout + result.stderr)
        except OSError:
            pass
        return ""

    def _get_tool_hint(self, tool_id: str) -> str | None:
        """Get installation hint for a tool."""
        platform_key = get_platform_key(self.platform, self.distro)
        hint = self.hints.get_tool_hint(tool_id, platform_key)

        # Prefer `winget` for selected tools on Windows when available.
        if tool_id == "git" and platform_key == "windows":
            if shutil.which("winget"):
                return "winget install --id Git.Git -e"
            return hint or "Install Git for Windows: https://git-scm.com/"

        if tool_id == "uv" and platform_key == "windows":
            if shutil.which("winget"):
                return "winget install --id astral-sh.uv -e"
            return hint or "Install uv: https://docs.astral.sh/uv/getting-started/installation/"

        return hint
