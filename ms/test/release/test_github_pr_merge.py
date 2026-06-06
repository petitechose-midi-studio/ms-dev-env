from __future__ import annotations

from pathlib import Path

from pytest import MonkeyPatch

from ms.core.result import Err, Ok
from ms.output.console import MockConsole
from ms.platform.process import ProcessError
from ms.release.infra.github.pr_merge import merge_pull_request


def test_merge_pull_request_reports_disabled_auto_merge(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    import ms.release.infra.github.pr_merge as pr_merge

    calls: list[str] = []

    def fake_run_gh_process(cmd: list[str], **_: object) -> Err[ProcessError]:
        calls.append(" ".join(cmd))
        if "--auto" in cmd:
            return Err(
                ProcessError(
                    command=tuple(cmd),
                    returncode=1,
                    stdout="",
                    stderr="Auto merge is not allowed for this repository",
                )
            )
        return Err(
            ProcessError(
                command=tuple(cmd),
                returncode=1,
                stdout="",
                stderr="Pull request is already merged",
            )
        )

    def fake_wait_until_merged(**_: object) -> Ok[None]:
        calls.append("merged")
        return Ok(None)

    monkeypatch.setattr(pr_merge, "run_gh_process", fake_run_gh_process)
    monkeypatch.setattr(pr_merge, "wait_until_merged", fake_wait_until_merged)

    result = merge_pull_request(
        workspace_root=tmp_path,
        repo_slug="owner/repo",
        pr_url="https://example.invalid/pr/1",
        repo_label="core",
        delete_branch=True,
        console=MockConsole(),
        dry_run=False,
    )

    assert isinstance(result, Err)
    assert result.error.message == "auto-merge is disabled for core repo"
    assert result.error.hint == (
        "Enable Allow auto-merge for owner/repo, then rerun. "
        "PR: https://example.invalid/pr/1"
    )
    assert calls == [
        " ".join(
            (
                "gh pr merge https://example.invalid/pr/1 --repo owner/repo",
                "--rebase --auto --delete-branch",
            )
        ),
    ]
