from __future__ import annotations

from pathlib import Path

from pytest import MonkeyPatch

from ms.core.result import Err, Ok
from ms.output.console import MockConsole
from ms.platform.process import ProcessError
from ms.release.infra.github.pr_review import approve_pull_request_if_required


def test_approve_pull_request_skips_when_review_not_required(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    import ms.release.infra.github.pr_review as pr_review

    calls: list[str] = []

    def fake_run_gh_process(cmd: list[str], **_: object) -> Ok[str]:
        calls.append(" ".join(cmd))
        return Ok('{"reviewDecision":"APPROVED"}')

    monkeypatch.setattr(pr_review, "run_gh_process", fake_run_gh_process)

    result = approve_pull_request_if_required(
        workspace_root=tmp_path,
        repo_slug="owner/repo",
        pr_url="https://example.invalid/pr/1",
        repo_label="core",
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
        )
    ]


def test_approve_pull_request_approves_when_review_required(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    import ms.release.infra.github.pr_review as pr_review

    calls: list[str] = []

    def fake_run_gh_process(cmd: list[str], **_: object) -> Ok[str]:
        calls.append(" ".join(cmd))
        if cmd[:3] == ["gh", "pr", "view"]:
            return Ok('{"reviewDecision":"REVIEW_REQUIRED"}')
        return Ok("")

    monkeypatch.setattr(pr_review, "run_gh_process", fake_run_gh_process)

    result = approve_pull_request_if_required(
        workspace_root=tmp_path,
        repo_slug="owner/repo",
        pr_url="https://example.invalid/pr/1",
        repo_label="core",
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
                "gh pr review https://example.invalid/pr/1 --repo owner/repo",
                "--approve --body Approved by ms release after local release preflight.",
            )
        ),
    ]


def test_approve_pull_request_reports_self_approval_when_review_required(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    import ms.release.infra.github.pr_review as pr_review

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

    monkeypatch.setattr(pr_review, "run_gh_process", fake_run_gh_process)

    result = approve_pull_request_if_required(
        workspace_root=tmp_path,
        repo_slug="owner/repo",
        pr_url="https://example.invalid/pr/1",
        repo_label="core",
        console=MockConsole(),
        dry_run=False,
    )

    assert isinstance(result, Err)
    assert result.error.message == "core PR requires approval from a different GitHub identity"
    assert result.error.hint == (
        "Configure the release GitHub App so the PR is authored by the app, "
        "then approve with the maintainer account. PR: https://example.invalid/pr/1"
    )
