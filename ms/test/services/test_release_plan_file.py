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
    )
    plan = PlanInput(channel="stable", tag="v1.2.3", pinned=pinned)
    path = tmp_path / "plan.json"

    written = write_plan_file(path=path, plan=plan)
    assert isinstance(written, Ok)

    read = read_plan_file(path=path)
    assert isinstance(read, Ok)
    assert read.value.channel == "stable"
    assert read.value.tag == "v1.2.3"
    assert [p.repo.id for p in read.value.pinned] == ["loader", "oc-bridge"]
    assert [p.sha for p in read.value.pinned] == ["0" * 40, "1" * 40]


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
