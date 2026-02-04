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
from ms.services.release.model import (
    PinnedRepo,
    ReleaseBump,
    ReleaseChannel,
    ReleasePlan,
    ReleaseRepo,
)
from ms.services.release.auto import (
    AutoSuggestion,
    RepoReadiness,
    probe_release_readiness,
    resolve_pinned_auto_smart,
)
from ms.services.release.open_control import OpenControlPreflightReport, preflight_open_control
from ms.services.release.plan_file import PlanInput, read_plan_file, write_plan_file
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


release_app = typer.Typer(add_completion=False, no_args_is_help=True)


def _exit(err: str, *, code: ErrorCode) -> NoReturn:
    typer.echo(f"error: {err}", err=True)
    raise typer.Exit(code=int(code))


def _confirm_tag(tag: str, *, confirm_tag: str | None) -> None:
    if confirm_tag is not None:
        if confirm_tag.strip() != tag:
            _exit("confirmation mismatch", code=ErrorCode.USER_ERROR)
        return

    typed = typer.prompt("Type the tag to confirm", default="")
    if typed.strip() != tag:
        _exit("confirmation mismatch", code=ErrorCode.USER_ERROR)


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
    def parse_overrides(items: list[str], *, flag: str) -> dict[str, str]:
        out: dict[str, str] = {}
        for item in items:
            if "=" not in item:
                _exit(f"invalid {flag} (expected id=value): {item}", code=ErrorCode.USER_ERROR)
            k, v = item.split("=", 1)
            k = k.strip()
            v = v.strip()
            if not k or not v:
                _exit(f"invalid {flag} (expected id=value): {item}", code=ErrorCode.USER_ERROR)
            out[k] = v
        return out

    overrides = parse_overrides(repo_overrides, flag="--repo")
    refs = parse_overrides(ref_overrides, flag="--ref")

    if interactive and not auto:
        _print_release_preflight(console=console, workspace_root=workspace_root, refs=refs)

    if auto:
        if overrides:
            _exit("--auto cannot be combined with --repo overrides", code=ErrorCode.USER_ERROR)
        if allow_non_green:
            _exit("--auto is strict: remove --allow-non-green", code=ErrorCode.USER_ERROR)

        resolved = resolve_pinned_auto_smart(
            workspace_root=workspace_root,
            channel=channel,
            dist_repo=config.DIST_REPO_SLUG,
            repos=config.RELEASE_REPOS,
            ref_overrides=refs,
            head_repo_ids=frozenset({"core", "plugin-bitwig"}),
        )
        if isinstance(resolved, Err):
            _print_auto_blockers(console=console, blockers=resolved.error)
            _exit("auto release is blocked", code=ErrorCode.USER_ERROR)
        pinned_auto, suggestions = resolved.value
        console.success("auto pins: OK")
        _print_auto_suggestions(console=console, suggestions=suggestions)
        return pinned_auto

    pinned: list[PinnedRepo] = []
    for repo in config.RELEASE_REPOS:
        ref = refs.get(repo.id, repo.ref)
        repo_sel = ReleaseRepo(
            id=repo.id,
            slug=repo.slug,
            ref=ref,
            required_ci_workflow_file=repo.required_ci_workflow_file,
        )

        if repo.id in overrides:
            pinned.append(PinnedRepo(repo=repo_sel, sha=overrides[repo.id]))
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
            ref=ref,
            limit=20,
        )
        if isinstance(commits_r, Err):
            _exit(commits_r.error.message, code=ErrorCode.NETWORK_ERROR)
        commits = commits_r.value
        if not commits:
            _exit(f"no commits found for {repo.slug}", code=ErrorCode.NETWORK_ERROR)

        green = None
        if repo.required_ci_workflow_file is not None:
            green_r = fetch_green_head_shas(
                workspace_root=workspace_root,
                repo=repo.slug,
                workflow_file=repo.required_ci_workflow_file,
                branch=ref,
                limit=100,
            )
            if isinstance(green_r, Err):
                _exit(green_r.error.message, code=ErrorCode.NETWORK_ERROR)
            green = green_r.value

        default_idx = 1
        if green is not None:
            for i, c in enumerate(commits, start=1):
                if green.is_green(c.sha):
                    default_idx = i
                    break

        for i, c in enumerate(commits, start=1):
            status = "NA" if green is None else ("OK" if green.is_green(c.sha) else "--")
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
            if green is not None and (not green.is_green(chosen.sha)) and (not allow_non_green):
                console.error("selected commit CI is not green (use --allow-non-green to override)")
                continue

            pinned.append(PinnedRepo(repo=repo_sel, sha=chosen.sha))
            console.success(f"{repo.id}={chosen.sha} (ref={ref})")
            break

    return tuple(pinned)


def _print_release_preflight(
    *,
    console: ConsoleProtocol,
    workspace_root: Path,
    refs: dict[str, str],
) -> None:
    issues: list[RepoReadiness] = []
    for repo in config.RELEASE_REPOS:
        ref = refs.get(repo.id, repo.ref)
        rr = probe_release_readiness(workspace_root=workspace_root, repo=repo, ref=ref)
        if isinstance(rr, Err):
            # Treat as an issue so the user sees it.
            issues.append(
                RepoReadiness(
                    repo=repo,
                    ref=ref,
                    local_path=workspace_root,
                    local_exists=False,
                    status=None,
                    local_head_sha=None,
                    remote_head_sha=None,
                    head_green=None,
                    error=rr.error.message,
                )
            )
            continue
        r = rr.value
        if r.is_ready():
            continue
        issues.append(r)

    if not issues:
        return

    console.header("Release preflight")
    console.print("Non-blocking warnings (interactive mode).", Style.DIM)
    console.print("Use --auto to enforce strict readiness.", Style.DIM)
    for r in issues:
        console.print(f"- {r.repo.id}: {_gh_repo_url(r.repo.slug)}", Style.DIM)
        if not r.local_exists:
            console.print(f"  missing checkout: {r.local_path}", Style.DIM)
            continue
        if r.status is None:
            console.print("  status unavailable", Style.DIM)
            continue
        if not r.status.is_clean:
            console.print("  dirty", Style.DIM)
            for e in r.status.entries[:10]:
                console.print(f"    {e.pretty_xy()} {e.path}", Style.DIM)
                if r.status.upstream is not None and r.status.ahead == 0 and r.status.behind == 0:
                    console.print(
                        f"      {_gh_blob_url(r.repo.slug, r.status.branch, e.path)}",
                        Style.DIM,
                    )
        if r.status.upstream is None:
            console.print("  no upstream", Style.DIM)
        else:
            if r.status.ahead:
                console.print(f"  ahead {r.status.ahead} (push)", Style.DIM)
                base = r.status.upstream.split("/", 1)[-1]
                console.print(f"  {_gh_compare_url(r.repo.slug, base, r.status.branch)}", Style.DIM)
            if r.status.behind:
                console.print(f"  behind {r.status.behind} (pull)", Style.DIM)
        if r.local_head_sha and r.remote_head_sha and r.local_head_sha != r.remote_head_sha:
            console.print(
                f"  local {r.local_head_sha[:7]} != remote {r.remote_head_sha[:7]}",
                Style.DIM,
            )
        if r.repo.required_ci_workflow_file is None:
            console.print("  not CI-gated (auto will refuse)", Style.DIM)
        else:
            console.print(
                f"  ci: {_gh_actions_workflow_url(r.repo.slug, r.repo.required_ci_workflow_file)}",
                Style.DIM,
            )
            if r.remote_head_sha is not None and r.head_green is not True:
                console.print("  ci: HEAD not green", Style.DIM)
    console.newline()


def _gh_repo_url(slug: str) -> str:
    return f"https://github.com/{slug}"


def _gh_actions_workflow_url(slug: str, workflow_file: str) -> str:
    return f"https://github.com/{slug}/actions/workflows/{workflow_file}"


def _gh_blob_url(slug: str, ref: str, path: str) -> str:
    return f"https://github.com/{slug}/blob/{ref}/{path}"


def _gh_compare_url(slug: str, base: str, head: str) -> str:
    return f"https://github.com/{slug}/compare/{base}...{head}"


def _print_auto_blockers(*, console: ConsoleProtocol, blockers: tuple[RepoReadiness, ...]) -> None:
    console.header("Auto Release Blocked")
    console.print("--auto is strict by default.", Style.DIM)
    console.print("Fix the issues below, then rerun.", Style.DIM)
    console.newline()

    for r in blockers:
        console.header(f"{r.repo.id} ({r.repo.slug})")
        console.print(_gh_repo_url(r.repo.slug), Style.DIM)
        console.print(str(r.local_path), Style.DIM)
        console.print(f"ref: {r.ref}", Style.DIM)
        if r.error is not None:
            console.error(r.error)
            continue

        if not r.local_exists:
            console.error("repo not found in workspace")
            console.print("hint: run `ms sync --repos --profile maintainer`", Style.DIM)
            continue

        st = r.status
        if st is None:
            console.error("repo status unavailable")
            continue

        if not st.is_clean:
            console.error("working tree is dirty")
            for e in st.entries[:20]:
                console.print(f"- {e.pretty_xy()} {Path(r.local_path, e.path)}", Style.DIM)
                if st.upstream is not None and st.ahead == 0 and st.behind == 0:
                    console.print(f"  {_gh_blob_url(r.repo.slug, st.branch, e.path)}", Style.DIM)
            if len(st.entries) > 20:
                console.print(f"... ({len(st.entries) - 20} more)", Style.DIM)
            console.print("hint: commit/stash changes before auto release", Style.DIM)

        if st.upstream is None:
            console.error("no upstream configured")
            console.print("hint: set upstream and push the branch", Style.DIM)
        else:
            if st.ahead:
                console.error(f"ahead of upstream by {st.ahead} commit(s)")
                console.print("hint: push to remote and wait for CI", Style.DIM)
                base = st.upstream.split("/", 1)[-1]
                console.print(_gh_compare_url(r.repo.slug, base, st.branch), Style.DIM)
            if st.behind:
                console.error(f"behind upstream by {st.behind} commit(s)")
                console.print("hint: pull/rebase to sync before auto release", Style.DIM)

        if r.local_head_sha is not None and r.remote_head_sha is not None:
            if r.local_head_sha != r.remote_head_sha:
                console.error(
                    f"local HEAD {r.local_head_sha[:7]} != remote HEAD {r.remote_head_sha[:7]}"
                )
                console.print("hint: push/pull so local matches remote", Style.DIM)

        if r.repo.required_ci_workflow_file is None:
            console.error("repo is not CI-gated")
            console.print(
                "hint: add a CI workflow to the repo and set required_ci_workflow_file in ms release config",
                Style.DIM,
            )
        else:
            console.print(
                _gh_actions_workflow_url(r.repo.slug, r.repo.required_ci_workflow_file),
                Style.DIM,
            )
            if r.remote_head_sha is not None and (r.head_green is not True):
                console.error("remote HEAD is not green")
                console.print("hint: wait for CI success on the branch HEAD", Style.DIM)


def _print_auto_suggestions(
    *, console: ConsoleProtocol, suggestions: tuple[AutoSuggestion, ...]
) -> None:
    if not suggestions:
        return

    console.header("Optional bumps")
    for s in suggestions:
        if s.kind == "bump":
            console.print(
                f"- {s.repo.id} ({s.repo.slug}): {s.from_sha[:7]} -> {s.to_sha[:7]} ({s.reason})",
                Style.DIM,
            )
            if not s.applyable:
                console.print(
                    "  note: local repo not clean/synced; bump will be safer after cleanup/push",
                    Style.DIM,
                )
            continue

        # kind == "local"
        console.print(
            f"- {s.repo.id} ({s.repo.slug}): local state ({s.reason}); auto keeps {s.from_sha[:7]}",
            Style.DIM,
        )


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


def _print_replay(*, plan: ReleasePlan, console: ConsoleProtocol, plan_file: Path | None) -> None:
    repo_args = " ".join([f"--repo {p.repo.id}={p.sha}" for p in plan.pinned])
    console.newline()
    console.print("Replay:", Style.DIM)
    if plan_file is not None:
        console.print(f"ms release publish --plan {plan_file}", Style.DIM)
    console.print(
        f"ms release publish --channel {plan.channel} --tag {plan.tag} --no-interactive {repo_args}",
        Style.DIM,
    )


def _render_open_control_preflight(
    *,
    workspace_root: Path,
    pinned: tuple[PinnedRepo, ...],
    console: ConsoleProtocol,
) -> OpenControlPreflightReport | None:
    core = next((p for p in pinned if p.repo.id == "core"), None)
    if core is None:
        return None

    report = preflight_open_control(workspace_root=workspace_root, core_sha=core.sha)

    if not any(r.exists for r in report.repos):
        console.header("OpenControl preflight")
        console.print("skip (no open-control workspace)", Style.DIM)
        return report

    console.header("OpenControl preflight")
    if report.oc_sdk.lock is None:
        err = report.oc_sdk.error or "oc-sdk lock unavailable"
        console.print(f"oc-sdk: unavailable ({err})", Style.DIM)
    else:
        src = report.oc_sdk.source or "?"
        console.print(f"oc-sdk: v{report.oc_sdk.lock.version} ({src})", Style.DIM)

    dirty = report.dirty_repos()
    if dirty:
        console.print(f"dirty: {len(dirty)} repo(s)", Style.DIM)
        for r in dirty:
            console.print(f"- open-control/{r.repo}", Style.DIM)

    if report.mismatches:
        console.print(f"mismatch: {len(report.mismatches)} repo(s)", Style.DIM)
        for m in report.mismatches:
            console.print(
                f"- {m.repo}: local {m.local_sha[:7]} != pinned {m.pinned_sha[:7]}",
                Style.DIM,
            )

    return report


@release_app.command("plan")
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
        channel=channel,
        repo_overrides=repo,
        ref_overrides=ref,
        auto=auto,
        allow_non_green=allow_non_green,
        interactive=not no_interactive,
    )

    report = _render_open_control_preflight(
        workspace_root=ctx.workspace.root,
        pinned=pinned,
        console=ctx.console,
    )
    if report is not None and report.dirty_repos() and not allow_open_control_dirty:
        ctx.console.print(
            "warning: open-control has uncommitted changes; dev symlink tests may not reflect release builds",
            Style.DIM,
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

    if out is not None:
        plan_file = write_plan_file(
            path=out,
            plan=PlanInput(
                channel=plan_r.value.channel, tag=plan_r.value.tag, pinned=plan_r.value.pinned
            ),
        )
        if isinstance(plan_file, Err):
            _exit(plan_file.error.message, code=ErrorCode.IO_ERROR)
        ctx.console.success(str(out))

    _print_replay(plan=plan_r.value, console=ctx.console, plan_file=out)


@release_app.command("prepare")
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
        None,
        "--confirm-tag",
        help="Skip confirmation prompt by providing the tag",
    ),
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

    if plan is not None:
        if auto or repo or ref:
            _exit("--plan cannot be combined with --auto/--repo/--ref", code=ErrorCode.USER_ERROR)
        plan_in = read_plan_file(path=plan)
        if isinstance(plan_in, Err):
            _exit(plan_in.error.message, code=ErrorCode.USER_ERROR)
        channel = plan_in.value.channel
        tag = plan_in.value.tag
        pinned = plan_in.value.pinned
    else:
        if channel is None:
            _exit("missing --channel (or pass --plan)", code=ErrorCode.USER_ERROR)
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

    report = _render_open_control_preflight(
        workspace_root=ctx.workspace.root,
        pinned=pinned,
        console=ctx.console,
    )
    if report is not None and report.dirty_repos() and not allow_open_control_dirty:
        _exit(
            "open-control has uncommitted changes (release builds may differ from dev symlink)",
            code=ErrorCode.USER_ERROR,
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
    _print_replay(plan=plan_r.value, console=ctx.console, plan_file=plan)
    if not dry_run:
        _confirm_tag(plan_r.value.tag, confirm_tag=confirm_tag)

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
        None,
        "--confirm-tag",
        help="Skip confirmation prompt by providing the tag",
    ),
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

    if plan is not None:
        if auto or repo or ref:
            _exit("--plan cannot be combined with --auto/--repo/--ref", code=ErrorCode.USER_ERROR)
        plan_in = read_plan_file(path=plan)
        if isinstance(plan_in, Err):
            _exit(plan_in.error.message, code=ErrorCode.USER_ERROR)
        channel = plan_in.value.channel
        tag = plan_in.value.tag
        pinned = plan_in.value.pinned
    else:
        if channel is None:
            _exit("missing --channel (or pass --plan)", code=ErrorCode.USER_ERROR)
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

    report = _render_open_control_preflight(
        workspace_root=ctx.workspace.root,
        pinned=pinned,
        console=ctx.console,
    )
    if report is not None and report.dirty_repos() and not allow_open_control_dirty:
        _exit(
            "open-control has uncommitted changes (release builds may differ from dev symlink)",
            code=ErrorCode.USER_ERROR,
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
    _print_replay(plan=plan_r.value, console=ctx.console, plan_file=plan)
    if not dry_run:
        _confirm_tag(plan_r.value.tag, confirm_tag=confirm_tag)

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


@release_app.command("remove")
def remove_cmd(
    tag: list[str] = typer.Option([], "--tag", help="Release tag to delete (repeatable)"),
    force: bool = typer.Option(False, "--force", help="Allow deleting stable tags"),
    ignore_missing: bool = typer.Option(False, "--ignore-missing", help="Ignore missing releases"),
    yes: bool = typer.Option(False, "-y", "--yes", help="Skip confirmation prompt"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print actions without mutating"),
) -> None:
    """Remove releases (cleanup artifacts + delete GitHub Releases)."""
    ctx = build_context()

    ok = ensure_release_permissions(
        workspace_root=ctx.workspace.root,
        console=ctx.console,
        require_write=True,
    )
    if isinstance(ok, Err):
        _exit(ok.error.message, code=ErrorCode.USER_ERROR)

    valid = validate_remove_tags(tags=tag, force=force)
    if isinstance(valid, Err):
        _exit(valid.error.message, code=ErrorCode.USER_ERROR)
    tags = valid.value

    ctx.console.header("Remove Releases")
    for t in tags:
        ctx.console.print(f"- {t}")
    if not dry_run and not yes:
        typed = typer.prompt("Type DELETE to confirm", default="")
        if typed.strip() != "DELETE":
            _exit("confirmation mismatch", code=ErrorCode.USER_ERROR)

    # 1) Remove spec/notes artifacts via PR (safe, reversible).
    artifacts = remove_distribution_artifacts(
        workspace_root=ctx.workspace.root,
        console=ctx.console,
        tags=tags,
        dry_run=dry_run,
    )
    if isinstance(artifacts, Err):
        _exit(artifacts.error.message, code=ErrorCode.IO_ERROR)

    # 2) Delete GitHub releases (irreversible).
    deleted = delete_github_releases(
        workspace_root=ctx.workspace.root,
        console=ctx.console,
        tags=tags,
        ignore_missing=ignore_missing,
        dry_run=dry_run,
    )
    if isinstance(deleted, Err):
        _exit(deleted.error.message, code=ErrorCode.NETWORK_ERROR)

    ctx.console.success("done")
