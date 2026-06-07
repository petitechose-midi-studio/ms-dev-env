from __future__ import annotations

import json
from pathlib import Path

from pytest import MonkeyPatch

from ms.core.result import Err, Ok
from ms.output.console import MockConsole
from ms.platform.process import ProcessError
from ms.release.infra.github.run_watch import watch_run


def _run_payload(
    *,
    status: str,
    conclusion: str | None = None,
    jobs: list[dict[str, str | None]] | None = None,
) -> str:
    return json.dumps(
        {
            "status": status,
            "conclusion": conclusion,
            "url": "https://example.test/run/123",
            "jobs": jobs or [],
        }
    )


def test_watch_run_prints_concise_progress_until_success(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    import ms.release.infra.github.run_watch as run_watch

    payloads = iter(
        (
            _run_payload(status="queued"),
            _run_payload(
                status="in_progress",
                jobs=[
                    {"name": "architecture", "status": "completed", "conclusion": "success"},
                    {"name": "release alignment", "status": "in_progress", "conclusion": None},
                ],
            ),
            _run_payload(
                status="completed",
                conclusion="success",
                jobs=[
                    {"name": "architecture", "status": "completed", "conclusion": "success"},
                    {
                        "name": "release alignment",
                        "status": "completed",
                        "conclusion": "success",
                    },
                ],
            ),
        )
    )
    commands: list[list[str]] = []

    def fake_run_gh_process(cmd: list[str], **_: object) -> Ok[str]:
        commands.append(cmd)
        return Ok(next(payloads))

    monkeypatch.setattr(run_watch, "run_gh_process", fake_run_gh_process)
    console = MockConsole()

    result = watch_run(
        workspace_root=tmp_path,
        run_id=123,
        repo_slug="owner/repo",
        console=console,
        dry_run=False,
        poll_interval_seconds=0.1,
        sleep_fn=lambda _: None,
        clock_fn=lambda: 0.0,
    )

    assert isinstance(result, Ok)
    assert all(command[:3] == ["gh", "run", "view"] for command in commands)
    assert "watching: https://github.com/owner/repo/actions/runs/123" in console.text
    assert "progress: queued" in console.text
    assert "progress: in_progress | jobs 1/2 | active: release alignment" in console.text
    assert "progress: completed | jobs 2/2 | result: success" in console.text


def test_watch_run_failure_reports_failed_jobs_and_log_command(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    import ms.release.infra.github.run_watch as run_watch

    def fake_run_gh_process(cmd: list[str], **_: object) -> Ok[str]:
        return Ok(
            _run_payload(
                status="completed",
                conclusion="failure",
                jobs=[
                    {
                        "name": "test (ubuntu-latest)",
                        "status": "completed",
                        "conclusion": "success",
                    },
                    {"name": "release alignment", "status": "completed", "conclusion": "failure"},
                ],
            )
        )

    monkeypatch.setattr(run_watch, "run_gh_process", fake_run_gh_process)
    console = MockConsole()

    result = watch_run(
        workspace_root=tmp_path,
        run_id=123,
        repo_slug="owner/repo",
        console=console,
        dry_run=False,
        sleep_fn=lambda _: None,
        clock_fn=lambda: 0.0,
    )

    assert isinstance(result, Err)
    assert "progress: completed | jobs 2/2 | failed: release alignment" in console.text
    assert result.error.hint is not None
    assert "failed jobs: release alignment" in result.error.hint
    assert "gh run view 123 --repo owner/repo --log-failed" in result.error.hint


def test_watch_run_failure_includes_run_url_and_log_command(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    import ms.release.infra.github.run_watch as run_watch

    def fake_run_gh_process(cmd: list[str], **_: object) -> Err[ProcessError]:
        return Err(
            ProcessError(
                command=tuple(cmd),
                returncode=1,
                stdout="",
                stderr="failed",
            )
        )

    monkeypatch.setattr(run_watch, "run_gh_process", fake_run_gh_process)

    result = watch_run(
        workspace_root=tmp_path,
        run_id=123,
        repo_slug="owner/repo",
        console=MockConsole(),
        dry_run=False,
    )

    assert isinstance(result, Err)
    assert result.error.hint is not None
    assert "https://github.com/owner/repo/actions/runs/123" in result.error.hint
    assert "gh run view 123 --repo owner/repo --log-failed" in result.error.hint
