"""Tests for release resume: pending_op reconciliation and write-ahead persistence."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from ms.core.result import Err, Ok, Result
from ms.output.console import ConsoleProtocol, MockConsole
from ms.platform.process import ProcessError
from ms.release.domain import config
from ms.release.domain.models import PinnedRepo, ReleasePlan, ReleaseRepo, ReleaseTooling
from ms.release.errors import ReleaseError
from ms.release.flow.app_prepare import AppPrepareResult
from ms.release.flow.app_publish import publish_app_release
from ms.release.flow.guided import app_confirm_step, content_confirm_step, pending_op
from ms.release.flow.guided.app_confirm_step import run_app_confirm_step
from ms.release.flow.guided.app_contracts import AppGuidedDependencies
from ms.release.flow.guided.content_confirm_step import run_content_confirm_step
from ms.release.flow.guided.content_contracts import ContentGuidedDependencies
from ms.release.flow.guided.fsm import FINISH, StepOutcome
from ms.release.flow.guided.pending_op import PendingReconciliation
from ms.release.flow.guided.session_models import SessionCursor
from ms.release.flow.guided.sessions import (
    AppReleaseSession,
    ContentReleaseSession,
    clear_app_session,
    clear_content_session,
    load_app_session,
    load_content_session,
    new_app_session,
    new_content_session,
    save_app_session,
    save_content_session,
)
from ms.release.flow.pr_outcome import PrMergeOutcome
from ms.release.flow.remote_coherence import RemoteCoherenceReport
from ms.release.infra.github import gh_base
from ms.release.infra.github.workflow_dispatch_lookup import WorkflowRunResolution
from ms.release.infra.github.workflows import BeforeDispatch, dispatch_request_id

_SHA = "a" * 40
_TOOLING = "b" * 40
_HEAD = "c" * 40
_INPUTS = (("tag", "app-v1.0.0"), ("source_sha", _SHA), ("tooling_sha", _TOOLING))
_REQUEST = dispatch_request_id(
    repo_slug=config.APP_REPO_SLUG, workflow_file=config.APP_RELEASE_WORKFLOW,
    ref=_HEAD, inputs=_INPUTS,
)


def _session() -> AppReleaseSession:
    session = new_app_session(created_by="test", notes_path=None)
    return replace(
        session,
        step="confirm",
        channel="beta",
        bump="patch",
        tag="app-v1.0.0",
        version="1.0.0",
        repo_sha=_SHA,
        tooling_sha=_TOOLING,
    )


def _pending_session() -> AppReleaseSession:
    return replace(
        _session(),
        pending_kind="app_release",
        pending_request_id=_REQUEST,
        pending_repo=config.APP_REPO_SLUG,
        pending_workflow=config.APP_RELEASE_WORKFLOW,
        pending_tag="app-v1.0.0",
        pending_source_sha=_SHA,
        pending_tooling_sha=_TOOLING,
        pending_at="2026-09-26T00:00:00+00:00",
        pending_inputs=_INPUTS,
    )


# --- session round-trip --------------------------------------------------------


class TestSessionRoundTrip:
    def test_app_session_round_trip(self, tmp_path: Path) -> None:
        session = replace(
            _pending_session(),
            cursor=SessionCursor(channel=2, bump=3, sha=4, summary=5, return_to_summary=True),
        )
        assert isinstance(save_app_session(workspace_root=tmp_path, session=session), Ok)

        loaded = load_app_session(workspace_root=tmp_path)
        assert isinstance(loaded, Ok)
        assert loaded.value == session

    def test_content_session_round_trip(self, tmp_path: Path) -> None:
        session = new_content_session(created_by="test", notes_path=None)
        session = replace(
            session,
            step="summary",
            channel="beta",
            bump="patch",
            tag="content-v1",
            cursor=SessionCursor(
                channel=2, bump=3, repo=1, summary=4, candidates=5, return_to_summary=True
            ),
            pending_kind="content_release",
            pending_request_id="ms-creq",
            pending_tag="content-v1",
            pending_at="2026-09-26T00:00:00+00:00",
        )
        assert isinstance(save_content_session(workspace_root=tmp_path, session=session), Ok)

        loaded = load_content_session(workspace_root=tmp_path)
        assert isinstance(loaded, Ok)
        assert loaded.value == session


# --- pending_op reconciliation -------------------------------------------------


def _run_found(
    *, workspace_root: Path, repo_slug: str, request_id: str
) -> Result[WorkflowRunResolution | None, ReleaseError]:
    return Ok(WorkflowRunResolution(run_id=42, url="https://example.test/run/42"))


def _run_missing(
    *, workspace_root: Path, repo_slug: str, request_id: str
) -> Result[WorkflowRunResolution | None, ReleaseError]:
    return Ok(None)


def _released(
    *, workspace_root: Path, repo: str, tag: str
) -> Result[bool, ReleaseError]:
    return Ok(True)


def _not_released(
    *, workspace_root: Path, repo: str, tag: str
) -> Result[bool, ReleaseError]:
    return Ok(False)


def _run_status_in_progress(
    *, workspace_root: Path, endpoint: str
) -> Result[object, ReleaseError]:
    return Ok(_run_payload("in_progress", None))


def _run_status_failed(
    *, workspace_root: Path, endpoint: str
) -> Result[object, ReleaseError]:
    return Ok(_run_payload("completed", "failure"))


def _run_status_success(
    *, workspace_root: Path, endpoint: str
) -> Result[object, ReleaseError]:
    return Ok(_run_payload("completed", "success"))


def _run_payload(status: str, conclusion: str | None) -> dict[str, object]:
    return {
        "status": status, "conclusion": conclusion, "head_sha": _HEAD,
        "event": "workflow_dispatch", "path": f".github/workflows/{config.APP_RELEASE_WORKFLOW}",
    }


class TestReconcilePendingOp:
    def _reconcile(self, monkeypatch: pytest.MonkeyPatch) -> PendingReconciliation:
        result = pending_op.reconcile_pending_op(
            workspace_root=Path("/tmp/ws"),
            repo=config.APP_REPO_SLUG,
            workflow_file=config.APP_RELEASE_WORKFLOW,
            tag="app-v1.0.0",
            request_id=_REQUEST,
            inputs=_INPUTS,
            source_sha=_SHA,
            tooling_sha=_TOOLING,
            attempts=1,
        )
        assert isinstance(result, Ok)
        return result.value

    def test_release_without_proven_run_is_undetermined(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(pending_op, "find_dispatched_run", _run_missing)
        monkeypatch.setattr(pending_op, "release_exists_by_tag", _released)

        outcome = self._reconcile(monkeypatch)

        assert outcome.state == "undetermined"
        assert "identity is not verified" in outcome.detail

    def test_persisted_request_id_is_used_for_lookup(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: list[str] = []

        def lookup(
            *, workspace_root: Path, repo_slug: str, request_id: str
        ) -> Result[WorkflowRunResolution | None, ReleaseError]:
            seen.append(request_id)
            return Ok(None)

        monkeypatch.setattr(pending_op, "find_dispatched_run", lookup)
        monkeypatch.setattr(pending_op, "release_exists_by_tag", _not_released)

        outcome = self._reconcile(monkeypatch)

        assert seen == [_REQUEST]
        assert outcome.state == "undetermined"

    def test_run_in_progress_is_not_replayed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(pending_op, "find_dispatched_run", _run_found)
        monkeypatch.setattr(pending_op, "gh_api_json", _run_status_in_progress)
        monkeypatch.setattr(pending_op, "release_exists_by_tag", _not_released)

        outcome = self._reconcile(monkeypatch)

        assert outcome.state == "in_flight"
        assert outcome.run_url == "https://example.test/run/42"

    def test_failed_run_is_reported(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(pending_op, "find_dispatched_run", _run_found)
        monkeypatch.setattr(pending_op, "gh_api_json", _run_status_failed)

        outcome = self._reconcile(monkeypatch)

        assert outcome.state == "failed"

    def test_success_and_release_visible_completes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(pending_op, "find_dispatched_run", _run_found)
        monkeypatch.setattr(pending_op, "gh_api_json", _run_status_success)
        monkeypatch.setattr(pending_op, "release_exists_by_tag", _released)

        outcome = self._reconcile(monkeypatch)

        assert outcome.state == "completed"

    def test_success_without_release_is_undetermined(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(pending_op, "find_dispatched_run", _run_found)
        monkeypatch.setattr(pending_op, "gh_api_json", _run_status_success)
        monkeypatch.setattr(pending_op, "release_exists_by_tag", _not_released)

        outcome = self._reconcile(monkeypatch)

        assert outcome.state == "undetermined"

    def test_nothing_found_is_undetermined(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(pending_op, "find_dispatched_run", _run_missing)
        monkeypatch.setattr(pending_op, "release_exists_by_tag", _not_released)

        outcome = self._reconcile(monkeypatch)

        assert outcome.state == "undetermined"


# --- confirm step resume behavior ---------------------------------------------


class _FakeDeps:
    def __init__(self, *, fail_save: bool = False) -> None:
        self.calls: list[str] = []
        self.saved: list[AppReleaseSession] = []
        self.confirm_called = False
        self._fail_save = fail_save

    def save_state(
        self, *, session: AppReleaseSession
    ) -> Result[AppReleaseSession, ReleaseError]:
        self.calls.append("save")
        if self._fail_save:
            return Err(ReleaseError(kind="repo_failed", message="save failed"))
        self.saved.append(session)
        return Ok(session)

    def confirm(self, *, prompt: str) -> bool:
        self.confirm_called = True
        return True

    def clear_session(self) -> Result[None, ReleaseError]:
        self.calls.append("clear")
        return Ok(None)

    def ensure_ci_green(
        self, *, workspace_root: Path, pinned: tuple[PinnedRepo, ...], allow_non_green: bool
    ) -> Result[None, ReleaseError]:
        return Ok(None)


def _deps(deps: _FakeDeps) -> AppGuidedDependencies[AppPrepareResult]:
    return cast(AppGuidedDependencies[AppPrepareResult], deps)


def _content_deps(deps: _FakeDeps) -> ContentGuidedDependencies:
    return cast(ContentGuidedDependencies, deps)


def _fake_reconcile(state: str, detail: str = "detail") -> object:
    def reconcile(**kwargs: object) -> Result[PendingReconciliation, ReleaseError]:
        return Ok(PendingReconciliation(state=state, detail=detail))  # type: ignore[arg-type]

    return reconcile


def test_completed_pending_clears_and_finishes(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _pending_session()
    deps = _FakeDeps()
    monkeypatch.setattr(app_confirm_step, "reconcile_pending_op", _fake_reconcile("completed"))

    result = run_app_confirm_step(
        session=session,
        workspace_root=Path("/tmp/ws"),
        console=MockConsole(),
        watch=False,
        dry_run=False,
        app_release_repo=config.APP_RELEASE_REPO,
        deps=_deps(deps),
    )

    assert isinstance(result, Ok)
    assert result.value is FINISH
    assert not deps.confirm_called
    assert deps.calls == ["clear"]


@pytest.mark.parametrize("state", ["in_flight", "failed", "undetermined"])
def test_pending_not_replayed_when_unresolved(
    monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    session = _pending_session()
    deps = _FakeDeps()
    monkeypatch.setattr(app_confirm_step, "reconcile_pending_op", _fake_reconcile(state))

    result = run_app_confirm_step(
        session=session,
        workspace_root=Path("/tmp/ws"),
        console=MockConsole(),
        watch=False,
        dry_run=False,
        app_release_repo=config.APP_RELEASE_REPO,
        deps=_deps(deps),
    )

    assert isinstance(result, Err)
    assert not deps.confirm_called
    assert deps.calls == []


# --- write-ahead persistence before dispatch -----------------------------------


def _identity_refresh(
    *, session: AppReleaseSession, workspace_root: Path, console: ConsoleProtocol
) -> Result[AppReleaseSession, ReleaseError]:
    return Ok(session)


def _coherence_ok(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    pinned: tuple[PinnedRepo, ...],
    tooling: ReleaseTooling,
    dry_run: bool,
    verify_ci: bool = True,
) -> Result[RemoteCoherenceReport, ReleaseError]:
    return Ok(RemoteCoherenceReport(items=()))


def _pinned_ok(
    *, app_release_repo: ReleaseRepo, session: AppReleaseSession
) -> Result[tuple[PinnedRepo, ...], ReleaseError]:
    return Ok(())


class _DispatchRecorder:
    def __init__(self) -> None:
        self.request_ids: list[str | None] = []
        self.pending_seen: list[str | None] = []

    def __call__(
        self,
        *,
        deps: object,
        workspace_root: Path,
        console: ConsoleProtocol,
        watch: bool,
        dry_run: bool,
        session: AppReleaseSession,
        prepared: object,
        tag: str,
        tooling_sha: str,
        request_id: str | None = None,
        before_dispatch: BeforeDispatch | None = None,
    ) -> Result[None, ReleaseError]:
        if before_dispatch is not None:
            saved = before_dispatch("ms-req123", _INPUTS)
            if isinstance(saved, Err):
                return saved
            request_id = "ms-req123"
        self.request_ids.append(request_id)
        self.pending_seen.append(request_id)
        return Ok(None)


class _PreparedDouble:
    @property
    def source_sha(self) -> str:
        return _SHA


class _DispatchRecorderContent:
    def __init__(self) -> None:
        self.request_ids: list[str | None] = []

    def __call__(
        self,
        *,
        deps: object,
        workspace_root: Path,
        console: ConsoleProtocol,
        watch: bool,
        dry_run: bool,
        plan: object,
        request_id: str | None = None,
    ) -> Result[None, ReleaseError]:
        self.request_ids.append(request_id)
        return Ok(None)


def _prepare_app_release_ok(
    *,
    deps: object,
    workspace_root: Path,
    console: ConsoleProtocol,
    dry_run: bool,
    session: AppReleaseSession,
    pinned: tuple[PinnedRepo, ...],
    tag: str,
    version: str,
    repo_sha: str,
    remote_coherence_checked: bool = False,
) -> Result[_PreparedDouble, ReleaseError]:
    return Ok(_PreparedDouble())


def _prepare_confirm_step(monkeypatch: pytest.MonkeyPatch, deps: _FakeDeps) -> _DispatchRecorder:
    recorder = _DispatchRecorder()
    monkeypatch.setattr(app_confirm_step, "refresh_app_session_tooling", _identity_refresh)
    monkeypatch.setattr(app_confirm_step, "assert_release_remote_coherence", _coherence_ok)
    monkeypatch.setattr(app_confirm_step, "pinned_app_repo", _pinned_ok)
    monkeypatch.setattr(app_confirm_step, "prepare_app_release", _prepare_app_release_ok)
    monkeypatch.setattr(app_confirm_step, "publish_prepared_app_release", recorder)
    return recorder


def _content_session() -> ContentReleaseSession:
    session = new_content_session(created_by="test", notes_path=None)
    return replace(session, step="confirm", channel="beta", bump="patch", tag="content-v1")


def _pending_content_session() -> ContentReleaseSession:
    session = new_content_session(created_by="test", notes_path=None)
    return replace(
        session,
        step="confirm",
        channel="beta",
        bump="patch",
        tag="content-v1",
        pending_kind="content_release",
        pending_request_id="ms-creq",
        pending_repo=config.DIST_REPO_SLUG,
        pending_workflow=config.DIST_PUBLISH_WORKFLOW,
        pending_tag="content-v1",
        pending_tooling_sha=_TOOLING,
        pending_at="2026-09-26T00:00:00+00:00",
    )


def test_content_completed_pending_clears(monkeypatch: pytest.MonkeyPatch) -> None:
    deps = _FakeDeps()
    monkeypatch.setattr(content_confirm_step, "reconcile_pending_op", _fake_reconcile("completed"))

    result = run_content_confirm_step(
        deps=_content_deps(deps),
        workspace_root=Path("/tmp/ws"),
        console=MockConsole(),
        watch=False,
        dry_run=False,
        session=_pending_content_session(),
        release_repos=(),
    )

    assert isinstance(result, Ok)
    assert result.value is FINISH
    assert not deps.confirm_called
    assert deps.calls == ["clear"]


@pytest.mark.parametrize("state", ["in_flight", "failed", "undetermined"])
def test_content_pending_not_replayed(monkeypatch: pytest.MonkeyPatch, state: str) -> None:
    deps = _FakeDeps()
    monkeypatch.setattr(content_confirm_step, "reconcile_pending_op", _fake_reconcile(state))

    result = run_content_confirm_step(
        deps=_content_deps(deps),
        workspace_root=Path("/tmp/ws"),
        console=MockConsole(),
        watch=False,
        dry_run=False,
        session=_pending_content_session(),
        release_repos=(),
    )

    assert isinstance(result, Err)
    assert not deps.confirm_called
    assert deps.calls == []


class _RealStoreDeps(_FakeDeps):
    def __init__(self, *, workspace: Path) -> None:
        super().__init__()
        self._workspace = workspace

    def save_state(
        self, *, session: AppReleaseSession
    ) -> Result[AppReleaseSession, ReleaseError]:
        written = save_app_session(workspace_root=self._workspace, session=session)
        if isinstance(written, Err):
            return Err(written.error)
        self.saved.append(session)
        return Ok(session)

    def clear_session(self) -> Result[None, ReleaseError]:
        return clear_app_session(workspace_root=self._workspace)


def test_remote_success_then_crash_resumes_without_redispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 1) dispatch succeeded remotely, crash before local clear: session on disk keeps pending_op
    first_deps = _RealStoreDeps(workspace=tmp_path)
    first_recorder = _prepare_confirm_step(monkeypatch, first_deps)

    first = run_app_confirm_step(
        session=_session(),
        workspace_root=tmp_path,
        console=MockConsole(),
        watch=True,
        dry_run=False,
        app_release_repo=config.APP_RELEASE_REPO,
        deps=_deps(first_deps),
    )
    assert isinstance(first, Ok)
    assert first_recorder.request_ids == ["ms-req123"]

    on_disk = load_app_session(workspace_root=tmp_path)
    assert isinstance(on_disk, Ok)
    assert on_disk.value is not None
    assert on_disk.value.pending_request_id == "ms-req123"

    # 2) resume: GitHub boundary says the dispatch completed; no re-dispatch, disk cleared
    seen_request_ids: list[str | None] = []

    def reconcile_completed(**kwargs: object) -> Result[PendingReconciliation, ReleaseError]:
        seen_request_ids.append(cast(str | None, kwargs.get("request_id")))
        return Ok(PendingReconciliation(state="completed", detail="proven"))

    monkeypatch.setattr(app_confirm_step, "reconcile_pending_op", reconcile_completed)
    resume_deps = _RealStoreDeps(workspace=tmp_path)
    resume_recorder = _DispatchRecorder()
    monkeypatch.setattr(app_confirm_step, "publish_prepared_app_release", resume_recorder)

    resumed = run_app_confirm_step(
        session=on_disk.value,
        workspace_root=tmp_path,
        console=MockConsole(),
        watch=False,
        dry_run=False,
        app_release_repo=config.APP_RELEASE_REPO,
        deps=_deps(resume_deps),
    )

    assert isinstance(resumed, Ok)
    assert resumed.value is FINISH
    assert resume_recorder.request_ids == []
    assert seen_request_ids == ["ms-req123"]
    cleared = load_app_session(workspace_root=tmp_path)
    assert isinstance(cleared, Ok)
    assert cleared.value is None


def test_content_pending_persisted_before_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    deps = _FakeDeps()
    recorder = _DispatchRecorderContent()

    def bom_aligned(**kwargs: object) -> object:
        return SimpleNamespace(status="aligned", label="aligned", detail="")

    def plan_ok(**kwargs: object) -> Result[ReleasePlan, ReleaseError]:
        return Ok(
            ReleasePlan(
                channel="beta",
                tag="content-v1",
                spec_path="releases/beta/spec-content-v1.json",
                tooling=ReleaseTooling(
                    repo="petitechose-midi-studio/ms-dev-env", ref="main", sha=_TOOLING
                ),
                pinned=(),
                notes_path=None,
                title="Content v1",
            )
        )

    def clean_ok(**kwargs: object) -> Result[None, ReleaseError]:
        return Ok(None)

    def prepare_ok(**kwargs: object) -> Result[object, ReleaseError]:
        return Ok(object())

    def request_ok(**kwargs: object) -> Result[str, ReleaseError]:
        return Ok("ms-creq")

    monkeypatch.setattr(content_confirm_step, "assess_content_bom", bom_aligned)
    monkeypatch.setattr(content_confirm_step, "resolve_content_release_plan", plan_ok)
    monkeypatch.setattr(content_confirm_step, "ensure_open_control_clean", clean_ok)
    monkeypatch.setattr(content_confirm_step, "assert_release_remote_coherence", _coherence_ok)
    monkeypatch.setattr(content_confirm_step, "prepare_content_release", prepare_ok)
    monkeypatch.setattr(content_confirm_step, "dispatch_publish_request_id", request_ok)
    monkeypatch.setattr(content_confirm_step, "publish_prepared_content_release", recorder)

    result = run_content_confirm_step(
        deps=_content_deps(deps),
        workspace_root=Path("/tmp/ws"),
        console=MockConsole(),
        watch=True,
        dry_run=False,
        session=_content_session(),
        release_repos=(),
    )

    assert isinstance(result, Ok)
    assert deps.saved[0].pending_request_id == "ms-creq"
    assert recorder.request_ids == ["ms-creq"]


def test_pending_persisted_before_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    deps = _FakeDeps()
    recorder = _prepare_confirm_step(monkeypatch, deps)

    result = run_app_confirm_step(
        session=_session(),
        workspace_root=Path("/tmp/ws"),
        console=MockConsole(),
        watch=True,
        dry_run=False,
        app_release_repo=config.APP_RELEASE_REPO,
        deps=_deps(deps),
    )

    assert isinstance(result, Ok)
    assert deps.calls == ["save"]
    assert deps.saved[0].pending_request_id == "ms-req123"
    assert recorder.pending_seen == ["ms-req123"]
    assert recorder.request_ids == ["ms-req123"]


def test_save_failure_blocks_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    deps = _FakeDeps(fail_save=True)
    recorder = _prepare_confirm_step(monkeypatch, deps)

    result = run_app_confirm_step(
        session=_session(),
        workspace_root=Path("/tmp/ws"),
        console=MockConsole(),
        watch=True,
        dry_run=False,
        app_release_repo=config.APP_RELEASE_REPO,
        deps=_deps(deps),
    )

    assert isinstance(result, Err)
    assert recorder.request_ids == []


class _RemoteCrash(RuntimeError):
    pass


class _GitHub:
    """Process-boundary fake: real dispatch, candidate and reconciliation code."""

    def __init__(
        self, *, candidate_fails: bool = False, crash: bool = True, timeout: bool = False
    ) -> None:
        self.head = _HEAD
        self.run_head = _HEAD
        self.candidate_fails = candidate_fails
        self.crash = crash
        self.timeout = timeout
        self.dispatches: list[tuple[str, dict[str, str]]] = []
        self.markers: dict[str, int] = {}
        self.released = False
        self.workflow = config.APP_RELEASE_WORKFLOW

    def run(
        self, cmd: list[str], cwd: Path, env: dict[str, str] | None = None,
        *, timeout: float | None = None,
    ) -> Result[str, ProcessError]:
        if cmd[1:3] == ["workflow", "run"]:
            inputs = dict(cmd[i + 1].split("=", 1) for i, arg in enumerate(cmd) if arg == "-f")
            self.dispatches.append((cmd[3], inputs))
            is_release = cmd[3] == self.workflow
            self.markers[inputs["request_id"]] = 42 if is_release else 41
            if is_release:
                self.released = True
                self.run_head = self.head
                if self.crash:
                    raise _RemoteCrash("accepted remotely; client interrupted before response")
                if self.timeout:
                    return Err(ProcessError(tuple(cmd), -1, "", "dispatch timed out"))
            return Ok("")
        if cmd[1:3] == ["release", "download"]:
            return Err(ProcessError(tuple(cmd), 1, "", "release not found"))
        if cmd[1:3] == ["release", "view"]:
            if self.released and not cmd[3].startswith("rc-"):
                return Ok(json.dumps({"tagName": cmd[3]}))
            return Err(ProcessError(tuple(cmd), 1, "", "release not found"))
        if cmd[1:3] == ["run", "view"]:
            failed = cmd[3] == "41" and self.candidate_fails
            return Ok(json.dumps({
                "status": "completed", "conclusion": "failure" if failed else "success",
                "jobs": [],
            }))
        if cmd[1] == "api":
            endpoint = cmd[2]
            if "/commits/" in endpoint:
                return Ok(json.dumps({"sha": self.head}))
            if "/actions/artifacts?" in endpoint:
                artifacts = [
                    {"name": f"dispatch-{request}", "workflow_run": {"id": run}}
                    for request, run in self.markers.items()
                    if endpoint.endswith(f"name=dispatch-{request}")
                ]
                return Ok(json.dumps({"artifacts": artifacts, "total_count": len(artifacts)}))
            if "/actions/runs/" in endpoint:
                return Ok(json.dumps({
                    **_run_payload("completed", "success"),
                    "head_sha": self.run_head,
                    "path": f".github/workflows/{self.workflow}",
                }))
        raise AssertionError(f"unexpected external call: {cmd}")


class _OrchestratedAppDeps(_RealStoreDeps):
    publish_app_release = staticmethod(publish_app_release)

    def prepare_app_pr(self, **kwargs: object) -> Result[AppPrepareResult, ReleaseError]:
        # Model the remote merge: its SHA differs from the selected base commit.
        return Ok(AppPrepareResult(
            source_sha="d" * 40,
            pr=PrMergeOutcome(kind="merged_pr", url="https://example.test/pr/1", label="merged"),
        ))

    def print_notes_status(self, **kwargs: object) -> None:
        pass


def _run_real_app(
    workspace: Path, session: AppReleaseSession
) -> Result[StepOutcome[AppReleaseSession], ReleaseError]:
    deps = _OrchestratedAppDeps(workspace=workspace)
    return run_app_confirm_step(
        session=session, workspace_root=workspace, console=MockConsole(), watch=True,
        dry_run=False, app_release_repo=config.APP_RELEASE_REPO, deps=_deps(deps),
    )


def _external_preflight_ok(monkeypatch: pytest.MonkeyPatch, github: _GitHub) -> None:
    monkeypatch.setattr(gh_base, "run_process", github.run)
    # Repository/CI checks are independent of the publication transaction.
    monkeypatch.setattr(app_confirm_step, "refresh_app_session_tooling", _identity_refresh)
    monkeypatch.setattr(app_confirm_step, "assert_release_remote_coherence", _coherence_ok)


@pytest.mark.parametrize("interruption", ["crash", "timeout", "cleanup_failure"])
def test_real_dispatch_crash_reload_reconcile_and_terminal_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, interruption: str,
) -> None:
    github = _GitHub(crash=interruption == "crash", timeout=interruption == "timeout")
    _external_preflight_ok(monkeypatch, github)
    with monkeypatch.context() as failure:
        if interruption == "cleanup_failure":
            original_unlink = Path.unlink

            def denied_unlink(path: Path, missing_ok: bool = False) -> None:
                if path.name == "app-release.json":
                    raise PermissionError("injected session cleanup failure")
                original_unlink(path, missing_ok=missing_ok)

            failure.setattr(Path, "unlink", denied_unlink)
        if interruption == "crash":
            with pytest.raises(_RemoteCrash):
                _run_real_app(tmp_path, _session())
        else:
            assert isinstance(_run_real_app(tmp_path, _session()), Err)

    loaded = load_app_session(workspace_root=tmp_path)
    assert isinstance(loaded, Ok) and loaded.value is not None
    pending = loaded.value
    assert pending.pending_source_sha == "d" * 40  # merged SHA, not base SHA
    release_inputs = github.dispatches[-1][1]
    assert release_inputs["source_sha"] == pending.pending_source_sha
    assert release_inputs["request_id"] == pending.pending_request_id
    assert dict(pending.pending_inputs) == {
        key: value for key, value in release_inputs.items() if key != "request_id"
    }

    github.head = "e" * 40  # main moved; identity must use the historical run
    resumed = _run_real_app(tmp_path, pending)
    assert isinstance(resumed, Ok) and resumed.value is FINISH
    assert len(github.dispatches) == 2  # one candidate + one release
    # Subsequent bootstrap sees no unfinished operation to resume/re-publish.
    assert load_app_session(workspace_root=tmp_path) == Ok(None)


def test_candidate_failure_leaves_no_release_intention(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    github = _GitHub(candidate_fails=True)
    _external_preflight_ok(monkeypatch, github)
    assert isinstance(save_app_session(workspace_root=tmp_path, session=_session()), Ok)
    result = _run_real_app(tmp_path, _session())
    assert isinstance(result, Err)
    loaded = load_app_session(workspace_root=tmp_path)
    assert isinstance(loaded, Ok) and loaded.value is not None
    assert loaded.value.pending_kind is None
    assert [workflow for workflow, _ in github.dispatches] == [config.APP_CANDIDATE_WORKFLOW]


def test_pending_write_failure_blocks_real_release_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    github = _GitHub()
    _external_preflight_ok(monkeypatch, github)
    from ms.release.flow.guided import session_store

    def denied_write(*args: object, **kwargs: object) -> None:
        raise PermissionError("injected persistence failure")

    monkeypatch.setattr(session_store, "atomic_write_text", denied_write)
    assert isinstance(_run_real_app(tmp_path, _session()), Err)
    assert [workflow for workflow, _ in github.dispatches] == [config.APP_CANDIDATE_WORKFLOW]
    assert load_app_session(workspace_root=tmp_path) == Ok(None)


def test_delayed_marker_uses_bounded_attempts_without_real_sleep(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    delays: list[float] = []

    def eventually_visible(
        *, workspace_root: Path, repo_slug: str, request_id: str,
    ) -> Result[WorkflowRunResolution | None, ReleaseError]:
        calls.append(request_id)
        if len(calls) < 3:
            return Ok(None)
        return _run_found(workspace_root=workspace_root, repo_slug=repo_slug, request_id=request_id)

    monkeypatch.setattr(pending_op, "find_dispatched_run", eventually_visible)
    monkeypatch.setattr(pending_op, "sleep", delays.append)
    monkeypatch.setattr(pending_op, "gh_api_json", _run_status_success)
    monkeypatch.setattr(pending_op, "release_exists_by_tag", _released)
    result = pending_op.reconcile_pending_op(
        workspace_root=Path("unused"), repo=config.APP_REPO_SLUG,
        workflow_file=config.APP_RELEASE_WORKFLOW, tag="app-v1.0.0", request_id=_REQUEST,
        source_sha=_SHA, tooling_sha=_TOOLING, inputs=_INPUTS, attempts=3, delay_seconds=5,
    )
    assert isinstance(result, Ok) and result.value.state == "completed"
    assert calls == [_REQUEST] * 3
    assert delays == [5, 5]


@pytest.mark.parametrize("field", ["source_sha", "tooling_sha", "head_sha", "workflow"])
def test_real_reconciliation_rejects_mismatched_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str,
) -> None:
    github = _GitHub()
    _external_preflight_ok(monkeypatch, github)
    with pytest.raises(_RemoteCrash):
        _run_real_app(tmp_path, _session())
    loaded = load_app_session(workspace_root=tmp_path)
    assert isinstance(loaded, Ok) and loaded.value is not None
    session = loaded.value
    if field == "source_sha":
        session = replace(session, pending_source_sha="f" * 40)
    elif field == "tooling_sha":
        session = replace(session, pending_tooling_sha="f" * 40)
    elif field == "head_sha":
        github.run_head = "f" * 40
    else:
        github.workflow = "other.yml"
    result = _run_real_app(tmp_path, session)
    assert isinstance(result, Err)
    assert "undetermined" in result.error.message
    assert len(github.dispatches) == 2
    assert load_app_session(workspace_root=tmp_path) == loaded


def test_content_completion_removes_session_from_disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = (("channel", "beta"), ("tag", "content-v1"),
              ("spec_path", "releases/beta/content-v1.json"), ("tooling_sha", _TOOLING))
    request = dispatch_request_id(
        repo_slug=config.DIST_REPO_SLUG, workflow_file=config.DIST_PUBLISH_WORKFLOW,
        ref=_HEAD, inputs=inputs,
    )
    session = replace(_pending_content_session(), pending_request_id=request, pending_inputs=inputs)
    assert isinstance(save_content_session(workspace_root=tmp_path, session=session), Ok)
    github = _GitHub()
    github.workflow = config.DIST_PUBLISH_WORKFLOW
    github.markers[request] = 42
    github.released = True
    monkeypatch.setattr(gh_base, "run_process", github.run)

    class ContentDeps(_FakeDeps):
        def clear_session(self) -> Result[None, ReleaseError]:
            return clear_content_session(workspace_root=tmp_path)

    loaded = load_content_session(workspace_root=tmp_path)
    assert isinstance(loaded, Ok) and loaded.value is not None
    result = run_content_confirm_step(
        deps=_content_deps(ContentDeps()), workspace_root=tmp_path, console=MockConsole(),
        watch=True, dry_run=False, session=loaded.value, release_repos=(),
    )
    assert isinstance(result, Ok) and result.value is FINISH
    assert load_content_session(workspace_root=tmp_path) == Ok(None)
    assert github.dispatches == []
