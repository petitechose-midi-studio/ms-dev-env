from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ms.core.result import Err, Ok, Result
from ms.core.structured import StrDict, as_str_dict, get_int, get_list, get_str
from ms.git.sha import is_git_sha
from ms.platform.files import atomic_write_text
from ms.release.domain import config
from ms.release.domain.models import PinnedRepo, ReleaseChannel, ReleaseRepo, ReleaseTooling
from ms.release.errors import ReleaseError

PLAN_SCHEMA = 3


@dataclass(frozen=True, slots=True)
class PlanInput:
    product: Literal["content", "app"]
    channel: ReleaseChannel
    tag: str
    pinned: tuple[PinnedRepo, ...]
    tooling: ReleaseTooling | None = None


def write_plan_file(*, path: Path, plan: PlanInput) -> Result[None, ReleaseError]:
    payload: dict[str, object] = {
        "schema": PLAN_SCHEMA,
        "product": plan.product,
        "channel": plan.channel,
        "tag": plan.tag,
        "repos": [
            {
                "id": p.repo.id,
                "slug": p.repo.slug,
                "sha": p.sha,
                "ref": p.repo.ref,
            }
            for p in plan.pinned
        ],
    }
    if plan.tooling is not None:
        payload["tooling"] = {
            "repo": plan.tooling.repo,
            "ref": plan.tooling.ref,
            "sha": plan.tooling.sha,
        }

    try:
        atomic_write_text(path, json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    except OSError as e:
        return Err(
            ReleaseError(
                kind="repo_failed",
                message=f"failed to write plan file: {e}",
                hint=str(path),
            )
        )

    return Ok(None)


def _plan_error(*, path: Path, message: str, hint: str | None = None) -> ReleaseError:
    return ReleaseError(
        kind="invalid_input",
        message=message,
        hint=hint or str(path),
    )


def _read_plan_data(path: Path) -> Result[StrDict, ReleaseError]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        return Err(_plan_error(path=path, message=f"failed to read plan file: {e}"))

    try:
        obj: object = json.loads(text)
    except json.JSONDecodeError as e:
        return Err(_plan_error(path=path, message=f"invalid JSON in plan file: {e}"))

    data = as_str_dict(obj)
    if data is None:
        return Err(_plan_error(path=path, message="plan file root must be a JSON object"))
    return Ok(data)


def _parse_pinned_repos(
    *, data: StrDict, product: Literal["content", "app"], path: Path
) -> Result[tuple[PinnedRepo, ...], ReleaseError]:
    repos = get_list(data, "repos")
    if repos is None:
        return Err(_plan_error(path=path, message="missing or invalid repos[] in plan"))

    repos_cfg = (config.APP_RELEASE_REPO,) if product == "app" else config.RELEASE_REPOS
    by_id = {repo.id: repo for repo in repos_cfg}
    pinned: list[PinnedRepo] = []
    seen: set[str] = set()

    for index, item in enumerate(repos):
        entry = as_str_dict(item)
        if entry is None:
            return Err(_plan_error(path=path, message=f"invalid repo entry at index {index}"))

        repo_id = get_str(entry, "id")
        slug = get_str(entry, "slug")
        sha = get_str(entry, "sha")
        ref = get_str(entry, "ref")
        if repo_id is None or slug is None or sha is None or ref is None:
            return Err(
                _plan_error(path=path, message=f"repo entry {index} is missing id/slug/sha/ref")
            )
        if repo_id in seen:
            return Err(_plan_error(path=path, message=f"duplicate repo id in plan: {repo_id}"))
        seen.add(repo_id)

        repo = by_id.get(repo_id)
        if repo is None:
            return Err(_plan_error(path=path, message=f"unknown repo id in plan: {repo_id}"))
        if slug != repo.slug:
            return Err(
                _plan_error(
                    path=path,
                    message=f"repo slug mismatch for {repo_id}",
                    hint=f"expected {repo.slug}, got {slug}",
                )
            )
        if not is_git_sha(sha):
            return Err(
                _plan_error(path=path, message=f"invalid sha for {repo_id} in plan", hint=sha)
            )

        pinned.append(
            PinnedRepo(
                repo=ReleaseRepo(
                    id=repo.id,
                    slug=repo.slug,
                    ref=ref,
                    required_ci_workflow_file=repo.required_ci_workflow_file,
                ),
                sha=sha,
            )
        )

    missing = [repo.id for repo in repos_cfg if repo.id not in seen]
    if missing:
        return Err(_plan_error(path=path, message=f"plan missing repos: {', '.join(missing)}"))
    return Ok(tuple(pinned))


def _parse_tooling(*, data: StrDict, path: Path) -> Result[ReleaseTooling | None, ReleaseError]:
    raw = data.get("tooling")
    if raw is None:
        return Ok(None)
    tooling = as_str_dict(raw)
    if tooling is None:
        return Err(_plan_error(path=path, message="tooling must be an object"))

    repo = get_str(tooling, "repo")
    ref = get_str(tooling, "ref")
    sha = get_str(tooling, "sha")
    if repo is None or ref is None or sha is None:
        return Err(_plan_error(path=path, message="tooling is missing repo/ref/sha"))
    if not is_git_sha(sha):
        return Err(_plan_error(path=path, message="invalid tooling sha in plan", hint=sha))
    return Ok(ReleaseTooling(repo=repo, ref=ref, sha=sha))


def read_plan_file(*, path: Path) -> Result[PlanInput, ReleaseError]:
    loaded = _read_plan_data(path)
    if isinstance(loaded, Err):
        return loaded
    data = loaded.value

    schema = get_int(data, "schema")
    if schema != PLAN_SCHEMA:
        return Err(_plan_error(path=path, message=f"unsupported plan schema: {schema}"))

    channel = get_str(data, "channel")
    if channel not in ("stable", "beta"):
        return Err(_plan_error(path=path, message=f"invalid channel in plan: {channel!r}"))

    product = get_str(data, "product")
    if product not in ("content", "app"):
        return Err(_plan_error(path=path, message=f"invalid product in plan: {product!r}"))

    tag = get_str(data, "tag")
    if tag is None:
        return Err(_plan_error(path=path, message="missing tag in plan"))

    pinned = _parse_pinned_repos(data=data, product=product, path=path)
    if isinstance(pinned, Err):
        return pinned
    tooling = _parse_tooling(data=data, path=path)
    if isinstance(tooling, Err):
        return tooling

    return Ok(
        PlanInput(
            product=product,
            channel=channel,
            tag=tag,
            pinned=pinned.value,
            tooling=tooling.value,
        )
    )
