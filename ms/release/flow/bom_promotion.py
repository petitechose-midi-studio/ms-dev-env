from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.output.console import ConsoleProtocol, Style
from ms.release.domain.config import CORE_DEFAULT_BRANCH, CORE_REPO_SLUG
from ms.release.domain.open_control_models import BomPromotionPlan
from ms.release.errors import ReleaseError
from ms.release.flow.pr_outcome import PrMergeOutcome
from ms.release.infra.github.client import get_ref_head_sha

from .bom_promotion_steps import (
    apply_bom_promotion,
    finalize_bom_promotion,
    prepare_bom_promotion,
    publish_bom_promotion_pr,
)


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

    prepared = prepare_bom_promotion(
        workspace_root=workspace_root,
        console=console,
        dry_run=dry_run,
    )
    if isinstance(prepared, Err):
        return prepared

    if (
        not prepared.value.preview.plan.requires_write
        and not prepared.value.core_pin_plan.requires_write
    ):
        return _already_merged_bom_result(
            workspace_root=workspace_root,
            plan=prepared.value.preview.plan,
        )

    applied = apply_bom_promotion(
        workspace_root=workspace_root,
        core_root=prepared.value.core_root,
        plan=prepared.value.preview.plan,
        core_pin_plan=prepared.value.core_pin_plan,
        console=console,
        dry_run=dry_run,
    )
    if isinstance(applied, Err):
        return applied

    pr = publish_bom_promotion_pr(
        workspace_root=workspace_root,
        core_root=prepared.value.core_root,
        branch=applied.value.branch,
        plan=applied.value.synced.plan,
        core_pin_plan=prepared.value.core_pin_plan,
        written=applied.value.synced.written,
        console=console,
        dry_run=dry_run,
    )
    if isinstance(pr, Err):
        return pr

    merged_core_sha = finalize_bom_promotion(
        workspace_root=workspace_root,
        core_root=prepared.value.core_root,
        branch=applied.value.branch,
        pr_url=pr.value,
        console=console,
        dry_run=dry_run,
    )
    if isinstance(merged_core_sha, Err):
        return merged_core_sha

    console.print(f"core BOM merged on {merged_core_sha.value[:12]}", Style.DIM)
    return Ok(
        BomPromotionResult(
            pr=PrMergeOutcome(kind="merged_pr", url=pr.value, label=pr.value),
            merged_core_sha=merged_core_sha.value,
            plan=applied.value.synced.plan,
        )
    )


def _already_merged_bom_result(
    *,
    workspace_root: Path,
    plan: BomPromotionPlan,
) -> Result[BomPromotionResult, ReleaseError]:
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
                label=f"(already merged) oc-sdk v{plan.next_version}",
            ),
            merged_core_sha=head.value,
            plan=plan,
        )
    )
