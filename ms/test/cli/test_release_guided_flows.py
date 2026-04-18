from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from ms.cli.selector import SelectorResult
from ms.core.result import Ok
from ms.output.console import MockConsole
from ms.release.domain.models import (
    AppReleasePlan,
    PinnedRepo,
    ReleaseBump,
    ReleaseChannel,
    ReleasePlan,
    ReleaseTooling,
)
from ms.release.domain.open_control_models import (
    BomPromotionPlan,
    BomStateComparison,
    OcSdkLoad,
    OcSdkLock,
    OcSdkMismatch,
    OcSdkPin,
    OpenControlPreflightReport,
)
from ms.release.flow.app_prepare import AppPrepareResult
from ms.release.flow.bom_promotion import BomPromotionResult
from ms.release.flow.content_candidates import (
    ContentCandidateAssessment,
    ContentCandidateState,
    ContentCandidateTarget,
)
from ms.release.flow.guided.sessions import (
    AppReleaseSession,
    ContentReleaseSession,
    new_app_session,
    new_content_session,
)
from ms.release.flow.pr_outcome import PrMergeOutcome


def _sel(value: str, index: int = 0) -> SelectorResult[str]:
    return SelectorResult(action="select", value=value, index=index)


def _oc_sdk_lock(*, version: str) -> OcSdkLock:
    return OcSdkLock(
        version=version,
        pins=(
            OcSdkPin(repo="framework", sha="1" * 40),
            OcSdkPin(repo="note", sha="2" * 40),
            OcSdkPin(repo="hal-common", sha="3" * 40),
            OcSdkPin(repo="hal-teensy", sha="4" * 40),
            OcSdkPin(repo="ui-lvgl", sha="5" * 40),
            OcSdkPin(repo="ui-lvgl-components", sha="6" * 40),
        ),
    )


def _tooling() -> ReleaseTooling:
    return ReleaseTooling(
        repo="petitechose-midi-studio/ms-dev-env",
        ref="main",
        sha="f" * 40,
    )


def _candidate_assessments(*, available: bool) -> tuple[ContentCandidateAssessment, ...]:
    targets = (
        ContentCandidateTarget(
            id="loader-binaries",
            label="loader",
            producer_id="loader-binaries",
            repo_slug="petitechose-midi-studio/loader",
            workflow_file=".github/workflows/candidate.yml",
            ref="main",
            candidate_tag="rc-loader",
            workflow_inputs=(),
            expected_input_repos=(),
            public_key_b64="pk",
        ),
        ContentCandidateTarget(
            id="core-default-firmware",
            label="core firmware",
            producer_id="core-default-firmware",
            repo_slug="petitechose-midi-studio/core",
            workflow_file=".github/workflows/candidate.yml",
            ref="main",
            candidate_tag="rc-core",
            workflow_inputs=(),
            expected_input_repos=(),
            public_key_b64="pk",
        ),
    )
    return tuple(
        ContentCandidateAssessment(
            target=target,
            state=ContentCandidateState.READY if available else ContentCandidateState.MISSING,
        )
        for target in targets
    )


def test_guided_app_happy_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import ms.cli.release_guided_app as app

    session = new_app_session(created_by="alice", notes_path=None)
    session = replace(
        session, notes_path="/tmp/notes.md", notes_markdown="hello notes", notes_sha256="f" * 64
    )

    def fake_preflight(*args: object, **kwargs: object):
        return Ok("alice")

    def fake_bootstrap(*args: object, **kwargs: object):
        return Ok(session)

    def fake_save_state(*args: object, **kwargs: object):
        s = kwargs.get("session")
        assert isinstance(s, AppReleaseSession)
        return Ok(s)

    def fake_channel(*args: object, **kwargs: object):
        return _sel("stable")

    def fake_bump(*args: object, **kwargs: object):
        return _sel("patch")

    def fake_green(*args: object, **kwargs: object):
        return Ok(_sel("a" * 40))

    def fake_plan(*args: object, **kwargs: object):
        return Ok(
            AppReleasePlan(
                channel="stable",
                tag="v1.2.3",
                version="1.2.3",
                pinned=(),
                tooling=_tooling(),
                title="release(app): v1.2.3",
            )
        )

    summary_calls = {"count": 0}

    def fake_select_one(*args: object, **kwargs: object) -> SelectorResult[str]:
        title = str(kwargs.get("title", ""))
        if title == "Release Tag":
            return _sel("accept")
        if title == "App Release Summary":
            summary_calls["count"] += 1
            return _sel("start", index=5)
        raise AssertionError(f"unexpected selector title: {title}")

    def fake_confirm(*args: object, **kwargs: object) -> bool:
        return True

    def fake_ci_green(*args: object, **kwargs: object):
        return Ok(None)

    def fake_prepare(*args: object, **kwargs: object):
        return Ok(
            AppPrepareResult(
                pr=PrMergeOutcome(
                    kind="merged_pr",
                    url="https://example/pr/1",
                    label="https://example/pr/1",
                ),
                source_sha="b" * 40,
            )
        )

    published: dict[str, object] = {}

    def fake_publish(*args: object, **kwargs: object):
        published.update(kwargs)
        return Ok(("https://example/candidate", "https://example/release"))

    def fake_clear(*args: object, **kwargs: object):
        return Ok(None)

    monkeypatch.setattr(app, "preflight_with_permission", fake_preflight)
    monkeypatch.setattr(app, "bootstrap_app_session", fake_bootstrap)
    monkeypatch.setattr(app, "save_app_state", fake_save_state)
    monkeypatch.setattr(app, "select_channel", fake_channel)
    monkeypatch.setattr(app, "select_bump", fake_bump)
    monkeypatch.setattr(app, "select_green_commit", fake_green)
    monkeypatch.setattr(app, "plan_app_release", fake_plan)
    monkeypatch.setattr(app, "select_one", fake_select_one)
    monkeypatch.setattr(app, "confirm_yn", fake_confirm)
    monkeypatch.setattr(app, "ensure_ci_green", fake_ci_green)
    monkeypatch.setattr(app, "prepare_app_pr", fake_prepare)
    monkeypatch.setattr(app, "publish_app_release", fake_publish)
    monkeypatch.setattr(app, "clear_app_session", fake_clear)

    result = app.run_guided_app_release(
        workspace_root=tmp_path,
        console=MockConsole(),
        notes_file=None,
        watch=False,
        dry_run=True,
    )

    assert isinstance(result, Ok)
    assert summary_calls["count"] == 1
    assert published["tag"] == "v1.2.3"
    assert published["source_sha"] == "b" * 40
    assert published["notes_markdown"] == "hello notes"
    assert published["notes_source_path"] == "/tmp/notes.md"


def test_guided_app_summary_edit_recomputes_tag(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import ms.cli.release_guided_app as app

    session = new_app_session(created_by="alice", notes_path=None)

    def fake_preflight(*args: object, **kwargs: object):
        return Ok("alice")

    def fake_bootstrap(*args: object, **kwargs: object):
        return Ok(session)

    def fake_save_state(*args: object, **kwargs: object):
        s = kwargs.get("session")
        assert isinstance(s, AppReleaseSession)
        return Ok(s)

    channel_calls = {"count": 0}

    def fake_channel(*args: object, **kwargs: object):
        channel_calls["count"] += 1
        return _sel("stable")

    def fake_bump(*args: object, **kwargs: object):
        return _sel("patch")

    def fake_green(*args: object, **kwargs: object):
        return Ok(_sel("a" * 40))

    tag_calls = {"count": 0}

    def fake_plan(*args: object, **kwargs: object):
        tag_calls["count"] += 1
        return Ok(
            AppReleasePlan(
                channel="stable",
                tag="v1.2.3",
                version="1.2.3",
                pinned=(),
                tooling=_tooling(),
                title="release(app): v1.2.3",
            )
        )

    summary_seq = [_sel("channel", index=0), _sel("start", index=5), _sel("start", index=5)]
    tag_seq = [_sel("accept"), _sel("accept")]

    def fake_select_one(*args: object, **kwargs: object) -> SelectorResult[str]:
        title = str(kwargs.get("title", ""))
        if title == "Release Tag":
            return tag_seq.pop(0)
        if title == "App Release Summary":
            return summary_seq.pop(0)
        raise AssertionError(f"unexpected selector title: {title}")

    def fake_confirm(*args: object, **kwargs: object) -> bool:
        return True

    def fake_ci_green(*args: object, **kwargs: object):
        return Ok(None)

    def fake_prepare(*args: object, **kwargs: object):
        return Ok(
            AppPrepareResult(
                pr=PrMergeOutcome(
                    kind="merged_pr",
                    url="https://example/pr/2",
                    label="https://example/pr/2",
                ),
                source_sha="b" * 40,
            )
        )

    def fake_publish(*args: object, **kwargs: object):
        return Ok(("c", "r"))

    def fake_clear(*args: object, **kwargs: object):
        return Ok(None)

    monkeypatch.setattr(app, "preflight_with_permission", fake_preflight)
    monkeypatch.setattr(app, "bootstrap_app_session", fake_bootstrap)
    monkeypatch.setattr(app, "save_app_state", fake_save_state)
    monkeypatch.setattr(app, "select_channel", fake_channel)
    monkeypatch.setattr(app, "select_bump", fake_bump)
    monkeypatch.setattr(app, "select_green_commit", fake_green)
    monkeypatch.setattr(app, "plan_app_release", fake_plan)
    monkeypatch.setattr(app, "select_one", fake_select_one)
    monkeypatch.setattr(app, "confirm_yn", fake_confirm)
    monkeypatch.setattr(app, "ensure_ci_green", fake_ci_green)
    monkeypatch.setattr(app, "prepare_app_pr", fake_prepare)
    monkeypatch.setattr(app, "publish_app_release", fake_publish)
    monkeypatch.setattr(app, "clear_app_session", fake_clear)

    result = app.run_guided_app_release(
        workspace_root=tmp_path,
        console=MockConsole(),
        notes_file=None,
        watch=False,
        dry_run=True,
    )

    assert isinstance(result, Ok)
    assert channel_calls["count"] == 2
    assert tag_calls["count"] == 2


def test_guided_content_happy_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import ms.cli.release_guided_content as content

    session = new_content_session(created_by="alice", notes_path=None)

    def fake_preflight(*args: object, **kwargs: object):
        return Ok("alice")

    def fake_bootstrap(*args: object, **kwargs: object):
        return Ok(session)

    def fake_save_state(*args: object, **kwargs: object):
        s = kwargs.get("session")
        assert isinstance(s, ContentReleaseSession)
        return Ok(s)

    def fake_channel(*args: object, **kwargs: object):
        return _sel("stable")

    def fake_bump(*args: object, **kwargs: object):
        return _sel("patch")

    select_calls: list[str] = []
    sha_map = {
        "petitechose-midi-studio/loader": "1" * 40,
        "open-control/bridge": "2" * 40,
        "petitechose-midi-studio/core": "3" * 40,
        "petitechose-midi-studio/plugin-bitwig": "4" * 40,
    }

    def fake_green(*args: object, **kwargs: object):
        repo = str(kwargs["repo_slug"])
        select_calls.append(repo)
        return Ok(_sel(sha_map[repo]))

    def fake_plan(
        *,
        workspace_root: Path,
        channel: ReleaseChannel,
        bump: ReleaseBump,
        tag_override: str | None,
        pinned: tuple[PinnedRepo, ...],
    ) -> Ok[ReleasePlan]:
        del workspace_root, channel, bump, tag_override, pinned
        return Ok(
            ReleasePlan(
                channel="stable",
                tag="v9.9.9",
                pinned=(),
                tooling=_tooling(),
                spec_path="release-specs/v9.9.9.json",
                notes_path=None,
                title="release(content): v9.9.9",
            )
        )

    def fake_select_one(*args: object, **kwargs: object) -> SelectorResult[str]:
        title = str(kwargs.get("title", ""))
        if title == "Content Release Tag":
            return _sel("accept")
        if title == "Content Release Summary":
            return _sel("start", index=10)
        if title == "Content Release Candidates":
            return _sel("continue", index=2)
        raise AssertionError(f"unexpected selector title: {title}")

    def fake_confirm(*args: object, **kwargs: object) -> bool:
        return True

    def fake_ci_green(*args: object, **kwargs: object):
        return Ok(None)

    def fake_ensure_content_candidates(*args: object, **kwargs: object):
        return Ok(())

    def fake_assess_content_candidates(*args: object, **kwargs: object):
        return Ok(_candidate_assessments(available=True))

    def fake_open_control(*args: object, **kwargs: object) -> OpenControlPreflightReport:
        return OpenControlPreflightReport(
            oc_sdk=OcSdkLoad(lock=_oc_sdk_lock(version="0.1.3"), source="git", error=None),
            repos=(),
            mismatches=(),
            derived_lock=None,
            comparison=None,
        )

    def fake_prepare(*args: object, **kwargs: object):
        return Ok(
            PrMergeOutcome(
                kind="merged_pr", url="https://example/pr/3", label="https://example/pr/3"
            )
        )

    published: dict[str, object] = {}

    def fake_publish(*args: object, **kwargs: object):
        published.update(kwargs)
        return Ok("https://example/workflow/1")

    def fake_clear(*args: object, **kwargs: object):
        return Ok(None)

    monkeypatch.setattr(content, "preflight_with_permission", fake_preflight)
    monkeypatch.setattr(content, "bootstrap_content_session", fake_bootstrap)
    monkeypatch.setattr(content, "save_content_state", fake_save_state)
    monkeypatch.setattr(content, "select_channel", fake_channel)
    monkeypatch.setattr(content, "select_bump", fake_bump)
    monkeypatch.setattr(content, "select_green_commit", fake_green)
    monkeypatch.setattr(content, "plan_release", fake_plan)
    monkeypatch.setattr(content, "select_one", fake_select_one)
    monkeypatch.setattr(content, "confirm_yn", fake_confirm)
    monkeypatch.setattr(content, "ensure_ci_green", fake_ci_green)
    monkeypatch.setattr(content, "assess_content_candidates", fake_assess_content_candidates)
    monkeypatch.setattr(content, "ensure_content_candidates", fake_ensure_content_candidates)
    monkeypatch.setattr(content, "preflight_open_control", fake_open_control)
    monkeypatch.setattr(content, "prepare_distribution_pr", fake_prepare)
    monkeypatch.setattr(content, "publish_distribution_release", fake_publish)
    monkeypatch.setattr(content, "clear_content_session", fake_clear)

    result = content.run_guided_content_release(
        workspace_root=tmp_path,
        console=MockConsole(),
        notes_file=None,
        watch=False,
        dry_run=True,
    )

    assert isinstance(result, Ok)
    assert select_calls == [
        "petitechose-midi-studio/loader",
        "open-control/bridge",
        "petitechose-midi-studio/core",
        "petitechose-midi-studio/plugin-bitwig",
    ]
    assert "plan" in published
    plan_obj = published["plan"]
    assert isinstance(plan_obj, ReleasePlan)
    assert plan_obj.tag == "v9.9.9"


def test_guided_content_bom_promotion_updates_core_sha(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import ms.cli.release_guided_content as content

    session = new_content_session(created_by="alice", notes_path=None)

    def fake_preflight(*args: object, **kwargs: object):
        return Ok("alice")

    def fake_bootstrap(*args: object, **kwargs: object):
        return Ok(session)

    def fake_save_state(*args: object, **kwargs: object):
        s = kwargs.get("session")
        assert isinstance(s, ContentReleaseSession)
        return Ok(s)

    def fake_channel(*args: object, **kwargs: object):
        return _sel("stable")

    def fake_bump(*args: object, **kwargs: object):
        return _sel("patch")

    sha_map = {
        "petitechose-midi-studio/loader": "1" * 40,
        "open-control/bridge": "2" * 40,
        "petitechose-midi-studio/core": "3" * 40,
        "petitechose-midi-studio/plugin-bitwig": "4" * 40,
    }

    def fake_green(*args: object, **kwargs: object):
        return Ok(_sel(sha_map[str(kwargs["repo_slug"])]))

    planned_inputs: list[tuple[tuple[str, str], ...]] = []

    def fake_plan(
        *,
        workspace_root: Path,
        channel: ReleaseChannel,
        bump: ReleaseBump,
        tag_override: str | None,
        pinned: tuple[PinnedRepo, ...],
    ) -> Ok[ReleasePlan]:
        del workspace_root, channel, bump, tag_override
        pinned_snapshot = tuple((pin.repo.id, pin.sha) for pin in pinned)
        planned_inputs.append(pinned_snapshot)
        return Ok(
            ReleasePlan(
                channel="stable",
                tag="v9.9.9",
                pinned=pinned,
                tooling=_tooling(),
                spec_path="release-specs/v9.9.9.json",
                notes_path=None,
                title="release(content): v9.9.9",
            )
        )

    selections = {
        "Content Release Tag": [_sel("accept")],
        "Content Release Summary": [_sel("bom", index=6), _sel("start", index=10)],
        "Content Release Candidates": [_sel("continue", index=2)],
        "OpenControl BOM": [_sel("promote")],
    }

    def fake_select_one(*args: object, **kwargs: object) -> SelectorResult[str]:
        title = str(kwargs.get("title", ""))
        choices = selections.get(title)
        if not choices:
            raise AssertionError(f"unexpected selector title: {title}")
        return choices.pop(0)

    def fake_confirm(*args: object, **kwargs: object) -> bool:
        return True

    def fake_ci_green(*args: object, **kwargs: object):
        return Ok(None)

    def fake_ensure_content_candidates(*args: object, **kwargs: object):
        return Ok(())

    def fake_assess_content_candidates(*args: object, **kwargs: object):
        return Ok(_candidate_assessments(available=True))

    def fake_open_control(*args: object, **kwargs: object) -> OpenControlPreflightReport:
        core_sha = str(kwargs["core_sha"])
        if core_sha == "9" * 40:
            comparison = BomStateComparison(repos=(), status="aligned", blockers=())
            mismatches: tuple[OcSdkMismatch, ...] = ()
        else:
            comparison = BomStateComparison(
                repos=(),
                status="promotion_required",
                blockers=(),
            )
            mismatches = (OcSdkMismatch(repo="framework", pinned_sha="a", local_sha="b"),)
        return OpenControlPreflightReport(
            oc_sdk=OcSdkLoad(lock=_oc_sdk_lock(version="0.1.4"), source="git", error=None),
            repos=(),
            mismatches=mismatches,
            derived_lock=None,
            comparison=comparison,
        )

    def fake_promote(*args: object, **kwargs: object) -> Ok[BomPromotionResult]:
        return Ok(
            BomPromotionResult(
                pr=PrMergeOutcome(
                    kind="merged_pr",
                    url="https://example/pr/99",
                    label="https://example/pr/99",
                ),
                merged_core_sha="9" * 40,
                plan=BomPromotionPlan(
                    source="workspace",
                    current_version="0.1.3",
                    next_version="0.1.4",
                    items=(),
                    requires_write=True,
                ),
            )
        )

    def fake_prepare(*args: object, **kwargs: object):
        return Ok(
            PrMergeOutcome(
                kind="merged_pr",
                url="https://example/pr/3",
                label="https://example/pr/3",
            )
        )

    published: dict[str, object] = {}

    def fake_publish(*args: object, **kwargs: object):
        published.update(kwargs)
        return Ok("https://example/workflow/1")

    def fake_clear(*args: object, **kwargs: object):
        return Ok(None)

    monkeypatch.setattr(content, "preflight_with_permission", fake_preflight)
    monkeypatch.setattr(content, "bootstrap_content_session", fake_bootstrap)
    monkeypatch.setattr(content, "save_content_state", fake_save_state)
    monkeypatch.setattr(content, "select_channel", fake_channel)
    monkeypatch.setattr(content, "select_bump", fake_bump)
    monkeypatch.setattr(content, "select_green_commit", fake_green)
    monkeypatch.setattr(content, "plan_release", fake_plan)
    monkeypatch.setattr(content, "select_one", fake_select_one)
    monkeypatch.setattr(content, "confirm_yn", fake_confirm)
    monkeypatch.setattr(content, "ensure_ci_green", fake_ci_green)
    monkeypatch.setattr(content, "assess_content_candidates", fake_assess_content_candidates)
    monkeypatch.setattr(content, "ensure_content_candidates", fake_ensure_content_candidates)
    monkeypatch.setattr(content, "preflight_open_control", fake_open_control)
    def fake_ensure_core_release_permissions(**_: object) -> Ok[None]:
        return Ok(None)

    monkeypatch.setattr(
        content,
        "ensure_core_release_permissions",
        fake_ensure_core_release_permissions,
    )
    monkeypatch.setattr(content, "promote_open_control_bom_flow", fake_promote)
    monkeypatch.setattr(content, "prepare_distribution_pr", fake_prepare)
    monkeypatch.setattr(content, "publish_distribution_release", fake_publish)
    monkeypatch.setattr(content, "clear_content_session", fake_clear)

    result = content.run_guided_content_release(
        workspace_root=tmp_path,
        console=MockConsole(),
        notes_file=None,
        watch=False,
        dry_run=False,
    )

    assert isinstance(result, Ok)
    assert planned_inputs[0][2] == ("core", "3" * 40)
    assert planned_inputs[-1][2] == ("core", "9" * 40)
    assert "plan" in published
    plan_obj = published["plan"]
    assert isinstance(plan_obj, ReleasePlan)
    assert plan_obj.pinned[2].repo.id == "core"
    assert plan_obj.pinned[2].sha == "9" * 40


def test_guided_content_candidates_step_builds_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import ms.cli.release_guided_content as content

    session = new_content_session(created_by="alice", notes_path=None)

    def fake_preflight(*args: object, **kwargs: object):
        return Ok("alice")

    def fake_bootstrap(*args: object, **kwargs: object):
        return Ok(session)

    def fake_save_state(*args: object, **kwargs: object):
        s = kwargs.get("session")
        assert isinstance(s, ContentReleaseSession)
        return Ok(s)

    def fake_channel(*args: object, **kwargs: object):
        return _sel("stable")

    def fake_bump(*args: object, **kwargs: object):
        return _sel("patch")

    sha_map = {
        "petitechose-midi-studio/loader": "1" * 40,
        "open-control/bridge": "2" * 40,
        "petitechose-midi-studio/core": "3" * 40,
        "petitechose-midi-studio/plugin-bitwig": "4" * 40,
    }

    def fake_green(*args: object, **kwargs: object):
        return Ok(_sel(sha_map[str(kwargs["repo_slug"])]))

    def fake_plan(
        *,
        workspace_root: Path,
        channel: ReleaseChannel,
        bump: ReleaseBump,
        tag_override: str | None,
        pinned: tuple[PinnedRepo, ...],
    ) -> Ok[ReleasePlan]:
        del workspace_root, channel, bump, tag_override, pinned
        return Ok(
            ReleasePlan(
                channel="stable",
                tag="v9.9.9",
                pinned=(),
                tooling=_tooling(),
                spec_path="release-specs/v9.9.9.json",
                notes_path=None,
                title="release(content): v9.9.9",
            )
        )

    selections = {
        "Content Release Tag": [_sel("accept")],
        "Content Release Summary": [_sel("start", index=10)],
        "Content Release Candidates": [_sel("ensure", index=3), _sel("continue", index=2)],
    }

    def fake_select_one(*args: object, **kwargs: object) -> SelectorResult[str]:
        title = str(kwargs.get("title", ""))
        choices = selections.get(title)
        if not choices:
            raise AssertionError(f"unexpected selector title: {title}")
        return choices.pop(0)

    def fake_confirm(*args: object, **kwargs: object) -> bool:
        return True

    def fake_ci_green(*args: object, **kwargs: object):
        return Ok(None)

    assess_calls = {"count": 0}

    def fake_assess_content_candidates(*args: object, **kwargs: object):
        assess_calls["count"] += 1
        return Ok(_candidate_assessments(available=assess_calls["count"] > 1))

    ensure_calls = {"count": 0}

    def fake_ensure_content_candidates(*args: object, **kwargs: object):
        ensure_calls["count"] += 1
        return Ok(())

    def fake_open_control(*args: object, **kwargs: object) -> OpenControlPreflightReport:
        return OpenControlPreflightReport(
            oc_sdk=OcSdkLoad(lock=_oc_sdk_lock(version="0.1.3"), source="git", error=None),
            repos=(),
            mismatches=(),
            derived_lock=None,
            comparison=BomStateComparison(repos=(), status="aligned", blockers=()),
        )

    def fake_prepare(*args: object, **kwargs: object):
        return Ok(
            PrMergeOutcome(
                kind="merged_pr", url="https://example/pr/4", label="https://example/pr/4"
            )
        )

    def fake_publish(*args: object, **kwargs: object):
        return Ok("https://example/workflow/2")

    def fake_clear(*args: object, **kwargs: object):
        return Ok(None)

    monkeypatch.setattr(content, "preflight_with_permission", fake_preflight)
    monkeypatch.setattr(content, "bootstrap_content_session", fake_bootstrap)
    monkeypatch.setattr(content, "save_content_state", fake_save_state)
    monkeypatch.setattr(content, "select_channel", fake_channel)
    monkeypatch.setattr(content, "select_bump", fake_bump)
    monkeypatch.setattr(content, "select_green_commit", fake_green)
    monkeypatch.setattr(content, "plan_release", fake_plan)
    monkeypatch.setattr(content, "select_one", fake_select_one)
    monkeypatch.setattr(content, "confirm_yn", fake_confirm)
    monkeypatch.setattr(content, "ensure_ci_green", fake_ci_green)
    monkeypatch.setattr(content, "assess_content_candidates", fake_assess_content_candidates)
    monkeypatch.setattr(content, "ensure_content_candidates", fake_ensure_content_candidates)
    monkeypatch.setattr(content, "preflight_open_control", fake_open_control)
    monkeypatch.setattr(content, "prepare_distribution_pr", fake_prepare)
    monkeypatch.setattr(content, "publish_distribution_release", fake_publish)
    monkeypatch.setattr(content, "clear_content_session", fake_clear)

    result = content.run_guided_content_release(
        workspace_root=tmp_path,
        console=MockConsole(),
        notes_file=None,
        watch=False,
        dry_run=False,
    )

    assert isinstance(result, Ok)
    assert assess_calls["count"] >= 2
    assert ensure_calls["count"] == 2


def test_release_guided_routes_by_product(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import ms.cli.release_guided as guided

    def fake_tty() -> bool:
        return True

    calls: list[str] = []

    def fake_app(*args: object, **kwargs: object):
        calls.append("app")
        return Ok(None)

    def fake_content(*args: object, **kwargs: object):
        calls.append("content")
        return Ok(None)

    monkeypatch.setattr(guided, "is_interactive_terminal", fake_tty)
    monkeypatch.setattr(guided, "run_guided_app_release", fake_app)
    monkeypatch.setattr(guided, "run_guided_content_release", fake_content)

    def fake_select_content(*args: object, **kwargs: object) -> SelectorResult[str]:
        return _sel("content")

    monkeypatch.setattr(guided, "select_one", fake_select_content)

    res_content = guided.run_guided_release(
        workspace_root=tmp_path,
        console=MockConsole(),
        notes_file=None,
        watch=False,
        dry_run=True,
    )
    assert isinstance(res_content, Ok)

    def fake_select_app(*args: object, **kwargs: object) -> SelectorResult[str]:
        return _sel("app")

    monkeypatch.setattr(guided, "select_one", fake_select_app)
    res_app = guided.run_guided_release(
        workspace_root=tmp_path,
        console=MockConsole(),
        notes_file=None,
        watch=False,
        dry_run=True,
    )
    assert isinstance(res_app, Ok)
    assert calls == ["content", "app"]
