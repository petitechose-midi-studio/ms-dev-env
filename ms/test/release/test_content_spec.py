from __future__ import annotations

from pathlib import Path

from ms.core.result import Err, Ok
from ms.release.domain.config import RELEASE_REPOS
from ms.release.domain.models import PinnedRepo, ReleaseTooling
from ms.release.flow.content_spec import load_content_plan_from_spec
from ms.release.infra.artifacts.spec_writer import write_release_spec


def _pinned() -> tuple[PinnedRepo, ...]:
    return tuple(PinnedRepo(repo=repo, sha=str(idx) * 40) for idx, repo in enumerate(RELEASE_REPOS))


def _tooling() -> ReleaseTooling:
    return ReleaseTooling(
        repo="petitechose-midi-studio/ms-dev-env",
        ref="main",
        sha="f" * 40,
    )


def test_load_content_plan_from_spec_round_trips_written_spec(tmp_path: Path) -> None:
    written = write_release_spec(
        dist_repo_root=tmp_path,
        channel="beta",
        tag="v1.2.3-beta.4",
        pinned=_pinned(),
        tooling=_tooling(),
    )
    assert isinstance(written, Ok)

    loaded = load_content_plan_from_spec(spec_path=written.value.abs_path)
    assert isinstance(loaded, Ok)
    assert loaded.value.channel == "beta"
    assert loaded.value.tag == "v1.2.3-beta.4"
    assert loaded.value.tooling.sha == _tooling().sha
    assert tuple(pin.repo.id for pin in loaded.value.pinned) == tuple(
        pin.repo.id for pin in _pinned()
    )


def test_load_content_plan_from_spec_rejects_missing_tooling(tmp_path: Path) -> None:
    spec = tmp_path / "spec.json"
    spec.write_text(
        '{"schema": 2, "channel": "beta", "tag": "v1", "repos": []}\n',
        encoding="utf-8",
    )

    loaded = load_content_plan_from_spec(spec_path=spec)
    assert isinstance(loaded, Err)
    assert loaded.error.kind == "invalid_input"
