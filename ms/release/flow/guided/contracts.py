"""Shared guided-release boundary contracts."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Protocol

from ms.core.result import Result
from ms.output.console import ConsoleProtocol
from ms.release.domain.models import PinnedRepo
from ms.release.errors import ReleaseError

from .menu_option import MenuOption
from .selection import Selection


class MenuDependencies(Protocol):
    def select_menu(
        self,
        *,
        title: str,
        subtitle: str,
        options: list[MenuOption[str]],
        initial_index: int,
        allow_back: bool,
    ) -> Selection[str]: ...


class ConfirmationDependencies(MenuDependencies, Protocol):
    def confirm(self, *, prompt: str) -> bool: ...


class NotesStatusDependencies(Protocol):
    def print_notes_status(
        self,
        *,
        console: ConsoleProtocol,
        notes_markdown: str | None,
        notes_path: str | None,
        notes_sha256: str | None,
        auto_label: str,
    ) -> None: ...


class CiDependencies(Protocol):
    def ensure_ci_green(
        self,
        *,
        workspace_root: Path,
        pinned: tuple[PinnedRepo, ...],
        allow_non_green: bool,
    ) -> Result[None, ReleaseError]: ...


class SessionCleanupDependencies(Protocol):
    def clear_session(self) -> Result[None, ReleaseError]: ...


class TerminalDependencies(ConfirmationDependencies, NotesStatusDependencies, Protocol):
    """Interactive terminal boundary; no release or storage operations."""

    def select_channel(
        self, *, title: str, subtitle: str, initial_index: int, allow_back: bool
    ) -> Selection[Literal["stable", "beta"]]: ...

    def select_bump(
        self, *, title: str, subtitle: str, initial_index: int, allow_back: bool
    ) -> Selection[Literal["major", "minor", "patch"]]: ...

    def select_green_commit(
        self,
        *,
        workspace_root: Path,
        repo_slug: str,
        ref: str,
        workflow_file: str | None,
        title: str,
        subtitle: str,
        current_sha: str | None,
        initial_index: int,
        allow_back: bool,
    ) -> Result[Selection[str], ReleaseError]: ...
