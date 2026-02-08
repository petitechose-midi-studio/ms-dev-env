from __future__ import annotations

from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.release.domain.diagnostics import AutoSuggestion
from ms.release.domain.models import PinnedRepo, ReleaseChannel, ReleaseRepo

from .carry_mode import load_previous_channel_pins, resolve_carry_mode_pin
from .diagnostics import (
    RepoReadiness,
    build_dist_blocker,
    probe_repo_diagnostics,
    repo_with_ref,
    resolve_repo_ref,
)
from .head_mode import is_head_mode_repo, resolve_head_mode_pin


def resolve_pinned_auto_smart(
    *,
    workspace_root: Path,
    channel: ReleaseChannel,
    dist_repo: str,
    repos: tuple[ReleaseRepo, ...],
    ref_overrides: dict[str, str],
    head_repo_ids: frozenset[str],
) -> Result[tuple[tuple[PinnedRepo, ...], tuple[AutoSuggestion, ...]], tuple[RepoReadiness, ...]]:
    dist_repo_entry = ReleaseRepo(
        id="distribution",
        slug=dist_repo,
        ref="main",
        required_ci_workflow_file=None,
    )

    diagnostics = probe_repo_diagnostics(
        workspace_root=workspace_root,
        repos=repos,
        ref_overrides=ref_overrides,
    )

    previous_pins = load_previous_channel_pins(
        workspace_root=workspace_root,
        channel=channel,
        dist_repo=dist_repo,
    )
    if isinstance(previous_pins, Err):
        return Err(
            (
                build_dist_blocker(
                    workspace_root=workspace_root,
                    dist_repo_entry=dist_repo_entry,
                    error=previous_pins.error,
                ),
            )
        )

    pinned: list[PinnedRepo] = []
    suggestions: list[AutoSuggestion] = []
    blockers: list[RepoReadiness] = []

    for repo in repos:
        ref = resolve_repo_ref(repo=repo, ref_overrides=ref_overrides)
        selected_repo = repo_with_ref(repo=repo, ref=ref)
        diag = diagnostics.get(repo.id)

        if is_head_mode_repo(
            repo=repo,
            ref=ref,
            ref_overrides=ref_overrides,
            head_repo_ids=head_repo_ids,
        ):
            head_pin = resolve_head_mode_pin(
                workspace_root=workspace_root,
                repo=repo,
                ref=ref,
                selected_repo=selected_repo,
                diagnostics=diag,
            )
            if isinstance(head_pin, Err):
                blockers.append(head_pin.error)
                continue
            pinned.append(head_pin.value)
            continue

        carry_pin = resolve_carry_mode_pin(
            workspace_root=workspace_root,
            repo=repo,
            ref=ref,
            selected_repo=selected_repo,
            diagnostics=diag,
            prev_pins=previous_pins.value,
        )
        if isinstance(carry_pin, Err):
            blockers.append(carry_pin.error)
            continue

        selected, carry_suggestions = carry_pin.value
        pinned.append(selected)
        suggestions.extend(carry_suggestions)

    if blockers:
        return Err(tuple(blockers))

    by_id = {entry.repo.id: entry for entry in pinned}
    ordered = tuple(by_id[repo.id] for repo in repos if repo.id in by_id)
    return Ok((ordered, tuple(suggestions)))
