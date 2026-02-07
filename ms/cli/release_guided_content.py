from __future__ import annotations

from pathlib import Path

from ms.cli.release_guided_common import (
    bootstrap_content_session,
    preflight_with_permission,
    save_content_state,
    select_bump,
    select_channel,
    select_green_commit,
    to_guided_selection,
)
from ms.cli.selector import SelectorOption, SelectorResult, confirm_yn, select_one
from ms.core.result import Err, Ok, Result
from ms.output.console import ConsoleProtocol
from ms.release.domain.config import RELEASE_REPOS
from ms.release.domain.models import PinnedRepo, ReleaseBump, ReleaseChannel, ReleasePlan
from ms.release.errors import ReleaseError
from ms.release.flow.guided.content_steps import MenuOption, run_guided_content_release_flow
from ms.release.flow.guided.selection import Selection
from ms.release.flow.guided.sessions import ContentReleaseSession, clear_content_session
from ms.release.view.guided_console import print_notes_status
from ms.services.release.open_control import OpenControlPreflightReport, preflight_open_control
from ms.services.release.service import (
    ensure_ci_green,
    ensure_release_permissions,
    plan_release,
    prepare_distribution_pr,
    publish_distribution_release,
)


def _select_menu(
    *,
    title: str,
    subtitle: str,
    options: list[MenuOption[str]],
    initial_index: int,
    allow_back: bool,
) -> SelectorResult[str]:
    selector_options = [
        SelectorOption(value=option.value, label=option.label, detail=option.detail)
        for option in options
    ]
    return select_one(
        title=title,
        subtitle=subtitle,
        options=selector_options,
        initial_index=initial_index,
        allow_back=allow_back,
    )


def run_guided_content_release(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    notes_file: Path | None,
    watch: bool,
    dry_run: bool,
) -> Result[None, ReleaseError]:
    class _Deps:
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

        def select_channel(
            self, *, title: str, subtitle: str, initial_index: int, allow_back: bool
        ) -> Selection[ReleaseChannel]:
            return to_guided_selection(
                select_channel(
                    title=title,
                    subtitle=subtitle,
                    initial_index=initial_index,
                    allow_back=allow_back,
                )
            )

        def select_bump(
            self, *, title: str, subtitle: str, initial_index: int, allow_back: bool
        ) -> Selection[ReleaseBump]:
            return to_guided_selection(
                select_bump(
                    title=title,
                    subtitle=subtitle,
                    initial_index=initial_index,
                    allow_back=allow_back,
                )
            )

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
        ) -> Result[Selection[str], ReleaseError]:
            selected = select_green_commit(
                workspace_root=workspace_root,
                repo_slug=repo_slug,
                ref=ref,
                workflow_file=workflow_file,
                title=title,
                subtitle=subtitle,
                current_sha=current_sha,
                initial_index=initial_index,
                allow_back=allow_back,
            )
            if isinstance(selected, Err):
                return selected
            return Ok(to_guided_selection(selected.value))

        def select_menu(
            self,
            *,
            title: str,
            subtitle: str,
            options: list[MenuOption[str]],
            initial_index: int,
            allow_back: bool,
        ) -> Selection[str]:
            return to_guided_selection(
                _select_menu(
                    title=title,
                    subtitle=subtitle,
                    options=options,
                    initial_index=initial_index,
                    allow_back=allow_back,
                )
            )

        def confirm(self, *, prompt: str) -> bool:
            return confirm_yn(prompt=prompt)

        def ensure_ci_green(
            self,
            *,
            workspace_root: Path,
            pinned: tuple[PinnedRepo, ...],
            allow_non_green: bool,
        ) -> Result[None, ReleaseError]:
            return ensure_ci_green(
                workspace_root=workspace_root,
                pinned=pinned,
                allow_non_green=allow_non_green,
            )

        def preflight_open_control(
            self, *, workspace_root: Path, core_sha: str
        ) -> OpenControlPreflightReport:
            return preflight_open_control(workspace_root=workspace_root, core_sha=core_sha)

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
        ) -> Result[str, ReleaseError]:
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
        ) -> Result[str, ReleaseError]:
            return publish_distribution_release(
                workspace_root=workspace_root,
                console=console,
                plan=plan,
                watch=watch,
                dry_run=dry_run,
            )

        def print_notes_status(
            self,
            *,
            console: ConsoleProtocol,
            notes_markdown: str | None,
            notes_path: str | None,
            notes_sha256: str | None,
            auto_label: str,
        ) -> None:
            print_notes_status(
                console=console,
                notes_markdown=notes_markdown,
                notes_path=notes_path,
                notes_sha256=notes_sha256,
                auto_label=auto_label,
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
