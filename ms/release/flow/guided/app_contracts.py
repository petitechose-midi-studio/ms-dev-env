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

from .contracts import TerminalDependencies
from .sessions import AppReleaseSession


class AppPrepareResultLike(Protocol):
    @property
    def pr(self) -> PrMergeOutcome: ...

    @property
    def source_sha(self) -> str: ...


class AppStorageDependencies(Protocol):
    """Session persistence boundary."""

    def bootstrap_session(
        self, *, created_by: str, notes_file: Path | None
    ) -> Result[AppReleaseSession, ReleaseError]: ...

    def save_state(
        self, *, session: AppReleaseSession
    ) -> Result[AppReleaseSession, ReleaseError]: ...

    def clear_session(self) -> Result[None, ReleaseError]: ...


class AppReleaseOperations[PrepareT: AppPrepareResultLike](Protocol):
    """Release business operations (GitHub/workspace boundary)."""

    def preflight(self) -> Result[str, ReleaseError]: ...

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
        remote_coherence_checked: bool = False,
        request_id: str | None = None,
        before_dispatch: BeforeDispatch | None = None,
    ) -> Result[AppPublishResult, ReleaseError]: ...


class AppGuidedDependencies[PrepareT: AppPrepareResultLike](
    TerminalDependencies,
    AppStorageDependencies,
    AppReleaseOperations[PrepareT],
    Protocol,
):
    """Full guided app release boundary (composed of the three above)."""
