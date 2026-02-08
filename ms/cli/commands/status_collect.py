from __future__ import annotations

from pathlib import Path

from ms.cli.commands.status_models import RepoStatus
from ms.core.result import Err, Ok
from ms.git.repository import Repository


def collect_repos(root: Path, midi_studio: Path, open_control: Path) -> list[tuple[str, Path]]:
    """Collect all git repos in the workspace."""
    repos: list[tuple[str, Path]] = []

    if (root / ".git").exists():
        repos.append(("ms", root))

    for name in ("distribution", "ms-manager"):
        path = root / name
        if path.is_dir() and (path / ".git").exists():
            repos.append((name, path))

    if midi_studio.exists():
        for directory in sorted(midi_studio.iterdir()):
            if directory.is_dir() and (directory / ".git").exists():
                repos.append((f"midi-studio/{directory.name}", directory))

    if open_control.exists():
        for directory in sorted(open_control.iterdir()):
            if directory.is_dir() and (directory / ".git").exists():
                repos.append((f"open-control/{directory.name}", directory))

    return repos


def collect_repo_statuses(repo_list: list[tuple[str, Path]]) -> list[RepoStatus]:
    """Collect status payloads for each discovered repository."""
    statuses: list[RepoStatus] = []
    for name, path in repo_list:
        repo = Repository(path)
        result = repo.status()
        match result:
            case Err(error):
                statuses.append(RepoStatus(name, path, None, error.message))
            case Ok(status):
                statuses.append(RepoStatus(name, path, status))
    return statuses
