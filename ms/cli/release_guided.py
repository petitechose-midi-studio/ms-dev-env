from __future__ import annotations

from pathlib import Path

from ms.cli.release_guided_app import run_guided_app_release
from ms.cli.release_guided_content import run_guided_content_release
from ms.cli.release_guided_dependencies import run_guided_dependencies_release
from ms.cli.release_guided_selectors import GuidedCliDependencies
from ms.cli.selector import is_interactive_terminal
from ms.core.result import Result
from ms.output.console import ConsoleProtocol
from ms.release.errors import ReleaseError
from ms.release.flow.guided.router import run_guided_release_flow


def run_guided_release(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    notes_file: Path | None,
    watch: bool,
    dry_run: bool,
) -> Result[None, ReleaseError]:
    class _Deps(GuidedCliDependencies):
        def is_interactive_terminal(self) -> bool:
            return is_interactive_terminal()

        def run_guided_app_release(
            self,
            *,
            workspace_root: Path,
            console: ConsoleProtocol,
            notes_file: Path | None,
            watch: bool,
            dry_run: bool,
        ):
            return run_guided_app_release(
                workspace_root=workspace_root,
                console=console,
                notes_file=notes_file,
                watch=watch,
                dry_run=dry_run,
            )

        def run_guided_content_release(
            self,
            *,
            workspace_root: Path,
            console: ConsoleProtocol,
            notes_file: Path | None,
            watch: bool,
            dry_run: bool,
        ):
            return run_guided_content_release(
                workspace_root=workspace_root,
                console=console,
                notes_file=notes_file,
                watch=watch,
                dry_run=dry_run,
            )

        def run_guided_dependencies_release(
            self,
            *,
            workspace_root: Path,
            console: ConsoleProtocol,
            watch: bool,
            dry_run: bool,
        ):
            return run_guided_dependencies_release(
                workspace_root=workspace_root,
                console=console,
                watch=watch,
                dry_run=dry_run,
            )

    return run_guided_release_flow(
        workspace_root=workspace_root,
        console=console,
        notes_file=notes_file,
        watch=watch,
        dry_run=dry_run,
        deps=_Deps(),
    )
