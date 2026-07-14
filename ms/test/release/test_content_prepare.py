from __future__ import annotations

from pathlib import Path

from pytest import MonkeyPatch

from ms.core.result import Ok
from ms.output.console import ConsoleProtocol, MockConsole
from ms.release.domain.models import ReleasePlan, ReleaseTooling
from ms.release.flow import content_prepare


def test_prepare_distribution_pr_dry_run_does_not_write_artifacts(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    spec_path = "release-specs/v1.2.3-beta.4.json"
    notes_path = "release-notes/v1.2.3-beta.4.md"
    plan = ReleasePlan(
        channel="beta",
        tag="v1.2.3-beta.4",
        pinned=(),
        tooling=ReleaseTooling(repo="owner/tooling", ref="main", sha="a" * 40),
        spec_path=spec_path,
        notes_path=notes_path,
        title="release: v1.2.3-beta.4",
    )
    committed_paths: list[Path] = []

    def prepare_repo(
        *, workspace_root: Path, console: ConsoleProtocol, dry_run: bool
    ) -> Ok[Path]:
        del workspace_root, console, dry_run
        return Ok(tmp_path)

    def create_branch(
        *, repo_root: Path, branch: str, console: ConsoleProtocol, dry_run: bool
    ) -> Ok[None]:
        del repo_root, branch, console, dry_run
        return Ok(None)

    monkeypatch.setattr(content_prepare, "_prepare_distribution_repo", prepare_repo)
    monkeypatch.setattr(content_prepare, "create_branch", create_branch)

    def capture_commit(
        *,
        repo_root: Path,
        branch: str,
        paths: list[Path],
        message: str,
        console: ConsoleProtocol,
        dry_run: bool,
    ) -> Ok[None]:
        del repo_root, branch, message, console, dry_run
        committed_paths.extend(paths)
        return Ok(None)

    monkeypatch.setattr(content_prepare, "commit_and_push", capture_commit)

    def open_pr(
        *,
        workspace_root: Path,
        branch: str,
        title: str,
        body: str,
        console: ConsoleProtocol,
        dry_run: bool,
    ) -> Ok[str]:
        del workspace_root, branch, title, body, console, dry_run
        return Ok("https://github.com/owner/distribution/pull/1")

    def merge_pr(
        *,
        workspace_root: Path,
        pr_url: str,
        console: ConsoleProtocol,
        dry_run: bool,
    ) -> Ok[None]:
        del workspace_root, pr_url, console, dry_run
        return Ok(None)

    monkeypatch.setattr(content_prepare, "open_pr", open_pr)
    monkeypatch.setattr(content_prepare, "_merge_distribution_pr", merge_pr)

    def fail_if_written(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise AssertionError("dry-run must not materialize release artifacts")

    monkeypatch.setattr(content_prepare, "write_release_spec", fail_if_written)
    monkeypatch.setattr(content_prepare, "write_release_notes", fail_if_written)

    prepared = content_prepare.prepare_distribution_pr(
        workspace_root=tmp_path,
        console=MockConsole(),
        plan=plan,
        user_notes=None,
        user_notes_file=None,
        dry_run=True,
    )

    assert isinstance(prepared, Ok)
    assert committed_paths == [
        tmp_path / spec_path,
        tmp_path / notes_path,
    ]
    assert not (tmp_path / spec_path).exists()
    assert not (tmp_path / notes_path).exists()
