from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.output.console import ConsoleProtocol, Style
from ms.release.domain.config import CORE_DEFAULT_BRANCH, CORE_REPO_SLUG
from ms.release.domain.open_control_models import BomPromotionItem, BomPromotionPlan
from ms.release.errors import ReleaseError
from ms.release.flow.bom_workflow import plan_workspace_bom_sync, sync_workspace_bom
from ms.release.flow.pr_outcome import PrMergeOutcome
from ms.release.infra.github.client import get_ref_head_sha
from ms.release.infra.repos.core import (
    checkout_main_and_pull as core_checkout_main_and_pull,
)
from ms.release.infra.repos.core import commit_and_push as core_commit_and_push
from ms.release.infra.repos.core import create_branch as core_create_branch
from ms.release.infra.repos.core import ensure_clean_git_repo as ensure_clean_core_repo
from ms.release.infra.repos.core import ensure_core_repo
from ms.release.infra.repos.core import merge_pr as core_merge_pr
from ms.release.infra.repos.core import open_pr as core_open_pr


@dataclass(frozen=True, slots=True)
class BomPromotionResult:
    pr: PrMergeOutcome
    merged_core_sha: str
    plan: BomPromotionPlan


def promote_open_control_bom(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[BomPromotionResult, ReleaseError]:
    if dry_run:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message="dry-run cannot simulate BOM promotion",
                hint="Rerun without --dry-run to promote the BOM.",
            )
        )

    core_repo = ensure_core_repo(workspace_root=workspace_root, console=console, dry_run=dry_run)
    if isinstance(core_repo, Err):
        return core_repo
    core_root = core_repo.value.root

    clean = ensure_clean_core_repo(repo_root=core_root)
    if isinstance(clean, Err):
        return clean

    pulled = core_checkout_main_and_pull(repo_root=core_root, console=console, dry_run=dry_run)
    if isinstance(pulled, Err):
        return pulled

    preview = plan_workspace_bom_sync(workspace_root=workspace_root, allow_dirty_workspace=False)
    if isinstance(preview, Err):
        return preview

    if preview.value.state.comparison.status == "blocked":
        blockers = preview.value.state.comparison.blockers
        blocker = blockers[0] if blockers else None
        return Err(
            ReleaseError(
                kind="invalid_input",
                message="OpenControl BOM promotion is blocked",
                hint=blocker,
            )
        )

    if not preview.value.plan.requires_write:
        head = get_ref_head_sha(
            workspace_root=workspace_root,
            repo=CORE_REPO_SLUG,
            ref=CORE_DEFAULT_BRANCH,
        )
        if isinstance(head, Err):
            return head
        return Ok(
            BomPromotionResult(
                pr=PrMergeOutcome(
                    kind="already_merged",
                    url=None,
                    label=f"(already merged) oc-sdk v{preview.value.plan.next_version}",
                ),
                merged_core_sha=head.value,
                plan=preview.value.plan,
            )
        )

    branch = _branch_name(plan=preview.value.plan)
    created = core_create_branch(
        repo_root=core_root,
        branch=branch,
        console=console,
        dry_run=dry_run,
    )
    if isinstance(created, Err):
        return created

    synced = sync_workspace_bom(
        workspace_root=workspace_root,
        allow_dirty_workspace=False,
        validate_targets=True,
        include_plugin_release=True,
    )
    if isinstance(synced, Err):
        return synced

    title = f"release(core): promote OpenControl BOM to v{synced.value.plan.next_version}"
    commit_message = title
    body = _build_pr_body(plan=synced.value.plan)

    committed = core_commit_and_push(
        repo_root=core_root,
        branch=branch,
        paths=list(synced.value.written),
        message=commit_message,
        console=console,
        dry_run=dry_run,
    )
    if isinstance(committed, Err):
        return committed

    pr = core_open_pr(
        workspace_root=workspace_root,
        branch=branch,
        title=title,
        body=body,
        console=console,
        dry_run=dry_run,
    )
    if isinstance(pr, Err):
        return pr

    merged = core_merge_pr(
        workspace_root=workspace_root,
        pr_url=pr.value,
        console=console,
        dry_run=dry_run,
    )
    if isinstance(merged, Err):
        return Err(
            ReleaseError(
                kind=merged.error.kind,
                message=merged.error.message,
                hint=f"PR: {pr.value}\n{merged.error.hint or ''}".strip(),
            )
        )

    head = get_ref_head_sha(
        workspace_root=workspace_root,
        repo=CORE_REPO_SLUG,
        ref=CORE_DEFAULT_BRANCH,
    )
    if isinstance(head, Err):
        return head

    refreshed = core_checkout_main_and_pull(
        repo_root=core_root,
        console=console,
        dry_run=dry_run,
    )
    if isinstance(refreshed, Err):
        return refreshed

    console.print(f"core BOM merged on {head.value[:12]}", Style.DIM)
    return Ok(
        BomPromotionResult(
            pr=PrMergeOutcome(kind="merged_pr", url=pr.value, label=pr.value),
            merged_core_sha=head.value,
            plan=synced.value.plan,
        )
    )


def _branch_name(*, plan: BomPromotionPlan) -> str:
    changed = next((item for item in plan.items if item.changed), None)
    suffix = changed.to_sha[:8] if changed is not None else "current"
    return f"release/oc-sdk-v{plan.next_version}-{suffix}"


def _build_pr_body(*, plan: BomPromotionPlan) -> str:
    lines = [
        "Promote OpenControl BOM to the current workspace heads.",
        "",
        f"oc-sdk.version: {plan.current_version} -> {plan.next_version}",
        "",
        "Changed pins:",
    ]
    changed = [item for item in plan.items if item.changed]
    lines.extend(_render_item(item) for item in (changed or list(plan.items)))
    return "\n".join(lines)


def _render_item(item: BomPromotionItem) -> str:
    before = item.from_sha[:12] if item.from_sha is not None else "unset"
    after = item.to_sha[:12]
    return f"- {item.repo}: {before} -> {after}"
