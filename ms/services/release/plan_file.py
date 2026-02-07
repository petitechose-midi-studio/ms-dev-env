from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ms.core.result import Err, Ok, Result
from ms.core.structured import as_obj_list, as_str_dict, get_int, get_list, get_str
from ms.platform.files import atomic_write_text
from ms.services.release import config
from ms.services.release.errors import ReleaseError
from ms.services.release.model import PinnedRepo, ReleaseChannel, ReleaseRepo

PLAN_SCHEMA = 2


@dataclass(frozen=True, slots=True)
class PlanInput:
    product: Literal["content", "app"]
    channel: ReleaseChannel
    tag: str
    pinned: tuple[PinnedRepo, ...]


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

    try:
        atomic_write_text(path, json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    except OSError as e:
        return Err(
            ReleaseError(
                kind="dist_repo_failed",
                message=f"failed to write plan file: {e}",
                hint=str(path),
            )
        )

    return Ok(None)


def read_plan_file(*, path: Path) -> Result[PlanInput, ReleaseError]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"failed to read plan file: {e}",
                hint=str(path),
            )
        )

    try:
        obj: object = json.loads(text)
    except json.JSONDecodeError as e:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"invalid JSON in plan file: {e}",
                hint=str(path),
            )
        )

    data = as_str_dict(obj)
    if data is None:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message="plan file root must be a JSON object",
                hint=str(path),
            )
        )

    schema = get_int(data, "schema")
    if schema != PLAN_SCHEMA:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"unsupported plan schema: {schema}",
                hint=str(path),
            )
        )

    channel = get_str(data, "channel")
    if channel not in ("stable", "beta"):
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"invalid channel in plan: {channel!r}",
                hint=str(path),
            )
        )

    product = get_str(data, "product")
    if product not in ("content", "app"):
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"invalid product in plan: {product!r}",
                hint=str(path),
            )
        )

    tag = get_str(data, "tag")
    if tag is None:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message="missing tag in plan",
                hint=str(path),
            )
        )

    repos_obj = get_list(data, "repos")
    if repos_obj is None:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message="missing repos[] in plan",
                hint=str(path),
            )
        )

    repos = as_obj_list(repos_obj)
    if repos is None:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message="repos must be a list",
                hint=str(path),
            )
        )

    repos_cfg: tuple[ReleaseRepo, ...]
    repos_cfg = (config.APP_RELEASE_REPO,) if product == "app" else config.RELEASE_REPOS

    by_id = {r.id: r for r in repos_cfg}
    pinned: list[PinnedRepo] = []
    seen: set[str] = set()
    for item in repos:
        d = as_str_dict(item)
        if d is None:
            continue
        repo_id = get_str(d, "id")
        slug = get_str(d, "slug")
        sha = get_str(d, "sha")
        ref = get_str(d, "ref")
        if repo_id is None or slug is None or sha is None or ref is None:
            continue
        if repo_id in seen:
            continue
        seen.add(repo_id)

        repo = by_id.get(repo_id)
        if repo is None:
            return Err(
                ReleaseError(
                    kind="invalid_input",
                    message=f"unknown repo id in plan: {repo_id}",
                    hint=str(path),
                )
            )
        if slug != repo.slug:
            return Err(
                ReleaseError(
                    kind="invalid_input",
                    message=f"repo slug mismatch for {repo_id}",
                    hint=f"expected {repo.slug}, got {slug}",
                )
            )
        if len(sha) != 40:
            return Err(
                ReleaseError(
                    kind="invalid_input",
                    message=f"invalid sha for {repo_id} in plan",
                    hint=sha,
                )
            )

        repo_sel = ReleaseRepo(
            id=repo.id,
            slug=repo.slug,
            ref=ref,
            required_ci_workflow_file=repo.required_ci_workflow_file,
        )
        pinned.append(PinnedRepo(repo=repo_sel, sha=sha))

    missing = [r.id for r in repos_cfg if r.id not in {p.repo.id for p in pinned}]
    if missing:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"plan missing repos: {', '.join(missing)}",
                hint=str(path),
            )
        )

    return Ok(PlanInput(product=product, channel=channel, tag=tag, pinned=tuple(pinned)))
