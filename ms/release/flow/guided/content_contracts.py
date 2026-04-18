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

from .menu_option import MenuOption
from .selection import Selection
from .sessions import ContentReleaseSession


class ContentGuidedDependencies(Protocol):
    def preflight(self) -> Result[str, ReleaseError]: ...

    def bootstrap_session(
        self, *, created_by: str, notes_file: Path | None
    ) -> Result[ContentReleaseSession, ReleaseError]: ...

    def save_state(
        self, *, session: ContentReleaseSession
    ) -> Result[ContentReleaseSession, ReleaseError]: ...

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

    def ensure_content_candidates(
        self,
        *,
        workspace_root: Path,
        console: ConsoleProtocol,
        plan: ReleasePlan,
        dry_run: bool,
    ) -> Result[tuple[EnsuredContentCandidate, ...], ReleaseError]: ...

    def assess_content_candidates(
        self,
        *,
        workspace_root: Path,
        plan: ReleasePlan,
    ) -> Result[tuple[ContentCandidateAssessment, ...], ReleaseError]: ...

    def preflight_open_control(
        self,
        *,
        workspace_root: Path,
        core_sha: str,
    ) -> OpenControlPreflightReport: ...

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

    def plan_release(
        self,
        *,
        workspace_root: Path,
        channel: Literal["stable", "beta"],
        bump: Literal["major", "minor", "patch"],
        tag_override: str | None,
        pinned: tuple[PinnedRepo, ...],
    ) -> Result[ReleasePlan, ReleaseError]: ...

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

    def publish_distribution_release(
        self,
        *,
        workspace_root: Path,
        console: ConsoleProtocol,
        plan: ReleasePlan,
        watch: bool,
        dry_run: bool,
    ) -> Result[str, ReleaseError]: ...

    def print_notes_status(
        self,
        *,
        console: ConsoleProtocol,
        notes_markdown: str | None,
        notes_path: str | None,
        notes_sha256: str | None,
        auto_label: str,
    ) -> None: ...
