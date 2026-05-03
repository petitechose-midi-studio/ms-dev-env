from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.output.console import ConsoleProtocol, Style
from ms.release.domain.config import CORE_DEFAULT_BRANCH, CORE_REPO_SLUG
from ms.release.domain.open_control_models import BomPromotionPlan
from ms.release.errors import ReleaseError
from ms.release.flow.bom_promotion_helpers import (
    branch_name,
    build_pr_body,
    merge_failure_hint,
    pr_title,
    restore_bom_files,
    snapshot_bom_files,
    with_branch_hint,
)
from ms.release.flow.bom_validation import validate_workspace_bom_targets
from ms.release.flow.bom_workflow import (
    BomSyncPreview,
    BomSyncResult,
    plan_workspace_bom_sync,
    sync_workspace_bom,
)
from ms.release.flow.core_dependency_pins import (
    CoreDependencyPinPlan,
    plan_core_dependency_pin_sync,
    sync_core_dependency_pins,
)
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
class BomPromotionPrepared:
    core_root: Path
    preview: BomSyncPreview
    core_pin_plan: CoreDependencyPinPlan


@dataclass(frozen=True, slots=True)
class BomPromotionApplied:
    branch: str
    synced: BomSyncResult


def prepare_bom_promotion(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[BomPromotionPrepared, ReleaseError]:
    console.header("Dependency promotion")
    console.print("Checking core workspace", Style.DIM)
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

    console.print("Planning OpenControl BOM changes", Style.DIM)
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

    console.print("Planning core CI/runtime pins", Style.DIM)
    core_pin_plan = plan_core_dependency_pin_sync(
        workspace_root=workspace_root,
        core_root=core_root,
    )
    if isinstance(core_pin_plan, Err):
        return core_pin_plan

    return Ok(
        BomPromotionPrepared(
            core_root=core_root,
            preview=preview.value,
            core_pin_plan=core_pin_plan.value,
        )
    )


def apply_bom_promotion(
    *,
    workspace_root: Path,
    core_root: Path,
    plan: BomPromotionPlan,
    core_pin_plan: CoreDependencyPinPlan,
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[BomPromotionApplied, ReleaseError]:
    console.print("Snapshotting core dependency files", Style.DIM)
    snapshot = snapshot_bom_files(core_root=core_root)
    if isinstance(snapshot, Err):
        return snapshot

    console.print("Writing OpenControl BOM files", Style.DIM)
    synced = sync_workspace_bom(
        workspace_root=workspace_root,
        allow_dirty_workspace=False,
        validate_targets=False,
        include_plugin_release=True,
    )
    if isinstance(synced, Err):
        restored = restore_bom_files(snapshot=snapshot.value)
        if isinstance(restored, Err):
            return restored
        return synced

    console.print("Writing core CI/runtime pins", Style.DIM)
    core_pins = sync_core_dependency_pins(workspace_root=workspace_root, core_root=core_root)
    if isinstance(core_pins, Err):
        restored = restore_bom_files(snapshot=snapshot.value)
        if isinstance(restored, Err):
            return restored
        return core_pins

    console.print("Validating release targets", Style.DIM)
    validations = validate_workspace_bom_targets(
        workspace_root=workspace_root,
        include_plugin_release=True,
        console=console,
    )
    if isinstance(validations, Err):
        restored = restore_bom_files(snapshot=snapshot.value)
        if isinstance(restored, Err):
            return restored
        return validations

    combined_sync = BomSyncResult(
        before=synced.value.before,
        plan=synced.value.plan,
        written=(*synced.value.written, *core_pins.value.written),
        after=synced.value.after,
        validations=validations.value,
    )

    branch = branch_name(plan=plan, core_pin_plan=core_pin_plan)
    console.print(f"Creating promotion branch: {branch}", Style.DIM)
    created = core_create_branch(
        repo_root=core_root,
        branch=branch,
        console=console,
        dry_run=dry_run,
    )
    if isinstance(created, Err):
        restored = restore_bom_files(snapshot=snapshot.value)
        if isinstance(restored, Err):
            return restored
        return created

    return Ok(BomPromotionApplied(branch=branch, synced=combined_sync))


def publish_bom_promotion_pr(
    *,
    workspace_root: Path,
    core_root: Path,
    branch: str,
    plan: BomPromotionPlan,
    core_pin_plan: CoreDependencyPinPlan,
    written: tuple[Path, ...],
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[str, ReleaseError]:
    title = pr_title(plan=plan, core_pin_plan=core_pin_plan)
    console.print(f"Committing dependency promotion: {title}", Style.DIM)
    committed = core_commit_and_push(
        repo_root=core_root,
        branch=branch,
        paths=list(written),
        message=title,
        console=console,
        dry_run=dry_run,
    )
    if isinstance(committed, Err):
        return with_branch_hint(error=committed.error, branch=branch)

    console.print("Opening core dependency PR", Style.DIM)
    pr = core_open_pr(
        workspace_root=workspace_root,
        branch=branch,
        title=title,
        body=build_pr_body(plan=plan, core_pin_plan=core_pin_plan),
        console=console,
        dry_run=dry_run,
    )
    if isinstance(pr, Err):
        return with_branch_hint(error=pr.error, branch=branch)

    console.print("Merging core dependency PR", Style.DIM)
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
                hint=merge_failure_hint(
                    branch=branch,
                    pr_url=pr.value,
                    detail=merged.error.hint,
                ),
            )
        )

    return Ok(pr.value)


def finalize_bom_promotion(
    *,
    workspace_root: Path,
    core_root: Path,
    branch: str,
    pr_url: str,
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[str, ReleaseError]:
    head = get_ref_head_sha(
        workspace_root=workspace_root,
        repo=CORE_REPO_SLUG,
        ref=CORE_DEFAULT_BRANCH,
    )
    if isinstance(head, Err):
        return with_branch_hint(error=head.error, branch=branch, pr_url=pr_url)

    refreshed = core_checkout_main_and_pull(
        repo_root=core_root,
        console=console,
        dry_run=dry_run,
    )
    if isinstance(refreshed, Err):
        return with_branch_hint(error=refreshed.error, branch=branch, pr_url=pr_url)

    return Ok(head.value)
