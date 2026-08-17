# pyright: reportUnknownArgumentType=false, reportUnknownLambdaType=false
from __future__ import annotations

from pathlib import Path

import pytest

from ms.core.result import Err, Ok
from ms.output.console import MockConsole
from ms.platform.process import ProcessError
from ms.release.flow import permissions
from ms.release.infra.github import client as gh_client
from ms.release.infra.github import gh_base as gh_mod


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

    def fake_run(
        cmd: list[str],
        *,
        cwd: Path,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
    ):
        del cwd
        del env
        del timeout
        calls.append(cmd)
        return responses.pop(0)

    monkeypatch.setattr(gh_mod, "run_process", fake_run)
    monkeypatch.setattr(gh_mod, "sleep", _no_sleep)

    result = gh_mod.gh_api_json(workspace_root=tmp_path, endpoint="repos/example/project")
    assert isinstance(result, Ok)
    assert result.value == {"ok": True}
    assert len(calls) == 2


def test_gh_process_env_promotes_github_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setenv("GITHUB_TOKEN", "workflow-token")

    env = gh_mod.gh_process_env()

    assert env["GITHUB_TOKEN"] == "workflow-token"
    assert env["GH_TOKEN"] == "workflow-token"


def test_gh_api_json_does_not_retry_on_non_transient(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[list[str]] = []

    def fake_run(
        cmd: list[str],
        *,
        cwd: Path,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
    ):
        del cwd
        del env
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

    def fake_run(
        cmd: list[str],
        *,
        cwd: Path,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
    ):
        del cwd
        del env
        del timeout
        calls.append(cmd)
        return responses.pop(0)

    monkeypatch.setattr(gh_mod, "run_process", fake_run)
    monkeypatch.setattr(gh_mod, "sleep", _no_sleep)

    result = gh_client.viewer_permission(
        workspace_root=tmp_path,
        repo="petitechose-midi-studio/distribution",
    )
    assert isinstance(result, Ok)
    assert result.value == "WRITE"
    assert len(calls) == 2


def test_release_permission_preflight_checks_repo_settings_and_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    endpoints: list[str] = []

    monkeypatch.setattr(permissions, "ensure_gh_available", lambda: Ok(None))
    monkeypatch.setattr(permissions, "ensure_gh_auth", lambda **_: Ok(None))
    monkeypatch.setattr(permissions, "viewer_permission", lambda **_: Ok("WRITE"))

    def fake_gh_api_json(*, workspace_root: Path, endpoint: str) -> Ok[object]:
        del workspace_root
        endpoints.append(endpoint)
        if "/environments/" in endpoint:
            return Ok({"name": "app-release"})
        return Ok({"allow_auto_merge": True, "allow_rebase_merge": True})

    monkeypatch.setattr(permissions, "gh_api_json", fake_gh_api_json)

    result = permissions.ensure_app_release_permissions(
        workspace_root=tmp_path,
        console=MockConsole(),
        require_write=True,
    )

    assert isinstance(result, Ok)
    assert endpoints == [
        "repos/petitechose-midi-studio/ms-manager",
        "repos/petitechose-midi-studio/ms-manager/environments/app-release",
    ]


def test_release_permission_preflight_rejects_disabled_auto_merge(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(permissions, "ensure_gh_available", lambda: Ok(None))
    monkeypatch.setattr(permissions, "ensure_gh_auth", lambda **_: Ok(None))
    monkeypatch.setattr(permissions, "viewer_permission", lambda **_: Ok("WRITE"))
    monkeypatch.setattr(
        permissions,
        "gh_api_json",
        lambda **_: Ok({"allow_auto_merge": False, "allow_rebase_merge": True}),
    )

    result = permissions.ensure_app_release_permissions(
        workspace_root=tmp_path,
        console=MockConsole(),
        require_write=True,
    )

    assert isinstance(result, Err)
    assert result.error.message == ("auto-merge is disabled for petitechose-midi-studio/ms-manager")


def test_full_release_preflight_authenticates_once_and_checks_all_repos(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    auth_calls = 0
    repos: list[str] = []

    monkeypatch.setattr(permissions, "ensure_gh_available", lambda: Ok(None))

    def fake_auth(**_: object) -> Ok[None]:
        nonlocal auth_calls
        auth_calls += 1
        return Ok(None)

    def fake_write_contract(*, repo_slug: str, **_: object) -> Ok[None]:
        repos.append(repo_slug)
        return Ok(None)

    monkeypatch.setattr(permissions, "ensure_gh_auth", fake_auth)
    monkeypatch.setattr(
        permissions,
        "_ensure_repo_write_contract",
        fake_write_contract,
    )

    result = permissions.ensure_full_release_permissions(
        workspace_root=tmp_path,
        console=MockConsole(),
    )

    assert isinstance(result, Ok)
    assert auth_calls == 1
    assert repos == [
        "petitechose-midi-studio/core",
        "petitechose-midi-studio/ms-manager",
        "petitechose-midi-studio/distribution",
    ]
