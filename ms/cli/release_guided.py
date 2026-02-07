from __future__ import annotations

from pathlib import Path

from ms.cli.release_guided_app import run_guided_app_release
from ms.cli.release_guided_content import run_guided_content_release
from ms.cli.selector import SelectorOption, is_interactive_terminal, select_one
from ms.core.result import Result
from ms.output.console import ConsoleProtocol
from ms.release.flow.guided.router import MenuOption, run_guided_release_flow
from ms.services.release.errors import ReleaseError


def _select_product(
    *,
    title: str,
    subtitle: str,
    options: list[MenuOption[str]],
    initial_index: int,
    allow_back: bool,
):
    selector_options = [
        SelectorOption(value=option.value, label=option.label, detail=option.detail)
        for option in options
    ]
    return select_one(
        title=title,
        subtitle=subtitle,
        options=selector_options,
        initial_index=initial_index,
        allow_back=allow_back,
    )


def run_guided_release(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    notes_file: Path | None,
    watch: bool,
    dry_run: bool,
) -> Result[None, ReleaseError]:
    class _Deps:
        def is_interactive_terminal(self) -> bool:
            return is_interactive_terminal()

        def select_product(
            self,
            *,
            title: str,
            subtitle: str,
            options: list[MenuOption[str]],
            initial_index: int,
            allow_back: bool,
        ):
            return _select_product(
                title=title,
                subtitle=subtitle,
                options=options,
                initial_index=initial_index,
                allow_back=allow_back,
            )

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

    return run_guided_release_flow(
        workspace_root=workspace_root,
        console=console,
        notes_file=notes_file,
        watch=watch,
        dry_run=dry_run,
        deps=_Deps(),
    )
