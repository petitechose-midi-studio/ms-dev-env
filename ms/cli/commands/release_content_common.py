from __future__ import annotations

from pathlib import Path

from ms.cli.commands.release_common import exit_release, pick_pinned_repo_interactive
from ms.core.errors import ErrorCode
from ms.core.result import Err
from ms.output.console import ConsoleProtocol
from ms.release.domain import PinnedRepo, ReleaseChannel, config
from ms.release.flow.content_preflight import collect_release_preflight_issues
from ms.release.resolve.auto.smart import resolve_pinned_auto_smart
from ms.release.resolve.content_inputs import resolve_pinned_content
from ms.release.resolve.overrides import parse_override_items
from ms.release.view.content_console import (
    print_auto_blockers,
    print_auto_suggestions,
    print_release_preflight_issues,
)


def resolve_pinned_or_exit(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    channel: ReleaseChannel,
    repo_overrides: list[str],
    ref_overrides: list[str],
    auto: bool,
    allow_non_green: bool,
    interactive: bool,
) -> tuple[PinnedRepo, ...]:
    refs = parse_override_items(ref_overrides, flag="--ref")
    if isinstance(refs, Err):
        exit_release(refs.error.message, code=ErrorCode.USER_ERROR)

    if interactive and not auto:
        print_release_preflight_issues(
            console=console,
            issues=collect_release_preflight_issues(
                workspace_root=workspace_root,
                release_repos=config.RELEASE_REPOS,
                refs=refs.value,
            ),
        )

    resolved = resolve_pinned_content(
        workspace_root=workspace_root,
        channel=channel,
        release_repos=config.RELEASE_REPOS,
        repo_overrides=repo_overrides,
        ref_overrides=ref_overrides,
        auto=auto,
        allow_non_green=allow_non_green,
        interactive=interactive,
        auto_resolver=lambda current_workspace,
        current_channel,
        current_refs: resolve_pinned_auto_smart(
            workspace_root=current_workspace,
            channel=current_channel,
            dist_repo=config.DIST_REPO_SLUG,
            repos=config.RELEASE_REPOS,
            ref_overrides=current_refs,
            head_repo_ids=frozenset({"core", "plugin-bitwig"}),
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
        print_auto_blockers(console=console, blockers=resolved.value.blockers)
        exit_release("auto release is blocked", code=ErrorCode.USER_ERROR)

    if auto:
        console.success("auto pins: OK")
        print_auto_suggestions(console=console, suggestions=resolved.value.suggestions)

    if resolved.value.pinned is None:
        exit_release("auto release is blocked", code=ErrorCode.USER_ERROR)
    return resolved.value.pinned
