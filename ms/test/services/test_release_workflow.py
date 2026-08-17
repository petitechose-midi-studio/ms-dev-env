# pyright: reportUnknownArgumentType=false, reportUnknownLambdaType=false
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ms.core.result import Err, Ok
from ms.output.console import MockConsole
from ms.release.infra.github import workflow_dispatch_lookup as lookup_mod
from ms.release.infra.github import workflows as workflow_mod
from ms.release.infra.github.workflow_dispatch_lookup import WorkflowRunResolution


def _dispatch_artifact(*, run_id: int, request_id: str) -> dict[str, object]:
    return {
        "name": f"dispatch-{request_id}",
        "expired": False,
        "workflow_run": {"id": run_id},
    }


def _no_sleep(seconds: float) -> None:
    del seconds


def _fixed_new_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        workflow_mod,
        "_dispatch_request_id",
        lambda **_: "ms-123456781234",
    )
    monkeypatch.setattr(workflow_mod, "find_dispatched_run", lambda **_: Ok(None))
    monkeypatch.setattr(workflow_mod, "get_ref_head_sha", lambda **_: Ok("a" * 40))


def test_dispatch_publish_workflow_matches_request_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _fixed_new_dispatch(monkeypatch)

    calls: list[list[str]] = []

    def fake_run(cmd: list[str], *, cwd: Path, timeout: float | None = None):
        del cwd
        del timeout
        calls.append(cmd)
        if cmd[:3] == ["gh", "workflow", "run"]:
            return Ok("")
        if cmd[:2] == ["gh", "api"]:
            payload = {"artifacts": [_dispatch_artifact(run_id=101, request_id="ms-123456781234")]}
            return Ok(json.dumps(payload))
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(workflow_mod, "run_gh_process", fake_run)
    monkeypatch.setattr(lookup_mod, "run_gh_process", fake_run)

    result = workflow_mod.dispatch_publish_workflow(
        workspace_root=tmp_path,
        channel="stable",
        tag="v1.2.3",
        spec_path="releases/stable/spec-v1.2.3.json",
        tooling_sha="f" * 40,
        console=MockConsole(),
        dry_run=False,
    )
    assert isinstance(result, Ok)
    assert result.value.id == 101
    assert result.value.request_id == "ms-123456781234"
    assert result.value.url.endswith("/101")
    assert sum(1 for cmd in calls if cmd[:2] == ["gh", "api"]) == 1
    assert any(
        cmd[2].endswith("?per_page=100&page=1&name=dispatch-ms-123456781234")
        for cmd in calls
        if cmd[:2] == ["gh", "api"]
    )


def test_dispatch_release_alignment_workflow_uses_ms_dev_env_workflow(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _fixed_new_dispatch(monkeypatch)
    request: dict[str, object] = {}

    def fake_request_id(**kwargs: object) -> str:
        request.update(kwargs)
        return "ms-123456781234"

    monkeypatch.setattr(workflow_mod, "_dispatch_request_id", fake_request_id)

    calls: list[list[str]] = []

    def fake_run(cmd: list[str], *, cwd: Path, timeout: float | None = None):
        del cwd
        del timeout
        calls.append(cmd)
        if cmd[:3] == ["gh", "workflow", "run"]:
            return Ok("")
        if cmd[:2] == ["gh", "api"]:
            payload = {"artifacts": [_dispatch_artifact(run_id=401, request_id="ms-123456781234")]}
            return Ok(json.dumps(payload))
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(workflow_mod, "run_gh_process", fake_run)
    monkeypatch.setattr(lookup_mod, "run_gh_process", fake_run)

    result = workflow_mod.dispatch_release_alignment_workflow(
        workspace_root=tmp_path,
        build_wasm=False,
        core_sha="c" * 40,
        console=MockConsole(),
        dry_run=False,
    )

    assert isinstance(result, Ok)
    assert result.value.id == 401
    dispatch = calls[0]
    assert dispatch[:7] == [
        "gh",
        "workflow",
        "run",
        "integration.yml",
        "--repo",
        "petitechose-midi-studio/ms-dev-env",
        "--ref",
    ]
    assert "main" in dispatch
    assert "-f" in dispatch
    assert "build_wasm=false" in dispatch
    assert "request_id=ms-123456781234" in dispatch
    assert request["ref"] == "a" * 40
    assert request["identity"] == (("core_sha", "c" * 40),)


def test_dispatch_publish_workflow_retries_until_match(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _fixed_new_dispatch(monkeypatch)
    monkeypatch.setattr(lookup_mod, "_LOOKUP_MAX_ATTEMPTS", 3)
    monkeypatch.setattr(lookup_mod, "_LOOKUP_DELAY_SECONDS", 0.0)
    monkeypatch.setattr(lookup_mod, "sleep", _no_sleep)

    artifact_payloads = [
        json.dumps({"artifacts": []}),
        json.dumps({"artifacts": [_dispatch_artifact(run_id=201, request_id="ms-123456781234")]}),
    ]
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], *, cwd: Path, timeout: float | None = None):
        del cwd
        del timeout
        calls.append(cmd)
        if cmd[:3] == ["gh", "workflow", "run"]:
            return Ok("")
        if cmd[:2] == ["gh", "api"]:
            return Ok(artifact_payloads.pop(0))
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(workflow_mod, "run_gh_process", fake_run)
    monkeypatch.setattr(lookup_mod, "run_gh_process", fake_run)

    result = workflow_mod.dispatch_publish_workflow(
        workspace_root=tmp_path,
        channel="stable",
        tag="v1.2.3",
        spec_path="releases/stable/spec-v1.2.3.json",
        tooling_sha="f" * 40,
        console=MockConsole(),
        dry_run=False,
    )
    assert isinstance(result, Ok)
    assert result.value.id == 201
    assert sum(1 for cmd in calls if cmd[:2] == ["gh", "api"]) == 2
    assert all(
        cmd[2].endswith("?per_page=100&page=1&name=dispatch-ms-123456781234")
        for cmd in calls
        if cmd[:2] == ["gh", "api"]
    )


def test_dispatch_publish_workflow_paginates_artifact_lookup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _fixed_new_dispatch(monkeypatch)
    monkeypatch.setattr(lookup_mod, "_LOOKUP_MAX_ATTEMPTS", 1)

    calls: list[list[str]] = []

    page_1 = json.dumps(
        {
            "total_count": 101,
            "artifacts": [_dispatch_artifact(run_id=999, request_id="other")] * 100,
        }
    )
    page_2 = json.dumps(
        {
            "total_count": 101,
            "artifacts": [_dispatch_artifact(run_id=301, request_id="ms-123456781234")],
        }
    )

    def fake_run(cmd: list[str], *, cwd: Path, timeout: float | None = None):
        del cwd
        del timeout
        calls.append(cmd)
        if cmd[:3] == ["gh", "workflow", "run"]:
            return Ok("")
        if cmd[:2] == ["gh", "api"]:
            endpoint = cmd[2]
            if "&page=1&" in endpoint:
                return Ok(page_1)
            if "&page=2&" in endpoint:
                return Ok(page_2)
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(workflow_mod, "run_gh_process", fake_run)
    monkeypatch.setattr(lookup_mod, "run_gh_process", fake_run)

    result = workflow_mod.dispatch_publish_workflow(
        workspace_root=tmp_path,
        channel="stable",
        tag="v1.2.3",
        spec_path="releases/stable/spec-v1.2.3.json",
        tooling_sha="f" * 40,
        console=MockConsole(),
        dry_run=False,
    )
    assert isinstance(result, Ok)
    assert result.value.id == 301
    api_calls = [cmd for cmd in calls if cmd[:2] == ["gh", "api"]]
    assert len(api_calls) == 2
    assert "page=1" in api_calls[0][2]
    assert "page=2" in api_calls[1][2]


def test_dispatch_publish_workflow_fails_without_request_id_match(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _fixed_new_dispatch(monkeypatch)
    monkeypatch.setattr(lookup_mod, "_LOOKUP_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(lookup_mod, "_LOOKUP_DELAY_SECONDS", 0.0)
    monkeypatch.setattr(lookup_mod, "sleep", _no_sleep)

    payload = json.dumps({"artifacts": []})

    def fake_run(cmd: list[str], *, cwd: Path, timeout: float | None = None):
        del cwd
        del timeout
        if cmd[:3] == ["gh", "workflow", "run"]:
            return Ok("")
        if cmd[:2] == ["gh", "api"]:
            return Ok(payload)
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(workflow_mod, "run_gh_process", fake_run)
    monkeypatch.setattr(lookup_mod, "run_gh_process", fake_run)

    result = workflow_mod.dispatch_publish_workflow(
        workspace_root=tmp_path,
        channel="stable",
        tag="v1.2.3",
        spec_path="releases/stable/spec-v1.2.3.json",
        tooling_sha="f" * 40,
        console=MockConsole(),
        dry_run=False,
    )
    assert isinstance(result, Err)
    assert result.error.kind == "workflow_failed"
    assert "deterministically identify" in result.error.message
    assert result.error.hint is not None
    assert "dispatch-ms-123456781234" in result.error.hint


def test_dispatch_publish_workflow_reuses_matching_dispatch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        workflow_mod,
        "_dispatch_request_id",
        lambda **_: "ms-stable-request",
    )
    monkeypatch.setattr(workflow_mod, "get_ref_head_sha", lambda **_: Ok("a" * 40))
    monkeypatch.setattr(
        workflow_mod,
        "find_dispatched_run",
        lambda **_: Ok(
            WorkflowRunResolution(
                run_id=501,
                url="https://github.com/owner/repo/actions/runs/501",
            )
        ),
    )
    monkeypatch.setattr(
        workflow_mod,
        "run_gh_process",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("matching dispatch must not be duplicated")
        ),
    )

    result = workflow_mod.dispatch_publish_workflow(
        workspace_root=tmp_path,
        channel="stable",
        tag="v1.2.3",
        spec_path="releases/stable/spec-v1.2.3.json",
        tooling_sha="f" * 40,
        console=MockConsole(),
        dry_run=False,
    )

    assert isinstance(result, Ok)
    assert result.value.id == 501
    assert result.value.request_id == "ms-stable-request"
