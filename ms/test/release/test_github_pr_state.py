from __future__ import annotations

from pathlib import Path

from pytest import MonkeyPatch

from ms.core.result import Ok
from ms.release.infra.github.pr_state import wait_until_mergeable, wait_until_merged


def test_wait_until_merged_accepts_lowercase_merged_state(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    import ms.release.infra.github.pr_state as pr_state

    def fake_run_gh_process(_cmd: list[str], **_: object) -> Ok[str]:
        return Ok('{"state":"merged","mergedAt":null}')

    monkeypatch.setattr(pr_state, "run_gh_process", fake_run_gh_process)

    result = wait_until_merged(
        workspace_root=tmp_path,
        repo_slug="owner/repo",
        pr_url="https://example.invalid/pr/1",
        repo_label="core",
    )

    assert isinstance(result, Ok)


def test_wait_until_mergeable_accepts_pr_merged_during_poll(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    import ms.release.infra.github.pr_state as pr_state

    def fake_run_gh_process(_cmd: list[str], **_: object) -> Ok[str]:
        return Ok('{"state":"MERGED","mergeStateStatus":"UNKNOWN"}')

    monkeypatch.setattr(pr_state, "run_gh_process", fake_run_gh_process)

    result = wait_until_mergeable(
        workspace_root=tmp_path,
        repo_slug="owner/repo",
        pr_url="https://example.invalid/pr/1",
        repo_label="core",
    )

    assert isinstance(result, Ok)
