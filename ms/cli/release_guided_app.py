from __future__ import annotations

from pathlib import Path

from ms.cli.release_guided_bootstrap import (
    bootstrap_app_session,
    preflight_with_permission,
    save_app_state,
)
from ms.cli.release_guided_selectors import GuidedCliDependencies
from ms.core.result import Result
from ms.output.console import ConsoleProtocol
from ms.release.domain.config import APP_RELEASE_REPO, APP_REPO_SLUG
from ms.release.domain.models import AppReleasePlan, PinnedRepo, ReleaseBump, ReleaseChannel
from ms.release.errors import ReleaseError
from ms.release.flow.app_plan import plan_app_release
from ms.release.flow.app_prepare import AppPrepareResult, prepare_app_pr
from ms.release.flow.app_publish import AppPublishResult, publish_app_release
from ms.release.flow.guided.app_steps import run_guided_app_release_flow
from ms.release.flow.guided.sessions import AppReleaseSession, clear_app_session
from ms.release.flow.permissions import ensure_app_release_permissions


def run_guided_app_release(
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
                permission_check=ensure_app_release_permissions,
            )

        def bootstrap_session(
            self, *, created_by: str, notes_file: Path | None
        ) -> Result[AppReleaseSession, ReleaseError]:
            return bootstrap_app_session(
                workspace_root=workspace_root,
                created_by=created_by,
                notes_file=notes_file,
            )

        def save_state(
            self, *, session: AppReleaseSession
        ) -> Result[AppReleaseSession, ReleaseError]:
            return save_app_state(workspace_root=workspace_root, session=session)

        def clear_session(self) -> Result[None, ReleaseError]:
            return clear_app_session(workspace_root=workspace_root)

        def plan_app_release(
            self,
            *,
            workspace_root: Path,
            channel: ReleaseChannel,
            bump: ReleaseBump,
            tag_override: str | None,
            pinned: tuple[PinnedRepo, ...],
        ) -> Result[AppReleasePlan, ReleaseError]:
            return plan_app_release(
                workspace_root=workspace_root,
                channel=channel,
                bump=bump,
                tag_override=tag_override,
                pinned=pinned,
            )

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
        ) -> Result[AppPrepareResult, ReleaseError]:
            return prepare_app_pr(
                workspace_root=workspace_root,
                console=console,
                tag=tag,
                version=version,
                base_sha=base_sha,
                pinned=pinned,
                dry_run=dry_run,
            )

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
        ) -> Result[AppPublishResult, ReleaseError]:
            return publish_app_release(
                workspace_root=workspace_root,
                console=console,
                tag=tag,
                source_sha=source_sha,
                tooling_sha=tooling_sha,
                notes_markdown=notes_markdown,
                notes_source_path=notes_source_path,
                watch=watch,
                dry_run=dry_run,
                remote_coherence_checked=remote_coherence_checked,
            )

    return run_guided_app_release_flow(
        workspace_root=workspace_root,
        console=console,
        notes_file=notes_file,
        watch=watch,
        dry_run=dry_run,
        app_repo_slug=APP_REPO_SLUG,
        app_release_repo=APP_RELEASE_REPO,
        deps=_Deps(),
    )
