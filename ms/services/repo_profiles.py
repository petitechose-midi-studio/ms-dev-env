from __future__ import annotations

from enum import StrEnum
from pathlib import Path


class RepoProfile(StrEnum):
    dev = "dev"
    maintainer = "maintainer"


def repo_manifest_path(profile: RepoProfile) -> Path:
    data_dir = Path(__file__).parent.parent / "data"
    if profile == RepoProfile.maintainer:
        return data_dir / "repos.maintainer.toml"
    return data_dir / "repos.toml"
