from __future__ import annotations

from pathlib import Path
from typing import NoReturn

import typer

from ms.cli.context import build_context
from ms.core.errors import ErrorCode
from ms.core.result import Err
from ms.output.console import ConsoleProtocol, Style
from ms.services.release import config
from ms.services.release.ci import fetch_green_head_shas
from ms.services.release.gh import current_user, list_recent_commits
from ms.services.release.model import PinnedRepo, ReleaseBump, ReleaseChannel, ReleasePlan
from ms.services.release.service import (
    ensure_ci_green,
    ensure_release_permissions,
    plan_release,
    prepare_distribution_pr,
    publish_distribution_release,
)


release_app = typer.Typer(add_completion=False, no_args_is_help=True)


def _exit(err: str, *, code: ErrorCode) -> NoReturn:
    typer.echo(f"error: {err}", err=True)
    raise typer.Exit(code=int(code))


def _confirm_tag(tag: str) -> None:
    typed = typer.prompt("Type the tag to confirm", default="")
    if typed.strip() != tag:
        _exit("confirmation mismatch", code=ErrorCode.USER_ERROR)


def _resolve_pinned(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    repo_overrides: list[str],
    allow_non_green: bool,
    interactive: bool,
) -> tuple[PinnedRepo, ...]:
    overrides: dict[str, str] = {}
    for item in repo_overrides:
        if "=" not in item:
            _exit(f"invalid --repo (expected id=sha): {item}", code=ErrorCode.USER_ERROR)
        repo_id, sha = item.split("=", 1)
        repo_id = repo_id.strip()
        sha = sha.strip()
        if not repo_id or not sha:
            _exit(f"invalid --repo (expected id=sha): {item}", code=ErrorCode.USER_ERROR)
        overrides[repo_id] = sha

    pinned: list[PinnedRepo] = []
    for repo in config.RELEASE_REPOS:
        if repo.id in overrides:
            pinned.append(PinnedRepo(repo=repo, sha=overrides[repo.id]))
            continue

        if not interactive:
            _exit(
                f"missing --repo {repo.id}=<sha> (or run without --no-interactive)",
                code=ErrorCode.USER_ERROR,
            )

        console.header(f"Select commit: {repo.id} ({repo.slug})")
        commits_r = list_recent_commits(
            workspace_root=workspace_root,
            repo=repo.slug,
            ref=repo.ref,
            limit=20,
        )
        if isinstance(commits_r, Err):
            _exit(commits_r.error.message, code=ErrorCode.NETWORK_ERROR)
        commits = commits_r.value
        if not commits:
            _exit(f"no commits found for {repo.slug}", code=ErrorCode.NETWORK_ERROR)

        green_r = fetch_green_head_shas(
            workspace_root=workspace_root,
            repo=repo.slug,
            workflow_file=repo.required_ci_workflow_file,
            branch=repo.ref,
            limit=100,
        )
        if isinstance(green_r, Err):
            _exit(green_r.error.message, code=ErrorCode.NETWORK_ERROR)
        green = green_r.value

        default_idx = 1
        for i, c in enumerate(commits, start=1):
            if green.is_green(c.sha):
                default_idx = i
                break

        for i, c in enumerate(commits, start=1):
            status = "OK" if green.is_green(c.sha) else "--"
            date = c.date_utc or ""
            console.print(f"{i:2}. [{status}] {c.short_sha} {date} {c.message}", Style.DIM)

        while True:
            raw = typer.prompt("Pick commit number", default=str(default_idx))
            try:
                idx = int(raw)
            except ValueError:
                console.error("invalid number")
                continue
            if idx < 1 or idx > len(commits):
                console.error("out of range")
                continue

            chosen = commits[idx - 1]
            if not green.is_green(chosen.sha) and not allow_non_green:
                console.error("selected commit CI is not green (use --allow-non-green to override)")
                continue

            pinned.append(PinnedRepo(repo=repo, sha=chosen.sha))
            console.success(f"{repo.id}={chosen.sha}")
            break

    return tuple(pinned)


def _print_plan(*, plan: ReleasePlan, console: ConsoleProtocol) -> None:
    console.header("Release Plan")
    console.print(f"channel: {plan.channel}")
    console.print(f"tag: {plan.tag}")
    console.print("repos:")
    for p in plan.pinned:
        console.print(f"- {p.repo.id}: {p.sha}")
    console.print(f"spec: {plan.spec_path}")
    if plan.notes_path is not None:
        console.print(f"notes: {plan.notes_path}")


@release_app.command("plan")
def plan_cmd(
    channel: ReleaseChannel = typer.Option(..., "--channel", help="stable or beta"),
    bump: ReleaseBump = typer.Option("patch", "--bump", help="major/minor/patch"),
    tag: str | None = typer.Option(None, "--tag", help="Override tag"),
    repo: list[str] = typer.Option([], "--repo", help="Override repo SHA (id=sha)"),
    allow_non_green: bool = typer.Option(False, "--allow-non-green", help="Allow non-green SHAs"),
    no_interactive: bool = typer.Option(
        False, "--no-interactive", help="Require explicit --repo overrides"
    ),
) -> None:
    """Plan a release (no side effects)."""
    ctx = build_context()

    ok = ensure_release_permissions(
        workspace_root=ctx.workspace.root,
        console=ctx.console,
        require_write=False,
    )
    if isinstance(ok, Err):
        _exit(ok.error.message, code=ErrorCode.ENV_ERROR)

    who = current_user(workspace_root=ctx.workspace.root)
    if isinstance(who, Err):
        _exit(who.error.message, code=ErrorCode.NETWORK_ERROR)
    ctx.console.print(f"gh user: {who.value.login}", Style.DIM)

    pinned = _resolve_pinned(
        workspace_root=ctx.workspace.root,
        console=ctx.console,
        repo_overrides=repo,
        allow_non_green=allow_non_green,
        interactive=not no_interactive,
    )

    plan_r = plan_release(
        workspace_root=ctx.workspace.root,
        channel=channel,
        bump=bump,
        tag_override=tag,
        pinned=pinned,
    )
    if isinstance(plan_r, Err):
        _exit(plan_r.error.message, code=ErrorCode.USER_ERROR)

    _print_plan(plan=plan_r.value, console=ctx.console)


@release_app.command("prepare")
def prepare_cmd(
    channel: ReleaseChannel = typer.Option(..., "--channel", help="stable or beta"),
    bump: ReleaseBump = typer.Option("patch", "--bump", help="major/minor/patch"),
    tag: str | None = typer.Option(None, "--tag", help="Override tag"),
    repo: list[str] = typer.Option([], "--repo", help="Override repo SHA (id=sha)"),
    notes: str | None = typer.Option(None, "--notes", help="Short release notes"),
    notes_file: Path | None = typer.Option(None, "--notes-file", help="Extra markdown file"),
    allow_non_green: bool = typer.Option(False, "--allow-non-green", help="Allow non-green SHAs"),
    no_interactive: bool = typer.Option(
        False, "--no-interactive", help="Require explicit --repo overrides"
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print actions without mutating"),
) -> None:
    """Create + merge the distribution PR for a release spec."""
    ctx = build_context()

    ok = ensure_release_permissions(
        workspace_root=ctx.workspace.root,
        console=ctx.console,
        require_write=True,
    )
    if isinstance(ok, Err):
        _exit(ok.error.message, code=ErrorCode.USER_ERROR)

    pinned = _resolve_pinned(
        workspace_root=ctx.workspace.root,
        console=ctx.console,
        repo_overrides=repo,
        allow_non_green=allow_non_green,
        interactive=not no_interactive,
    )

    plan_r = plan_release(
        workspace_root=ctx.workspace.root,
        channel=channel,
        bump=bump,
        tag_override=tag,
        pinned=pinned,
    )
    if isinstance(plan_r, Err):
        _exit(plan_r.error.message, code=ErrorCode.USER_ERROR)

    green = ensure_ci_green(
        workspace_root=ctx.workspace.root,
        pinned=pinned,
        allow_non_green=allow_non_green,
    )
    if isinstance(green, Err):
        _exit(green.error.message, code=ErrorCode.USER_ERROR)

    _print_plan(plan=plan_r.value, console=ctx.console)
    if not dry_run:
        _confirm_tag(plan_r.value.tag)

    pr = prepare_distribution_pr(
        workspace_root=ctx.workspace.root,
        console=ctx.console,
        plan=plan_r.value,
        user_notes=notes,
        user_notes_file=notes_file,
        dry_run=dry_run,
    )
    if isinstance(pr, Err):
        _exit(pr.error.message, code=ErrorCode.IO_ERROR)

    ctx.console.success(f"PR: {pr.value}")


@release_app.command("publish")
def publish_cmd(
    channel: ReleaseChannel = typer.Option(..., "--channel", help="stable or beta"),
    bump: ReleaseBump = typer.Option("patch", "--bump", help="major/minor/patch"),
    tag: str | None = typer.Option(None, "--tag", help="Override tag"),
    repo: list[str] = typer.Option([], "--repo", help="Override repo SHA (id=sha)"),
    notes: str | None = typer.Option(None, "--notes", help="Short release notes"),
    notes_file: Path | None = typer.Option(None, "--notes-file", help="Extra markdown file"),
    allow_non_green: bool = typer.Option(False, "--allow-non-green", help="Allow non-green SHAs"),
    no_interactive: bool = typer.Option(
        False, "--no-interactive", help="Require explicit --repo overrides"
    ),
    watch: bool = typer.Option(False, "--watch", help="Watch workflow run until completion"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print actions without mutating"),
) -> None:
    """Prepare spec PR + dispatch the Publish workflow (approval remains manual)."""
    ctx = build_context()

    ok = ensure_release_permissions(
        workspace_root=ctx.workspace.root,
        console=ctx.console,
        require_write=True,
    )
    if isinstance(ok, Err):
        _exit(ok.error.message, code=ErrorCode.USER_ERROR)

    pinned = _resolve_pinned(
        workspace_root=ctx.workspace.root,
        console=ctx.console,
        repo_overrides=repo,
        allow_non_green=allow_non_green,
        interactive=not no_interactive,
    )

    plan_r = plan_release(
        workspace_root=ctx.workspace.root,
        channel=channel,
        bump=bump,
        tag_override=tag,
        pinned=pinned,
    )
    if isinstance(plan_r, Err):
        _exit(plan_r.error.message, code=ErrorCode.USER_ERROR)

    green = ensure_ci_green(
        workspace_root=ctx.workspace.root,
        pinned=pinned,
        allow_non_green=allow_non_green,
    )
    if isinstance(green, Err):
        _exit(green.error.message, code=ErrorCode.USER_ERROR)

    _print_plan(plan=plan_r.value, console=ctx.console)
    if not dry_run:
        _confirm_tag(plan_r.value.tag)

    pr = prepare_distribution_pr(
        workspace_root=ctx.workspace.root,
        console=ctx.console,
        plan=plan_r.value,
        user_notes=notes,
        user_notes_file=notes_file,
        dry_run=dry_run,
    )
    if isinstance(pr, Err):
        _exit(pr.error.message, code=ErrorCode.IO_ERROR)

    ctx.console.success(f"PR merged: {pr.value}")

    run = publish_distribution_release(
        workspace_root=ctx.workspace.root,
        console=ctx.console,
        plan=plan_r.value,
        watch=watch,
        dry_run=dry_run,
    )
    if isinstance(run, Err):
        _exit(run.error.message, code=ErrorCode.NETWORK_ERROR)

    ctx.console.success(f"Workflow run: {run.value}")
    ctx.console.print(
        "Next: approve the 'release' environment in GitHub Actions to sign + publish.",
        Style.DIM,
    )
