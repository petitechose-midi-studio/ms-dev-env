from __future__ import annotations

from pathlib import Path

from ms.cli.release_guided_bootstrap import (
    bootstrap_content_session,
    preflight_with_permission,
    save_content_state,
)
from ms.cli.release_guided_selectors import GuidedCliDependencies
from ms.core.result import Err, Result
from ms.output.console import ConsoleProtocol
from ms.release.domain.config import RELEASE_REPOS
from ms.release.domain.models import PinnedRepo, ReleaseBump, ReleaseChannel, ReleasePlan
from ms.release.domain.open_control_models import OpenControlPreflightReport
from ms.release.errors import ReleaseError
from ms.release.flow.bom_promotion import (
    BomPromotionResult,
)
from ms.release.flow.bom_promotion import (
    promote_open_control_bom as promote_open_control_bom_flow,
)
from ms.release.flow.content_candidates import (
    assess_content_candidates,
    ensure_content_candidates,
)
from ms.release.flow.content_plan import plan_release
from ms.release.flow.content_prepare import prepare_distribution_pr
from ms.release.flow.content_publish import publish_distribution_release
from ms.release.flow.guided.content_steps import run_guided_content_release_flow
from ms.release.flow.guided.sessions import ContentReleaseSession, clear_content_session
from ms.release.flow.permissions import ensure_core_release_permissions, ensure_release_permissions
from ms.release.flow.pr_outcome import PrMergeOutcome
from ms.release.infra.open_control import preflight_open_control
from ms.release.view.content_console import print_open_control_preflight


def run_guided_content_release(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    notes_file: Path | None,
    watch: bool,
    dry_run: bool,
) -> Result[None, ReleaseError]:
    class _Deps(GuidedCliDependencies):
        def preflight(self) -> Result[str, ReleaseError]:
            return preflight_with_permission(
                workspace_root=workspace_root,
                console=console,
                permission_check=ensure_release_permissions,
            )

        def bootstrap_session(
            self, *, created_by: str, notes_file: Path | None
        ) -> Result[ContentReleaseSession, ReleaseError]:
            return bootstrap_content_session(
                workspace_root=workspace_root,
                created_by=created_by,
                notes_file=notes_file,
            )

        def save_state(
            self, *, session: ContentReleaseSession
        ) -> Result[ContentReleaseSession, ReleaseError]:
            return save_content_state(workspace_root=workspace_root, session=session)

        def clear_session(self) -> Result[None, ReleaseError]:
            return clear_content_session(workspace_root=workspace_root)

        def ensure_content_candidates(
            self,
            *,
            workspace_root: Path,
            console: ConsoleProtocol,
            plan: ReleasePlan,
            dry_run: bool,
        ):
            return ensure_content_candidates(
                workspace_root=workspace_root,
                console=console,
                plan=plan,
                dry_run=dry_run,
            )

        def assess_content_candidates(
            self,
            *,
            workspace_root: Path,
            plan: ReleasePlan,
        ):
            return assess_content_candidates(
                workspace_root=workspace_root,
                plan=plan,
            )

        def preflight_open_control(
            self, *, workspace_root: Path, core_sha: str
        ) -> OpenControlPreflightReport:
            return preflight_open_control(workspace_root=workspace_root, core_sha=core_sha)

        def print_open_control_preflight(
            self,
            *,
            console: ConsoleProtocol,
            report: OpenControlPreflightReport,
        ) -> None:
            print_open_control_preflight(console=console, report=report)

        def promote_open_control_bom(
            self,
            *,
            workspace_root: Path,
            console: ConsoleProtocol,
            dry_run: bool,
        ) -> Result[BomPromotionResult, ReleaseError]:
            allowed = ensure_core_release_permissions(
                workspace_root=workspace_root,
                console=console,
                require_write=True,
            )
            if isinstance(allowed, Err):
                return allowed
            return promote_open_control_bom_flow(
                workspace_root=workspace_root,
                console=console,
                dry_run=dry_run,
            )

        def plan_release(
            self,
            *,
            workspace_root: Path,
            channel: ReleaseChannel,
            bump: ReleaseBump,
            tag_override: str | None,
            pinned: tuple[PinnedRepo, ...],
        ) -> Result[ReleasePlan, ReleaseError]:
            return plan_release(
                workspace_root=workspace_root,
                channel=channel,
                bump=bump,
                tag_override=tag_override,
                pinned=pinned,
            )

        def prepare_distribution_pr(
            self,
            *,
            workspace_root: Path,
            console: ConsoleProtocol,
            plan: ReleasePlan,
            user_notes: str | None,
            user_notes_file: Path | None,
            dry_run: bool,
        ) -> Result[PrMergeOutcome, ReleaseError]:
            return prepare_distribution_pr(
                workspace_root=workspace_root,
                console=console,
                plan=plan,
                user_notes=user_notes,
                user_notes_file=user_notes_file,
                dry_run=dry_run,
            )

        def publish_distribution_release(
            self,
            *,
            workspace_root: Path,
            console: ConsoleProtocol,
            plan: ReleasePlan,
            watch: bool,
            dry_run: bool,
            remote_coherence_checked: bool = False,
        ) -> Result[str, ReleaseError]:
            return publish_distribution_release(
                workspace_root=workspace_root,
                console=console,
                plan=plan,
                watch=watch,
                dry_run=dry_run,
                remote_coherence_checked=remote_coherence_checked,
            )

    return run_guided_content_release_flow(
        workspace_root=workspace_root,
        console=console,
        notes_file=notes_file,
        watch=watch,
        dry_run=dry_run,
        release_repos=RELEASE_REPOS,
        deps=_Deps(),
    )
