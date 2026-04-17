from __future__ import annotations

from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.release.domain.open_control_models import (
    OPEN_CONTROL_BOM_REPOS,
    OPEN_CONTROL_NATIVE_CI_REPOS,
    BomPromotionItem,
    BomPromotionPlan,
    BomRepoState,
    BomStateComparison,
    DerivedBomLock,
    OcSdkLoad,
    OcSdkLock,
    OcSdkPin,
    OpenControlRepoState,
)
from ms.release.errors import ReleaseError
from ms.release.flow.bom_native_ci import load_native_ci_bom as load_native_ci_bom_from_files
from ms.release.infra.open_control import (
    OC_SDK_LOCK_FILE,
    collect_open_control_repos,
    parse_oc_sdk_ini,
)
from ms.release.infra.open_control_writer import (
    next_bom_version,
    write_native_ci_sdk_ini,
    write_oc_sdk_ini,
)


def collect_workspace_bom_state(
    *, workspace_root: Path
) -> Result[tuple[OpenControlRepoState, ...], ReleaseError]:
    return Ok(collect_open_control_repos(workspace_root=workspace_root))


def load_bom_lock_from_file(*, path: Path) -> Result[OcSdkLock, ReleaseError]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"failed to read {path.name}",
                hint=str(error),
            )
        )
    return parse_oc_sdk_ini(text=text)


def load_native_ci_bom(*, core_root: Path) -> Result[DerivedBomLock, ReleaseError]:
    return load_native_ci_bom_from_files(core_root=core_root)


def compare_bom_state(
    *,
    bom_lock: OcSdkLock,
    workspace_repos: tuple[OpenControlRepoState, ...],
    derived_lock: DerivedBomLock | None,
    allow_dirty_workspace: bool = False,
) -> BomStateComparison:
    workspace_by_repo = {repo.repo: repo for repo in workspace_repos}
    bom_by_repo = bom_lock.pins_by_repo()
    derived_by_repo = derived_lock.pins_by_repo() if derived_lock is not None else {}
    expected_derived_repos = (
        derived_lock.expected_repos if derived_lock is not None else OPEN_CONTROL_NATIVE_CI_REPOS
    )

    blockers: list[str] = []
    repo_states: list[BomRepoState] = []

    for repo in OPEN_CONTROL_BOM_REPOS:
        workspace_state = workspace_by_repo.get(repo)
        bom_sha = bom_by_repo.get(repo)
        workspace_sha = workspace_state.head_sha if workspace_state is not None else None
        derived_sha = derived_by_repo.get(repo)
        exists = workspace_state.exists if workspace_state is not None else False
        dirty = workspace_state.dirty if workspace_state is not None else False

        if not exists:
            blockers.append(f"workspace repo missing: open-control/{repo}")
        elif workspace_sha is None:
            blockers.append(f"workspace repo head unavailable: open-control/{repo}")
        elif dirty and not allow_dirty_workspace:
            blockers.append(f"workspace repo dirty: open-control/{repo}")

        if derived_lock is None:
            blockers.append("native_ci BOM unavailable")
        elif repo in expected_derived_repos and derived_sha is None:
            blockers.append(f"derived native_ci pin missing: {repo}")

        repo_states.append(
            BomRepoState(
                repo=repo,
                bom_sha=bom_sha,
                workspace_sha=workspace_sha,
                derived_sha=derived_sha,
                workspace_exists=exists,
                workspace_dirty=dirty,
            )
        )

    if blockers:
        return BomStateComparison(
            repos=tuple(repo_states),
            status="blocked",
            blockers=tuple(_dedupe_preserve_order(blockers)),
        )

    requires_promotion = any(state.workspace_sha != state.bom_sha for state in repo_states) or any(
        state.repo in expected_derived_repos and state.derived_sha != state.bom_sha
        for state in repo_states
    )
    return BomStateComparison(
        repos=tuple(repo_states),
        status=("promotion_required" if requires_promotion else "aligned"),
        blockers=(),
    )


def plan_bom_promotion(
    *,
    current_lock: OcSdkLock,
    workspace_repos: tuple[OpenControlRepoState, ...],
    allow_dirty_workspace: bool = False,
) -> Result[BomPromotionPlan, ReleaseError]:
    workspace_by_repo = {repo.repo: repo for repo in workspace_repos}
    current_pins = current_lock.pins_by_repo()

    items: list[BomPromotionItem] = []
    for repo in OPEN_CONTROL_BOM_REPOS:
        workspace_state = workspace_by_repo.get(repo)
        if (
            workspace_state is None
            or not workspace_state.exists
            or workspace_state.head_sha is None
        ):
            return Err(
                ReleaseError(
                    kind="invalid_input",
                    message=f"workspace repo unavailable for BOM promotion: open-control/{repo}",
                    hint="Run: uv run ms sync --repos",
                )
            )
        if workspace_state.dirty and not allow_dirty_workspace:
            return Err(
                ReleaseError(
                    kind="invalid_input",
                    message=f"workspace repo dirty for BOM promotion: open-control/{repo}",
                    hint="Commit or stash changes before promoting the BOM.",
                )
            )

        current_sha = current_pins.get(repo)
        target_sha = workspace_state.head_sha
        items.append(
            BomPromotionItem(
                repo=repo,
                from_sha=current_sha,
                to_sha=target_sha,
                changed=current_sha != target_sha,
            )
        )

    requires_write = any(item.changed for item in items)
    next_version = (
        next_bom_version(current_lock.version) if requires_write else current_lock.version
    )
    return Ok(
        BomPromotionPlan(
            source="workspace",
            current_version=current_lock.version,
            next_version=next_version,
            items=tuple(items),
            requires_write=requires_write,
        )
    )


def verify_bom_files(
    *,
    bom_lock: OcSdkLock,
    derived_lock: DerivedBomLock | None,
) -> Result[None, ReleaseError]:
    if derived_lock is None:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message="native_ci BOM unavailable",
                hint="Add a derived native_ci BOM source for the release workflow.",
            )
        )

    bom_pins = bom_lock.pins_by_repo()
    derived_pins = derived_lock.pins_by_repo()

    missing = [repo for repo in derived_lock.expected_repos if repo not in derived_pins]
    if missing:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"native_ci BOM missing pins: {', '.join(missing)}",
                hint=derived_lock.source,
            )
        )

    mismatches = [
        repo for repo in derived_lock.expected_repos if derived_pins[repo] != bom_pins[repo]
    ]
    if mismatches:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"native_ci BOM mismatches canonical BOM: {', '.join(mismatches)}",
                hint=derived_lock.source,
            )
        )

    return Ok(None)


def load_bom_state_from_core(
    *, core_root: Path
) -> Result[tuple[OcSdkLock, DerivedBomLock | None], ReleaseError]:
    bom_lock = load_bom_lock_from_file(path=core_root / OC_SDK_LOCK_FILE)
    if isinstance(bom_lock, Err):
        return bom_lock

    derived_lock = load_native_ci_bom(core_root=core_root)
    if isinstance(derived_lock, Err):
        return Ok((bom_lock.value, None))
    return Ok((bom_lock.value, derived_lock.value))


def sync_bom_files(
    *, core_root: Path, plan: BomPromotionPlan
) -> Result[tuple[Path, ...], ReleaseError]:
    pins = tuple(OcSdkPin(repo=item.repo, sha=item.to_sha) for item in plan.items)

    written: list[Path] = []
    sdk = write_oc_sdk_ini(core_root=core_root, version=plan.next_version, pins=pins)
    if isinstance(sdk, Err):
        return sdk
    written.append(sdk.value)

    native = write_native_ci_sdk_ini(core_root=core_root, pins=pins)
    if isinstance(native, Err):
        return native
    written.append(native.value)

    return Ok(tuple(written))


def describe_bom_alignment(
    *,
    oc_sdk: OcSdkLoad,
    workspace_repos: tuple[OpenControlRepoState, ...],
    derived_lock: DerivedBomLock | None,
    allow_dirty_workspace: bool = False,
) -> BomStateComparison | None:
    if oc_sdk.lock is None:
        return None
    return compare_bom_state(
        bom_lock=oc_sdk.lock,
        workspace_repos=workspace_repos,
        derived_lock=derived_lock,
        allow_dirty_workspace=allow_dirty_workspace,
    )


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result
