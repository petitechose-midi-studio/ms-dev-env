from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.output.console import ConsoleProtocol, Style
from ms.release.domain.models import AppReleasePlan, PinnedRepo
from ms.release.errors import ReleaseError
from ms.release.flow.ci_gate import ensure_ci_green
from ms.release.flow.remote_coherence import assert_release_remote_coherence
from ms.release.infra.artifacts.app_version_writer import (
    app_version_files,
    apply_version,
    current_version,
)
from ms.release.infra.repos.app import (
    checkout_main_and_pull as app_checkout_main_and_pull,
)
from ms.release.infra.repos.app import (
    commit_and_push as app_commit_and_push,
)
from ms.release.infra.repos.app import (
    create_branch as app_create_branch,
)
from ms.release.infra.repos.app import (
    ensure_app_repo,
)
from ms.release.infra.repos.app import (
    ensure_clean_git_repo as ensure_clean_app_repo,
)
from ms.release.infra.repos.app import (
    merge_pr as app_merge_pr,
)
from ms.release.infra.repos.app import (
    open_pr as app_open_pr,
)

from .pinned_body import build_pinned_body
from .pr_outcome import PrMergeOutcome


@dataclass(frozen=True, slots=True)
class AppPrepareResult:
    pr: PrMergeOutcome
    source_sha: str


@dataclass(frozen=True, slots=True)
class PreparedAppRelease:
    plan: AppReleasePlan
    pr: PrMergeOutcome
    source_sha: str


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
                kind="repo_failed",
                message="version update produced no file changes",
                hint=f"Target version: {version}",
            )
        )
    return Ok(changed.value)


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
            return Ok(
                AppPrepareResult(
                    pr=PrMergeOutcome(
                        kind="already_merged",
                        url=None,
                        label=f"(already merged) {tag}",
                    ),
                    source_sha=base_sha,
                )
            )

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
    body = build_pinned_body(intro=(f"tag={tag}", f"version={version}"), pinned=pinned)

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

    return Ok(
        AppPrepareResult(
            pr=PrMergeOutcome(kind="merged_pr", url=pr.value, label=pr.value),
            source_sha=source_sha,
        )
    )


def prepare_app_release_distribution(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    plan: AppReleasePlan,
    allow_non_green: bool,
    dry_run: bool,
) -> Result[PreparedAppRelease, ReleaseError]:
    green = ensure_ci_green(
        workspace_root=workspace_root,
        pinned=plan.pinned,
        allow_non_green=allow_non_green,
    )
    if isinstance(green, Err):
        return green

    coherence = assert_release_remote_coherence(
        workspace_root=workspace_root,
        console=console,
        pinned=plan.pinned,
        tooling=plan.tooling,
        dry_run=dry_run,
        verify_ci=False,
    )
    if isinstance(coherence, Err):
        return coherence

    prepared = prepare_app_pr(
        workspace_root=workspace_root,
        console=console,
        tag=plan.tag,
        version=plan.version,
        base_sha=plan.pinned[0].sha,
        pinned=plan.pinned,
        dry_run=dry_run,
    )
    if isinstance(prepared, Err):
        return prepared

    return Ok(
        PreparedAppRelease(
            plan=plan,
            pr=prepared.value.pr,
            source_sha=prepared.value.source_sha,
        )
    )
