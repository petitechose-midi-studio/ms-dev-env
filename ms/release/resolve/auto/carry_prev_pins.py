from __future__ import annotations

import json
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.core.structured import as_obj_list, as_str_dict, get_int, get_list, get_str
from ms.release.domain.planner import ReleaseHistory, compute_history
from ms.release.domain.semver import format_beta_tag
from ms.release.errors import ReleaseError
from ms.release.infra.github.client import get_repo_file_text, list_distribution_releases


def _latest_beta_tag(history: ReleaseHistory) -> str | None:
    base = history.latest_beta_base
    if base is None:
        return None
    value = history.beta_max_by_base.get(base)
    if value is None:
        return None
    return format_beta_tag(base, value)


def _prev_dist_tag_for_channel(*, channel: str, history: ReleaseHistory) -> str | None:
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


def load_previous_channel_pins(
    *,
    workspace_root: Path,
    channel: str,
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
