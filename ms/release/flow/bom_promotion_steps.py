from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.output.console import ConsoleProtocol
from ms.release.domain.config import CORE_DEFAULT_BRANCH, CORE_REPO_SLUG
from ms.release.domain.open_control_models import BomPromotionItem, BomPromotionPlan
from ms.release.errors import ReleaseError
from ms.release.flow.bom_workflow import (
    BomSyncPreview,
    BomSyncResult,
    plan_workspace_bom_sync,
    sync_workspace_bom,
)
from ms.release.infra.github.client import get_ref_head_sha
from ms.release.infra.open_control import OC_SDK_LOCK_FILE
from ms.release.infra.open_control_writer import OC_NATIVE_SDK_FILE
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

    return Ok(BomPromotionPrepared(core_root=core_root, preview=preview.value))


def apply_bom_promotion(
    *,
    workspace_root: Path,
    core_root: Path,
    plan: BomPromotionPlan,
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[BomPromotionApplied, ReleaseError]:
    snapshot = _snapshot_bom_files(core_root=core_root)
    if isinstance(snapshot, Err):
        return snapshot

    synced = sync_workspace_bom(
        workspace_root=workspace_root,
        allow_dirty_workspace=False,
        validate_targets=True,
        include_plugin_release=True,
    )
    if isinstance(synced, Err):
        restored = _restore_bom_files(snapshot=snapshot.value)
        if isinstance(restored, Err):
            return restored
        return synced

    branch = _branch_name(plan=plan)
    created = core_create_branch(
        repo_root=core_root,
        branch=branch,
        console=console,
        dry_run=dry_run,
    )
    if isinstance(created, Err):
        restored = _restore_bom_files(snapshot=snapshot.value)
        if isinstance(restored, Err):
            return restored
        return created

    return Ok(BomPromotionApplied(branch=branch, synced=synced.value))


def publish_bom_promotion_pr(
    *,
    workspace_root: Path,
    core_root: Path,
    branch: str,
    plan: BomPromotionPlan,
    written: tuple[Path, ...],
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[str, ReleaseError]:
    title = f"release(core): promote OpenControl BOM to v{plan.next_version}"
    committed = core_commit_and_push(
        repo_root=core_root,
        branch=branch,
        paths=list(written),
        message=title,
        console=console,
        dry_run=dry_run,
    )
    if isinstance(committed, Err):
        return _with_branch_hint(error=committed.error, branch=branch)

    pr = core_open_pr(
        workspace_root=workspace_root,
        branch=branch,
        title=title,
        body=_build_pr_body(plan=plan),
        console=console,
        dry_run=dry_run,
    )
    if isinstance(pr, Err):
        return _with_branch_hint(error=pr.error, branch=branch)

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
                hint=_merge_failure_hint(branch=branch, pr_url=pr.value, detail=merged.error.hint),
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
        return _with_branch_hint(error=head.error, branch=branch, pr_url=pr_url)

    refreshed = core_checkout_main_and_pull(
        repo_root=core_root,
        console=console,
        dry_run=dry_run,
    )
    if isinstance(refreshed, Err):
        return _with_branch_hint(error=refreshed.error, branch=branch, pr_url=pr_url)

    return Ok(head.value)


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


def _snapshot_bom_files(*, core_root: Path) -> Result[dict[Path, str | None], ReleaseError]:
    snapshot: dict[Path, str | None] = {}
    for path in _bom_files(core_root=core_root):
        try:
            snapshot[path] = path.read_text(encoding="utf-8") if path.exists() else None
        except OSError as error:
            return Err(
                ReleaseError(
                    kind="repo_failed",
                    message=f"failed to snapshot {path.name}",
                    hint=str(error),
                )
            )
    return Ok(snapshot)


def _restore_bom_files(*, snapshot: dict[Path, str | None]) -> Result[None, ReleaseError]:
    for path, content in snapshot.items():
        try:
            if content is None:
                if path.exists():
                    path.unlink()
                continue
            path.write_text(content, encoding="utf-8")
        except OSError as error:
            return Err(
                ReleaseError(
                    kind="repo_failed",
                    message=f"failed to restore {path.name} after BOM promotion error",
                    hint=str(error),
                )
            )
    return Ok(None)


def _bom_files(*, core_root: Path) -> tuple[Path, ...]:
    return (
        core_root / OC_SDK_LOCK_FILE,
        core_root / OC_NATIVE_SDK_FILE,
    )


def _with_branch_hint(
    *, error: ReleaseError, branch: str, pr_url: str | None = None
) -> Err[ReleaseError]:
    lines = [f"core branch: {branch}"]
    if pr_url is not None:
        lines.append(f"PR: {pr_url}")
    if error.hint:
        lines.append(error.hint)
    return Err(
        ReleaseError(
            kind=error.kind,
            message=error.message,
            hint="\n".join(lines),
        )
    )


def _merge_failure_hint(*, branch: str, pr_url: str, detail: str | None) -> str:
    lines = [f"core branch: {branch}", f"PR: {pr_url}"]
    if detail:
        lines.append(detail)
    return "\n".join(lines)
