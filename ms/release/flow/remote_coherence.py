from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ms.core.result import Err, Ok, Result
from ms.output.console import ConsoleProtocol, Style
from ms.release.domain.models import PinnedRepo, ReleaseTooling
from ms.release.errors import ReleaseError
from ms.release.flow.dependency_readiness import is_commit_fetchable
from ms.release.infra.github.ci import is_ci_green_for_sha
from ms.release.infra.github.client import get_ref_head_sha
from ms.release.resolve.auto.diagnostics import probe_release_readiness

from .release_tooling import ensure_release_tooling_on_main

RemoteCoherenceStatus = Literal["eligible", "blocked", "warning"]


@dataclass(frozen=True, slots=True)
class RemoteCoherenceItem:
    repo_id: str
    repo: str
    role: str
    target_sha: str
    local_sha: str | None
    remote_ref: str
    remote_sha: str | None
    status: RemoteCoherenceStatus
    detail: str
    hint: str | None = None


@dataclass(frozen=True, slots=True)
class RemoteCoherenceReport:
    items: tuple[RemoteCoherenceItem, ...]

    @property
    def blockers(self) -> tuple[RemoteCoherenceItem, ...]:
        return tuple(item for item in self.items if item.status == "blocked")

    @property
    def is_eligible(self) -> bool:
        return not self.blockers


def assert_release_remote_coherence(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    pinned: tuple[PinnedRepo, ...],
    tooling: ReleaseTooling,
    dry_run: bool,
    verify_ci: bool = True,
) -> Result[RemoteCoherenceReport, ReleaseError]:
    report = assess_release_remote_coherence(
        workspace_root=workspace_root,
        pinned=pinned,
        tooling=tooling,
        dry_run=dry_run,
        verify_ci=verify_ci,
    )
    if isinstance(report, Err):
        return report

    print_release_remote_coherence(console=console, report=report.value)
    if report.value.is_eligible:
        return report

    blockers = report.value.blockers
    first = blockers[0]
    hints = [item.hint for item in blockers if item.hint]
    return Err(
        ReleaseError(
            kind="invalid_input",
            message=f"release remote coherence blocked: {first.repo_id} - {first.detail}",
            hint="\n".join(hints) if hints else first.detail,
        )
    )


def assess_release_remote_coherence(
    *,
    workspace_root: Path,
    pinned: tuple[PinnedRepo, ...],
    tooling: ReleaseTooling,
    dry_run: bool,
    verify_ci: bool = True,
) -> Result[RemoteCoherenceReport, ReleaseError]:
    items: list[RemoteCoherenceItem] = []

    tooling_item = _assess_tooling(
        workspace_root=workspace_root,
        tooling=tooling,
        dry_run=dry_run,
    )
    if isinstance(tooling_item, Err):
        return tooling_item
    items.append(tooling_item.value)

    for pinned_repo in pinned:
        item = _assess_pinned_repo(
            workspace_root=workspace_root,
            pinned=pinned_repo,
            verify_ci=verify_ci,
        )
        if isinstance(item, Err):
            return item
        items.append(item.value)

    return Ok(RemoteCoherenceReport(items=tuple(items)))


def print_release_remote_coherence(
    *, console: ConsoleProtocol, report: RemoteCoherenceReport
) -> None:
    console.header("Remote Coherence")
    console.print("Only GitHub-resolvable, CI-valid SHAs are release-eligible.", Style.DIM)
    for item in report.items:
        target = item.target_sha[:12]
        local = item.local_sha[:12] if item.local_sha else "unavailable"
        remote = item.remote_sha[:12] if item.remote_sha else "unavailable"
        line = (
            f"{item.repo_id}: {item.status} "
            f"(target {target}, local {local}, {item.remote_ref} {remote})"
        )
        if item.status == "eligible":
            console.success(line)
        elif item.status == "warning":
            console.warning(line)
        else:
            console.error(line)
        console.print(f"  {item.detail}", Style.DIM)
        if item.hint:
            for hint_line in item.hint.splitlines():
                console.print(f"  hint: {hint_line}", Style.DIM)


def _assess_tooling(
    *, workspace_root: Path, tooling: ReleaseTooling, dry_run: bool
) -> Result[RemoteCoherenceItem, ReleaseError]:
    remote = get_ref_head_sha(workspace_root=workspace_root, repo=tooling.repo, ref=tooling.ref)
    if isinstance(remote, Err):
        return remote

    local = _local_head_sha(workspace_root=workspace_root)
    if dry_run:
        return Ok(
            RemoteCoherenceItem(
                repo_id="ms-dev-env",
                repo=tooling.repo,
                role="release tooling",
                target_sha=tooling.sha,
                local_sha=local,
                remote_ref=tooling.ref,
                remote_sha=remote.value,
                status="warning",
                detail="dry-run skips tooling reachability enforcement",
            )
        )

    ready = ensure_release_tooling_on_main(
        workspace_root=workspace_root,
        tooling_sha=tooling.sha,
    )
    if isinstance(ready, Err):
        return Ok(
            RemoteCoherenceItem(
                repo_id="ms-dev-env",
                repo=tooling.repo,
                role="release tooling",
                target_sha=tooling.sha,
                local_sha=local,
                remote_ref=tooling.ref,
                remote_sha=remote.value,
                status="blocked",
                detail="tooling SHA is not reachable from the workflow ref",
                hint=ready.error.hint,
            )
        )

    detail = "tooling SHA is reachable from the workflow ref"
    if local is not None and local != tooling.sha:
        detail = f"{detail}; local HEAD differs from selected tooling SHA"
    return Ok(
        RemoteCoherenceItem(
            repo_id="ms-dev-env",
            repo=tooling.repo,
            role="release tooling",
            target_sha=tooling.sha,
            local_sha=local,
            remote_ref=tooling.ref,
            remote_sha=remote.value,
            status="eligible",
            detail=detail,
        )
    )


def _assess_pinned_repo(
    *, workspace_root: Path, pinned: PinnedRepo, verify_ci: bool
) -> Result[RemoteCoherenceItem, ReleaseError]:
    readiness = probe_release_readiness(
        workspace_root=workspace_root,
        repo=pinned.repo,
        ref=pinned.repo.ref,
    )
    if isinstance(readiness, Err):
        return readiness
    local = readiness.value.local_head_sha
    remote = readiness.value.remote_head_sha

    fetchable = is_commit_fetchable(
        workspace_root=workspace_root,
        repo=pinned.repo.slug,
        sha=pinned.sha,
    )
    if isinstance(fetchable, Err):
        return fetchable
    if not fetchable.value:
        return Ok(
            RemoteCoherenceItem(
                repo_id=pinned.repo.id,
                repo=pinned.repo.slug,
                role="release input",
                target_sha=pinned.sha,
                local_sha=local,
                remote_ref=pinned.repo.ref,
                remote_sha=remote,
                status="blocked",
                detail="target SHA is not fetchable from GitHub",
                hint=f"Push or merge {pinned.repo.slug}@{pinned.sha} before release.",
            )
        )

    workflow = pinned.repo.required_ci_workflow_file
    if verify_ci and workflow is not None:
        green = is_ci_green_for_sha(
            workspace_root=workspace_root,
            repo=pinned.repo.slug,
            workflow=workflow,
            sha=pinned.sha,
        )
        if isinstance(green, Err):
            return green
        if not green.value:
            return Ok(
                RemoteCoherenceItem(
                    repo_id=pinned.repo.id,
                    repo=pinned.repo.slug,
                    role="release input",
                    target_sha=pinned.sha,
                    local_sha=local,
                    remote_ref=pinned.repo.ref,
                    remote_sha=remote,
                    status="blocked",
                    detail="target SHA does not have green CI",
                    hint=f"Wait for CI success on {pinned.repo.slug}@{pinned.sha}.",
                )
            )

    detail = "target SHA is fetchable"
    if workflow is not None:
        detail = f"{detail} and CI-green" if verify_ci else f"{detail}; CI already checked"
    if local is not None and remote is not None and local != remote:
        detail = f"{detail}; local HEAD differs from remote HEAD"
    if remote is not None and pinned.sha != remote:
        detail = f"{detail}; target is not current remote HEAD"

    return Ok(
        RemoteCoherenceItem(
            repo_id=pinned.repo.id,
            repo=pinned.repo.slug,
            role="release input",
            target_sha=pinned.sha,
            local_sha=local,
            remote_ref=pinned.repo.ref,
            remote_sha=remote,
            status="eligible",
            detail=detail,
        )
    )


def _local_head_sha(*, workspace_root: Path) -> str | None:
    from ms.release.infra.repos.git_ops import run_git_command

    head = run_git_command(cmd=["git", "rev-parse", "HEAD"], repo_root=workspace_root)
    if isinstance(head, Err):
        return None
    sha = head.value.strip()
    return sha if len(sha) == 40 else None
