from __future__ import annotations

from pathlib import Path

import typer

from ms.cli.commands.release_common import (
    confirm_tag as confirm_release_tag,
)
from ms.cli.commands.release_common import (
    ensure_release_permissions_or_exit,
    exit_release,
    pick_pinned_repo_interactive,
    print_current_release_user,
    resolve_release_inputs,
)
from ms.cli.context import CLIContext, build_context
from ms.core.errors import ErrorCode
from ms.core.result import Err
from ms.output.console import ConsoleProtocol, Style
from ms.release.domain import PinnedRepo, ReleaseBump, ReleaseChannel, config
from ms.release.flow.content_plan import build_content_release_plan
from ms.release.flow.content_preflight import (
    collect_release_preflight_issues,
    load_open_control_report,
)
from ms.release.flow.content_prepare import (
    PreparedContentRelease,
    prepare_content_release_distribution,
)
from ms.release.flow.content_publish import publish_content_release
from ms.release.flow.content_remove import (
    remove_content_github_releases,
    remove_content_release_artifacts,
    resolve_remove_tags,
)
from ms.release.infra.open_control import preflight_open_control
from ms.release.resolve.content_inputs import parse_override_items, resolve_pinned_content
from ms.release.resolve.plan_io import PlanInput, write_plan_file
from ms.release.view.content_console import (
    print_auto_blockers,
    print_auto_suggestions,
    print_content_plan,
    print_content_replay,
    print_open_control_preflight,
    print_release_preflight_issues,
)
from ms.services.release.auto import (
    RepoReadiness,
    probe_release_readiness,
    resolve_pinned_auto_smart,
)
from ms.services.release.remove import (
    delete_github_releases,
    remove_distribution_artifacts,
    validate_remove_tags,
)
from ms.services.release.service import (
    ensure_ci_green,
    ensure_release_permissions,
    plan_release,
    prepare_distribution_pr,
    publish_distribution_release,
)


def _resolve_pinned(
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
                probe_readiness_fn=probe_release_readiness,
                make_error_readiness_fn=lambda repo, ref, message: RepoReadiness(
                    repo=repo,
                    ref=ref,
                    local_path=workspace_root,
                    local_exists=False,
                    status=None,
                    local_head_sha=None,
                    remote_head_sha=None,
                    head_green=None,
                    error=message,
                ),
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


def plan_cmd(
    channel: ReleaseChannel = typer.Option(..., "--channel", help="stable or beta"),
    bump: ReleaseBump = typer.Option("patch", "--bump", help="major/minor/patch"),
    tag: str | None = typer.Option(None, "--tag", help="Override tag"),
    auto: bool = typer.Option(False, "--auto", help="Auto-select pins (strict)"),
    repo: list[str] = typer.Option([], "--repo", help="Override repo SHA (id=sha)"),
    ref: list[str] = typer.Option([], "--ref", help="Override repo ref (id=ref)"),
    allow_non_green: bool = typer.Option(False, "--allow-non-green", help="Allow non-green SHAs"),
    allow_open_control_dirty: bool = typer.Option(
        False,
        "--allow-open-control-dirty",
        help="Allow dirty open-control repos (dev symlink drift)",
    ),
    no_interactive: bool = typer.Option(
        False, "--no-interactive", help="Require explicit --repo overrides"
    ),
    out: Path | None = typer.Option(None, "--out", help="Write plan JSON to file"),
) -> None:
    """Plan a release (no side effects)."""
    ctx = build_context()

    ensure_release_permissions_or_exit(
        workspace_root=ctx.workspace.root,
        console=ctx.console,
        permission_check=ensure_release_permissions,
        require_write=False,
        failure_code=ErrorCode.ENV_ERROR,
    )
    print_current_release_user(workspace_root=ctx.workspace.root, console=ctx.console)

    pinned = _resolve_pinned(
        workspace_root=ctx.workspace.root,
        console=ctx.console,
        channel=channel,
        repo_overrides=repo,
        ref_overrides=ref,
        auto=auto,
        allow_non_green=allow_non_green,
        interactive=not no_interactive,
    )

    report = load_open_control_report(
        workspace_root=ctx.workspace.root,
        pinned=pinned,
        preflight_fn=preflight_open_control,
    )
    if report is not None:
        print_open_control_preflight(console=ctx.console, report=report)
    if report is not None and report.dirty_repos() and not allow_open_control_dirty:
        ctx.console.print(
            "warning: open-control has uncommitted changes; "
            "dev symlink tests may not reflect release builds",
            Style.DIM,
        )

    plan_r = build_content_release_plan(
        planner=plan_release,
        workspace_root=ctx.workspace.root,
        channel=channel,
        bump=bump,
        tag_override=tag,
        pinned=pinned,
    )
    if isinstance(plan_r, Err):
        exit_release(plan_r.error.message, code=ErrorCode.USER_ERROR)

    print_content_plan(plan=plan_r.value, console=ctx.console)

    if out is not None:
        plan_file = write_plan_file(
            path=out,
            plan=PlanInput(
                product="content",
                channel=plan_r.value.channel,
                tag=plan_r.value.tag,
                pinned=plan_r.value.pinned,
            ),
        )
        if isinstance(plan_file, Err):
            exit_release(plan_file.error.message, code=ErrorCode.IO_ERROR)
        ctx.console.success(str(out))

    print_content_replay(plan=plan_r.value, console=ctx.console, plan_file=out)


def _prepare_content_release(
    *,
    ctx: CLIContext,
    channel: ReleaseChannel | None,
    bump: ReleaseBump,
    tag: str | None,
    auto: bool,
    repo: list[str],
    ref: list[str],
    plan_file: Path | None,
    notes: str | None,
    notes_file: Path | None,
    allow_non_green: bool,
    allow_open_control_dirty: bool,
    confirm_tag: str | None,
    no_interactive: bool,
    dry_run: bool,
) -> PreparedContentRelease:
    resolved = resolve_release_inputs(
        product="content",
        plan=plan_file,
        channel=channel,
        tag=tag,
        auto=auto,
        repo=repo,
        ref=ref,
        resolve_pinned=lambda selected_channel: _resolve_pinned(
            workspace_root=ctx.workspace.root,
            console=ctx.console,
            channel=selected_channel,
            repo_overrides=repo,
            ref_overrides=ref,
            auto=auto,
            allow_non_green=allow_non_green,
            interactive=not no_interactive,
        ),
    )

    report = load_open_control_report(
        workspace_root=ctx.workspace.root,
        pinned=resolved.pinned,
        preflight_fn=preflight_open_control,
    )
    if report is not None:
        print_open_control_preflight(console=ctx.console, report=report)
    if report is not None and report.dirty_repos() and not allow_open_control_dirty:
        exit_release(
            "open-control has uncommitted changes (release builds may differ from dev symlink)",
            code=ErrorCode.USER_ERROR,
        )

    planned = build_content_release_plan(
        planner=plan_release,
        workspace_root=ctx.workspace.root,
        channel=resolved.channel,
        bump=bump,
        tag_override=resolved.tag,
        pinned=resolved.pinned,
    )
    if isinstance(planned, Err):
        exit_release(planned.error.message, code=ErrorCode.USER_ERROR)

    print_content_plan(plan=planned.value, console=ctx.console)
    print_content_replay(plan=planned.value, console=ctx.console, plan_file=plan_file)
    if not dry_run:
        confirm_release_tag(planned.value.tag, confirm_tag=confirm_tag)

    prepared = prepare_content_release_distribution(
        ensure_ci_green_fn=ensure_ci_green,
        prepare_distribution_pr_fn=prepare_distribution_pr,
        workspace_root=ctx.workspace.root,
        console=ctx.console,
        plan=planned.value,
        pinned=resolved.pinned,
        notes=notes,
        notes_file=notes_file,
        allow_non_green=allow_non_green,
        dry_run=dry_run,
    )
    if isinstance(prepared, Err):
        code = (
            ErrorCode.IO_ERROR
            if prepared.error.kind in {"dist_repo_failed", "dist_repo_dirty"}
            else ErrorCode.USER_ERROR
        )
        exit_release(prepared.error.message, code=code)

    return prepared.value


def prepare_cmd(
    channel: ReleaseChannel | None = typer.Option(None, "--channel", help="stable or beta"),
    bump: ReleaseBump = typer.Option("patch", "--bump", help="major/minor/patch"),
    tag: str | None = typer.Option(None, "--tag", help="Override tag"),
    auto: bool = typer.Option(False, "--auto", help="Auto-select pins (strict)"),
    repo: list[str] = typer.Option([], "--repo", help="Override repo SHA (id=sha)"),
    ref: list[str] = typer.Option([], "--ref", help="Override repo ref (id=ref)"),
    plan: Path | None = typer.Option(None, "--plan", help="Use a previously saved plan JSON"),
    notes: str | None = typer.Option(None, "--notes", help="Short release notes"),
    notes_file: Path | None = typer.Option(None, "--notes-file", help="Extra markdown file"),
    allow_non_green: bool = typer.Option(False, "--allow-non-green", help="Allow non-green SHAs"),
    allow_open_control_dirty: bool = typer.Option(
        False,
        "--allow-open-control-dirty",
        help="Allow dirty open-control repos (dev symlink drift)",
    ),
    confirm_tag: str | None = typer.Option(
        None, "--confirm-tag", help="Skip confirmation prompt by providing the tag"
    ),
    no_interactive: bool = typer.Option(
        False, "--no-interactive", help="Require explicit --repo overrides"
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print actions without mutating"),
) -> None:
    """Create + merge the distribution PR for a release spec."""
    ctx = build_context()

    ensure_release_permissions_or_exit(
        workspace_root=ctx.workspace.root,
        console=ctx.console,
        permission_check=ensure_release_permissions,
        require_write=True,
        failure_code=ErrorCode.USER_ERROR,
    )

    prepared = _prepare_content_release(
        ctx=ctx,
        channel=channel,
        bump=bump,
        tag=tag,
        auto=auto,
        repo=repo,
        ref=ref,
        plan_file=plan,
        notes=notes,
        notes_file=notes_file,
        allow_non_green=allow_non_green,
        allow_open_control_dirty=allow_open_control_dirty,
        confirm_tag=confirm_tag,
        no_interactive=no_interactive,
        dry_run=dry_run,
    )

    ctx.console.success(f"PR: {prepared.pr_url}")


def publish_cmd(
    channel: ReleaseChannel | None = typer.Option(None, "--channel", help="stable or beta"),
    bump: ReleaseBump = typer.Option("patch", "--bump", help="major/minor/patch"),
    tag: str | None = typer.Option(None, "--tag", help="Override tag"),
    auto: bool = typer.Option(False, "--auto", help="Auto-select pins (strict)"),
    repo: list[str] = typer.Option([], "--repo", help="Override repo SHA (id=sha)"),
    ref: list[str] = typer.Option([], "--ref", help="Override repo ref (id=ref)"),
    plan: Path | None = typer.Option(None, "--plan", help="Use a previously saved plan JSON"),
    notes: str | None = typer.Option(None, "--notes", help="Short release notes"),
    notes_file: Path | None = typer.Option(None, "--notes-file", help="Extra markdown file"),
    allow_non_green: bool = typer.Option(False, "--allow-non-green", help="Allow non-green SHAs"),
    allow_open_control_dirty: bool = typer.Option(
        False,
        "--allow-open-control-dirty",
        help="Allow dirty open-control repos (dev symlink drift)",
    ),
    confirm_tag: str | None = typer.Option(
        None, "--confirm-tag", help="Skip confirmation prompt by providing the tag"
    ),
    no_interactive: bool = typer.Option(
        False, "--no-interactive", help="Require explicit --repo overrides"
    ),
    watch: bool = typer.Option(False, "--watch", help="Watch workflow run until completion"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print actions without mutating"),
) -> None:
    """Prepare spec PR + dispatch the Publish workflow (approval remains manual)."""
    ctx = build_context()

    ensure_release_permissions_or_exit(
        workspace_root=ctx.workspace.root,
        console=ctx.console,
        permission_check=ensure_release_permissions,
        require_write=True,
        failure_code=ErrorCode.USER_ERROR,
    )

    prepared = _prepare_content_release(
        ctx=ctx,
        channel=channel,
        bump=bump,
        tag=tag,
        auto=auto,
        repo=repo,
        ref=ref,
        plan_file=plan,
        notes=notes,
        notes_file=notes_file,
        allow_non_green=allow_non_green,
        allow_open_control_dirty=allow_open_control_dirty,
        confirm_tag=confirm_tag,
        no_interactive=no_interactive,
        dry_run=dry_run,
    )

    ctx.console.success(f"PR merged: {prepared.pr_url}")

    run = publish_content_release(
        publish_distribution_release_fn=publish_distribution_release,
        workspace_root=ctx.workspace.root,
        console=ctx.console,
        plan=prepared.plan,
        watch=watch,
        dry_run=dry_run,
    )
    if isinstance(run, Err):
        exit_release(run.error.message, code=ErrorCode.NETWORK_ERROR)

    ctx.console.success(f"Workflow run: {run.value}")
    ctx.console.print(
        "Next: approve the 'release' environment in GitHub Actions to sign + publish.",
        Style.DIM,
    )


def remove_cmd(
    tag: list[str] = typer.Option([], "--tag", help="Release tag to delete (repeatable)"),
    force: bool = typer.Option(False, "--force", help="Allow deleting stable tags"),
    ignore_missing: bool = typer.Option(False, "--ignore-missing", help="Ignore missing releases"),
    yes: bool = typer.Option(False, "-y", "--yes", help="Skip confirmation prompt"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print actions without mutating"),
) -> None:
    """Remove releases (cleanup artifacts + delete GitHub Releases)."""
    ctx = build_context()

    ensure_release_permissions_or_exit(
        workspace_root=ctx.workspace.root,
        console=ctx.console,
        permission_check=ensure_release_permissions,
        require_write=True,
        failure_code=ErrorCode.USER_ERROR,
    )

    valid = resolve_remove_tags(
        validate_remove_tags_fn=validate_remove_tags,
        tags=tag,
        force=force,
    )
    if isinstance(valid, Err):
        exit_release(valid.error.message, code=ErrorCode.USER_ERROR)
    tags = valid.value

    ctx.console.header("Remove Releases")
    for release_tag in tags:
        ctx.console.print(f"- {release_tag}")
    if not dry_run and not yes:
        typed = typer.prompt("Type DELETE to confirm", default="")
        if typed.strip() != "DELETE":
            exit_release("confirmation mismatch", code=ErrorCode.USER_ERROR)

    artifacts = remove_content_release_artifacts(
        remove_distribution_artifacts_fn=remove_distribution_artifacts,
        workspace_root=ctx.workspace.root,
        console=ctx.console,
        tags=tags,
        dry_run=dry_run,
    )
    if isinstance(artifacts, Err):
        exit_release(artifacts.error.message, code=ErrorCode.IO_ERROR)

    deleted = remove_content_github_releases(
        delete_github_releases_fn=delete_github_releases,
        workspace_root=ctx.workspace.root,
        console=ctx.console,
        tags=tags,
        ignore_missing=ignore_missing,
        dry_run=dry_run,
    )
    if isinstance(deleted, Err):
        exit_release(deleted.error.message, code=ErrorCode.NETWORK_ERROR)

    ctx.console.success("done")


def register_content_commands(*, top_level: typer.Typer, namespace: typer.Typer) -> None:
    top_level.command("plan")(plan_cmd)
    top_level.command("prepare")(prepare_cmd)
    top_level.command("publish")(publish_cmd)
    top_level.command("remove")(remove_cmd)

    namespace.command("plan")(plan_cmd)
    namespace.command("prepare")(prepare_cmd)
    namespace.command("publish")(publish_cmd)
    namespace.command("remove")(remove_cmd)
