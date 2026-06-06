from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

DependencyReadinessStatus = Literal[
    "ok",
    "missing",
    "dirty",
    "no_upstream",
    "behind_remote",
    "ahead_remote",
    "ahead_unpushed",
    "diverged",
    "detached",
    "wrong_branch",
    "wrong_upstream",
    "not_fetchable",
    "blocked_by_dependency",
    "repo_failed",
]


@dataclass(frozen=True, slots=True)
class DependencyReadinessItem:
    node_id: str
    repo: str
    path: Path
    status: DependencyReadinessStatus
    sha: str | None = None
    branch: str | None = None
    detail: str | None = None
    hint: str | None = None

    @property
    def is_blocking(self) -> bool:
        return self.status != "ok"


@dataclass(frozen=True, slots=True)
class DependencyReadinessAction:
    summary: str
    command: str | None = None


@dataclass(frozen=True, slots=True)
class DependencyReadinessReport:
    items: tuple[DependencyReadinessItem, ...]

    @property
    def is_ready(self) -> bool:
        return all(not item.is_blocking for item in self.items)

    @property
    def ready_count(self) -> int:
        return sum(1 for item in self.items if not item.is_blocking)

    @property
    def blocker_count(self) -> int:
        return len(self.items) - self.ready_count

    @property
    def blockers(self) -> tuple[DependencyReadinessItem, ...]:
        return tuple(item for item in self.items if item.is_blocking)

    def by_node_id(self) -> dict[str, DependencyReadinessItem]:
        return {item.node_id: item for item in self.items}


def next_action_for_item(item: DependencyReadinessItem) -> DependencyReadinessAction:
    path = _quote_path(item.path)
    branch = item.branch or "<branch>"
    expected = _expected_branch_from_hint(item.hint) or "main"

    match item.status:
        case "ok":
            return DependencyReadinessAction("No action needed.")
        case "missing":
            return DependencyReadinessAction(
                "Clone or resync the workspace repositories.",
                "uv run ms sync --repos",
            )
        case "dirty":
            return DependencyReadinessAction(
                "Keep -> PR/CI/auto-merge; discard -> revert/stash; then pull+rerun.",
                f"git -C {path} status --short",
            )
        case "no_upstream":
            return DependencyReadinessAction(
                "Push branch -> PR -> CI -> auto-merge -> pull main -> rerun.",
                f"git -C {path} push -u origin {branch}",
            )
        case "behind_remote":
            return DependencyReadinessAction(
                "Fast-forward the local branch from GitHub, then rerun ms release.",
                f"git -C {path} pull --ff-only",
            )
        case "ahead_remote":
            return DependencyReadinessAction(
                "Local main has unpublished commits. Move through PR/CI, pull main, then rerun.",
                f"git -C {path} status",
            )
        case "ahead_unpushed":
            return DependencyReadinessAction(
                "Push branch. If release-bound, merge through PR/CI before pinning.",
                f"git -C {path} push",
            )
        case "diverged":
            return DependencyReadinessAction(
                "Resolve divergence, merge needed changes through PR/CI, then rerun.",
                f"git -C {path} status",
            )
        case "detached":
            return DependencyReadinessAction(
                "Checkout the canonical branch or publish an explicit release branch before rerun.",
                f"git -C {path} switch {expected}",
            )
        case "wrong_branch":
            return DependencyReadinessAction(
                f"Merge {branch} if needed, then switch {expected} -> pull -> rerun.",
                f"git -C {path} switch {expected}",
            )
        case "wrong_upstream":
            return DependencyReadinessAction(
                "Point the local branch at the canonical GitHub upstream, then rerun ms release.",
                f"git -C {path} branch --set-upstream-to=origin/{expected} {branch}",
            )
        case "not_fetchable":
            return DependencyReadinessAction(
                "Make the commit fetchable from GitHub; prefer origin/main before pinning.",
                f"git -C {path} push",
            )
        case "blocked_by_dependency":
            return DependencyReadinessAction(
                (
                    "Resolve the upstream dependency blockers first; "
                    "this repo should unblock naturally."
                ),
            )
        case "repo_failed":
            return DependencyReadinessAction(
                "Inspect and fix the repository state before rerunning ms release.",
                f"git -C {path} status",
            )


def _quote_path(path: Path) -> str:
    text = str(path)
    if " " in text:
        return f'"{text}"'
    return text


def _expected_branch_from_hint(hint: str | None) -> str | None:
    if hint is None:
        return None
    marker = "git -C "
    if marker not in hint or " switch " not in hint:
        return None
    branch = hint.rsplit(" switch ", maxsplit=1)[-1].strip()
    return branch or None


__all__ = [
    "DependencyReadinessAction",
    "DependencyReadinessItem",
    "DependencyReadinessReport",
    "DependencyReadinessStatus",
    "next_action_for_item",
]
