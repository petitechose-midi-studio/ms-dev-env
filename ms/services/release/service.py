from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.core.structured import as_obj_list, as_str_dict
from ms.output.console import ConsoleProtocol, Style
from ms.services.release import config
from ms.services.release.app_repo import (
    checkout_main_and_pull as app_checkout_main_and_pull,
)
from ms.services.release.app_repo import (
    commit_and_push as app_commit_and_push,
)
from ms.services.release.app_repo import (
    create_branch as app_create_branch,
)
from ms.services.release.app_repo import (
    ensure_app_repo,
)
from ms.services.release.app_repo import (
    ensure_clean_git_repo as ensure_clean_app_repo,
)
from ms.services.release.app_repo import (
    merge_pr as app_merge_pr,
)
from ms.services.release.app_repo import (
    open_pr as app_open_pr,
)
from ms.services.release.app_version import (
    app_version_files,
    apply_version,
    current_version,
    version_from_tag,
)
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
from ms.services.release.workflow import (
    dispatch_app_candidate_workflow,
    dispatch_app_release_workflow,
    dispatch_publish_workflow,
    watch_run,
)


@dataclass(frozen=True, slots=True)
class AppPrepareResult:
    pr_url: str
    source_sha: str


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


def ensure_app_release_permissions(
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

    perm = viewer_permission(workspace_root=workspace_root, repo=config.APP_REPO_SLUG)
    if isinstance(perm, Err):
        return perm

    allowed = {"ADMIN", "MAINTAIN", "WRITE"}
    if perm.value not in allowed:
        console.print(f"permission: {perm.value}", Style.DIM)
        return Err(
            ReleaseError(
                kind="permission_denied",
                message="insufficient permission for app repo",
                hint=f"You need WRITE/MAINTAIN/ADMIN on {config.APP_REPO_SLUG}.",
            )
        )

    return Ok(None)


def load_app_history(*, workspace_root: Path) -> Result[ReleaseHistory, ReleaseError]:
    releases = list_distribution_releases(
        workspace_root=workspace_root, repo=config.APP_REPO_SLUG, limit=100
    )
    if isinstance(releases, Err):
        return releases
    return Ok(compute_history(releases.value))


def plan_app_release(
    *,
    workspace_root: Path,
    channel: ReleaseChannel,
    bump: ReleaseBump,
    tag_override: str | None,
    pinned: tuple[PinnedRepo, ...],
) -> Result[tuple[str, str], ReleaseError]:
    history_result = load_app_history(workspace_root=workspace_root)
    if isinstance(history_result, Err):
        return history_result
    history = history_result.value

    tag = tag_override or suggest_tag(channel=channel, bump=bump, history=history)
    valid = validate_tag(channel=channel, tag=tag, history=history)
    if isinstance(valid, Err):
        return valid

    version = version_from_tag(tag=tag)
    if isinstance(version, Err):
        return version

    return Ok((tag, version.value))


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


def _prepare_distribution_repo(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[Path, ReleaseError]:
    dist = ensure_distribution_repo(workspace_root=workspace_root, console=console, dry_run=dry_run)
    if isinstance(dist, Err):
        return dist

    dist_root = dist.value.root
    if not dry_run:
        clean = ensure_clean_git_repo(repo_root=dist_root)
        if isinstance(clean, Err):
            return clean

    pull = checkout_main_and_pull(repo_root=dist_root, console=console, dry_run=dry_run)
    if isinstance(pull, Err):
        return pull

    return Ok(dist_root)


def _prepare_app_repo(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[Path, ReleaseError]:
    app = ensure_app_repo(workspace_root=workspace_root, console=console, dry_run=dry_run)
    if isinstance(app, Err):
        return app

    app_root = app.value.root
    if not dry_run:
        clean = ensure_clean_app_repo(repo_root=app_root)
        if isinstance(clean, Err):
            return clean

    pull = app_checkout_main_and_pull(repo_root=app_root, console=console, dry_run=dry_run)
    if isinstance(pull, Err):
        return pull

    return Ok(app_root)


def _build_pinned_body(*, intro: tuple[str, ...], pinned: tuple[PinnedRepo, ...]) -> str:
    lines = [*intro, "", "Pinned SHAs:"]
    lines.extend(f"- {p.repo.id}: {p.sha}" for p in pinned)
    return "\n".join(lines)


def _merge_distribution_pr(
    *,
    workspace_root: Path,
    pr_url: str,
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[None, ReleaseError]:
    merged = merge_pr(
        workspace_root=workspace_root,
        pr_url=pr_url,
        console=console,
        dry_run=dry_run,
    )
    if isinstance(merged, Err):
        return Err(
            ReleaseError(
                kind=merged.error.kind,
                message=merged.error.message,
                hint=f"PR: {pr_url}\n{merged.error.hint or ''}".strip(),
            )
        )
    return Ok(None)


def _merge_app_pr(
    *,
    workspace_root: Path,
    pr_url: str,
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[None, ReleaseError]:
    merged = app_merge_pr(
        workspace_root=workspace_root,
        pr_url=pr_url,
        delete_branch=False,
        console=console,
        dry_run=dry_run,
    )
    if isinstance(merged, Err):
        return Err(
            ReleaseError(
                kind=merged.error.kind,
                message=merged.error.message,
                hint=f"PR: {pr_url}\n{merged.error.hint or ''}".strip(),
            )
        )
    return Ok(None)


def _is_app_version_already_present(*, app_root: Path, version: str) -> Result[bool, ReleaseError]:
    cur = current_version(app_repo_root=app_root)
    if isinstance(cur, Err):
        return cur
    return Ok(cur.value == version)


def _resolve_app_changed_paths(
    *,
    app_root: Path,
    version: str,
    dry_run: bool,
) -> Result[list[Path], ReleaseError]:
    if dry_run:
        vf = app_version_files(app_repo_root=app_root)
        return Ok([vf.package_json, vf.cargo_toml, vf.tauri_conf])

    changed = apply_version(app_repo_root=app_root, version=version)
    if isinstance(changed, Err):
        return changed
    if not changed.value:
        return Err(
            ReleaseError(
                kind="dist_repo_failed",
                message="version update produced no file changes",
                hint=f"Target version: {version}",
            )
        )
    return Ok(changed.value)


def prepare_distribution_pr(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    plan: ReleasePlan,
    user_notes: str | None,
    user_notes_file: Path | None,
    dry_run: bool,
) -> Result[str, ReleaseError]:
    dist_root_r = _prepare_distribution_repo(
        workspace_root=workspace_root,
        console=console,
        dry_run=dry_run,
    )
    if isinstance(dist_root_r, Err):
        return dist_root_r
    dist_root = dist_root_r.value

    # Idempotency: if the spec/notes already exist on the default branch and match the plan,
    # skip PR creation and proceed.
    if not dry_run and _distribution_artifacts_match_plan(dist_root=dist_root, plan=plan):
        console.print("distribution spec already present on main; skipping PR", Style.DIM)
        return Ok(f"(already merged) {plan.spec_path}")

    branch = f"release/{plan.tag}"
    br = create_branch(repo_root=dist_root, branch=branch, console=console, dry_run=dry_run)
    if isinstance(br, Err):
        return br

    spec = write_release_spec(
        dist_repo_root=dist_root,
        channel=plan.channel,
        tag=plan.tag,
        pinned=plan.pinned,
    )
    if isinstance(spec, Err):
        return spec

    notes = write_release_notes(
        dist_repo_root=dist_root,
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
        repo_root=dist_root,
        branch=branch,
        paths=[spec.value.abs_path, notes.value.abs_path],
        message=commit_msg,
        console=console,
        dry_run=dry_run,
    )
    if isinstance(commit, Err):
        return commit

    body = _build_pinned_body(intro=(f"channel={plan.channel}",), pinned=plan.pinned)

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

    merged = _merge_distribution_pr(
        workspace_root=workspace_root,
        pr_url=pr.value,
        console=console,
        dry_run=dry_run,
    )
    if isinstance(merged, Err):
        return merged

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

    repos_obj = as_obj_list(spec.get("repos"))
    if repos_obj is None:
        return False

    repo_map: dict[str, str] = {}
    for obj in repos_obj:
        r = as_str_dict(obj)
        if r is None:
            continue
        rid = r.get("id")
        sha = r.get("sha")
        if isinstance(rid, str) and isinstance(sha, str):
            repo_map[rid] = sha

    return all(repo_map.get(p.repo.id) == p.sha for p in plan.pinned)


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
            workspace_root=workspace_root,
            run_id=run.value.id,
            repo_slug=config.DIST_REPO_SLUG,
            console=console,
            dry_run=dry_run,
        )
        if isinstance(watched, Err):
            return watched

    return Ok(run.value.url)


def prepare_app_pr(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    tag: str,
    version: str,
    base_sha: str,
    pinned: tuple[PinnedRepo, ...],
    dry_run: bool,
) -> Result[AppPrepareResult, ReleaseError]:
    app_root_r = _prepare_app_repo(workspace_root=workspace_root, console=console, dry_run=dry_run)
    if isinstance(app_root_r, Err):
        return app_root_r
    app_root = app_root_r.value

    if not dry_run:
        already_r = _is_app_version_already_present(app_root=app_root, version=version)
        if isinstance(already_r, Err):
            return already_r
        if already_r.value:
            console.print("app version already present on main; skipping PR", Style.DIM)
            return Ok(AppPrepareResult(pr_url=f"(already merged) {tag}", source_sha=base_sha))

    branch = f"release/{tag}-{base_sha[:8]}"
    br = app_create_branch(
        repo_root=app_root,
        branch=branch,
        base_sha=base_sha,
        console=console,
        dry_run=dry_run,
    )
    if isinstance(br, Err):
        return br

    changed_paths_r = _resolve_app_changed_paths(
        app_root=app_root, version=version, dry_run=dry_run
    )
    if isinstance(changed_paths_r, Err):
        return changed_paths_r
    changed_paths = changed_paths_r.value

    title = f"release(app): {tag}"
    commit_msg = f"release(app): bump version to {version}"
    body = _build_pinned_body(intro=(f"tag={tag}", f"version={version}"), pinned=pinned)

    commit = app_commit_and_push(
        repo_root=app_root,
        branch=branch,
        paths=changed_paths,
        message=commit_msg,
        console=console,
        dry_run=dry_run,
    )
    if isinstance(commit, Err):
        return commit

    source_sha = base_sha if dry_run else commit.value

    pr = app_open_pr(
        workspace_root=workspace_root,
        branch=branch,
        title=title,
        body=body,
        console=console,
        dry_run=dry_run,
    )
    if isinstance(pr, Err):
        return pr

    merged = _merge_app_pr(
        workspace_root=workspace_root,
        pr_url=pr.value,
        console=console,
        dry_run=dry_run,
    )
    if isinstance(merged, Err):
        return merged

    return Ok(AppPrepareResult(pr_url=pr.value, source_sha=source_sha))


def publish_app_release(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    tag: str,
    source_sha: str,
    notes_markdown: str | None,
    notes_source_path: str | None,
    watch: bool,
    dry_run: bool,
) -> Result[tuple[str, str], ReleaseError]:
    if notes_markdown is not None:
        source_label = notes_source_path or "(unknown source)"
        console.print(
            "release notes: external markdown attached from "
            f"{source_label} (prepended above auto-notes)",
            Style.DIM,
        )
    else:
        console.print("release notes: automatic notes only", Style.DIM)

    candidate = dispatch_app_candidate_workflow(
        workspace_root=workspace_root,
        source_sha=source_sha,
        console=console,
        dry_run=dry_run,
    )
    if isinstance(candidate, Err):
        return candidate

    if watch:
        watched = watch_run(
            workspace_root=workspace_root,
            run_id=candidate.value.id,
            repo_slug=config.APP_REPO_SLUG,
            console=console,
            dry_run=dry_run,
        )
        if isinstance(watched, Err):
            return watched

    release = dispatch_app_release_workflow(
        workspace_root=workspace_root,
        tag=tag,
        source_sha=source_sha,
        notes_markdown=notes_markdown,
        notes_source_path=notes_source_path,
        console=console,
        dry_run=dry_run,
    )
    if isinstance(release, Err):
        return release

    if watch:
        watched = watch_run(
            workspace_root=workspace_root,
            run_id=release.value.id,
            repo_slug=config.APP_REPO_SLUG,
            console=console,
            dry_run=dry_run,
        )
        if isinstance(watched, Err):
            return watched

    return Ok((candidate.value.url, release.value.url))
