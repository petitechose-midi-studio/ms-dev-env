from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ms.core.platformio_runtime import resolve_platformio_runtime
from ms.core.result import Err, Ok, Result
from ms.platform.process import run as run_process
from ms.release.domain.open_control_models import (
    BomPromotionPlan,
    BomStateComparison,
    DerivedBomLock,
    OcSdkLock,
)
from ms.release.errors import ReleaseError
from ms.release.flow.bom import (
    collect_workspace_bom_state,
    compare_bom_state,
    load_bom_state_from_core,
    plan_bom_promotion,
    sync_bom_files,
    verify_bom_files,
)

_PLATFORMIO_TIMEOUT_SECONDS = 30 * 60.0


@dataclass(frozen=True, slots=True)
class BomWorkspaceState:
    core_root: Path
    bom_lock: OcSdkLock
    derived_lock: DerivedBomLock | None
    comparison: BomStateComparison


@dataclass(frozen=True, slots=True)
class BomSyncPreview:
    state: BomWorkspaceState
    plan: BomPromotionPlan


@dataclass(frozen=True, slots=True)
class BomValidationTarget:
    key: str
    label: str
    cwd: Path
    command: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BomSyncResult:
    before: BomWorkspaceState
    plan: BomPromotionPlan
    written: tuple[Path, ...]
    after: BomWorkspaceState
    validations: tuple[BomValidationTarget, ...]


def inspect_workspace_bom(
    *, workspace_root: Path, allow_dirty_workspace: bool = False
) -> Result[BomWorkspaceState, ReleaseError]:
    core_root = workspace_root / "midi-studio" / "core"
    if not core_root.is_dir():
        return Err(
            ReleaseError(
                kind="invalid_input",
                message="midi-studio/core workspace missing",
                hint="Run: uv run ms sync --repos",
            )
        )

    state = load_bom_state_from_core(core_root=core_root)
    if isinstance(state, Err):
        return state

    workspace_repos = collect_workspace_bom_state(workspace_root=workspace_root)
    if isinstance(workspace_repos, Err):
        return workspace_repos

    bom_lock, derived_lock = state.value
    comparison = compare_bom_state(
        bom_lock=bom_lock,
        workspace_repos=workspace_repos.value,
        derived_lock=derived_lock,
        allow_dirty_workspace=allow_dirty_workspace,
    )
    return Ok(
        BomWorkspaceState(
            core_root=core_root,
            bom_lock=bom_lock,
            derived_lock=derived_lock,
            comparison=comparison,
        )
    )


def plan_workspace_bom_sync(
    *, workspace_root: Path, allow_dirty_workspace: bool = False
) -> Result[BomSyncPreview, ReleaseError]:
    inspected = inspect_workspace_bom(
        workspace_root=workspace_root,
        allow_dirty_workspace=allow_dirty_workspace,
    )
    if isinstance(inspected, Err):
        return inspected

    workspace_repos = collect_workspace_bom_state(workspace_root=workspace_root)
    if isinstance(workspace_repos, Err):
        return workspace_repos

    plan = plan_bom_promotion(
        current_lock=inspected.value.bom_lock,
        workspace_repos=workspace_repos.value,
        allow_dirty_workspace=allow_dirty_workspace,
    )
    if isinstance(plan, Err):
        return plan

    return Ok(BomSyncPreview(state=inspected.value, plan=plan.value))


def verify_workspace_bom_files(
    *, workspace_root: Path, allow_dirty_workspace: bool = False
) -> Result[BomWorkspaceState, ReleaseError]:
    inspected = inspect_workspace_bom(
        workspace_root=workspace_root,
        allow_dirty_workspace=allow_dirty_workspace,
    )
    if isinstance(inspected, Err):
        return inspected

    verified = verify_bom_files(
        bom_lock=inspected.value.bom_lock,
        derived_lock=inspected.value.derived_lock,
    )
    if isinstance(verified, Err):
        return verified

    return inspected


def validate_workspace_bom_targets(
    *, workspace_root: Path, include_plugin_release: bool = True
) -> Result[tuple[BomValidationTarget, ...], ReleaseError]:
    runtime = resolve_platformio_runtime(workspace_root)
    if isinstance(runtime, Err):
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=runtime.error.message,
                hint=runtime.error.hint,
            )
        )

    runtime_command = tuple(runtime.value.command())
    targets = list(
        _validation_targets(
            workspace_root=workspace_root,
            command=runtime_command,
        )
    )
    if not include_plugin_release:
        targets = [target for target in targets if target.key != "plugin-bitwig-release"]

    validated: list[BomValidationTarget] = []
    for target in targets:
        result = run_process(
            list(target.command),
            cwd=target.cwd,
            env=runtime.value.env,
            timeout=_PLATFORMIO_TIMEOUT_SECONDS,
        )
        if isinstance(result, Err):
            return Err(
                ReleaseError(
                    kind="repo_failed",
                    message=f"{target.label} failed",
                    hint=_process_hint(result.error.stdout, result.error.stderr),
                )
            )
        validated.append(target)

    return Ok(tuple(validated))


def sync_workspace_bom(
    *,
    workspace_root: Path,
    allow_dirty_workspace: bool = False,
    validate_targets: bool = True,
    include_plugin_release: bool = True,
) -> Result[BomSyncResult, ReleaseError]:
    preview = plan_workspace_bom_sync(
        workspace_root=workspace_root,
        allow_dirty_workspace=allow_dirty_workspace,
    )
    if isinstance(preview, Err):
        return preview

    written: tuple[Path, ...] = ()
    if preview.value.plan.requires_write:
        synced = sync_bom_files(core_root=preview.value.state.core_root, plan=preview.value.plan)
        if isinstance(synced, Err):
            return synced
        written = synced.value

    after = verify_workspace_bom_files(
        workspace_root=workspace_root,
        allow_dirty_workspace=allow_dirty_workspace,
    )
    if isinstance(after, Err):
        return after

    validations: tuple[BomValidationTarget, ...] = ()
    if validate_targets:
        validated = validate_workspace_bom_targets(
            workspace_root=workspace_root,
            include_plugin_release=include_plugin_release,
        )
        if isinstance(validated, Err):
            return validated
        validations = validated.value

    return Ok(
        BomSyncResult(
            before=preview.value.state,
            plan=preview.value.plan,
            written=written,
            after=after.value,
            validations=validations,
        )
    )


def _validation_targets(
    *, workspace_root: Path, command: tuple[str, ...]
) -> tuple[BomValidationTarget, ...]:
    core_root = workspace_root / "midi-studio" / "core"
    plugin_root = workspace_root / "midi-studio" / "plugin-bitwig"

    return (
        BomValidationTarget(
            key="core-release",
            label="core release",
            cwd=core_root,
            command=(*command, "run", "-e", "release"),
        ),
        BomValidationTarget(
            key="core-native-ci",
            label="core native_ci",
            cwd=core_root,
            command=(*command, "test", "-e", "native_ci"),
        ),
        BomValidationTarget(
            key="plugin-bitwig-release",
            label="plugin-bitwig release",
            cwd=plugin_root,
            command=(*command, "run", "-e", "release"),
        ),
    )


def _process_hint(stdout: str, stderr: str) -> str | None:
    text = (stderr or stdout).strip()
    if not text:
        return None
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None
    hint = lines[-1]
    if len(hint) > 300:
        return hint[:297] + "..."
    return hint
