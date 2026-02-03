from __future__ import annotations

from enum import Enum
from pathlib import Path


class RepoProfile(str, Enum):
    dev = "dev"
    maintainer = "maintainer"


def repo_manifest_path(profile: RepoProfile) -> Path:
    data_dir = Path(__file__).parent.parent / "data"
    if profile == RepoProfile.maintainer:
        return data_dir / "repos.maintainer.toml"
    return data_dir / "repos.toml"
