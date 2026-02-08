from __future__ import annotations

from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.core.structured import as_obj_list, as_str_dict, get_str
from ms.release.domain.models import DistributionRelease
from ms.release.errors import ReleaseError
from ms.release.infra.github.gh_base import gh_api_json


def list_distribution_releases(
    *,
    workspace_root: Path,
    repo: str,
    limit: int,
) -> Result[list[DistributionRelease], ReleaseError]:
    obj = gh_api_json(
        workspace_root=workspace_root,
        endpoint=f"repos/{repo}/releases?per_page={limit}",
    )
    if isinstance(obj, Err):
        return obj

    raw = as_obj_list(obj.value)
    if raw is None:
        return Err(
            ReleaseError(kind="invalid_input", message=f"unexpected releases payload: {repo}")
        )

    out: list[DistributionRelease] = []
    for item in raw:
        d = as_str_dict(item)
        if d is None:
            continue

        tag = get_str(d, "tag_name")
        if tag is None:
            continue

        prerelease_obj = d.get("prerelease")
        if not isinstance(prerelease_obj, bool):
            continue

        out.append(DistributionRelease(tag=tag, prerelease=prerelease_obj))

    return Ok(out)
