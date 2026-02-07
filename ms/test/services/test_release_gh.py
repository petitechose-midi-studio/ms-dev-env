from __future__ import annotations

from pathlib import Path

import pytest

from ms.core.result import Err, Ok
from ms.platform.process import ProcessError
from ms.services.release import gh as gh_mod


def _err(*, stderr: str, returncode: int = 1) -> Err[ProcessError]:
    return Err(
        ProcessError(
            command=("gh", "api", "repos/example/project"),
            returncode=returncode,
            stdout="",
            stderr=stderr,
        )
    )


def _no_sleep(seconds: float) -> None:
    del seconds


def test_gh_api_json_retries_transient_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[list[str]] = []
    responses = [
        _err(stderr="HTTP 503 Service Unavailable", returncode=1),
        Ok('{"ok": true}'),
    ]

    def fake_run(cmd: list[str], *, cwd: Path, timeout: float | None = None):
        del cwd
        del timeout
        calls.append(cmd)
        return responses.pop(0)

    monkeypatch.setattr(gh_mod, "run_process", fake_run)
    monkeypatch.setattr(gh_mod, "sleep", _no_sleep)

    result = gh_mod.gh_api_json(workspace_root=tmp_path, endpoint="repos/example/project")
    assert isinstance(result, Ok)
    assert result.value == {"ok": True}
    assert len(calls) == 2


def test_gh_api_json_does_not_retry_on_non_transient(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], *, cwd: Path, timeout: float | None = None):
        del cwd
        del timeout
        calls.append(cmd)
        return _err(stderr="HTTP 404 Not Found", returncode=1)

    monkeypatch.setattr(gh_mod, "run_process", fake_run)
    monkeypatch.setattr(gh_mod, "sleep", _no_sleep)

    result = gh_mod.gh_api_json(workspace_root=tmp_path, endpoint="repos/example/project")
    assert isinstance(result, Err)
    assert result.error.kind == "invalid_input"
    assert len(calls) == 1


def test_viewer_permission_retries_transient_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[list[str]] = []
    responses = [
        _err(stderr="HTTP 502 Bad Gateway", returncode=1),
        Ok('{"viewerPermission": "WRITE"}'),
    ]

    def fake_run(cmd: list[str], *, cwd: Path, timeout: float | None = None):
        del cwd
        del timeout
        calls.append(cmd)
        return responses.pop(0)

    monkeypatch.setattr(gh_mod, "run_process", fake_run)
    monkeypatch.setattr(gh_mod, "sleep", _no_sleep)

    result = gh_mod.viewer_permission(
        workspace_root=tmp_path,
        repo="petitechose-midi-studio/distribution",
    )
    assert isinstance(result, Ok)
    assert result.value == "WRITE"
    assert len(calls) == 2
