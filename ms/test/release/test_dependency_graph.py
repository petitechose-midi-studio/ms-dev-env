from __future__ import annotations

from pathlib import Path

from ms.core.result import Err, Ok
from ms.release.domain.dependency_graph_models import ReleaseGraph, ReleaseGraphNode
from ms.release.flow.dependency_graph import load_release_graph, topological_release_nodes


def _write_repos(path: Path) -> None:
    path.write_text(
        """
[[repos]]
org = "open-control"
name = "framework"
url = "https://github.com/open-control/framework"
path = "open-control/framework"

[[repos]]
org = "open-control"
name = "note"
url = "https://github.com/open-control/note"
path = "open-control/note"

[[repos]]
org = "petitechose-midi-studio"
name = "core"
url = "https://github.com/petitechose-midi-studio/core"
path = "midi-studio/core"
""".strip(),
        encoding="utf-8",
    )


def test_load_release_graph_resolves_manifest_paths_and_topological_order(
    tmp_path: Path,
) -> None:
    repos_path = tmp_path / "repos.toml"
    graph_path = tmp_path / "release_graph.toml"
    _write_repos(repos_path)
    graph_path.write_text(
        """
[[nodes]]
id = "core"
repo = "petitechose-midi-studio/core"
role = "bom_consumer"
depends_on = ["oc-note"]
validations = ["core-release"]

[[nodes]]
id = "oc-note"
repo = "open-control/note"
role = "bom_dependency"
depends_on = ["oc-framework"]

[[nodes]]
id = "oc-framework"
repo = "open-control/framework"
role = "bom_dependency"
""".strip(),
        encoding="utf-8",
    )

    graph = load_release_graph(graph_path=graph_path, repos_manifest_path=repos_path)

    assert isinstance(graph, Ok)
    assert [node.id for node in graph.value.nodes] == ["oc-framework", "oc-note", "core"]
    assert graph.value.by_id()["core"].local_path == "midi-studio/core"
    assert graph.value.by_id()["core"].validations == ("core-release",)


def test_load_release_graph_rejects_repo_missing_from_manifest(tmp_path: Path) -> None:
    repos_path = tmp_path / "repos.toml"
    graph_path = tmp_path / "release_graph.toml"
    _write_repos(repos_path)
    graph_path.write_text(
        """
[[nodes]]
id = "oc-missing"
repo = "open-control/missing"
role = "bom_dependency"
""".strip(),
        encoding="utf-8",
    )

    graph = load_release_graph(graph_path=graph_path, repos_manifest_path=repos_path)

    assert isinstance(graph, Err)
    assert "not declared" in graph.error.message


def test_topological_release_nodes_rejects_cycles() -> None:
    graph = ReleaseGraph(
        nodes=(
            ReleaseGraphNode(
                id="a",
                repo="example/a",
                local_path="a",
                role="bom_dependency",
                depends_on=("b",),
            ),
            ReleaseGraphNode(
                id="b",
                repo="example/b",
                local_path="b",
                role="bom_dependency",
                depends_on=("a",),
            ),
        )
    )

    sorted_nodes = topological_release_nodes(graph)

    assert isinstance(sorted_nodes, Err)
    assert sorted_nodes.error.message == "cycle in release dependency graph"
    assert sorted_nodes.error.hint == "a -> b -> a"

