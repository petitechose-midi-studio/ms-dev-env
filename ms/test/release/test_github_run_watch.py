from __future__ import annotations

from pathlib import Path

from pytest import MonkeyPatch

from ms.core.result import Err
from ms.output.console import MockConsole
from ms.platform.process import ProcessError
from ms.release.infra.github.run_watch import watch_run


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
