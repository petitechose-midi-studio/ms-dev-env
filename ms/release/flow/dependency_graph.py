from __future__ import annotations

import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from ms.core.result import Err, Ok, Result
from ms.core.structured import as_obj_list, as_str_dict, get_list, get_str
from ms.release.domain.dependency_graph_models import (
    ReleaseGraph,
    ReleaseGraphNode,
    ReleaseGraphRole,
)
from ms.release.errors import ReleaseError
from ms.services.repos.manifest import load_manifest
from ms.services.repos.models import RepoSpec

_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DEFAULT_RELEASE_GRAPH_PATH = _DATA_DIR / "release_graph.toml"
DEFAULT_REPOS_MANIFEST_PATH = _DATA_DIR / "repos.toml"
_VALID_ROLES: frozenset[str] = frozenset(
    {
        "bom_dependency",
        "bom_consumer",
        "dev_dependency",
        "release_producer",
        "release_consumer",
    }
)


def load_release_graph(
    *,
    graph_path: Path = DEFAULT_RELEASE_GRAPH_PATH,
    repos_manifest_path: Path = DEFAULT_REPOS_MANIFEST_PATH,
) -> Result[ReleaseGraph, ReleaseError]:
    repo_specs = load_manifest(repos_manifest_path)
    if isinstance(repo_specs, Err):
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=repo_specs.error.message,
                hint=repo_specs.error.hint,
            )
        )

    try:
        data_obj: object = tomllib.loads(graph_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"release graph is invalid: {error}",
                hint=str(graph_path),
            )
        )

    data = as_str_dict(data_obj)
    if data is None:
        return Err(_graph_error("release graph root must be a TOML table", graph_path))

    raw_nodes = get_list(data, "nodes")
    if raw_nodes is None:
        return Err(_graph_error("release graph missing nodes[]", graph_path))

    repos_by_slug = _repo_specs_by_slug(repo_specs.value)
    nodes: list[ReleaseGraphNode] = []
    seen_ids: set[str] = set()
    seen_repos: set[str] = set()
    for raw in raw_nodes:
        item = as_str_dict(raw)
        if item is None:
            return Err(_graph_error("release graph nodes must be TOML tables", graph_path))

        parsed = _parse_node(item=item, repos_by_slug=repos_by_slug, graph_path=graph_path)
        if isinstance(parsed, Err):
            return parsed
        node = parsed.value

        if node.id in seen_ids:
            return Err(_graph_error(f"duplicate release graph node id: {node.id}", graph_path))
        if node.repo in seen_repos:
            return Err(_graph_error(f"duplicate release graph repo: {node.repo}", graph_path))
        seen_ids.add(node.id)
        seen_repos.add(node.repo)
        nodes.append(node)

    graph = ReleaseGraph(nodes=tuple(nodes))
    sorted_nodes = topological_release_nodes(graph)
    if isinstance(sorted_nodes, Err):
        return sorted_nodes
    return Ok(ReleaseGraph(nodes=sorted_nodes.value))


def topological_release_nodes(
    graph: ReleaseGraph,
) -> Result[tuple[ReleaseGraphNode, ...], ReleaseError]:
    by_id = graph.by_id()
    ordered: list[ReleaseGraphNode] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str, path: tuple[str, ...]) -> Result[None, ReleaseError]:
        node = by_id.get(node_id)
        if node is None:
            parent = path[-1] if path else "<root>"
            return Err(
                ReleaseError(
                    kind="invalid_input",
                    message=f"release graph dependency not found: {node_id}",
                    hint=f"referenced by {parent}",
                )
            )
        if node_id in visited:
            return Ok(None)
        if node_id in visiting:
            cycle = " -> ".join((*path, node_id))
            return Err(
                ReleaseError(
                    kind="invalid_input",
                    message="cycle in release dependency graph",
                    hint=cycle,
                )
            )

        visiting.add(node_id)
        for dependency in node.depends_on:
            visited_dep = visit(dependency, (*path, node_id))
            if isinstance(visited_dep, Err):
                return visited_dep
        visiting.remove(node_id)
        visited.add(node_id)
        ordered.append(node)
        return Ok(None)

    for node in graph.nodes:
        result = visit(node.id, ())
        if isinstance(result, Err):
            return result

    return Ok(tuple(ordered))


def _parse_node(
    *,
    item: Mapping[str, object],
    repos_by_slug: dict[str, RepoSpec],
    graph_path: Path,
) -> Result[ReleaseGraphNode, ReleaseError]:
    node_id = get_str(item, "id")
    repo = get_str(item, "repo")
    role = get_str(item, "role")
    if node_id is None or repo is None or role is None:
        return Err(_graph_error("release graph node requires id, repo, and role", graph_path))
    if role not in _VALID_ROLES:
        return Err(_graph_error(f"invalid release graph role for {node_id}: {role}", graph_path))

    spec = repos_by_slug.get(repo)
    if spec is None:
        return Err(
            _graph_error(
                f"release graph repo is not declared in repos manifest: {repo}",
                graph_path,
            )
        )

    depends_on = _string_tuple(item, "depends_on")
    if isinstance(depends_on, Err):
        return depends_on
    validations = _string_tuple(item, "validations")
    if isinstance(validations, Err):
        return validations

    return Ok(
        ReleaseGraphNode(
            id=node_id,
            repo=repo,
            local_path=spec.path,
            role=cast("ReleaseGraphRole", role),
            depends_on=depends_on.value,
            validations=validations.value,
        )
    )


def _string_tuple(
    item: Mapping[str, object], key: str
) -> Result[tuple[str, ...], ReleaseError]:
    raw = item.get(key)
    if raw is None:
        return Ok(())
    values = as_obj_list(raw)
    if values is None:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"release graph field must be a string list: {key}",
            )
        )
    out: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            return Err(
                ReleaseError(
                    kind="invalid_input",
                    message=f"release graph field must be a string list: {key}",
                )
            )
        out.append(value.strip())
    return Ok(tuple(out))


def _repo_specs_by_slug(specs: list[RepoSpec]) -> dict[str, RepoSpec]:
    return {f"{spec.org}/{spec.name}": spec for spec in specs}


def _graph_error(message: str, graph_path: Path) -> ReleaseError:
    return ReleaseError(kind="invalid_input", message=message, hint=str(graph_path))

