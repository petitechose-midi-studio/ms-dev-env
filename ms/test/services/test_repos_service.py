from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from ms.core.result import Ok
from ms.core.workspace import Workspace
from ms.output.console import MockConsole
from ms.services.repos import RepoService


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed (code {result.returncode}): {result.stderr.strip()}"
        )
    return result.stdout.strip()


def _init_remote_repo(tmp_path: Path, name: str) -> tuple[str, Path]:
    """Create a bare repo + push an initial commit, return (url, seed_dir)."""
    remote = tmp_path / f"{name}.git"
    seed = tmp_path / f"{name}-seed"

    _git(tmp_path, "init", "--bare", str(remote))

    seed.mkdir()
    _git(seed, "init", "-b", "main")
    _git(seed, "config", "user.email", "test@example.com")
    _git(seed, "config", "user.name", "Test")

    (seed / "hello.txt").write_text("v1\n", encoding="utf-8")
    _git(seed, "add", "hello.txt")
    _git(seed, "commit", "-m", "init")

    url = remote.as_uri()
    _git(seed, "remote", "add", "origin", url)
    _git(seed, "push", "-u", "origin", "main")

    return url, seed


def _write_manifest(path: Path, *, url: str) -> None:
    content = "\n".join(
        [
            "[[repos]]",
            'org = "open-control"',
            'name = "framework"',
            f'url = "{url}"',
            'path = "open-control/framework"',
            'branch = "main"',
            "",
        ]
    )
    path.write_text(content, encoding="utf-8")


@pytest.mark.skipif(shutil.which("git") is None, reason="git not available")
def test_sync_clones_and_updates_repo(tmp_path: Path) -> None:
    url, seed = _init_remote_repo(tmp_path, "framework")

    ws_root = tmp_path / "ws"
    ws_root.mkdir()
    manifest = tmp_path / "repos.toml"
    _write_manifest(manifest, url=url)

    console = MockConsole()
    service = RepoService(
        workspace=Workspace(root=ws_root), console=console, manifest_path=manifest
    )

    result = service.sync_all(dry_run=False)
    assert isinstance(result, Ok)

    dest = ws_root / "open-control" / "framework"
    assert (dest / ".git").exists()
    assert (dest / "hello.txt").read_text(encoding="utf-8") == "v1\n"

    # Update remote
    (seed / "hello.txt").write_text("v2\n", encoding="utf-8")
    _git(seed, "add", "hello.txt")
    _git(seed, "commit", "-m", "update")
    _git(seed, "push")

    result2 = service.sync_all(dry_run=False)
    assert isinstance(result2, Ok)
    assert (dest / "hello.txt").read_text(encoding="utf-8") == "v2\n"


@pytest.mark.skipif(shutil.which("git") is None, reason="git not available")
def test_sync_skips_dirty_repo(tmp_path: Path) -> None:
    url, seed = _init_remote_repo(tmp_path, "framework")

    ws_root = tmp_path / "ws"
    ws_root.mkdir()
    manifest = tmp_path / "repos.toml"
    _write_manifest(manifest, url=url)

    console = MockConsole()
    service = RepoService(
        workspace=Workspace(root=ws_root), console=console, manifest_path=manifest
    )

    assert isinstance(service.sync_all(dry_run=False), Ok)

    dest = ws_root / "open-control" / "framework"
    (dest / "hello.txt").write_text("local\n", encoding="utf-8")

    # New commit on remote
    (seed / "hello.txt").write_text("v2\n", encoding="utf-8")
    _git(seed, "add", "hello.txt")
    _git(seed, "commit", "-m", "update")
    _git(seed, "push")

    console.clear()
    result = service.sync_all(dry_run=False)
    assert isinstance(result, Ok)
    assert "skip dirty repo" in console.text
    assert (dest / "hello.txt").read_text(encoding="utf-8") == "local\n"


@pytest.mark.skipif(shutil.which("git") is None, reason="git not available")
def test_sync_skips_repo_on_wrong_branch(tmp_path: Path) -> None:
    url, seed = _init_remote_repo(tmp_path, "framework")

    ws_root = tmp_path / "ws"
    ws_root.mkdir()
    manifest = tmp_path / "repos.toml"
    _write_manifest(manifest, url=url)

    console = MockConsole()
    service = RepoService(
        workspace=Workspace(root=ws_root), console=console, manifest_path=manifest
    )

    assert isinstance(service.sync_all(dry_run=False), Ok)

    dest = ws_root / "open-control" / "framework"
    _git(dest, "checkout", "-b", "feature")

    # New commit on remote main
    (seed / "hello.txt").write_text("v2\n", encoding="utf-8")
    _git(seed, "add", "hello.txt")
    _git(seed, "commit", "-m", "update")
    _git(seed, "push")

    console.clear()
    result = service.sync_all(dry_run=False)
    assert isinstance(result, Ok)
    assert "skip (on branch" in console.text
    assert _git(dest, "rev-parse", "--abbrev-ref", "HEAD") == "feature"
    assert (dest / "hello.txt").read_text(encoding="utf-8") == "v1\n"
