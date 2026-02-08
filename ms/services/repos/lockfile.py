from __future__ import annotations

import json

from ms.core.workspace import Workspace
from ms.platform.files import atomic_write_text

from .models import RepoLockEntry, RepoLockPayload


def write_lock_file(*, workspace: Workspace, lock: list[RepoLockEntry]) -> None:
    workspace.state_dir.mkdir(parents=True, exist_ok=True)
    path = workspace.state_dir / "repos.lock.json"
    payload: list[RepoLockPayload] = [
        {
            "org": entry.org,
            "name": entry.name,
            "url": entry.url,
            "default_branch": entry.default_branch,
            "head_sha": entry.head_sha,
        }
        for entry in lock
    ]
    atomic_write_text(path, json.dumps(payload, indent=2), encoding="utf-8")
