from __future__ import annotations

from functools import partial
from pathlib import Path

from ms.cli.release_guided_bootstrap import (
    bootstrap_content_session,
    preflight_with_permission,
    save_content_state,
)
from ms.cli.release_guided_selectors import GuidedCliTerminal
from ms.core.result import Err, Result
from ms.output.console import ConsoleProtocol
from ms.release.domain.config import RELEASE_REPOS
from ms.release.errors import ReleaseError
from ms.release.flow.bom_promotion import BomPromotionResult
from ms.release.flow.bom_promotion import (
    promote_open_control_bom as promote_open_control_bom_flow,
)
from ms.release.flow.ci_gate import ensure_ci_green
from ms.release.flow.content_candidates import assess_content_candidates, ensure_content_candidates
from ms.release.flow.content_plan import plan_release
from ms.release.flow.content_prepare import prepare_distribution_pr
from ms.release.flow.content_publish import publish_distribution_release
from ms.release.flow.guided.content_steps import run_guided_content_release_flow
from ms.release.flow.guided.sessions import clear_content_session
from ms.release.flow.permissions import ensure_core_release_permissions, ensure_release_permissions
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
    class _Deps(GuidedCliTerminal):
        preflight = staticmethod(partial(
            preflight_with_permission,
            workspace_root=workspace_root,
            console=console,
            permission_check=ensure_release_permissions,
        ))
        bootstrap_session = staticmethod(partial(
            bootstrap_content_session, workspace_root=workspace_root,
        ))
        save_state = staticmethod(partial(save_content_state, workspace_root=workspace_root))
        clear_session = staticmethod(partial(clear_content_session, workspace_root=workspace_root))
        ensure_ci_green = staticmethod(ensure_ci_green)
        ensure_content_candidates = staticmethod(ensure_content_candidates)
        assess_content_candidates = staticmethod(assess_content_candidates)
        preflight_open_control = staticmethod(preflight_open_control)
        print_open_control_preflight = staticmethod(print_open_control_preflight)
        plan_release = staticmethod(plan_release)
        prepare_distribution_pr = staticmethod(prepare_distribution_pr)
        publish_distribution_release = staticmethod(publish_distribution_release)

        # This adapter owns a real permission boundary, not just argument forwarding.
        @staticmethod
        def promote_open_control_bom(
            *, workspace_root: Path, console: ConsoleProtocol, dry_run: bool,
        ) -> Result[BomPromotionResult, ReleaseError]:
            allowed = ensure_core_release_permissions(
                workspace_root=workspace_root, console=console, require_write=True,
            )
            if isinstance(allowed, Err):
                return allowed
            return promote_open_control_bom_flow(
                workspace_root=workspace_root, console=console, dry_run=dry_run,
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
