"""App guided-release dependency contracts, split by boundary."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Protocol

from ms.core.result import Result
from ms.output.console import ConsoleProtocol
from ms.release.domain.models import AppReleasePlan, PinnedRepo
from ms.release.errors import ReleaseError
from ms.release.flow.app_publish import AppPublishResult
from ms.release.flow.pr_outcome import PrMergeOutcome
from ms.release.infra.github.workflows import BeforeDispatch

from .contracts import (
    CiDependencies,
    ConfirmationDependencies,
    NotesStatusDependencies,
    SessionCleanupDependencies,
    TerminalDependencies,
)
from .sessions import AppReleaseSession


class AppPrepareResultLike(Protocol):
    @property
    def pr(self) -> PrMergeOutcome: ...

    @property
    def source_sha(self) -> str: ...


class AppSessionDependencies(SessionCleanupDependencies, Protocol):
    def save_state(
        self, *, session: AppReleaseSession
    ) -> Result[AppReleaseSession, ReleaseError]: ...


class AppStorageDependencies(AppSessionDependencies, Protocol):
    def bootstrap_session(
        self, *, created_by: str, notes_file: Path | None
    ) -> Result[AppReleaseSession, ReleaseError]: ...


class AppPlanningDependencies(Protocol):
    def plan_app_release(
        self,
        *,
        workspace_root: Path,
        channel: Literal["stable", "beta"],
        bump: Literal["major", "minor", "patch"],
        tag_override: str | None,
        pinned: tuple[PinnedRepo, ...],
    ) -> Result[AppReleasePlan, ReleaseError]: ...


class AppPreparationDependencies[PrepareT: AppPrepareResultLike](NotesStatusDependencies, Protocol):
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


class AppPublicationDependencies(SessionCleanupDependencies, Protocol):
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
        remote_coherence_checked: bool = False,
        request_id: str | None = None,
        before_dispatch: BeforeDispatch | None = None,
    ) -> Result[AppPublishResult, ReleaseError]: ...


class AppConfirmationDependencies[PrepareT: AppPrepareResultLike](
    ConfirmationDependencies,
    CiDependencies,
    AppSessionDependencies,
    AppPreparationDependencies[PrepareT],
    AppPublicationDependencies,
    Protocol,
):
    """Confirm, prepare, persist intent, publish, and reconcile."""


class AppGuidedDependencies[PrepareT: AppPrepareResultLike](
    AppConfirmationDependencies[PrepareT],
    AppStorageDependencies,
    AppPlanningDependencies,
    TerminalDependencies,
    Protocol,
):
    """Complete dependency surface, only for the top-level flow."""

    def preflight(self) -> Result[str, ReleaseError]: ...
