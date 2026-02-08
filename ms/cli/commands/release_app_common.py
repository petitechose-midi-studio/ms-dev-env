from __future__ import annotations

from pathlib import Path

from ms.cli.commands.release_common import exit_release, pick_pinned_repo_interactive
from ms.core.errors import ErrorCode
from ms.core.result import Err
from ms.output.console import ConsoleProtocol
from ms.release.domain import PinnedRepo, config
from ms.release.resolve.app_inputs import resolve_pinned_app
from ms.release.resolve.auto.strict import resolve_pinned_auto_strict
from ms.release.view.app_console import print_app_auto_blockers


def resolve_app_pinned_or_exit(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    repo_overrides: list[str],
    ref_overrides: list[str],
    auto: bool,
    allow_non_green: bool,
    interactive: bool,
) -> tuple[PinnedRepo, ...]:
    resolved = resolve_pinned_app(
        workspace_root=workspace_root,
        app_release_repo=config.APP_RELEASE_REPO,
        repo_overrides=repo_overrides,
        ref_overrides=ref_overrides,
        auto=auto,
        allow_non_green=allow_non_green,
        interactive=interactive,
        auto_resolver=lambda current_workspace, repos, current_refs: resolve_pinned_auto_strict(
            workspace_root=current_workspace,
            repos=repos,
            ref_overrides=current_refs,
        ),
        picker=lambda repo, ref: pick_pinned_repo_interactive(
            workspace_root=workspace_root,
            console=console,
            repo=repo,
            ref=ref,
            allow_non_green=allow_non_green,
        ),
    )
    if isinstance(resolved, Err):
        exit_release(resolved.error.message, code=ErrorCode.USER_ERROR)

    if resolved.value.blockers:
        print_app_auto_blockers(console=console, blockers=resolved.value.blockers)
        exit_release("auto release is blocked", code=ErrorCode.USER_ERROR)

    if auto:
        console.success("auto pins: OK")

    if resolved.value.pinned is None:
        exit_release("auto release is blocked", code=ErrorCode.USER_ERROR)
    return resolved.value.pinned
