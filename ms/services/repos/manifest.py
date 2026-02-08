from __future__ import annotations

import tomllib
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.core.structured import as_obj_list, as_str_dict, get_str

from .models import RepoError, RepoSpec


def load_manifest(path: Path) -> Result[list[RepoSpec], RepoError]:
    if not path.exists():
        return Err(
            RepoError(
                kind="manifest_invalid",
                message=f"repo manifest not found: {path}",
                hint="Reinstall or update the workspace package",
            )
        )

    try:
        data_obj: object = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        return Err(
            RepoError(
                kind="manifest_invalid",
                message=f"repo manifest is invalid TOML: {error}",
            )
        )

    data = as_str_dict(data_obj)
    if data is None:
        return Err(
            RepoError(
                kind="manifest_invalid",
                message="repo manifest root must be a TOML table",
            )
        )

    raw_obj = data.get("repos")
    if raw_obj is None:
        return Err(
            RepoError(
                kind="manifest_invalid",
                message="repo manifest missing 'repos' section",
            )
        )

    raw = as_obj_list(raw_obj)
    if raw is None:
        return Err(
            RepoError(
                kind="manifest_invalid",
                message="repo manifest 'repos' must be a list",
            )
        )

    specs: list[RepoSpec] = []
    for item in raw:
        item_dict = as_str_dict(item)
        if item_dict is None:
            continue

        org = get_str(item_dict, "org")
        name = get_str(item_dict, "name")
        url = get_str(item_dict, "url")
        rel_path = get_str(item_dict, "path")
        branch = get_str(item_dict, "branch")

        if org is None:
            continue
        if name is None:
            continue
        if url is None:
            continue
        if rel_path is None:
            continue

        repo_path = Path(rel_path)
        if repo_path.is_absolute() or ".." in repo_path.parts:
            return Err(
                RepoError(
                    kind="manifest_invalid",
                    message=f"invalid repo path in manifest: {rel_path}",
                )
            )

        specs.append(
            RepoSpec(
                org=org,
                name=name,
                url=url,
                path=rel_path,
                branch=branch,
            )
        )

    if not specs:
        return Err(
            RepoError(
                kind="manifest_invalid",
                message="repo manifest contains no repos",
            )
        )

    return Ok(specs)
