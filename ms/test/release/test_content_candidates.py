from __future__ import annotations

from pathlib import Path

from pytest import MonkeyPatch

from ms.core.result import Ok
from ms.output.console import MockConsole
from ms.release.domain.models import PinnedRepo, ReleaseRepo
from ms.release.flow.content_candidates import (
    ContentCandidateTarget,
    ensure_content_candidates,
    plan_content_candidates,
)
from ms.release.infra.github.workflows import WorkflowRun


def _pinned() -> tuple[PinnedRepo, ...]:
    return (
        PinnedRepo(
            repo=ReleaseRepo(
                id="loader",
                slug="petitechose-midi-studio/loader",
                ref="main",
                required_ci_workflow_file=".github/workflows/ci.yml",
            ),
            sha="1" * 40,
        ),
        PinnedRepo(
            repo=ReleaseRepo(
                id="oc-bridge",
                slug="open-control/bridge",
                ref="main",
                required_ci_workflow_file=".github/workflows/ci.yml",
            ),
            sha="2" * 40,
        ),
        PinnedRepo(
            repo=ReleaseRepo(
                id="core",
                slug="petitechose-midi-studio/core",
                ref="main",
                required_ci_workflow_file=".github/workflows/ci.yml",
            ),
            sha="3" * 40,
        ),
        PinnedRepo(
            repo=ReleaseRepo(
                id="plugin-bitwig",
                slug="petitechose-midi-studio/plugin-bitwig",
                ref="main",
                required_ci_workflow_file=".github/workflows/ci.yml",
            ),
            sha="4" * 40,
        ),
    )


def test_plan_content_candidates_resolves_tags_and_ui_sha(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    import ms.release.flow.content_candidate_planning as planning

    def fake_get_repo_file_text(
        *, workspace_root: Path, repo: str, path: str, ref: str
    ) -> Ok[str]:
        del workspace_root, repo, path, ref
        return Ok(
            "ms-ui=https://github.com/petitechose-midi-studio/ui.git#"
            + ("a" * 40)
            + "\n"
        )

    monkeypatch.setattr(planning, "get_repo_file_text", fake_get_repo_file_text)

    planned = plan_content_candidates(workspace_root=tmp_path, pinned=_pinned())

    assert isinstance(planned, Ok)
    assert [target.id for target in planned.value] == [
        "loader-binaries",
        "oc-bridge-binaries",
        "core-default-firmware",
        "plugin-bitwig-extension",
        "plugin-bitwig-firmware",
    ]
    assert planned.value[2].candidate_tag == "rc-" + ("3" * 40)
    assert (
        planned.value[4].candidate_tag
        == "rc-plugin-bitwig-firmware-" + ("3" * 40) + "-" + ("4" * 40)
    )
    assert planned.value[4].expected_input_repos[2].sha == "a" * 40


def test_ensure_content_candidates_dispatches_only_missing_targets(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    import ms.release.flow.content_candidate_ensure as ensure_module

    target = ContentCandidateTarget(
        id="core-default-firmware",
        label="core firmware",
        producer_id="core-default-firmware",
        repo_slug="petitechose-midi-studio/core",
        workflow_file=".github/workflows/candidate.yml",
        ref="main",
        candidate_tag="rc-" + ("3" * 40),
        workflow_inputs=(("source_sha", "3" * 40),),
        expected_input_repos=(),
        public_key_b64="pk",
    )

    probes = iter([False, True])
    dispatched: list[tuple[str, tuple[tuple[str, str], ...]]] = []

    def fake_plan_content_candidates(
        *, workspace_root: Path, pinned: tuple[PinnedRepo, ...]
    ) -> Ok[tuple[ContentCandidateTarget, ...]]:
        del workspace_root, pinned
        return Ok((target,))

    def fake_probe_content_candidate(
        *, workspace_root: Path, target: ContentCandidateTarget
    ) -> Ok[bool]:
        del workspace_root, target
        return Ok(next(probes))

    monkeypatch.setattr(ensure_module, "plan_content_candidates", fake_plan_content_candidates)
    monkeypatch.setattr(ensure_module, "_probe_content_candidate", fake_probe_content_candidate)

    def fake_dispatch_candidate_workflow(**kwargs: object) -> Ok[WorkflowRun]:
        dispatched.append((kwargs["repo_slug"], kwargs["inputs"]))  # type: ignore[index]
        return Ok(WorkflowRun(id=42, url="https://example.test/run/42", request_id="req"))

    monkeypatch.setattr(
        ensure_module,
        "dispatch_candidate_workflow",
        fake_dispatch_candidate_workflow,
    )
    def fake_watch_run(
        *,
        workspace_root: Path,
        run_id: int,
        repo_slug: str,
        console: MockConsole,
        dry_run: bool,
    ) -> Ok[None]:
        del workspace_root, run_id, repo_slug, console, dry_run
        return Ok(None)

    monkeypatch.setattr(ensure_module, "watch_run", fake_watch_run)

    ensured = ensure_content_candidates(
        workspace_root=tmp_path,
        console=MockConsole(),
        pinned=_pinned(),
        dry_run=False,
    )

    assert isinstance(ensured, Ok)
    assert dispatched == [("petitechose-midi-studio/core", (("source_sha", "3" * 40),))]
    assert ensured.value[0].ready_on_entry is False
    assert ensured.value[0].run is not None
