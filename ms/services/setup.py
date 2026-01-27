from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Literal

from ms.core.config import Config
from ms.core.result import Err, Ok, Result
from ms.core.workspace import Workspace
from ms.output.console import ConsoleProtocol, Style
from ms.platform.detection import PlatformInfo
from ms.platform.process import run_silent
from ms.services.check import CheckService
from ms.services.bridge import BridgeService
from ms.services.repos import RepoService
from ms.services.prereqs import PrereqsService
from ms.services.toolchains import ToolchainService


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
                require_gh=not skip_repos,
                require_gh_auth=not skip_repos,
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
            result = RepoService(workspace=self._workspace, console=self._console).sync_all(
                limit=200,
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
        ).build(dry_run=dry_run)
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
            if report.has_errors():
                return Err(
                    SetupError(
                        kind="check_failed",
                        message="workspace check found errors",
                    )
                )

        return Ok(None)

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
