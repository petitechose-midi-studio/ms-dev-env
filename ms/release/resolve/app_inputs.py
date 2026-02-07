from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.release.domain.models import PinnedRepo, ReleaseRepo
from ms.release.errors import ReleaseError


@dataclass(frozen=True, slots=True)
class ResolvePinnedAppOutcome[BlockerT]:
    pinned: tuple[PinnedRepo, ...] | None
    blockers: tuple[BlockerT, ...]


AppPicker = Callable[[ReleaseRepo, str], PinnedRepo]
type AutoResolver[BlockerT] = Callable[
    [Path, tuple[ReleaseRepo, ...], dict[str, str]],
    Result[tuple[PinnedRepo, ...], tuple[BlockerT, ...]],
]


def parse_override_items(items: list[str], *, flag: str) -> Result[dict[str, str], ReleaseError]:
    out: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            return Err(
                ReleaseError(
                    kind="invalid_input",
                    message=f"invalid {flag} (expected id=value): {item}",
                )
            )
        key, value = item.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or not value:
            return Err(
                ReleaseError(
                    kind="invalid_input",
                    message=f"invalid {flag} (expected id=value): {item}",
                )
            )
        out[key] = value
    return Ok(out)


def enforce_auto_constraints(
    *,
    auto: bool,
    overrides: dict[str, str],
    allow_non_green: bool,
) -> Result[None, ReleaseError]:
    if not auto:
        return Ok(None)

    if overrides:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message="--auto cannot be combined with --repo overrides",
            )
        )

    if allow_non_green:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message="--auto is strict: remove --allow-non-green",
            )
        )

    return Ok(None)


def resolve_pinned_app[BlockerT](
    *,
    workspace_root: Path,
    app_release_repo: ReleaseRepo,
    repo_overrides: list[str],
    ref_overrides: list[str],
    auto: bool,
    allow_non_green: bool,
    interactive: bool,
    picker: AppPicker,
    auto_resolver: AutoResolver[BlockerT],
) -> Result[ResolvePinnedAppOutcome[BlockerT], ReleaseError]:
    overrides_r = parse_override_items(repo_overrides, flag="--repo")
    if isinstance(overrides_r, Err):
        return overrides_r
    overrides = overrides_r.value

    refs_r = parse_override_items(ref_overrides, flag="--ref")
    if isinstance(refs_r, Err):
        return refs_r
    refs = refs_r.value

    auto_constraints = enforce_auto_constraints(
        auto=auto,
        overrides=overrides,
        allow_non_green=allow_non_green,
    )
    if isinstance(auto_constraints, Err):
        return auto_constraints

    ref = refs.get(app_release_repo.id, app_release_repo.ref)
    selected_repo = ReleaseRepo(
        id=app_release_repo.id,
        slug=app_release_repo.slug,
        ref=ref,
        required_ci_workflow_file=app_release_repo.required_ci_workflow_file,
    )

    if auto:
        auto_pins = auto_resolver(
            workspace_root,
            (selected_repo,),
            {selected_repo.id: ref},
        )
        if isinstance(auto_pins, Err):
            return Ok(ResolvePinnedAppOutcome(pinned=None, blockers=auto_pins.error))
        return Ok(ResolvePinnedAppOutcome(pinned=auto_pins.value, blockers=()))

    if selected_repo.id in overrides:
        return Ok(
            ResolvePinnedAppOutcome(
                pinned=(PinnedRepo(repo=selected_repo, sha=overrides[selected_repo.id]),),
                blockers=(),
            )
        )

    if not interactive:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=(
                    f"missing --repo {selected_repo.id}=<sha> (or run without --no-interactive)"
                ),
            )
        )

    return Ok(
        ResolvePinnedAppOutcome(
            pinned=(picker(selected_repo, ref),),
            blockers=(),
        )
    )
