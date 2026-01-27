from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

from ms.core.config import Config
from ms.core.result import Err, Ok, Result
from ms.core.workspace import Workspace
from ms.output.console import ConsoleProtocol, Style
from ms.platform.detection import PlatformInfo
from ms.services.checkers.base import CheckResult, CheckStatus
from ms.services.system_install import SystemInstaller


@dataclass(frozen=True, slots=True)
class PrereqsError:
    kind: Literal["missing", "manual_required", "install_failed"]
    message: str
    hint: str | None = None


class PrereqsService:
    def __init__(
        self,
        *,
        workspace: Workspace,
        platform: PlatformInfo,
        config: Config | None,
        console: ConsoleProtocol,
        confirm: Callable[[str], bool] | None = None,
    ) -> None:
        self._workspace = workspace
        self._platform = platform
        self._config = config
        self._console = console
        self._confirm = confirm

    def ensure(
        self,
        *,
        require_git: bool,
        require_uv: bool,
        install: bool,
        dry_run: bool,
        assume_yes: bool,
        fail_if_missing: bool,
    ) -> Result[None, PrereqsError]:
        """Check prerequisites and (optionally) install safe ones."""
        self._console.header("Prerequisites")

        issues = self._check(
            require_git=require_git,
            require_uv=require_uv,
        )

        if not issues:
            self._console.success("All prerequisites installed")
            return Ok(None)

        for r in issues:
            self._console.print(f"  {r.name}: {r.message}", Style.ERROR)
        self._console.newline()

        hinted = [r for r in issues if r.hint and r.hint.strip()]
        installer = SystemInstaller(console=self._console, confirm=self._confirm)
        plan = installer.plan_installation(hinted)

        # Always show the plan. Only execute if install=True and dry_run=False.
        execute = install and not dry_run
        installer_ok = installer.apply(plan, dry_run=not execute, assume_yes=assume_yes)

        if dry_run:
            return Ok(None)

        if not install:
            if fail_if_missing:
                return Err(
                    PrereqsError(
                        kind="missing",
                        message="Prerequisites are missing",
                        hint="Run with --install or see 'uv run ms check'",
                    )
                )
            return Ok(None)

        if plan.manual:
            return Err(
                PrereqsError(
                    kind="manual_required",
                    message="Prerequisites require manual steps",
                    hint="Run 'uv run ms check' for details",
                )
            )

        if not installer_ok:
            return Err(
                PrereqsError(
                    kind="install_failed",
                    message="Prerequisites installation did not complete",
                    hint="Run 'uv run ms check' for details",
                )
            )

        remaining = self._check(
            require_git=require_git,
            require_uv=require_uv,
        )
        if remaining:
            return Err(
                PrereqsError(
                    kind="missing",
                    message="Prerequisites are still missing after installation",
                    hint="Run 'uv run ms check' for details",
                )
            )

        return Ok(None)

    def _check(
        self,
        *,
        require_git: bool,
        require_uv: bool,
    ) -> list[CheckResult]:
        from ms.services.checkers import SystemChecker, ToolsChecker, load_hints

        hints = load_hints()
        tools_dir = self._workspace.root / (self._config.paths.tools if self._config else "tools")

        system_checker = SystemChecker(
            platform=self._platform.platform,
            distro=self._platform.distro,
            tools_dir=tools_dir,
            hints=hints,
        )
        issues: list[CheckResult] = [
            r for r in system_checker.check_all() if r.status == CheckStatus.ERROR
        ]

        tools_checker = ToolsChecker(
            platform=self._platform.platform,
            tools_dir=tools_dir,
            hints=hints,
            distro=self._platform.distro,
        )

        # Rust toolchain is required (oc-bridge).
        rustc = tools_checker.check_rustc()
        if rustc.status != CheckStatus.OK:
            issues.append(rustc)

        cargo = tools_checker.check_cargo()
        if cargo.status != CheckStatus.OK:
            issues.append(cargo)

        if require_uv:
            uv = tools_checker.check_system_tool("uv", ["--version"])
            if uv.status != CheckStatus.OK:
                issues.append(uv)

        if require_git:
            git = tools_checker.check_system_tool("git", ["--version"])
            if git.status != CheckStatus.OK:
                issues.append(git)

        return issues
