from __future__ import annotations

from functools import partial
from pathlib import Path

from ms.cli.release_guided_bootstrap import (
    bootstrap_app_session,
    preflight_with_permission,
    save_app_state,
)
from ms.cli.release_guided_selectors import GuidedCliTerminal
from ms.core.result import Result
from ms.output.console import ConsoleProtocol
from ms.release.domain.config import APP_RELEASE_REPO, APP_REPO_SLUG
from ms.release.errors import ReleaseError
from ms.release.flow.app_plan import plan_app_release
from ms.release.flow.app_prepare import prepare_app_pr
from ms.release.flow.app_publish import publish_app_release
from ms.release.flow.ci_gate import ensure_ci_green
from ms.release.flow.guided.app_steps import run_guided_app_release_flow
from ms.release.flow.guided.sessions import clear_app_session
from ms.release.flow.permissions import ensure_app_release_permissions


def run_guided_app_release(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    notes_file: Path | None,
    watch: bool,
    dry_run: bool,
) -> Result[None, ReleaseError]:
    # Bind at invocation time so each run owns its workspace and injected effects.
    class _Deps(GuidedCliTerminal):
        preflight = staticmethod(partial(
            preflight_with_permission,
            workspace_root=workspace_root,
            console=console,
            permission_check=ensure_app_release_permissions,
        ))
        bootstrap_session = staticmethod(
            partial(bootstrap_app_session, workspace_root=workspace_root)
        )
        save_state = staticmethod(partial(save_app_state, workspace_root=workspace_root))
        clear_session = staticmethod(partial(clear_app_session, workspace_root=workspace_root))
        ensure_ci_green = staticmethod(ensure_ci_green)
        plan_app_release = staticmethod(plan_app_release)
        prepare_app_pr = staticmethod(prepare_app_pr)
        publish_app_release = staticmethod(publish_app_release)

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
