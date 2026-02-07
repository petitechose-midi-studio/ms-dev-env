from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import pytest

from ms.core.result import Err, Ok
from ms.output.console import MockConsole
from ms.services.release import workflow as workflow_mod


def _dispatch_item(*, run_id: int, title: str, branch: str = "main") -> dict[str, object]:
    return {
        "databaseId": run_id,
        "url": f"https://github.com/open-control/distribution/actions/runs/{run_id}",
        "event": "workflow_dispatch",
        "headBranch": branch,
        "displayTitle": title,
    }


def _no_sleep(seconds: float) -> None:
    del seconds


def test_dispatch_publish_workflow_matches_request_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(workflow_mod, "uuid4", lambda: UUID("12345678-1234-5678-1234-567812345678"))

    calls: list[list[str]] = []

    def fake_run(cmd: list[str], *, cwd: Path, timeout: float | None = None):
        del cwd
        del timeout
        calls.append(cmd)
        if cmd[:3] == ["gh", "workflow", "run"]:
            return Ok("")
        if cmd[:3] == ["gh", "run", "list"]:
            payload = [_dispatch_item(run_id=101, title="publish ms-123456781234")]
            return Ok(json.dumps(payload))
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(workflow_mod, "run_process", fake_run)

    result = workflow_mod.dispatch_publish_workflow(
        workspace_root=tmp_path,
        channel="stable",
        tag="v1.2.3",
        spec_path="releases/stable/spec-v1.2.3.json",
        console=MockConsole(),
        dry_run=False,
    )
    assert isinstance(result, Ok)
    assert result.value.id == 101
    assert result.value.request_id == "ms-123456781234"
    assert result.value.url.endswith("/101")
    assert sum(1 for cmd in calls if cmd[:3] == ["gh", "run", "list"]) == 1


def test_dispatch_publish_workflow_retries_until_match(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(workflow_mod, "uuid4", lambda: UUID("12345678-1234-5678-1234-567812345678"))
    monkeypatch.setattr(workflow_mod, "_RUN_LOOKUP_MAX_ATTEMPTS", 3)
    monkeypatch.setattr(workflow_mod, "_RUN_LOOKUP_DELAY_SECONDS", 0.0)
    monkeypatch.setattr(workflow_mod, "sleep", _no_sleep)

    list_payloads = [
        json.dumps([_dispatch_item(run_id=200, title="publish run without request id")]),
        json.dumps([_dispatch_item(run_id=201, title="publish ms-123456781234")]),
    ]
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], *, cwd: Path, timeout: float | None = None):
        del cwd
        del timeout
        calls.append(cmd)
        if cmd[:3] == ["gh", "workflow", "run"]:
            return Ok("")
        if cmd[:3] == ["gh", "run", "list"]:
            return Ok(list_payloads.pop(0))
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(workflow_mod, "run_process", fake_run)

    result = workflow_mod.dispatch_publish_workflow(
        workspace_root=tmp_path,
        channel="stable",
        tag="v1.2.3",
        spec_path="releases/stable/spec-v1.2.3.json",
        console=MockConsole(),
        dry_run=False,
    )
    assert isinstance(result, Ok)
    assert result.value.id == 201
    assert sum(1 for cmd in calls if cmd[:3] == ["gh", "run", "list"]) == 2


def test_dispatch_publish_workflow_fails_without_request_id_match(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(workflow_mod, "uuid4", lambda: UUID("12345678-1234-5678-1234-567812345678"))
    monkeypatch.setattr(workflow_mod, "_RUN_LOOKUP_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(workflow_mod, "_RUN_LOOKUP_DELAY_SECONDS", 0.0)
    monkeypatch.setattr(workflow_mod, "sleep", _no_sleep)

    payload = json.dumps([_dispatch_item(run_id=300, title="publish old run")])

    def fake_run(cmd: list[str], *, cwd: Path, timeout: float | None = None):
        del cwd
        del timeout
        if cmd[:3] == ["gh", "workflow", "run"]:
            return Ok("")
        if cmd[:3] == ["gh", "run", "list"]:
            return Ok(payload)
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(workflow_mod, "run_process", fake_run)

    result = workflow_mod.dispatch_publish_workflow(
        workspace_root=tmp_path,
        channel="stable",
        tag="v1.2.3",
        spec_path="releases/stable/spec-v1.2.3.json",
        console=MockConsole(),
        dry_run=False,
    )
    assert isinstance(result, Err)
    assert result.error.kind == "workflow_failed"
    assert "deterministically identify" in result.error.message
    assert result.error.hint is not None
    assert "request_id=ms-123456781234" in result.error.hint
