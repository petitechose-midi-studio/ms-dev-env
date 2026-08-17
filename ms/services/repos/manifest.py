from __future__ import annotations

import tomllib
from collections.abc import Sequence
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.core.structured import as_obj_list, as_str_dict, get_str

from .models import RepoError, RepoSpec


def load_manifest(path: Path) -> Result[list[RepoSpec], RepoError]:
    return load_manifests((path,))


def load_manifests(paths: Sequence[Path]) -> Result[list[RepoSpec], RepoError]:
    specs: list[RepoSpec] = []
    for path in paths:
        loaded = _load_manifest(path)
        if isinstance(loaded, Err):
            return loaded
        specs.extend(loaded.value)

    if not specs:
        return Err(
            RepoError(
                kind="manifest_invalid",
                message="repo manifests contain no repos",
            )
        )

    seen_names: set[tuple[str, str]] = set()
    seen_paths: set[str] = set()
    for spec in specs:
        name = (spec.org, spec.name)
        if name in seen_names:
            return Err(
                RepoError(
                    kind="manifest_invalid",
                    message=f"duplicate repo in manifests: {spec.org}/{spec.name}",
                )
            )
        if spec.path in seen_paths:
            return Err(
                RepoError(
                    kind="manifest_invalid",
                    message=f"duplicate repo path in manifests: {spec.path}",
                )
            )
        seen_names.add(name)
        seen_paths.add(spec.path)

    return Ok(specs)


def _load_manifest(path: Path) -> Result[list[RepoSpec], RepoError]:
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
    for index, item in enumerate(raw):
        item_dict = as_str_dict(item)
        if item_dict is None:
            return Err(
                RepoError(
                    kind="manifest_invalid",
                    message=f"repo manifest entry {index} must be a TOML table",
                )
            )

        org = get_str(item_dict, "org")
        name = get_str(item_dict, "name")
        url = get_str(item_dict, "url")
        rel_path = get_str(item_dict, "path")
        branch = get_str(item_dict, "branch")

        required = {"org": org, "name": name, "url": url, "path": rel_path}
        missing = [key for key, value in required.items() if value is None]
        if missing:
            return Err(
                RepoError(
                    kind="manifest_invalid",
                    message=(f"repo manifest entry {index} missing required field: {missing[0]}"),
                )
            )
        assert org is not None and name is not None and url is not None and rel_path is not None

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

    return Ok(specs)
