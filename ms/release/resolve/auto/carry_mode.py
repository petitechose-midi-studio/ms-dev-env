from __future__ import annotations

from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.release.domain.diagnostics import AutoSuggestion
from ms.release.domain.models import PinnedRepo, ReleaseRepo
from ms.release.errors import ReleaseError
from ms.release.infra.github.ci import fetch_green_head_shas, is_ci_green_for_sha
from ms.release.infra.github.client import (
    compare_commits,
    list_recent_commits,
)

from .carry_prev_pins import load_previous_channel_pins
from .diagnostics import (
    RepoReadiness,
    build_diag_blocker,
    is_applyable_locally,
    local_issue_reason,
    repo_with_ref,
)

__all__ = [
    "load_previous_channel_pins",
    "resolve_carry_mode_pin",
]


def _find_latest_green_sha(
    *,
    workspace_root: Path,
    repo: ReleaseRepo,
    limit_commits: int,
    limit_runs: int,
) -> Result[str | None, ReleaseError]:
    workflow = repo.required_ci_workflow_file
    if workflow is None:
        return Ok(None)

    commits = list_recent_commits(
        workspace_root=workspace_root,
        repo=repo.slug,
        ref=repo.ref,
        limit=limit_commits,
    )
    if isinstance(commits, Err):
        return commits

    green = fetch_green_head_shas(
        workspace_root=workspace_root,
        repo=repo.slug,
        workflow_file=workflow,
        branch=repo.ref,
        limit=limit_runs,
    )
    if isinstance(green, Err):
        return green

    for commit in commits.value:
        if green.value.is_green(commit.sha):
            return Ok(commit.sha)
    return Ok(None)


def _collect_carry_mode_suggestions(
    *,
    workspace_root: Path,
    repo: ReleaseRepo,
    selected_repo: ReleaseRepo,
    diagnostics: RepoReadiness | None,
    carried_sha: str,
) -> tuple[AutoSuggestion, ...]:
    if repo.id not in {"loader", "oc-bridge"}:
        return ()

    suggestions: list[AutoSuggestion] = []

    latest_result = _find_latest_green_sha(
        workspace_root=workspace_root,
        repo=selected_repo,
        limit_commits=30,
        limit_runs=200,
    )
    if isinstance(latest_result, Ok):
        latest = latest_result.value
        if latest is not None and latest != carried_sha:
            compared = compare_commits(
                workspace_root=workspace_root,
                repo=repo.slug,
                base=carried_sha,
                head=latest,
            )
            if isinstance(compared, Ok) and compared.value.status == "ahead":
                suggestions.append(
                    AutoSuggestion(
                        repo=selected_repo,
                        from_sha=carried_sha,
                        to_sha=latest,
                        kind="bump",
                        reason="newer green commit available",
                        applyable=(diagnostics is not None and is_applyable_locally(diagnostics)),
                    )
                )

    if diagnostics is not None and not is_applyable_locally(diagnostics):
        suggestions.append(
            AutoSuggestion(
                repo=selected_repo,
                from_sha=carried_sha,
                to_sha=carried_sha,
                kind="local",
                reason=local_issue_reason(diagnostics),
                applyable=False,
            )
        )

    return tuple(suggestions)


def _resolve_previous_carry_pin(
    *,
    workspace_root: Path,
    repo: ReleaseRepo,
    ref: str,
    selected_repo: ReleaseRepo,
    diagnostics: RepoReadiness | None,
    prev_sha: str,
    prev_ref: str,
) -> Result[tuple[PinnedRepo, tuple[AutoSuggestion, ...]], RepoReadiness]:
    workflow = repo.required_ci_workflow_file
    if workflow is None:
        return Err(
            build_diag_blocker(
                workspace_root=workspace_root,
                repo=repo,
                ref=ref,
                diagnostics=diagnostics,
                error="repo is not CI-gated (auto is strict)",
            )
        )

    green = is_ci_green_for_sha(
        workspace_root=workspace_root,
        repo=repo.slug,
        workflow=workflow,
        sha=prev_sha,
    )
    if isinstance(green, Err):
        return Err(
            build_diag_blocker(
                workspace_root=workspace_root,
                repo=repo,
                ref=ref,
                diagnostics=diagnostics,
                error=green.error.message,
            )
        )
    if not green.value:
        return Err(
            build_diag_blocker(
                workspace_root=workspace_root,
                repo=repo,
                ref=ref,
                diagnostics=diagnostics,
                error=f"previous pin is not CI green: {repo.slug}@{prev_sha}",
            )
        )

    carried_repo = repo_with_ref(repo=repo, ref=prev_ref)
    suggestions = _collect_carry_mode_suggestions(
        workspace_root=workspace_root,
        repo=repo,
        selected_repo=selected_repo,
        diagnostics=diagnostics,
        carried_sha=prev_sha,
    )
    return Ok((PinnedRepo(repo=carried_repo, sha=prev_sha), suggestions))


def _resolve_latest_green_carry_pin(
    *,
    workspace_root: Path,
    repo: ReleaseRepo,
    ref: str,
    selected_repo: ReleaseRepo,
    diagnostics: RepoReadiness | None,
) -> Result[PinnedRepo, RepoReadiness]:
    latest_result = _find_latest_green_sha(
        workspace_root=workspace_root,
        repo=selected_repo,
        limit_commits=30,
        limit_runs=200,
    )
    if isinstance(latest_result, Err):
        return Err(
            build_diag_blocker(
                workspace_root=workspace_root,
                repo=repo,
                ref=ref,
                diagnostics=diagnostics,
                error=latest_result.error.message,
            )
        )

    latest = latest_result.value
    if latest is None:
        return Err(
            build_diag_blocker(
                workspace_root=workspace_root,
                repo=repo,
                ref=ref,
                diagnostics=diagnostics,
                error=f"no green commits found on {repo.slug}@{ref}",
            )
        )

    return Ok(PinnedRepo(repo=selected_repo, sha=latest))


def resolve_carry_mode_pin(
    *,
    workspace_root: Path,
    repo: ReleaseRepo,
    ref: str,
    selected_repo: ReleaseRepo,
    diagnostics: RepoReadiness | None,
    prev_pins: dict[str, tuple[str, str]],
) -> Result[tuple[PinnedRepo, tuple[AutoSuggestion, ...]], RepoReadiness]:
    prev = prev_pins.get(repo.id)
    if prev is not None:
        prev_sha, prev_ref = prev
        return _resolve_previous_carry_pin(
            workspace_root=workspace_root,
            repo=repo,
            ref=ref,
            selected_repo=selected_repo,
            diagnostics=diagnostics,
            prev_sha=prev_sha,
            prev_ref=prev_ref,
        )

    latest_pin = _resolve_latest_green_carry_pin(
        workspace_root=workspace_root,
        repo=repo,
        ref=ref,
        selected_repo=selected_repo,
        diagnostics=diagnostics,
    )
    if isinstance(latest_pin, Err):
        return latest_pin
    return Ok((latest_pin.value, ()))
