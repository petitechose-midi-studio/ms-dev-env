from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.platform.files import atomic_write_text
from ms.services.release.config import DIST_SPEC_DIR
from ms.services.release.errors import ReleaseError
from ms.services.release.model import PinnedRepo, ReleaseChannel


@dataclass(frozen=True, slots=True)
class WrittenSpec:
    rel_path: str
    abs_path: Path


def spec_path_for_tag(tag: str) -> str:
    return f"{DIST_SPEC_DIR}/{tag}.json"


def _demo_url(channel: ReleaseChannel) -> str:
    return f"https://petitechose-midi-studio.github.io/distribution/demos/{channel}/"


def _spec_obj(
    *, channel: ReleaseChannel, tag: str, pinned: tuple[PinnedRepo, ...]
) -> dict[str, object]:
    repos: list[dict[str, object]] = []
    for p in pinned:
        repo_obj: dict[str, object] = {
            "id": p.repo.id,
            "url": f"https://github.com/{p.repo.slug}",
            "ref": p.repo.ref,
            "sha": p.sha,
        }
        if p.repo.required_ci_workflow_file is not None:
            repo_obj["required_ci_workflow_file"] = p.repo.required_ci_workflow_file
        repos.append(repo_obj)

    assets: list[dict[str, object]] = [
        {
            "id": "bundle-windows-x86_64",
            "kind": "bundle",
            "os": "windows",
            "arch": "x86_64",
            "filename": "midi-studio-windows-x86_64-bundle.zip",
        },
        {
            "id": "bundle-macos-x86_64",
            "kind": "bundle",
            "os": "macos",
            "arch": "x86_64",
            "filename": "midi-studio-macos-x86_64-bundle.zip",
        },
        {
            "id": "bundle-macos-arm64",
            "kind": "bundle",
            "os": "macos",
            "arch": "arm64",
            "filename": "midi-studio-macos-arm64-bundle.zip",
        },
        {
            "id": "bundle-linux-x86_64",
            "kind": "bundle",
            "os": "linux",
            "arch": "x86_64",
            "filename": "midi-studio-linux-x86_64-bundle.zip",
        },
        {
            "id": "firmware-default",
            "kind": "firmware",
            "filename": "midi-studio-default-firmware.hex",
        },
        {
            "id": "firmware-bitwig",
            "kind": "firmware",
            "filename": "midi-studio-bitwig-firmware.hex",
        },
        {
            "id": "bitwig-extension",
            "kind": "bitwig-extension",
            "filename": "midi_studio.bwextension",
        },
    ]

    install_sets: list[dict[str, object]] = [
        {
            "id": "default",
            "os": "windows",
            "arch": "x86_64",
            "assets": ["bundle-windows-x86_64", "firmware-default"],
        },
        {
            "id": "default",
            "os": "macos",
            "arch": "x86_64",
            "assets": ["bundle-macos-x86_64", "firmware-default"],
        },
        {
            "id": "default",
            "os": "macos",
            "arch": "arm64",
            "assets": ["bundle-macos-arm64", "firmware-default"],
        },
        {
            "id": "default",
            "os": "linux",
            "arch": "x86_64",
            "assets": ["bundle-linux-x86_64", "firmware-default"],
        },
        {
            "id": "bitwig",
            "os": "windows",
            "arch": "x86_64",
            "assets": ["bundle-windows-x86_64", "firmware-bitwig", "bitwig-extension"],
        },
        {
            "id": "bitwig",
            "os": "macos",
            "arch": "x86_64",
            "assets": ["bundle-macos-x86_64", "firmware-bitwig", "bitwig-extension"],
        },
        {
            "id": "bitwig",
            "os": "macos",
            "arch": "arm64",
            "assets": ["bundle-macos-arm64", "firmware-bitwig", "bitwig-extension"],
        },
        {
            "id": "bitwig",
            "os": "linux",
            "arch": "x86_64",
            "assets": ["bundle-linux-x86_64", "firmware-bitwig", "bitwig-extension"],
        },
    ]

    return {
        "schema": 1,
        "channel": channel,
        "tag": tag,
        "repos": repos,
        "assets": assets,
        "install_sets": install_sets,
        "pages": {"demo_url": _demo_url(channel)},
    }


def write_release_spec(
    *,
    dist_repo_root: Path,
    channel: ReleaseChannel,
    tag: str,
    pinned: tuple[PinnedRepo, ...],
) -> Result[WrittenSpec, ReleaseError]:
    rel = spec_path_for_tag(tag)
    path = dist_repo_root / rel
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        payload = _spec_obj(channel=channel, tag=tag, pinned=pinned)
        text = json.dumps(payload, indent=2) + "\n"
        atomic_write_text(path, text, encoding="utf-8")
    except OSError as e:
        return Err(
            ReleaseError(
                kind="dist_repo_failed",
                message=f"failed to write release spec: {e}",
                hint=str(path),
            )
        )

    return Ok(WrittenSpec(rel_path=rel, abs_path=path))
