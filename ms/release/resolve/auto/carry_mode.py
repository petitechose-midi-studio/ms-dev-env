from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ms.core.result import Err, Ok, Result
from ms.core.structured import as_obj_list, as_str_dict, get_int, get_list, get_str
from ms.release.domain.models import PinnedRepo, ReleaseChannel, ReleaseRepo
from ms.release.domain.planner import ReleaseHistory, compute_history
from ms.release.domain.semver import format_beta_tag
from ms.release.errors import ReleaseError
from ms.release.infra.github.ci import fetch_green_head_shas, is_ci_green_for_sha
from ms.release.infra.github.client import (
    compare_commits,
    get_repo_file_text,
    list_distribution_releases,
    list_recent_commits,
)

from .diagnostics import (
    RepoReadiness,
    build_diag_blocker,
    is_applyable_locally,
    local_issue_reason,
    repo_with_ref,
)


@dataclass(frozen=True, slots=True)
class AutoSuggestion:
    repo: ReleaseRepo
    from_sha: str
    to_sha: str
    kind: Literal["bump", "local"]
    reason: str
    applyable: bool


def _latest_beta_tag(history: ReleaseHistory) -> str | None:
    base = history.latest_beta_base
    if base is None:
        return None
    value = history.beta_max_by_base.get(base)
    if value is None:
        return None
    return format_beta_tag(base, value)


def _prev_dist_tag_for_channel(*, channel: ReleaseChannel, history: ReleaseHistory) -> str | None:
    latest_beta = _latest_beta_tag(history)
    latest_stable = history.latest_stable.to_tag() if history.latest_stable is not None else None
    if channel == "stable":
        return latest_stable or latest_beta
    return latest_beta or latest_stable


def _parse_spec_pins(text: str) -> Result[dict[str, tuple[str, str]], ReleaseError]:
    try:
        obj: object = json.loads(text)
    except json.JSONDecodeError as e:
        return Err(ReleaseError(kind="invalid_input", message=f"invalid spec JSON: {e}"))

    root = as_str_dict(obj)
    if root is None:
        return Err(ReleaseError(kind="invalid_input", message="invalid spec JSON: expected object"))

    schema = get_int(root, "schema")
    if schema != 1:
        return Err(ReleaseError(kind="invalid_input", message=f"unsupported spec schema: {schema}"))

    repos_obj = get_list(root, "repos")
    if repos_obj is None:
        return Err(ReleaseError(kind="invalid_input", message="invalid spec.repos"))

    repos = as_obj_list(repos_obj)
    if repos is None:
        return Err(ReleaseError(kind="invalid_input", message="invalid spec.repos"))

    parsed: dict[str, tuple[str, str]] = {}
    for item in repos:
        data = as_str_dict(item)
        if data is None:
            continue
        repo_id = get_str(data, "id")
        sha = get_str(data, "sha")
        ref = get_str(data, "ref")
        if repo_id is None or sha is None or ref is None:
            continue
        if len(sha) != 40:
            continue
        parsed[repo_id] = (sha, ref)
    return Ok(parsed)


def _load_prev_pins(
    *,
    workspace_root: Path,
    dist_repo: str,
    tag: str,
) -> Result[dict[str, tuple[str, str]], ReleaseError]:
    rel_path = f"release-specs/{tag}.json"
    text = get_repo_file_text(
        workspace_root=workspace_root,
        repo=dist_repo,
        path=rel_path,
        ref="main",
    )
    if isinstance(text, Err):
        return text
    return _parse_spec_pins(text.value)


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


def load_previous_channel_pins(
    *,
    workspace_root: Path,
    channel: ReleaseChannel,
    dist_repo: str,
) -> Result[dict[str, tuple[str, str]], str]:
    releases = list_distribution_releases(
        workspace_root=workspace_root,
        repo=dist_repo,
        limit=100,
    )
    if isinstance(releases, Err):
        return Err(releases.error.message)

    history = compute_history(releases.value)
    prev_tag = _prev_dist_tag_for_channel(channel=channel, history=history)
    if prev_tag is None:
        return Ok({})

    prev_pins = _load_prev_pins(workspace_root=workspace_root, dist_repo=dist_repo, tag=prev_tag)
    if isinstance(prev_pins, Err):
        return Err(f"failed to load previous pins for {prev_tag}: {prev_pins.error.message}")
    return Ok(prev_pins.value)
