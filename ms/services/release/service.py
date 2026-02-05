from __future__ import annotations

import json
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.core.structured import as_str_dict
from ms.output.console import ConsoleProtocol, Style
from ms.services.release import config
from ms.services.release.ci import is_ci_green_for_sha
from ms.services.release.dist_repo import (
    checkout_main_and_pull,
    commit_and_push,
    create_branch,
    ensure_clean_git_repo,
    ensure_distribution_repo,
    merge_pr,
    open_pr,
)
from ms.services.release.errors import ReleaseError
from ms.services.release.gh import (
    ensure_gh_auth,
    ensure_gh_available,
    list_distribution_releases,
    viewer_permission,
)
from ms.services.release.model import PinnedRepo, ReleaseBump, ReleaseChannel, ReleasePlan
from ms.services.release.notes import write_release_notes
from ms.services.release.planner import ReleaseHistory, compute_history, suggest_tag, validate_tag
from ms.services.release.spec import write_release_spec
from ms.services.release.workflow import dispatch_publish_workflow, watch_run


def ensure_release_permissions(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    require_write: bool,
) -> Result[None, ReleaseError]:
    ok = ensure_gh_available()
    if isinstance(ok, Err):
        return ok
    ok = ensure_gh_auth(workspace_root=workspace_root)
    if isinstance(ok, Err):
        return ok

    if not require_write:
        return Ok(None)

    perm = viewer_permission(workspace_root=workspace_root, repo=config.DIST_REPO_SLUG)
    if isinstance(perm, Err):
        return perm

    allowed = {"ADMIN", "MAINTAIN", "WRITE"}
    if perm.value not in allowed:
        console.print(f"permission: {perm.value}", Style.DIM)
        return Err(
            ReleaseError(
                kind="permission_denied",
                message="insufficient permission for distribution repo",
                hint="You need WRITE/MAINTAIN/ADMIN on petitechose-midi-studio/distribution.",
            )
        )

    return Ok(None)


def load_distribution_history(*, workspace_root: Path) -> Result[ReleaseHistory, ReleaseError]:
    releases = list_distribution_releases(
        workspace_root=workspace_root, repo=config.DIST_REPO_SLUG, limit=100
    )
    if isinstance(releases, Err):
        return releases
    return Ok(compute_history(releases.value))


def plan_release(
    *,
    workspace_root: Path,
    channel: ReleaseChannel,
    bump: ReleaseBump,
    tag_override: str | None,
    pinned: tuple[PinnedRepo, ...],
) -> Result[ReleasePlan, ReleaseError]:
    history_result = load_distribution_history(workspace_root=workspace_root)
    if isinstance(history_result, Err):
        return history_result
    history = history_result.value

    tag = tag_override or suggest_tag(channel=channel, bump=bump, history=history)
    valid = validate_tag(channel=channel, tag=tag, history=history)
    if isinstance(valid, Err):
        return valid

    spec_path = f"{config.DIST_SPEC_DIR}/{tag}.json"
    notes_path = f"{config.DIST_NOTES_DIR}/{tag}.md"
    title = f"release: {tag} ({channel})"

    return Ok(
        ReleasePlan(
            channel=channel,
            tag=tag,
            pinned=pinned,
            spec_path=spec_path,
            notes_path=notes_path,
            title=title,
        )
    )


def ensure_ci_green(
    *,
    workspace_root: Path,
    pinned: tuple[PinnedRepo, ...],
    allow_non_green: bool,
) -> Result[None, ReleaseError]:
    for p in pinned:
        wf = p.repo.required_ci_workflow_file
        if wf is None:
            # No CI gating configured for this repo.
            continue
        ok = is_ci_green_for_sha(
            workspace_root=workspace_root,
            repo=p.repo.slug,
            workflow=wf,
            sha=p.sha,
        )
        if isinstance(ok, Err):
            return ok

        if ok.value:
            continue

        if allow_non_green:
            continue

        return Err(
            ReleaseError(
                kind="ci_not_green",
                message=f"CI not green for {p.repo.slug}@{p.sha}",
                hint="Pick a SHA with successful CI, or pass --allow-non-green.",
            )
        )

    return Ok(None)


def prepare_distribution_pr(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    plan: ReleasePlan,
    user_notes: str | None,
    user_notes_file: Path | None,
    dry_run: bool,
) -> Result[str, ReleaseError]:
    dist = ensure_distribution_repo(workspace_root=workspace_root, console=console, dry_run=dry_run)
    if isinstance(dist, Err):
        return dist

    if not dry_run:
        clean = ensure_clean_git_repo(repo_root=dist.value.root)
        if isinstance(clean, Err):
            return clean

    pull = checkout_main_and_pull(repo_root=dist.value.root, console=console, dry_run=dry_run)
    if isinstance(pull, Err):
        return pull

    # Idempotency: if the spec/notes already exist on the default branch and match the plan,
    # skip PR creation and proceed.
    if not dry_run and _distribution_artifacts_match_plan(dist_root=dist.value.root, plan=plan):
        console.print("distribution spec already present on main; skipping PR", Style.DIM)
        return Ok(f"(already merged) {plan.spec_path}")

    branch = f"release/{plan.tag}"
    br = create_branch(repo_root=dist.value.root, branch=branch, console=console, dry_run=dry_run)
    if isinstance(br, Err):
        return br

    spec = write_release_spec(
        dist_repo_root=dist.value.root,
        channel=plan.channel,
        tag=plan.tag,
        pinned=plan.pinned,
    )
    if isinstance(spec, Err):
        return spec

    notes = write_release_notes(
        dist_repo_root=dist.value.root,
        channel=plan.channel,
        tag=plan.tag,
        pinned=plan.pinned,
        user_notes=user_notes,
        user_notes_file=user_notes_file,
    )
    if isinstance(notes, Err):
        return notes

    commit_msg = f"release: add {plan.tag} spec"
    commit = commit_and_push(
        repo_root=dist.value.root,
        branch=branch,
        paths=[spec.value.abs_path, notes.value.abs_path],
        message=commit_msg,
        console=console,
        dry_run=dry_run,
    )
    if isinstance(commit, Err):
        return commit

    body_lines = [
        f"channel={plan.channel}",
        "",
        "Pinned SHAs:",
    ]
    for p in plan.pinned:
        body_lines.append(f"- {p.repo.id}: {p.sha}")
    body = "\n".join(body_lines)

    pr = open_pr(
        workspace_root=workspace_root,
        branch=branch,
        title=plan.title,
        body=body,
        console=console,
        dry_run=dry_run,
    )
    if isinstance(pr, Err):
        return pr

    merged = merge_pr(
        workspace_root=workspace_root, pr_url=pr.value, console=console, dry_run=dry_run
    )
    if isinstance(merged, Err):
        return Err(
            ReleaseError(
                kind=merged.error.kind,
                message=merged.error.message,
                hint=f"PR: {pr.value}\n{merged.error.hint or ''}".strip(),
            )
        )

    return Ok(pr.value)


def _distribution_artifacts_match_plan(*, dist_root: Path, plan: ReleasePlan) -> bool:
    spec_path = dist_root / plan.spec_path
    if not spec_path.exists():
        return False

    if plan.notes_path is not None:
        notes_path = dist_root / plan.notes_path
        if not notes_path.exists():
            return False

    try:
        obj: object = json.loads(spec_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False

    spec = as_str_dict(obj)
    if spec is None:
        return False

    if spec.get("tag") != plan.tag:
        return False
    if spec.get("channel") != plan.channel:
        return False

    repos_obj = spec.get("repos")
    if not isinstance(repos_obj, list):
        return False

    repo_map: dict[str, str] = {}
    for r in repos_obj:
        if not isinstance(r, dict):
            continue
        rid = r.get("id")
        sha = r.get("sha")
        if isinstance(rid, str) and isinstance(sha, str):
            repo_map[rid] = sha

    for p in plan.pinned:
        if repo_map.get(p.repo.id) != p.sha:
            return False

    return True


def publish_distribution_release(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    plan: ReleasePlan,
    watch: bool,
    dry_run: bool,
) -> Result[str, ReleaseError]:
    run = dispatch_publish_workflow(
        workspace_root=workspace_root,
        channel=plan.channel,
        tag=plan.tag,
        spec_path=plan.spec_path,
        console=console,
        dry_run=dry_run,
    )
    if isinstance(run, Err):
        return run

    if watch:
        watched = watch_run(
            workspace_root=workspace_root, run_id=run.value.id, console=console, dry_run=dry_run
        )
        if isinstance(watched, Err):
            return watched

    return Ok(run.value.url)
