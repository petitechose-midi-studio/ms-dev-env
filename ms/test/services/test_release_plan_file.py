from __future__ import annotations

from pathlib import Path

from ms.core.result import Err, Ok
from ms.services.release.config import RELEASE_REPOS
from ms.services.release.model import PinnedRepo
from ms.services.release.plan_file import PlanInput, read_plan_file, write_plan_file


def test_plan_file_roundtrip(tmp_path: Path) -> None:
    pinned = (
        PinnedRepo(repo=RELEASE_REPOS[0], sha="0" * 40),
        PinnedRepo(repo=RELEASE_REPOS[1], sha="1" * 40),
        PinnedRepo(repo=RELEASE_REPOS[2], sha="2" * 40),
        PinnedRepo(repo=RELEASE_REPOS[3], sha="3" * 40),
    )
    plan = PlanInput(channel="stable", tag="v1.2.3", pinned=pinned)
    path = tmp_path / "plan.json"

    written = write_plan_file(path=path, plan=plan)
    assert isinstance(written, Ok)

    read = read_plan_file(path=path)
    assert isinstance(read, Ok)
    assert read.value.channel == "stable"
    assert read.value.tag == "v1.2.3"
    assert [p.repo.id for p in read.value.pinned] == [
        "loader",
        "oc-bridge",
        "core",
        "plugin-bitwig",
    ]
    assert [p.sha for p in read.value.pinned] == ["0" * 40, "1" * 40, "2" * 40, "3" * 40]


def test_plan_file_preserves_ref_override(tmp_path: Path) -> None:
    repo0 = RELEASE_REPOS[0]
    repo1 = RELEASE_REPOS[1]
    repo2 = RELEASE_REPOS[2]
    repo3 = RELEASE_REPOS[3]

    # Override core ref to simulate a feature branch plan.
    # ReleaseRepo is a dataclass; use type(...) to avoid importing it here.
    core_feature = type(repo2)(
        id=repo2.id,
        slug=repo2.slug,
        ref="feature/test",
        required_ci_workflow_file=repo2.required_ci_workflow_file,
    )

    pinned = (
        PinnedRepo(repo=repo0, sha="0" * 40),
        PinnedRepo(repo=repo1, sha="1" * 40),
        PinnedRepo(repo=core_feature, sha="2" * 40),
        PinnedRepo(repo=repo3, sha="3" * 40),
    )
    plan = PlanInput(channel="beta", tag="v1.2.3-beta.1", pinned=pinned)
    path = tmp_path / "plan.json"

    written = write_plan_file(path=path, plan=plan)
    assert isinstance(written, Ok)

    read = read_plan_file(path=path)
    assert isinstance(read, Ok)
    refs = {p.repo.id: p.repo.ref for p in read.value.pinned}
    assert refs["core"] == "feature/test"


def test_plan_file_rejects_missing_repos(tmp_path: Path) -> None:
    # Missing oc-bridge.
    path = tmp_path / "plan.json"
    path.write_text(
        """{
  "schema": 1,
  "channel": "stable",
  "tag": "v1.0.0",
  "repos": [
    {"id": "loader", "sha": "0000000000000000000000000000000000000000"}
  ]
}\n""",
        encoding="utf-8",
    )

    read = read_plan_file(path=path)
    assert isinstance(read, Err)
    assert read.error.kind == "invalid_input"
