from __future__ import annotations

from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.release.domain.open_control_models import BomPromotionItem, BomPromotionPlan
from ms.release.errors import ReleaseError
from ms.release.flow.core_dependency_pins import CoreDependencyPinPlan
from ms.release.infra.open_control import OC_SDK_LOCK_FILE
from ms.release.infra.open_control_writer import OC_NATIVE_SDK_FILE


def branch_name(*, plan: BomPromotionPlan, core_pin_plan: CoreDependencyPinPlan) -> str:
    changed = next((item for item in plan.items if item.changed), None)
    if changed is not None:
        suffix = changed.to_sha[:8]
    else:
        pin = next((item for item in core_pin_plan.items if item.changed), None)
        suffix = pin.to_sha[:8] if pin is not None else "current"
    return f"release/oc-sdk-v{plan.next_version}-{suffix}"


def pr_title(*, plan: BomPromotionPlan, core_pin_plan: CoreDependencyPinPlan) -> str:
    if plan.requires_write:
        return f"release(core): promote OpenControl BOM to v{plan.next_version}"
    if core_pin_plan.requires_write:
        return "release(core): promote dependency pins"
    return f"release(core): confirm OpenControl BOM v{plan.next_version}"


def build_pr_body(*, plan: BomPromotionPlan, core_pin_plan: CoreDependencyPinPlan) -> str:
    lines = [
        "Promote core dependency pins to the current workspace heads.",
        "",
        f"oc-sdk.version: {plan.current_version} -> {plan.next_version}",
        "",
        "Changed OpenControl BOM pins:",
    ]
    changed = [item for item in plan.items if item.changed]
    lines.extend(_render_item(item) for item in (changed or list(plan.items)))
    pin_changes = [item for item in core_pin_plan.items if item.changed]
    if pin_changes:
        lines.extend(("", "Changed core CI/runtime pins:"))
        lines.extend(
            f"- {item.key}: "
            f"{item.from_sha[:12] if item.from_sha else 'unset'} -> {item.to_sha[:12]}"
            for item in pin_changes
        )
    return "\n".join(lines)


def snapshot_bom_files(*, core_root: Path) -> Result[dict[Path, str | None], ReleaseError]:
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


def restore_bom_files(*, snapshot: dict[Path, str | None]) -> Result[None, ReleaseError]:
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


def with_branch_hint(
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


def merge_failure_hint(*, branch: str, pr_url: str, detail: str | None) -> str:
    lines = [f"core branch: {branch}", f"PR: {pr_url}"]
    if detail:
        lines.append(detail)
    return "\n".join(lines)


def _render_item(item: BomPromotionItem) -> str:
    before = item.from_sha[:12] if item.from_sha is not None else "unset"
    after = item.to_sha[:12]
    return f"- {item.repo}: {before} -> {after}"


def _bom_files(*, core_root: Path) -> tuple[Path, ...]:
    return (
        core_root / OC_SDK_LOCK_FILE,
        core_root / OC_NATIVE_SDK_FILE,
        core_root / "platformio.ini",
        core_root / ".github" / "workflows" / "ci.yml",
    )
