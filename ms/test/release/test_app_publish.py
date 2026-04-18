from __future__ import annotations

from pathlib import Path

from pytest import MonkeyPatch

from ms.core.result import Err, Ok
from ms.output.console import MockConsole
from ms.release.errors import ReleaseError
from ms.release.flow.app_publish import (
    AppCandidateState,
    AppPublishResult,
    EnsuredAppCandidate,
    ensure_app_candidate,
    publish_app_release,
)
from ms.release.infra.github.workflows import WorkflowRun


def test_ensure_app_candidate_reuses_ready_candidate(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    import ms.release.flow.app_publish as app_publish

    dispatch_calls = {"count": 0}

    def fake_probe_app_candidate(
        *, workspace_root: Path, source_sha: str, tooling_sha: str
    ) -> Ok[AppCandidateState]:
        del workspace_root, source_sha, tooling_sha
        return Ok(AppCandidateState.READY)

    def fake_dispatch_app_candidate_workflow(**kwargs: object) -> Ok[WorkflowRun]:
        del kwargs
        dispatch_calls["count"] += 1
        return Ok(WorkflowRun(id=41, url="https://example.test/run/41", request_id="req-41"))

    monkeypatch.setattr(app_publish, "_probe_app_candidate", fake_probe_app_candidate)
    monkeypatch.setattr(
        app_publish,
        "dispatch_app_candidate_workflow",
        fake_dispatch_app_candidate_workflow,
    )

    ensured = ensure_app_candidate(
        workspace_root=tmp_path,
        source_sha="a" * 40,
        tooling_sha="f" * 40,
        console=MockConsole(),
        dry_run=False,
    )

    assert isinstance(ensured, Ok)
    assert dispatch_calls["count"] == 0
    assert ensured.value.run is None
    assert ensured.value.candidate_tag == "rc-" + ("a" * 40) + "-tooling-" + ("f" * 40)


def test_ensure_app_candidate_waits_for_incomplete_candidate_before_dispatch(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    import ms.release.flow.app_publish as app_publish

    probes = iter(
        (
            AppCandidateState.INCOMPLETE,
            AppCandidateState.INCOMPLETE,
            AppCandidateState.READY,
        )
    )
    dispatch_calls = {"count": 0}

    def fake_probe_app_candidate(
        *, workspace_root: Path, source_sha: str, tooling_sha: str
    ) -> Ok[AppCandidateState]:
        del workspace_root, source_sha, tooling_sha
        return Ok(next(probes))

    def fake_dispatch_app_candidate_workflow(**kwargs: object) -> Ok[WorkflowRun]:
        del kwargs
        dispatch_calls["count"] += 1
        return Ok(WorkflowRun(id=42, url="https://example.test/run/42", request_id="req-42"))

    def fake_sleep(seconds: float) -> None:
        del seconds

    monkeypatch.setattr(app_publish, "_probe_app_candidate", fake_probe_app_candidate)
    monkeypatch.setattr(
        app_publish,
        "dispatch_app_candidate_workflow",
        fake_dispatch_app_candidate_workflow,
    )
    monkeypatch.setattr(app_publish, "_INCOMPLETE_PROBE_ATTEMPTS", 3)
    monkeypatch.setattr(app_publish, "_INCOMPLETE_PROBE_DELAY_SECONDS", 0.0)
    monkeypatch.setattr(app_publish, "sleep", fake_sleep)

    ensured = ensure_app_candidate(
        workspace_root=tmp_path,
        source_sha="a" * 40,
        tooling_sha="f" * 40,
        console=MockConsole(),
        dry_run=False,
    )

    assert isinstance(ensured, Ok)
    assert dispatch_calls["count"] == 0
    assert ensured.value.run is None


def test_ensure_app_candidate_fails_for_invalid_candidate(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    import ms.release.flow.app_publish as app_publish

    dispatch_calls = {"count": 0}

    def fake_probe_app_candidate(
        *, workspace_root: Path, source_sha: str, tooling_sha: str
    ) -> Err[ReleaseError]:
        del workspace_root, source_sha, tooling_sha
        return Err(
            ReleaseError(
                kind="verification_failed",
                message="candidate invalid: rc-demo",
                hint="signature mismatch",
            )
        )

    def fake_dispatch_app_candidate_workflow(**kwargs: object) -> Ok[WorkflowRun]:
        del kwargs
        dispatch_calls["count"] += 1
        return Ok(WorkflowRun(id=43, url="https://example.test/run/43", request_id="req-43"))

    monkeypatch.setattr(app_publish, "_probe_app_candidate", fake_probe_app_candidate)
    monkeypatch.setattr(
        app_publish,
        "dispatch_app_candidate_workflow",
        fake_dispatch_app_candidate_workflow,
    )

    ensured = ensure_app_candidate(
        workspace_root=tmp_path,
        source_sha="a" * 40,
        tooling_sha="f" * 40,
        console=MockConsole(),
        dry_run=False,
    )

    assert isinstance(ensured, Err)
    assert ensured.error.kind == "verification_failed"
    assert dispatch_calls["count"] == 0


def test_publish_app_release_reuses_ready_candidate_without_candidate_watch(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    import ms.release.flow.app_publish as app_publish

    watched_runs: list[int] = []

    def fake_ensure_app_candidate(**kwargs: object) -> Ok[EnsuredAppCandidate]:
        del kwargs
        return Ok(
            EnsuredAppCandidate(
                candidate_tag="rc-" + ("b" * 40) + "-tooling-" + ("f" * 40),
                release_url="https://github.com/petitechose-midi-studio/ms-manager/releases/tag/demo",
                run=None,
            )
        )

    def fake_dispatch_app_release_workflow(**kwargs: object) -> Ok[WorkflowRun]:
        del kwargs
        return Ok(
            WorkflowRun(
                id=51,
                url="https://example.test/run/51",
                request_id="req-51",
            )
        )

    def fake_watch_run(
        *,
        workspace_root: Path,
        run_id: int,
        repo_slug: str,
        console: MockConsole,
        dry_run: bool,
    ) -> Ok[None]:
        del workspace_root, repo_slug, console, dry_run
        watched_runs.append(run_id)
        return Ok(None)

    monkeypatch.setattr(app_publish, "ensure_app_candidate", fake_ensure_app_candidate)
    monkeypatch.setattr(
        app_publish,
        "dispatch_app_release_workflow",
        fake_dispatch_app_release_workflow,
    )
    monkeypatch.setattr(app_publish, "watch_run", fake_watch_run)

    published = publish_app_release(
        workspace_root=tmp_path,
        console=MockConsole(),
        tag="v1.2.3",
        source_sha="b" * 40,
        tooling_sha="f" * 40,
        notes_markdown=None,
        notes_source_path=None,
        watch=True,
        dry_run=False,
    )

    assert isinstance(published, Ok)
    assert isinstance(published.value, AppPublishResult)
    assert watched_runs == [51]
    assert published.value.candidate.run is None
    assert published.value.release.url == "https://example.test/run/51"


def test_publish_app_release_watches_candidate_run_when_dispatched(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    import ms.release.flow.app_publish as app_publish

    watched_runs: list[int] = []

    def fake_ensure_app_candidate(**kwargs: object) -> Ok[EnsuredAppCandidate]:
        del kwargs
        return Ok(
            EnsuredAppCandidate(
                candidate_tag="rc-" + ("b" * 40) + "-tooling-" + ("f" * 40),
                release_url="https://github.com/petitechose-midi-studio/ms-manager/releases/tag/demo",
                run=WorkflowRun(
                    id=61,
                    url="https://example.test/run/61",
                    request_id="req-61",
                ),
            )
        )

    def fake_dispatch_app_release_workflow(**kwargs: object) -> Ok[WorkflowRun]:
        del kwargs
        return Ok(
            WorkflowRun(
                id=62,
                url="https://example.test/run/62",
                request_id="req-62",
            )
        )

    def fake_watch_run(
        *,
        workspace_root: Path,
        run_id: int,
        repo_slug: str,
        console: MockConsole,
        dry_run: bool,
    ) -> Ok[None]:
        del workspace_root, repo_slug, console, dry_run
        watched_runs.append(run_id)
        return Ok(None)

    monkeypatch.setattr(app_publish, "ensure_app_candidate", fake_ensure_app_candidate)
    monkeypatch.setattr(
        app_publish,
        "dispatch_app_release_workflow",
        fake_dispatch_app_release_workflow,
    )
    monkeypatch.setattr(app_publish, "watch_run", fake_watch_run)

    published = publish_app_release(
        workspace_root=tmp_path,
        console=MockConsole(),
        tag="v1.2.3",
        source_sha="b" * 40,
        tooling_sha="f" * 40,
        notes_markdown="custom notes",
        notes_source_path="/tmp/notes.md",
        watch=True,
        dry_run=False,
    )

    assert isinstance(published, Ok)
    assert watched_runs == [61, 62]
    assert published.value.candidate.run is not None
    assert published.value.candidate.run.url == "https://example.test/run/61"
    assert published.value.release.url == "https://example.test/run/62"
