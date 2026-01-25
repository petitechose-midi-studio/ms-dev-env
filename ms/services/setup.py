from __future__ import annotations

import subprocess
from datetime import datetime

from ms.core.config import Config
from ms.core.workspace import Workspace
from ms.output.console import ConsoleProtocol, Style
from ms.platform.detection import PlatformInfo
from ms.services.check import CheckService
from ms.services.repos import RepoService
from ms.services.toolchains import ToolchainService


class SetupService:
    def __init__(
        self,
        *,
        workspace: Workspace,
        platform: PlatformInfo,
        config: Config | None,
        console: ConsoleProtocol,
    ) -> None:
        self._workspace = workspace
        self._platform = platform
        self._config = config
        self._console = console

    def setup_dev(
        self,
        *,
        mode: str,
        skip_repos: bool,
        skip_tools: bool,
        skip_python: bool,
        skip_check: bool,
        dry_run: bool,
    ) -> bool:
        if mode.lower() != "dev":
            self._console.print("Only --mode dev is supported for now", Style.ERROR)
            return False

        # Ensure state dirs exist
        if not dry_run:
            self._workspace.state_dir.mkdir(parents=True, exist_ok=True)
            self._workspace.cache_dir.mkdir(parents=True, exist_ok=True)
            self._workspace.build_dir.mkdir(parents=True, exist_ok=True)
            self._workspace.bin_dir.mkdir(parents=True, exist_ok=True)
            self._write_state(mode="dev")

        ok = True

        if not skip_repos:
            self._console.header("Repos")
            ok = (
                RepoService(workspace=self._workspace, console=self._console).sync_all(
                    limit=200,
                    dry_run=dry_run,
                )
                and ok
            )

        if not skip_tools:
            self._console.header("Tools")
            ok = (
                ToolchainService(
                    workspace=self._workspace,
                    platform=self._platform,
                    config=self._config,
                    console=self._console,
                ).sync_dev(dry_run=dry_run)
                and ok
            )

        if not skip_python:
            self._console.header("Python deps")
            ok = self._sync_python_deps(dry_run=dry_run) and ok

        if not skip_check:
            self._console.header("Check")
            report = CheckService(
                workspace=self._workspace,
                platform=self._platform,
                config=self._config,
            ).run()
            ok = (not report.has_errors()) and ok

        return ok

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
        proc = subprocess.run(cmd, cwd=str(self._workspace.root), check=False)
        return proc.returncode == 0
