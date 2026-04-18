from __future__ import annotations

from pathlib import Path
from typing import Literal, Protocol

from ms.core.result import Result
from ms.output.console import ConsoleProtocol
from ms.release.domain.models import AppReleasePlan, PinnedRepo
from ms.release.errors import ReleaseError
from ms.release.flow.pr_outcome import PrMergeOutcome

from .menu_option import MenuOption
from .selection import Selection
from .sessions import AppReleaseSession


class AppPrepareResultLike(Protocol):
    @property
    def pr(self) -> PrMergeOutcome: ...

    @property
    def source_sha(self) -> str: ...


class AppGuidedDependencies[PrepareT: AppPrepareResultLike](Protocol):
    def preflight(self) -> Result[str, ReleaseError]: ...

    def bootstrap_session(
        self, *, created_by: str, notes_file: Path | None
    ) -> Result[AppReleaseSession, ReleaseError]: ...

    def save_state(
        self, *, session: AppReleaseSession
    ) -> Result[AppReleaseSession, ReleaseError]: ...

    def clear_session(self) -> Result[None, ReleaseError]: ...

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

    def select_menu(
        self,
        *,
        title: str,
        subtitle: str,
        options: list[MenuOption[str]],
        initial_index: int,
        allow_back: bool,
    ) -> Selection[str]: ...

    def confirm(self, *, prompt: str) -> bool: ...

    def ensure_ci_green(
        self,
        *,
        workspace_root: Path,
        pinned: tuple[PinnedRepo, ...],
        allow_non_green: bool,
    ) -> Result[None, ReleaseError]: ...

    def plan_app_release(
        self,
        *,
        workspace_root: Path,
        channel: Literal["stable", "beta"],
        bump: Literal["major", "minor", "patch"],
        tag_override: str | None,
        pinned: tuple[PinnedRepo, ...],
    ) -> Result[AppReleasePlan, ReleaseError]: ...

    def prepare_app_pr(
        self,
        *,
        workspace_root: Path,
        console: ConsoleProtocol,
        tag: str,
        version: str,
        base_sha: str,
        pinned: tuple[PinnedRepo, ...],
        dry_run: bool,
    ) -> Result[PrepareT, ReleaseError]: ...

    def publish_app_release(
        self,
        *,
        workspace_root: Path,
        console: ConsoleProtocol,
        tag: str,
        source_sha: str,
        tooling_sha: str,
        notes_markdown: str | None,
        notes_source_path: str | None,
        watch: bool,
        dry_run: bool,
    ) -> Result[tuple[str, str], ReleaseError]: ...

    def print_notes_status(
        self,
        *,
        console: ConsoleProtocol,
        notes_markdown: str | None,
        notes_path: str | None,
        notes_sha256: str | None,
        auto_label: str,
    ) -> None: ...
