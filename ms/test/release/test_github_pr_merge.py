from __future__ import annotations

from pathlib import Path

from pytest import MonkeyPatch

from ms.core.result import Err, Ok
from ms.output.console import MockConsole
from ms.platform.process import ProcessError
from ms.release.infra.github.pr_merge import create_pull_request, merge_pull_request


def test_create_pull_request_uses_release_app_token(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    import ms.release.infra.github.pr_merge as pr_merge

    calls: list[tuple[list[str], dict[str, str] | None]] = []

    def fake_release_app_token_for_repo(**_: object) -> Ok[str]:
        return Ok("app-token")

    def fake_run_gh_process(
        cmd: list[str],
        *,
        env: dict[str, str] | None = None,
        **_: object,
    ) -> Ok[str]:
        calls.append((cmd, env))
        return Ok('{"html_url":"https://github.com/owner/repo/pull/1"}')

    monkeypatch.setattr(pr_merge, "release_app_token_for_repo", fake_release_app_token_for_repo)
    monkeypatch.setattr(pr_merge, "run_gh_process", fake_run_gh_process)

    result = create_pull_request(
        workspace_root=tmp_path,
        repo_slug="owner/repo",
        base_branch="main",
        branch="release/test",
        title="release: test",
        body="body",
        repo_label="core",
        console=MockConsole(),
        dry_run=False,
    )

    assert isinstance(result, Ok)
    assert result.value == "https://github.com/owner/repo/pull/1"
    assert calls == [
        (
            [
                "gh",
                "api",
                "--method",
                "POST",
                "/repos/owner/repo/pulls",
                "-f",
                "title=release: test",
                "-f",
                "head=release/test",
                "-f",
                "base=main",
                "-f",
                "body=body",
            ],
            {"GH_TOKEN": "app-token"},
        )
    ]


def test_create_pull_request_falls_back_to_gh_user_without_release_app(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    import ms.release.infra.github.pr_merge as pr_merge

    calls: list[list[str]] = []

    def fake_release_app_token_for_repo(**_: object) -> Ok[None]:
        return Ok(None)

    def fake_run_gh_process(cmd: list[str], **_: object) -> Ok[str]:
        calls.append(cmd)
        return Ok("https://github.com/owner/repo/pull/1\n")

    monkeypatch.setattr(pr_merge, "release_app_token_for_repo", fake_release_app_token_for_repo)
    monkeypatch.setattr(pr_merge, "run_gh_process", fake_run_gh_process)

    result = create_pull_request(
        workspace_root=tmp_path,
        repo_slug="owner/repo",
        base_branch="main",
        branch="release/test",
        title="release: test",
        body="body",
        repo_label="core",
        console=MockConsole(),
        dry_run=False,
    )

    assert isinstance(result, Ok)
    assert calls == [
        [
            "gh",
            "pr",
            "create",
            "--repo",
            "owner/repo",
            "--base",
            "main",
            "--head",
            "release/test",
            "--title",
            "release: test",
            "--body",
            "body",
        ]
    ]


def test_merge_pull_request_reports_disabled_auto_merge(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    import ms.release.infra.github.pr_merge as pr_merge

    calls: list[str] = []

    def fake_run_gh_process(cmd: list[str], **_: object) -> Ok[str] | Err[ProcessError]:
        calls.append(" ".join(cmd))
        if cmd[:3] == ["gh", "pr", "view"]:
            return Ok('{"reviewDecision":"REVIEW_REQUIRED"}')
        if cmd[:3] == ["gh", "pr", "review"]:
            return Ok("")
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
                "gh pr view https://example.invalid/pr/1 --repo owner/repo",
                "--json reviewDecision",
            )
        ),
        " ".join(
            (
                "gh pr review https://example.invalid/pr/1 --repo owner/repo",
                "--approve --body Approved by ms release after local release preflight.",
            )
        ),
        " ".join(
            (
                "gh pr merge https://example.invalid/pr/1 --repo owner/repo",
                "--rebase --auto --delete-branch",
            )
        ),
    ]


def test_merge_pull_request_skips_approval_when_review_not_required(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    import ms.release.infra.github.pr_merge as pr_merge

    calls: list[str] = []

    def fake_run_gh_process(cmd: list[str], **_: object) -> Ok[str]:
        calls.append(" ".join(cmd))
        if cmd[:3] == ["gh", "pr", "view"]:
            return Ok('{"reviewDecision":"APPROVED"}')
        return Ok("")

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

    assert isinstance(result, Ok)
    assert calls == [
        " ".join(
            (
                "gh pr view https://example.invalid/pr/1 --repo owner/repo",
                "--json reviewDecision",
            )
        ),
        " ".join(
            (
                "gh pr merge https://example.invalid/pr/1 --repo owner/repo",
                "--rebase --auto --delete-branch",
            )
        ),
        "merged",
    ]


def test_merge_pull_request_reports_self_approval_when_review_required(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    import ms.release.infra.github.pr_merge as pr_merge

    def fake_run_gh_process(cmd: list[str], **_: object) -> Ok[str] | Err[ProcessError]:
        if cmd[:3] == ["gh", "pr", "view"]:
            return Ok('{"reviewDecision":"REVIEW_REQUIRED"}')
        return Err(
            ProcessError(
                command=tuple(cmd),
                returncode=1,
                stdout="",
                stderr="GraphQL: Can not approve your own pull request",
            )
        )

    monkeypatch.setattr(pr_merge, "run_gh_process", fake_run_gh_process)

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
    assert result.error.message == "core PR requires approval from a different GitHub identity"
    assert result.error.hint == (
        "Configure the release GitHub App so the PR is authored by the app, "
        "then approve with the maintainer account. PR: https://example.invalid/pr/1"
    )
