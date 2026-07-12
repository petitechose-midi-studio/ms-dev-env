from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.git.repository import Repository
from ms.release.domain.dependency_graph_models import ReleaseGraph, ReleaseGraphNode
from ms.release.errors import ReleaseError
from ms.release.infra.atomic_text_file import read_utf8_text, write_utf8_text_atomic

_SHA_RE = r"[0-9a-fA-F]{40}"
_RELEASE_SECTION_RE = re.compile(r"(?ms)^\[env:release\]\s*$.*?(?=^\[|\Z)")


@dataclass(frozen=True, slots=True)
class ConsumerDependencyPinItem:
    dependency_id: str
    path: Path
    from_sha: str | None
    to_sha: str
    changed: bool


@dataclass(frozen=True, slots=True)
class ConsumerDependencyPinPlan:
    consumer_id: str
    items: tuple[ConsumerDependencyPinItem, ...]
    requires_write: bool


@dataclass(frozen=True, slots=True)
class ConsumerDependencyPinSyncResult:
    plan: ConsumerDependencyPinPlan
    written: tuple[Path, ...]


def plan_consumer_dependency_pin_sync(
    *,
    workspace_root: Path,
    graph: ReleaseGraph,
    consumer_id: str,
    dependency_heads: Mapping[str, str] | None = None,
) -> Result[ConsumerDependencyPinPlan, ReleaseError]:
    nodes = graph.by_id()
    consumer = nodes.get(consumer_id)
    if consumer is None:
        return Err(_unknown_consumer(consumer_id))
    if not consumer.depends_on:
        return Ok(
            ConsumerDependencyPinPlan(consumer_id=consumer_id, items=(), requires_write=False)
        )

    platformio = workspace_root / consumer.local_path / "platformio.ini"
    text = read_utf8_text(path=platformio)
    if isinstance(text, Err):
        return text
    release_section = _RELEASE_SECTION_RE.search(text.value)
    if release_section is None:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"missing [env:release] in {platformio}",
            )
        )

    if dependency_heads is None:
        resolved_heads = _workspace_dependency_heads(
            workspace_root=workspace_root,
            nodes=nodes,
            dependency_ids=consumer.depends_on,
        )
        if isinstance(resolved_heads, Err):
            return resolved_heads
        heads = resolved_heads.value
    else:
        heads = dependency_heads

    items: list[ConsumerDependencyPinItem] = []
    for dependency_id in consumer.depends_on:
        dependency = nodes.get(dependency_id)
        if dependency is None:
            return Err(
                ReleaseError(
                    kind="invalid_input",
                    message=f"dependency graph node not found: {dependency_id}",
                    hint=f"referenced by {consumer_id}",
                )
            )
        pattern = _dependency_line_pattern(dependency)
        match = pattern.search(release_section.group(0))
        if match is None:
            return Err(
                ReleaseError(
                    kind="invalid_input",
                    message=f"missing release dependency for {dependency_id}",
                    hint=str(platformio),
                )
            )
        current = match.group(2).lower() if match.group(2) is not None else None
        target_head = heads.get(dependency_id)
        if target_head is None:
            return Err(
                ReleaseError(
                    kind="invalid_input",
                    message=f"dependency head unavailable: {dependency_id}",
                )
            )
        target = target_head.lower()
        items.append(
            ConsumerDependencyPinItem(
                dependency_id=dependency_id,
                path=platformio,
                from_sha=current,
                to_sha=target,
                changed=(
                    current != target or _pin_pattern(dependency).fullmatch(match.group(0)) is None
                ),
            )
        )

    return Ok(
        ConsumerDependencyPinPlan(
            consumer_id=consumer_id,
            items=tuple(items),
            requires_write=any(item.changed for item in items),
        )
    )


def sync_consumer_dependency_pin_plan(
    *,
    graph: ReleaseGraph,
    plan: ConsumerDependencyPinPlan,
) -> Result[ConsumerDependencyPinSyncResult, ReleaseError]:
    if not plan.requires_write:
        return Ok(ConsumerDependencyPinSyncResult(plan=plan, written=()))

    nodes = graph.by_id()
    by_path: dict[Path, list[ConsumerDependencyPinItem]] = {}
    for item in plan.items:
        if item.changed:
            by_path.setdefault(item.path, []).append(item)

    written: list[Path] = []
    for path, items in by_path.items():
        text = read_utf8_text(path=path)
        if isinstance(text, Err):
            return text
        rendered = text.value
        for item in items:
            dependency = nodes.get(item.dependency_id)
            if dependency is None:
                return Err(_unknown_consumer(item.dependency_id))
            release_section = _RELEASE_SECTION_RE.search(rendered)
            if release_section is None:
                return Err(
                    ReleaseError(
                        kind="invalid_input",
                        message=f"missing [env:release] in {path}",
                    )
                )
            section, count = _dependency_line_pattern(dependency).subn(
                (
                    rf"\g<1>{dependency.id}=https://github.com/"
                    rf"{dependency.repo}.git#{item.to_sha}\g<3>"
                ),
                release_section.group(0),
            )
            if count != 1:
                return Err(
                    ReleaseError(
                        kind="invalid_input",
                        message=f"release pin update was not unique: {item.dependency_id}",
                        hint=str(path),
                    )
                )
            rendered = (
                rendered[: release_section.start()] + section + rendered[release_section.end() :]
            )
        write = write_utf8_text_atomic(path=path, content=rendered)
        if isinstance(write, Err):
            return write
        written.append(path)

    verified = _verify_written_plan(graph=graph, plan=plan)
    if isinstance(verified, Err):
        return verified

    return Ok(ConsumerDependencyPinSyncResult(plan=plan, written=tuple(written)))


def _workspace_dependency_heads(
    *,
    workspace_root: Path,
    nodes: Mapping[str, ReleaseGraphNode],
    dependency_ids: tuple[str, ...],
) -> Result[dict[str, str], ReleaseError]:
    heads: dict[str, str] = {}
    for dependency_id in dependency_ids:
        dependency = nodes.get(dependency_id)
        if dependency is None:
            return Err(_unknown_consumer(dependency_id))
        head = Repository(workspace_root / dependency.local_path).head_sha()
        if isinstance(head, Err):
            return Err(
                ReleaseError(
                    kind="repo_failed",
                    message=f"failed to read dependency SHA: {dependency.repo}",
                    hint=head.error.message,
                )
            )
        heads[dependency_id] = head.value
    return Ok(heads)


def _pin_pattern(dependency: ReleaseGraphNode) -> re.Pattern[str]:
    return re.compile(
        rf"(?m)^(\s*{re.escape(dependency.id)}=https://github\.com/"
        rf"{re.escape(dependency.repo)}\.git#)({_SHA_RE})(\s*)$"
    )


def _dependency_line_pattern(dependency: ReleaseGraphNode) -> re.Pattern[str]:
    return re.compile(
        rf"(?m)^(\s*)(?:{re.escape(dependency.id)}=)?https://github\.com/"
        rf"{re.escape(dependency.repo)}(?:\.git)?(?:#({_SHA_RE}))?(\s*)$"
    )


def _verify_written_plan(
    *, graph: ReleaseGraph, plan: ConsumerDependencyPinPlan
) -> Result[None, ReleaseError]:
    nodes = graph.by_id()
    for item in plan.items:
        if not item.changed:
            continue
        dependency = nodes.get(item.dependency_id)
        if dependency is None:
            return Err(_unknown_consumer(item.dependency_id))
        text = read_utf8_text(path=item.path)
        if isinstance(text, Err):
            return text
        release_section = _RELEASE_SECTION_RE.search(text.value)
        match = (
            _pin_pattern(dependency).search(release_section.group(0))
            if release_section is not None
            else None
        )
        current = match.group(2).lower() if match is not None else None
        if current != item.to_sha:
            return Err(
                ReleaseError(
                    kind="invalid_input",
                    message="post-write verification failed for consumer dependency pins",
                    hint=(
                        f"{item.dependency_id}: expected {item.to_sha}, found {current or 'unset'}"
                    ),
                )
            )
    return Ok(None)


def _unknown_consumer(consumer_id: str) -> ReleaseError:
    return ReleaseError(kind="invalid_input", message=f"unknown release graph node: {consumer_id}")


__all__ = [
    "ConsumerDependencyPinItem",
    "ConsumerDependencyPinPlan",
    "ConsumerDependencyPinSyncResult",
    "plan_consumer_dependency_pin_sync",
    "sync_consumer_dependency_pin_plan",
]
