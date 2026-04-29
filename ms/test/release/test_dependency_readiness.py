from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.git.repository import GitError, GitStatus, StatusEntry
from ms.release.domain.dependency_graph_models import ReleaseGraph, ReleaseGraphNode
from ms.release.errors import ReleaseError
from ms.release.flow.dependency_readiness import (
    ReadinessRepository,
    assess_dependency_readiness,
)


@dataclass
class _FakeRepo:
    present: bool = True
    repo_status: GitStatus | GitError = GitStatus(
        branch="main",
        upstream="origin/main",
    )
    branch: str | None = "main"
    sha: str = "a" * 40

    def exists(self) -> bool:
        return self.present

    def status(self) -> Result[GitStatus, GitError]:
        if isinstance(self.repo_status, GitError):
            return Err(self.repo_status)
        return Ok(self.repo_status)

    def current_branch(self) -> str | None:
        return self.branch

    def head_sha(self) -> Result[str, GitError]:
        return Ok(self.sha)


def _graph() -> ReleaseGraph:
    return ReleaseGraph(
        nodes=(
            ReleaseGraphNode(
                id="oc-framework",
                repo="open-control/framework",
                local_path="open-control/framework",
                role="bom_dependency",
            ),
            ReleaseGraphNode(
                id="core",
                repo="petitechose-midi-studio/core",
                local_path="midi-studio/core",
                role="bom_consumer",
                depends_on=("oc-framework",),
            ),
        )
    )


def _factory(repos: dict[str, _FakeRepo]):
    def make(path: Path) -> ReadinessRepository:
        return repos[path.name]

    return make


def _fetchable(_: str, __: str) -> Ok[bool]:
    return Ok(True)


def test_assess_dependency_readiness_returns_ready_when_repos_are_clean_and_fetchable(
    tmp_path: Path,
) -> None:
    report = assess_dependency_readiness(
        workspace_root=tmp_path,
        graph=_graph(),
        repo_factory=_factory({"framework": _FakeRepo(), "core": _FakeRepo(sha="b" * 40)}),
        fetchable_checker=_fetchable,
    )

    assert report.is_ready
    assert [item.status for item in report.items] == ["ok", "ok"]
    assert report.by_node_id()["core"].sha == "b" * 40


def test_assess_dependency_readiness_blocks_dependents_when_dependency_is_dirty(
    tmp_path: Path,
) -> None:
    dirty = GitStatus(
        branch="main",
        upstream="origin/main",
        entries=(StatusEntry(xy=" M", path="src/foo.cpp"),),
    )

    report = assess_dependency_readiness(
        workspace_root=tmp_path,
        graph=_graph(),
        repo_factory=_factory(
            {
                "framework": _FakeRepo(repo_status=dirty),
                "core": _FakeRepo(sha="b" * 40),
            }
        ),
        fetchable_checker=_fetchable,
    )

    assert not report.is_ready
    assert report.by_node_id()["oc-framework"].status == "dirty"
    assert report.by_node_id()["oc-framework"].detail == "unstaged=1\n  .M src/foo.cpp"
    assert report.by_node_id()["core"].status == "blocked_by_dependency"


def test_assess_dependency_readiness_reports_unpushed_head(tmp_path: Path) -> None:
    ahead = GitStatus(branch="main", upstream="origin/main", ahead=1)

    report = assess_dependency_readiness(
        workspace_root=tmp_path,
        graph=ReleaseGraph(
            nodes=(
                ReleaseGraphNode(
                    id="oc-framework",
                    repo="open-control/framework",
                    local_path="open-control/framework",
                    role="bom_dependency",
                ),
            )
        ),
        repo_factory=_factory({"framework": _FakeRepo(repo_status=ahead)}),
        fetchable_checker=lambda _repo, _sha: Ok(False),
    )

    item = report.by_node_id()["oc-framework"]
    assert item.status == "ahead_unpushed"
    assert item.hint is not None
    assert "git -C" in item.hint


def test_assess_dependency_readiness_reports_github_lookup_errors_as_not_fetchable(
    tmp_path: Path,
) -> None:
    report = assess_dependency_readiness(
        workspace_root=tmp_path,
        graph=ReleaseGraph(
            nodes=(
                ReleaseGraphNode(
                    id="oc-framework",
                    repo="open-control/framework",
                    local_path="open-control/framework",
                    role="bom_dependency",
                ),
            )
        ),
        repo_factory=_factory({"framework": _FakeRepo()}),
        fetchable_checker=lambda _repo, _sha: Err(
            ReleaseError(
                kind="invalid_input",
                message="gh api failed",
                hint="commit not found",
            )
        ),
    )

    item = report.by_node_id()["oc-framework"]
    assert item.status == "not_fetchable"
    assert item.detail == "gh api failed"
    assert item.hint == "commit not found"


def test_assess_dependency_readiness_reports_behind_remote(tmp_path: Path) -> None:
    behind = GitStatus(branch="main", upstream="origin/main", behind=2)

    report = assess_dependency_readiness(
        workspace_root=tmp_path,
        graph=ReleaseGraph(
            nodes=(
                ReleaseGraphNode(
                    id="oc-framework",
                    repo="open-control/framework",
                    local_path="open-control/framework",
                    role="bom_dependency",
                ),
            )
        ),
        repo_factory=_factory({"framework": _FakeRepo(repo_status=behind)}),
        fetchable_checker=_fetchable,
    )

    item = report.by_node_id()["oc-framework"]
    assert item.status == "behind_remote"
    assert item.detail == "main is behind origin/main by 2"

