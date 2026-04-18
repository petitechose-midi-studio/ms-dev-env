from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, cast
from urllib.parse import urlparse

from ms.core.result import Err, Ok, Result
from ms.release.domain.config import RELEASE_REPOS
from ms.release.domain.models import PinnedRepo, ReleasePlan, ReleaseRepo, ReleaseTooling
from ms.release.errors import ReleaseError


def load_content_plan_from_spec(*, spec_path: Path) -> Result[ReleasePlan, ReleaseError]:
    try:
        payload = json.loads(spec_path.read_text(encoding="utf-8"))
    except OSError as e:
        return Err(
            ReleaseError(kind="repo_failed", message=f"failed to read content spec: {e}")
        )
    except json.JSONDecodeError as e:
        return Err(
            ReleaseError(kind="invalid_input", message=f"invalid content spec JSON: {e}")
        )

    if not isinstance(payload, dict):
        return Err(ReleaseError(kind="invalid_input", message="invalid content spec payload"))
    payload_obj = cast(dict[str, object], payload)

    if payload_obj.get("schema") != 2:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message="unsupported content spec schema",
                hint=str(payload_obj.get("schema")),
            )
        )

    channel = payload_obj.get("channel")
    tag = payload_obj.get("tag")
    if channel not in {"stable", "beta"} or not isinstance(tag, str) or not tag:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message="invalid content spec channel or tag",
            )
        )

    tooling = _parse_tooling(payload_obj.get("tooling"))
    if isinstance(tooling, Err):
        return tooling

    pinned = _parse_pinned_repos(payload_obj.get("repos"))
    if isinstance(pinned, Err):
        return pinned

    return Ok(
        ReleasePlan(
            channel=cast(Literal["stable", "beta"], channel),
            tag=tag,
            pinned=pinned.value,
            tooling=tooling.value,
            spec_path=str(spec_path),
            notes_path=None,
            title=f"release(content): {tag}",
        )
    )


def _parse_tooling(raw: object) -> Result[ReleaseTooling, ReleaseError]:
    if not isinstance(raw, dict):
        return Err(ReleaseError(kind="invalid_input", message="missing tooling block in spec"))
    raw_obj = cast(dict[str, object], raw)

    repo = raw_obj.get("repo")
    ref = raw_obj.get("ref")
    sha = raw_obj.get("sha")
    if not isinstance(repo, str) or not isinstance(ref, str) or not _is_sha(sha):
        return Err(ReleaseError(kind="invalid_input", message="invalid tooling block in spec"))
    return Ok(ReleaseTooling(repo=repo, ref=ref, sha=cast(str, sha)))


def _parse_pinned_repos(raw: object) -> Result[tuple[PinnedRepo, ...], ReleaseError]:
    if not isinstance(raw, list):
        return Err(ReleaseError(kind="invalid_input", message="missing repos list in spec"))

    defaults = {repo.id: repo for repo in RELEASE_REPOS}
    pinned: list[PinnedRepo] = []
    for item in cast(list[object], raw):
        if not isinstance(item, dict):
            return Err(ReleaseError(kind="invalid_input", message="invalid repo entry in spec"))
        item_obj = cast(dict[str, object], item)

        repo_id = item_obj.get("id")
        repo_slug = _repo_slug_from_url(item_obj.get("url"))
        ref = item_obj.get("ref")
        sha = item_obj.get("sha")
        required_ci = item_obj.get("required_ci_workflow_file")
        if (
            not isinstance(repo_id, str)
            or repo_slug is None
            or not isinstance(ref, str)
            or not _is_sha(sha)
            or (required_ci is not None and not isinstance(required_ci, str))
        ):
            return Err(ReleaseError(kind="invalid_input", message="invalid repo entry in spec"))

        default = defaults.get(repo_id)
        pinned.append(
            PinnedRepo(
                repo=ReleaseRepo(
                    id=repo_id,
                    slug=repo_slug,
                    ref=ref,
                    required_ci_workflow_file=(
                        required_ci
                        if required_ci is not None
                        else (default.required_ci_workflow_file if default is not None else None)
                    ),
                ),
                sha=cast(str, sha),
            )
        )
    return Ok(tuple(pinned))


def _repo_slug_from_url(raw: object) -> str | None:
    if not isinstance(raw, str):
        return None
    parsed = urlparse(raw)
    if parsed.scheme != "https" or parsed.netloc != "github.com":
        return None
    slug = parsed.path.strip("/")
    return slug if slug.count("/") == 1 else None


def _is_sha(value: object) -> bool:
    return isinstance(value, str) and len(value) == 40 and all(
        c in "0123456789abcdef" for c in value
    )
