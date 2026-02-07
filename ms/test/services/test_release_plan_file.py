from __future__ import annotations

from pathlib import Path

from ms.core.result import Err, Ok
from ms.services.release.config import APP_RELEASE_REPO, RELEASE_REPOS
from ms.services.release.model import PinnedRepo
from ms.services.release.plan_file import PlanInput, read_plan_file, write_plan_file


def test_plan_file_roundtrip_content_schema_v2(tmp_path: Path) -> None:
    pinned = (
        PinnedRepo(repo=RELEASE_REPOS[0], sha="0" * 40),
        PinnedRepo(repo=RELEASE_REPOS[1], sha="1" * 40),
        PinnedRepo(repo=RELEASE_REPOS[2], sha="2" * 40),
        PinnedRepo(repo=RELEASE_REPOS[3], sha="3" * 40),
    )
    plan = PlanInput(product="content", channel="stable", tag="v1.2.3", pinned=pinned)
    path = tmp_path / "plan.json"

    written = write_plan_file(path=path, plan=plan)
    assert isinstance(written, Ok)

    read = read_plan_file(path=path)
    assert isinstance(read, Ok)
    assert read.value.product == "content"
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
    plan = PlanInput(product="content", channel="beta", tag="v1.2.3-beta.1", pinned=pinned)
    path = tmp_path / "plan.json"

    written = write_plan_file(path=path, plan=plan)
    assert isinstance(written, Ok)

    read = read_plan_file(path=path)
    assert isinstance(read, Ok)
    refs = {p.repo.id: p.repo.ref for p in read.value.pinned}
    assert refs["core"] == "feature/test"


def test_plan_file_rejects_missing_repos(tmp_path: Path) -> None:
    path = tmp_path / "plan.json"
    path.write_text(
        """{
  "schema": 2,
  "product": "content",
  "channel": "stable",
  "tag": "v1.0.0",
  "repos": [
    {
      "id": "loader",
      "slug": "petitechose-midi-studio/loader",
      "ref": "main",
      "sha": "0000000000000000000000000000000000000000"
    }
  ]
}
""",
        encoding="utf-8",
    )

    read = read_plan_file(path=path)
    assert isinstance(read, Err)
    assert read.error.kind == "invalid_input"


def test_plan_file_roundtrip_app_product(tmp_path: Path) -> None:
    pinned = (PinnedRepo(repo=APP_RELEASE_REPO, sha="a" * 40),)
    plan = PlanInput(product="app", channel="beta", tag="v0.2.0-beta.1", pinned=pinned)
    path = tmp_path / "plan-app.json"

    written = write_plan_file(path=path, plan=plan)
    assert isinstance(written, Ok)

    read = read_plan_file(path=path)
    assert isinstance(read, Ok)
    assert read.value.product == "app"
    assert read.value.channel == "beta"
    assert read.value.tag == "v0.2.0-beta.1"
    assert [p.repo.id for p in read.value.pinned] == ["ms-manager"]
    assert [p.sha for p in read.value.pinned] == ["a" * 40]


def test_plan_file_rejects_schema_v1(tmp_path: Path) -> None:
    path = tmp_path / "plan-v1.json"
    path.write_text(
        """{
  "schema": 1,
  "product": "app",
  "channel": "stable",
  "tag": "v1.0.0",
  "repos": [
    {
      "id": "ms-manager",
      "slug": "petitechose-midi-studio/ms-manager",
      "ref": "main",
      "sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    }
  ]
}
""",
        encoding="utf-8",
    )

    read = read_plan_file(path=path)
    assert isinstance(read, Err)
    assert read.error.kind == "invalid_input"


def test_plan_file_rejects_missing_slug(tmp_path: Path) -> None:
    path = tmp_path / "plan-missing-slug.json"
    path.write_text(
        """{
  "schema": 2,
  "product": "app",
  "channel": "stable",
  "tag": "v1.0.0",
  "repos": [
    {
      "id": "ms-manager",
      "ref": "main",
      "sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    }
  ]
}
""",
        encoding="utf-8",
    )

    read = read_plan_file(path=path)
    assert isinstance(read, Err)
    assert read.error.kind == "invalid_input"
