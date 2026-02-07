from __future__ import annotations

from pathlib import Path

from ms.cli.release_guided_app import run_guided_app_release
from ms.cli.release_guided_content import run_guided_content_release
from ms.cli.selector import SelectorOption, is_interactive_terminal, select_one
from ms.core.result import Err, Result
from ms.output.console import ConsoleProtocol
from ms.services.release.errors import ReleaseError


def run_guided_release(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    notes_file: Path | None,
    watch: bool,
    dry_run: bool,
) -> Result[None, ReleaseError]:
    if not is_interactive_terminal():
        return Err(
            ReleaseError(
                kind="invalid_input",
                message="guided release requires an interactive TTY",
                hint="Run from a terminal and use arrow keys + Enter.",
            )
        )

    product = select_one(
        title="Release Product",
        subtitle="Choose release type",
        options=[
            SelectorOption(value="app", label="app", detail="ms-manager desktop application"),
            SelectorOption(
                value="content", label="content", detail="distribution/runtime content release"
            ),
        ],
        initial_index=0,
        allow_back=False,
    )
    if product.action == "cancel":
        return Err(ReleaseError(kind="invalid_input", message="release cancelled"))

    if product.value == "content":
        return run_guided_content_release(
            workspace_root=workspace_root,
            console=console,
            notes_file=notes_file,
            watch=watch,
            dry_run=dry_run,
        )

    return run_guided_app_release(
        workspace_root=workspace_root,
        console=console,
        notes_file=notes_file,
        watch=watch,
        dry_run=dry_run,
    )
