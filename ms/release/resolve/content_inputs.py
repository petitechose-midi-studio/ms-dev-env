from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.release.domain.models import PinnedRepo, ReleaseChannel, ReleaseRepo
from ms.release.errors import ReleaseError
from ms.release.resolve.overrides import enforce_auto_constraints, parse_override_items


@dataclass(frozen=True, slots=True)
class ResolvePinnedContentOutcome[SuggestionT, BlockerT]:
    pinned: tuple[PinnedRepo, ...] | None
    suggestions: tuple[SuggestionT, ...]
    blockers: tuple[BlockerT, ...]


ContentPicker = Callable[[ReleaseRepo, str], PinnedRepo]
type AutoResolver[SuggestionT, BlockerT] = Callable[
    [Path, ReleaseChannel, dict[str, str]],
    Result[tuple[tuple[PinnedRepo, ...], tuple[SuggestionT, ...]], tuple[BlockerT, ...]],
]


def resolve_pinned_content[SuggestionT, BlockerT](
    *,
    workspace_root: Path,
    channel: ReleaseChannel,
    release_repos: tuple[ReleaseRepo, ...],
    repo_overrides: list[str],
    ref_overrides: list[str],
    auto: bool,
    allow_non_green: bool,
    interactive: bool,
    picker: ContentPicker,
    auto_resolver: AutoResolver[SuggestionT, BlockerT],
) -> Result[ResolvePinnedContentOutcome[SuggestionT, BlockerT], ReleaseError]:
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

    if auto:
        auto_pins = auto_resolver(workspace_root, channel, refs)
        if isinstance(auto_pins, Err):
            return Ok(
                ResolvePinnedContentOutcome(
                    pinned=None,
                    suggestions=(),
                    blockers=auto_pins.error,
                )
            )

        pinned, suggestions = auto_pins.value
        return Ok(
            ResolvePinnedContentOutcome(
                pinned=pinned,
                suggestions=suggestions,
                blockers=(),
            )
        )

    pinned_manual: list[PinnedRepo] = []
    for repo in release_repos:
        ref = refs.get(repo.id, repo.ref)
        selected_repo = ReleaseRepo(
            id=repo.id,
            slug=repo.slug,
            ref=ref,
            required_ci_workflow_file=repo.required_ci_workflow_file,
        )

        if repo.id in overrides:
            pinned_manual.append(PinnedRepo(repo=selected_repo, sha=overrides[repo.id]))
            continue

        if not interactive:
            return Err(
                ReleaseError(
                    kind="invalid_input",
                    message=(f"missing --repo {repo.id}=<sha> (or run without --no-interactive)"),
                )
            )

        pinned_manual.append(picker(selected_repo, ref))

    return Ok(
        ResolvePinnedContentOutcome(
            pinned=tuple(pinned_manual),
            suggestions=(),
            blockers=(),
        )
    )
