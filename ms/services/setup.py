from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Callable, Literal

from ms.core.config import Config
from ms.core.result import Err, Ok, Result
from ms.core.workspace import Workspace
from ms.output.console import ConsoleProtocol, Style
from ms.platform.detection import PlatformInfo
from ms.platform.process import run_silent
from ms.services.check import CheckService
from ms.services.bridge import BridgeService
from ms.services.repos import RepoService
from ms.services.repo_profiles import RepoProfile, repo_manifest_path
from ms.services.prereqs import PrereqsService
from ms.services.toolchains import ToolchainService

if TYPE_CHECKING:
    from ms.services.check import CheckReport


# -----------------------------------------------------------------------------
# Error Types
# -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SetupError:
    """Error from setup operations."""

    kind: Literal[
        "mode_unsupported",
        "bridge_failed",
        "repos_failed",
        "tools_failed",
        "python_failed",
        "check_failed",
        "system_deps_failed",
    ]
    message: str
    hint: str | None = None


class SetupService:
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

    def setup_dev(
        self,
        *,
        mode: str,
        repo_profile: RepoProfile = RepoProfile.dev,
        skip_repos: bool,
        skip_tools: bool,
        skip_python: bool,
        skip_check: bool,
        skip_prereqs: bool = False,
        dry_run: bool,
        assume_yes: bool = False,
    ) -> Result[None, SetupError]:
        if mode.lower() != "dev":
            return Err(
                SetupError(
                    kind="mode_unsupported",
                    message=f"mode '{mode}' is not supported",
                    hint="use --mode dev",
                )
            )

        # Ensure state dirs exist
        if not dry_run:
            self._workspace.state_dir.mkdir(parents=True, exist_ok=True)
            self._workspace.cache_dir.mkdir(parents=True, exist_ok=True)
            self._workspace.build_dir.mkdir(parents=True, exist_ok=True)
            self._workspace.bin_dir.mkdir(parents=True, exist_ok=True)
            self._write_state(mode="dev")

        # Check and install host dependencies first.
        if not skip_prereqs:
            require_git_for_tools = False
            if not skip_tools:
                require_git_for_tools = ToolchainService(
                    workspace=self._workspace,
                    platform=self._platform,
                    config=self._config,
                    console=self._console,
                ).needs_git_for_sync_dev()

            prereqs_result = PrereqsService(
                workspace=self._workspace,
                platform=self._platform,
                config=self._config,
                console=self._console,
                confirm=self._confirm,
            ).ensure(
                require_git=(not skip_repos) or require_git_for_tools,
                require_uv=not skip_python,
                install=True,
                dry_run=dry_run,
                assume_yes=assume_yes,
                fail_if_missing=not dry_run,
            )
            if isinstance(prereqs_result, Err):
                return Err(
                    SetupError(
                        kind="system_deps_failed",
                        message=prereqs_result.error.message,
                        hint=prereqs_result.error.hint,
                    )
                )

        if not skip_repos:
            self._console.header("Repos")
            manifest_path = repo_manifest_path(repo_profile)
            result = RepoService(
                workspace=self._workspace,
                console=self._console,
                manifest_path=manifest_path,
            ).sync_all(
                dry_run=dry_run,
            )
            if isinstance(result, Err):
                return Err(
                    SetupError(
                        kind="repos_failed",
                        message=result.error.message,
                    )
                )

        # oc-bridge is required for the dev environment.
        self._console.header("Bridge")
        bridge_result = BridgeService(
            workspace=self._workspace,
            platform=self._platform,
            config=self._config,
            console=self._console,
        ).install_prebuilt(dry_run=dry_run)
        if isinstance(bridge_result, Err):
            return Err(
                SetupError(
                    kind="bridge_failed",
                    message=bridge_result.error.message,
                    hint=bridge_result.error.hint,
                )
            )

        if not skip_tools:
            self._console.header("Tools")
            result = ToolchainService(
                workspace=self._workspace,
                platform=self._platform,
                config=self._config,
                console=self._console,
            ).sync_dev(dry_run=dry_run)
            if isinstance(result, Err):
                return Err(
                    SetupError(
                        kind="tools_failed",
                        message=result.error.message,
                    )
                )

        if not skip_python:
            self._console.header("Python deps")
            if not self._sync_python_deps(dry_run=dry_run):
                return Err(
                    SetupError(
                        kind="python_failed",
                        message="uv sync failed",
                    )
                )

        if not skip_check:
            self._console.header("Check")
            report = CheckService(
                workspace=self._workspace,
                platform=self._platform,
                config=self._config,
            ).run()
            if report.has_errors() and not dry_run:
                self._print_check_issues(report)
                return Err(
                    SetupError(
                        kind="check_failed",
                        message="workspace check found errors",
                        hint="Run: uv run ms check",
                    )
                )

        return Ok(None)

    def _print_check_issues(self, report: "CheckReport") -> None:
        from ms.services.checkers import CheckStatus

        def print_group(title: str, results: Sequence[object]) -> None:
            issues = [r for r in results if getattr(r, "status", None) != CheckStatus.OK]
            if not issues:
                return
            self._console.print(title, Style.DIM)
            for r in issues:
                status = getattr(r, "status", None)
                name = getattr(r, "name", "")
                message = getattr(r, "message", "")
                hint = getattr(r, "hint", None)

                style = Style.ERROR if status == CheckStatus.ERROR else Style.WARNING
                self._console.print(f"{name}: {message}", style)
                if hint:
                    self._console.print(f"hint: {hint}", Style.DIM)

        self._console.newline()
        self._console.error("Environment check failed")
        print_group("Workspace", report.workspace)
        print_group("Tools", report.tools)
        print_group("System", report.system)
        print_group("Runtime", report.runtime)

    def _write_state(self, *, mode: str) -> None:
        # Minimal, forward-compatible state.
        # END-USER mode will extend this file later.
        content = "\n".join(
            [
                f'mode = "{mode}"',
                f'updated_at = "{datetime.now().isoformat()}"',
                "",
            ]
        )
        self._workspace.state_path.write_text(content, encoding="utf-8")

    def _sync_python_deps(self, *, dry_run: bool) -> bool:
        cmd = ["uv", "sync", "--frozen", "--extra", "dev"]
        self._console.print(" ".join(cmd), Style.DIM)
        if dry_run:
            return True
        result = run_silent(cmd, cwd=self._workspace.root)
        return not isinstance(result, Err)
