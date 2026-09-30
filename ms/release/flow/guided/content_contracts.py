"""Content guided-release dependency contracts, split by boundary."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Protocol

from ms.core.result import Result
from ms.output.console import ConsoleProtocol
from ms.release.domain.models import PinnedRepo, ReleasePlan
from ms.release.domain.open_control_models import OpenControlPreflightReport
from ms.release.errors import ReleaseError
from ms.release.flow.bom_promotion import BomPromotionResult
from ms.release.flow.content_candidates import (
    ContentCandidateAssessment,
    EnsuredContentCandidate,
)
from ms.release.flow.pr_outcome import PrMergeOutcome

from .contracts import (
    CiDependencies,
    ConfirmationDependencies,
    MenuDependencies,
    NotesStatusDependencies,
    SessionCleanupDependencies,
    TerminalDependencies,
)
from .sessions import ContentReleaseSession


class ContentSessionDependencies(SessionCleanupDependencies, Protocol):
    def save_state(
        self, *, session: ContentReleaseSession
    ) -> Result[ContentReleaseSession, ReleaseError]: ...


class ContentStorageDependencies(ContentSessionDependencies, Protocol):
    def bootstrap_session(
        self, *, created_by: str, notes_file: Path | None
    ) -> Result[ContentReleaseSession, ReleaseError]: ...


class ContentCandidatePreparationDependencies(Protocol):
    def ensure_content_candidates(
        self,
        *,
        workspace_root: Path,
        console: ConsoleProtocol,
        plan: ReleasePlan,
        dry_run: bool,
    ) -> Result[tuple[EnsuredContentCandidate, ...], ReleaseError]: ...


class ContentBomInspectionDependencies(Protocol):
    def preflight_open_control(
        self,
        *,
        workspace_root: Path,
        core_sha: str,
    ) -> OpenControlPreflightReport: ...


class ContentBomDependencies(MenuDependencies, ContentBomInspectionDependencies, Protocol):
    def print_open_control_preflight(
        self,
        *,
        console: ConsoleProtocol,
        report: OpenControlPreflightReport,
    ) -> None: ...

    def promote_open_control_bom(
        self,
        *,
        workspace_root: Path,
        console: ConsoleProtocol,
        dry_run: bool,
    ) -> Result[BomPromotionResult, ReleaseError]: ...


class ContentPlanningDependencies(Protocol):
    def plan_release(
        self,
        *,
        workspace_root: Path,
        channel: Literal["stable", "beta"],
        bump: Literal["major", "minor", "patch"],
        tag_override: str | None,
        pinned: tuple[PinnedRepo, ...],
    ) -> Result[ReleasePlan, ReleaseError]: ...


class ContentCandidatesDependencies(
    MenuDependencies, ContentPlanningDependencies, ContentCandidatePreparationDependencies, Protocol
):
    def assess_content_candidates(
        self,
        *,
        workspace_root: Path,
        plan: ReleasePlan,
    ) -> Result[tuple[ContentCandidateAssessment, ...], ReleaseError]: ...


class ContentSummaryDependencies(MenuDependencies, ContentBomInspectionDependencies, Protocol):
    """Summary can inspect the BOM, but cannot promote or publish."""


class ContentPreparationDependencies(
    NotesStatusDependencies, ContentCandidatePreparationDependencies, Protocol
):
    def prepare_distribution_pr(
        self,
        *,
        workspace_root: Path,
        console: ConsoleProtocol,
        plan: ReleasePlan,
        user_notes: str | None,
        user_notes_file: Path | None,
        dry_run: bool,
    ) -> Result[PrMergeOutcome, ReleaseError]: ...


class ContentPublicationDependencies(SessionCleanupDependencies, Protocol):
    def publish_distribution_release(
        self,
        *,
        workspace_root: Path,
        console: ConsoleProtocol,
        plan: ReleasePlan,
        watch: bool,
        dry_run: bool,
        remote_coherence_checked: bool = False,
        request_id: str | None = None,
    ) -> Result[str, ReleaseError]: ...


class ContentConfirmationDependencies(
    ConfirmationDependencies,
    CiDependencies,
    ContentSessionDependencies,
    ContentPlanningDependencies,
    ContentBomInspectionDependencies,
    ContentPreparationDependencies,
    ContentPublicationDependencies,
    Protocol,
):
    """Confirm, prepare, persist intent, publish, and reconcile."""


class ContentGuidedDependencies(
    ContentConfirmationDependencies,
    ContentStorageDependencies,
    ContentCandidatesDependencies,
    ContentBomDependencies,
    TerminalDependencies,
    Protocol,
):
    """Complete dependency surface, only for the top-level flow."""

    def preflight(self) -> Result[str, ReleaseError]: ...
