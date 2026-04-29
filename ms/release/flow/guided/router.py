from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ms.core.result import Err, Result
from ms.output.console import ConsoleProtocol
from ms.release.errors import ReleaseError

from .selection import Selection


@dataclass(frozen=True, slots=True)
class MenuOption[T]:
    value: T
    label: str
    detail: str | None = None


class GuidedRouterDependencies(Protocol):
    def is_interactive_terminal(self) -> bool: ...

    def select_product(
        self,
        *,
        title: str,
        subtitle: str,
        options: list[MenuOption[str]],
        initial_index: int,
        allow_back: bool,
    ) -> Selection[str]: ...

    def run_guided_app_release(
        self,
        *,
        workspace_root: Path,
        console: ConsoleProtocol,
        notes_file: Path | None,
        watch: bool,
        dry_run: bool,
    ) -> Result[None, ReleaseError]: ...

    def run_guided_content_release(
        self,
        *,
        workspace_root: Path,
        console: ConsoleProtocol,
        notes_file: Path | None,
        watch: bool,
        dry_run: bool,
    ) -> Result[None, ReleaseError]: ...

    def run_guided_dependencies_release(
        self,
        *,
        workspace_root: Path,
        console: ConsoleProtocol,
        notes_file: Path | None,
        watch: bool,
        dry_run: bool,
    ) -> Result[None, ReleaseError]: ...


def run_guided_release_flow(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    notes_file: Path | None,
    watch: bool,
    dry_run: bool,
    deps: GuidedRouterDependencies,
) -> Result[None, ReleaseError]:
    if not deps.is_interactive_terminal():
        return Err(
            ReleaseError(
                kind="invalid_input",
                message="guided release requires an interactive TTY",
                hint="Run from a terminal and use arrow keys + Enter.",
            )
        )

    product = deps.select_product(
        title="Release Product",
        subtitle="Choose release type",
        options=[
            MenuOption(
                value="dependencies",
                label="dependencies",
                detail="promote validated dev workspace dependencies",
            ),
            MenuOption(value="app", label="app", detail="ms-manager desktop application"),
            MenuOption(
                value="content",
                label="content",
                detail="distribution/runtime content release",
            ),
        ],
        initial_index=0,
        allow_back=False,
    )
    if product.action == "cancel":
        return Err(ReleaseError(kind="invalid_input", message="release cancelled"))

    if product.value == "content":
        return deps.run_guided_content_release(
            workspace_root=workspace_root,
            console=console,
            notes_file=notes_file,
            watch=watch,
            dry_run=dry_run,
        )

    if product.value == "dependencies":
        return deps.run_guided_dependencies_release(
            workspace_root=workspace_root,
            console=console,
            notes_file=notes_file,
            watch=watch,
            dry_run=dry_run,
        )

    return deps.run_guided_app_release(
        workspace_root=workspace_root,
        console=console,
        notes_file=notes_file,
        watch=watch,
        dry_run=dry_run,
    )
