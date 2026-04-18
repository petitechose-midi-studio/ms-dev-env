from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.core.structured import as_obj_list, as_str_dict
from ms.output.console import ConsoleProtocol, Style
from ms.release.domain.models import PinnedRepo, ReleasePlan
from ms.release.errors import ReleaseError
from ms.release.flow.ci_gate import ensure_ci_green
from ms.release.flow.content_candidates import ensure_content_candidates
from ms.release.infra.artifacts.notes_writer import write_release_notes
from ms.release.infra.artifacts.spec_writer import write_release_spec
from ms.release.infra.repos.distribution import (
    checkout_main_and_pull,
    commit_and_push,
    create_branch,
    ensure_clean_git_repo,
    ensure_distribution_repo,
    merge_pr,
    open_pr,
)

from .pinned_body import build_pinned_body
from .pr_outcome import PrMergeOutcome


@dataclass(frozen=True, slots=True)
class PreparedContentRelease:
    plan: ReleasePlan
    pr: PrMergeOutcome


def _prepare_distribution_repo(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[Path, ReleaseError]:
    dist = ensure_distribution_repo(
        workspace_root=workspace_root,
        console=console,
        dry_run=dry_run,
    )
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


def prepare_distribution_pr(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    plan: ReleasePlan,
    user_notes: str | None,
    user_notes_file: Path | None,
    dry_run: bool,
) -> Result[PrMergeOutcome, ReleaseError]:
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
        return Ok(
            PrMergeOutcome(
                kind="already_merged",
                url=None,
                label=f"(already merged) {plan.spec_path}",
            )
        )

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

    body = build_pinned_body(intro=(f"channel={plan.channel}",), pinned=plan.pinned)

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

    return Ok(PrMergeOutcome(kind="merged_pr", url=pr.value, label=pr.value))


def prepare_content_release_distribution(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    plan: ReleasePlan,
    pinned: tuple[PinnedRepo, ...],
    notes: str | None,
    notes_file: Path | None,
    allow_non_green: bool,
    dry_run: bool,
) -> Result[PreparedContentRelease, ReleaseError]:
    green = ensure_ci_green(
        workspace_root=workspace_root,
        pinned=pinned,
        allow_non_green=allow_non_green,
    )
    if isinstance(green, Err):
        return green

    candidates = ensure_content_candidates(
        workspace_root=workspace_root,
        console=console,
        pinned=pinned,
        dry_run=dry_run,
    )
    if isinstance(candidates, Err):
        return candidates

    pr = prepare_distribution_pr(
        workspace_root=workspace_root,
        console=console,
        plan=plan,
        user_notes=notes,
        user_notes_file=notes_file,
        dry_run=dry_run,
    )
    if isinstance(pr, Err):
        return pr

    return Ok(PreparedContentRelease(plan=plan, pr=pr.value))
