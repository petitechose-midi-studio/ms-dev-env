from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ms.core.result import Err, Ok, Result
from ms.output.console import ConsoleProtocol
from ms.release.domain.models import ReleaseRepo
from ms.release.domain.open_control_models import OpenControlPreflightReport
from ms.release.errors import ReleaseError

from .content_contracts import ContentGuidedDependencies
from .content_repo_pins import set_sha, sha_map
from .menu_option import MenuOption
from .sessions import ContentReleaseSession

ContentBomStatus = Literal["aligned", "review_required", "blocked"]


@dataclass(frozen=True, slots=True)
class ContentBomAssessment:
    status: ContentBomStatus
    label: str
    detail: str
    core_sha: str | None
    report: OpenControlPreflightReport | None


@dataclass(frozen=True, slots=True)
class ContentBomStepChoice:
    action: Literal["summary", "repo"]
    session: ContentReleaseSession


def assess_content_bom(
    *,
    deps: ContentGuidedDependencies,
    workspace_root: Path,
    session: ContentReleaseSession,
    release_repos: tuple[ReleaseRepo, ...],
) -> ContentBomAssessment:
    core_repo = next((repo for repo in release_repos if repo.id == "core"), None)
    if core_repo is None:
        return ContentBomAssessment(
            status="blocked",
            label="BOM: core repo missing",
            detail="release config has no core repo",
            core_sha=None,
            report=None,
        )

    core_sha = sha_map(session).get(core_repo.id)
    if core_sha is None:
        return ContentBomAssessment(
            status="blocked",
            label="BOM: core unset",
            detail="select the core commit first",
            core_sha=None,
            report=None,
        )

    report = deps.preflight_open_control(workspace_root=workspace_root, core_sha=core_sha)
    if report.comparison is not None and report.comparison.status == "blocked":
        blockers = report.comparison.blockers
        detail = blockers[0] if blockers else "BOM validation is blocked"
        return ContentBomAssessment(
            status="blocked",
            label="BOM: blocked",
            detail=detail,
            core_sha=core_sha,
            report=report,
        )

    dirty_repos = report.dirty_repos()
    if dirty_repos:
        count = len(dirty_repos)
        return ContentBomAssessment(
            status="blocked",
            label=f"BOM: dirty ({count})",
            detail="open-control repos have local changes",
            core_sha=core_sha,
            report=report,
        )

    if report.oc_sdk.lock is None:
        return ContentBomAssessment(
            status="blocked",
            label="BOM: oc-sdk unavailable",
            detail=report.oc_sdk.error or "selected core commit has no readable oc-sdk.ini",
            core_sha=core_sha,
            report=report,
        )

    if report.comparison is not None and report.comparison.status == "promotion_required":
        count = len(
            [repo for repo in report.comparison.repos if repo.bom_sha != repo.workspace_sha]
        )
        label = f"BOM: review required ({count})" if count else "BOM: review required"
        return ContentBomAssessment(
            status="review_required",
            label=label,
            detail="selected core BOM differs from local open-control workspace",
            core_sha=core_sha,
            report=report,
        )

    if report.mismatches:
        count = len(report.mismatches)
        return ContentBomAssessment(
            status="review_required",
            label=f"BOM: review required ({count})",
            detail="selected core BOM differs from local open-control heads",
            core_sha=core_sha,
            report=report,
        )

    version = report.oc_sdk.lock.version
    return ContentBomAssessment(
        status="aligned",
        label=f"BOM: aligned (v{version})",
        detail="selected core matches local open-control workspace",
        core_sha=core_sha,
        report=report,
    )


def run_content_bom_step(
    *,
    deps: ContentGuidedDependencies,
    workspace_root: Path,
    console: ConsoleProtocol,
    dry_run: bool,
    session: ContentReleaseSession,
    release_repos: tuple[ReleaseRepo, ...],
) -> Result[ContentBomStepChoice, ReleaseError]:
    assessment = assess_content_bom(
        deps=deps,
        workspace_root=workspace_root,
        session=session,
        release_repos=release_repos,
    )
    if assessment.report is not None:
        deps.print_open_control_preflight(console=console, report=assessment.report)

    options: list[MenuOption[str]] = []
    if assessment.status == "aligned":
        options.append(
            MenuOption(
                value="summary",
                label="Continue",
                detail="BOM is aligned; return to release summary",
            )
        )
    if assessment.status == "review_required":
        options.append(
            MenuOption(
                value="promote",
                label="Promote BOM",
                detail="Create + merge a core PR to align oc-sdk with workspace heads",
            )
        )
    options.extend(
        [
            MenuOption(
                value="repo",
                label="Change core commit",
                detail="Pick another core SHA for this release",
            ),
            MenuOption(
                value="summary",
                label="Back to summary",
                detail=assessment.detail,
            ),
        ]
    )

    choice = deps.select_menu(
        title="OpenControl BOM",
        subtitle=assessment.detail,
        options=options,
        initial_index=0,
        allow_back=True,
    )
    if choice.action == "cancel":
        return Err(ReleaseError(kind="invalid_input", message="release cancelled"))
    if choice.action == "back" or choice.value == "summary":
        return Ok(ContentBomStepChoice(action="summary", session=session))
    if choice.value == "repo":
        return Ok(ContentBomStepChoice(action="repo", session=session))
    if choice.value == "promote":
        promoted = deps.promote_open_control_bom(
            workspace_root=workspace_root,
            console=console,
            dry_run=dry_run,
        )
        if isinstance(promoted, Err):
            return promoted

        if promoted.value.pr.kind == "merged_pr":
            console.success(f"Core BOM PR merged: {promoted.value.pr.display()}")
        else:
            console.success(
                f"Core BOM already aligned on main: {promoted.value.merged_core_sha[:12]}"
            )
        updated = set_sha(
            session,
            release_repos=release_repos,
            repo_id="core",
            sha=promoted.value.merged_core_sha,
        )
        return Ok(ContentBomStepChoice(action="summary", session=updated))

    return Err(ReleaseError(kind="invalid_input", message=f"unknown BOM action: {choice.value}"))
