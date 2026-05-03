from __future__ import annotations

from pathlib import Path

from pytest import MonkeyPatch

from ms.core.result import Err, Ok
from ms.git.repository import GitStatus
from ms.output.console import MockConsole
from ms.release.domain.diagnostics import RepoReadiness
from ms.release.domain.models import PinnedRepo, ReleaseRepo, ReleaseTooling
from ms.release.errors import ReleaseError
from ms.release.flow.remote_coherence import assert_release_remote_coherence


def _repo() -> ReleaseRepo:
    return ReleaseRepo(
        id="app",
        slug="owner/app",
        ref="main",
        required_ci_workflow_file=".github/workflows/ci.yml",
    )


def test_assert_release_remote_coherence_reports_eligible_inputs(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    import ms.release.flow.remote_coherence as coherence

    def fake_get_ref_head_sha(**kwargs: object) -> Ok[str]:
        repo = kwargs["repo"]
        return Ok("f" * 40 if repo == "petitechose-midi-studio/ms-dev-env" else "a" * 40)

    def fake_local_head_sha(**_: object) -> str:
        return "f" * 40

    def fake_ensure_release_tooling_on_main(**_: object) -> Ok[None]:
        return Ok(None)

    def fake_probe_release_readiness(**kwargs: object) -> Ok[RepoReadiness]:
        repo = kwargs["repo"]
        assert isinstance(repo, ReleaseRepo)
        return Ok(
            RepoReadiness(
                repo=repo,
                ref="main",
                local_path=tmp_path / "app",
                local_exists=True,
                status=GitStatus(branch="main", upstream="origin/main"),
                local_head_sha="a" * 40,
                remote_head_sha="a" * 40,
                head_green=True,
                error=None,
            )
        )

    monkeypatch.setattr(coherence, "get_ref_head_sha", fake_get_ref_head_sha)
    monkeypatch.setattr(coherence, "_local_head_sha", fake_local_head_sha)
    monkeypatch.setattr(
        coherence,
        "ensure_release_tooling_on_main",
        fake_ensure_release_tooling_on_main,
    )
    monkeypatch.setattr(coherence, "probe_release_readiness", fake_probe_release_readiness)

    def fake_is_commit_fetchable(**_: object) -> Ok[bool]:
        return Ok(True)

    def fake_is_ci_green_for_sha(**_: object) -> Ok[bool]:
        return Ok(True)

    monkeypatch.setattr(coherence, "is_commit_fetchable", fake_is_commit_fetchable)
    monkeypatch.setattr(coherence, "is_ci_green_for_sha", fake_is_ci_green_for_sha)

    report = assert_release_remote_coherence(
        workspace_root=tmp_path,
        console=MockConsole(),
        pinned=(PinnedRepo(repo=_repo(), sha="a" * 40),),
        tooling=ReleaseTooling(
            repo="petitechose-midi-studio/ms-dev-env",
            ref="main",
            sha="f" * 40,
        ),
        dry_run=False,
    )

    assert isinstance(report, Ok)
    assert report.value.is_eligible


def test_assert_release_remote_coherence_blocks_unreachable_tooling(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    import ms.release.flow.remote_coherence as coherence

    def fake_get_ref_head_sha(**_: object) -> Ok[str]:
        return Ok("1" * 40)

    def fake_local_head_sha(**_: object) -> str:
        return "2" * 40

    def fake_ensure_release_tooling_on_main(**_: object) -> Err[ReleaseError]:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message="release tooling SHA is not reachable from ms-dev-env main",
                hint="merge tooling first",
            )
        )

    monkeypatch.setattr(coherence, "get_ref_head_sha", fake_get_ref_head_sha)
    monkeypatch.setattr(coherence, "_local_head_sha", fake_local_head_sha)
    monkeypatch.setattr(
        coherence,
        "ensure_release_tooling_on_main",
        fake_ensure_release_tooling_on_main,
    )

    report = assert_release_remote_coherence(
        workspace_root=tmp_path,
        console=MockConsole(),
        pinned=(),
        tooling=ReleaseTooling(
            repo="petitechose-midi-studio/ms-dev-env",
            ref="main",
            sha="2" * 40,
        ),
        dry_run=False,
    )

    assert isinstance(report, Err)
    assert report.error.message == (
        "release remote coherence blocked: ms-dev-env - "
        "tooling SHA is not reachable from the workflow ref"
    )
    assert report.error.hint == "merge tooling first"


def test_assert_release_remote_coherence_can_reuse_prior_ci_check(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    import ms.release.flow.remote_coherence as coherence

    def fake_get_ref_head_sha(**kwargs: object) -> Ok[str]:
        repo = kwargs["repo"]
        return Ok("f" * 40 if repo == "petitechose-midi-studio/ms-dev-env" else "a" * 40)

    def fake_local_head_sha(**_: object) -> str:
        return "f" * 40

    def fake_ensure_release_tooling_on_main(**_: object) -> Ok[None]:
        return Ok(None)

    def fake_probe_release_readiness(**kwargs: object) -> Ok[RepoReadiness]:
        repo = kwargs["repo"]
        assert isinstance(repo, ReleaseRepo)
        return Ok(
            RepoReadiness(
                repo=repo,
                ref="main",
                local_path=tmp_path / "app",
                local_exists=True,
                status=GitStatus(branch="main", upstream="origin/main"),
                local_head_sha="a" * 40,
                remote_head_sha="a" * 40,
                head_green=True,
                error=None,
            )
        )

    def fake_is_commit_fetchable(**_: object) -> Ok[bool]:
        return Ok(True)

    def fake_is_ci_green_for_sha(**_: object) -> Err[ReleaseError]:
        return Err(ReleaseError(kind="workflow_failed", message="should not re-check CI"))

    monkeypatch.setattr(coherence, "get_ref_head_sha", fake_get_ref_head_sha)
    monkeypatch.setattr(coherence, "_local_head_sha", fake_local_head_sha)
    monkeypatch.setattr(
        coherence,
        "ensure_release_tooling_on_main",
        fake_ensure_release_tooling_on_main,
    )
    monkeypatch.setattr(coherence, "probe_release_readiness", fake_probe_release_readiness)
    monkeypatch.setattr(coherence, "is_commit_fetchable", fake_is_commit_fetchable)
    monkeypatch.setattr(coherence, "is_ci_green_for_sha", fake_is_ci_green_for_sha)

    report = assert_release_remote_coherence(
        workspace_root=tmp_path,
        console=MockConsole(),
        pinned=(PinnedRepo(repo=_repo(), sha="a" * 40),),
        tooling=ReleaseTooling(
            repo="petitechose-midi-studio/ms-dev-env",
            ref="main",
            sha="f" * 40,
        ),
        dry_run=False,
        verify_ci=False,
    )

    assert isinstance(report, Ok)
    assert report.value.is_eligible
    assert "CI already checked" in report.value.items[1].detail
