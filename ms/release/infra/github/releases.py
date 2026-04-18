from __future__ import annotations

from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.core.structured import as_obj_list, as_str_dict, get_str
from ms.release.domain.models import DistributionRelease
from ms.release.errors import ReleaseError
from ms.release.infra.github.gh_base import gh_api_json, run_gh_process
from ms.release.infra.github.timeouts import GH_TIMEOUT_SECONDS


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


def download_release_assets(
    *,
    workspace_root: Path,
    repo: str,
    tag: str,
    out_dir: Path,
    patterns: tuple[str, ...] = (),
) -> Result[Path, ReleaseError]:
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "gh",
        "release",
        "download",
        tag,
        "--repo",
        repo,
        "--dir",
        str(out_dir),
        "--clobber",
    ]
    for pattern in patterns:
        cmd.extend(["--pattern", pattern])
    result = run_gh_process(
        cmd,
        cwd=workspace_root,
        timeout=GH_TIMEOUT_SECONDS,
    )
    if isinstance(result, Err):
        stderr = result.error.stderr.strip()
        lower = stderr.lower()
        kind = (
            "artifact_missing"
            if (
                "release not found" in lower
                or "http 404" in lower
                or "not found" in lower
                or "no assets match" in lower
            )
            else "workflow_failed"
        )
        return Err(
            ReleaseError(
                kind=kind,
                message=f"failed to download candidate release assets: {repo}@{tag}",
                hint=stderr or None,
            )
        )
    return Ok(out_dir)


def release_exists_by_tag(
    *,
    workspace_root: Path,
    repo: str,
    tag: str,
) -> Result[bool, ReleaseError]:
    result = run_gh_process(
        ["gh", "release", "view", tag, "--repo", repo, "--json", "tagName"],
        cwd=workspace_root,
        timeout=GH_TIMEOUT_SECONDS,
    )
    if isinstance(result, Ok):
        return Ok(True)

    stderr = result.error.stderr.strip()
    lower = stderr.lower()
    if "release not found" in lower or "http 404" in lower or "not found" in lower:
        return Ok(False)
    return Err(
        ReleaseError(
            kind="workflow_failed",
            message=f"failed to inspect release: {repo}@{tag}",
            hint=stderr or None,
        )
    )
