from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.output.console import ConsoleProtocol
from ms.release.domain.models import ReleaseRepo
from ms.release.errors import ReleaseError
from ms.release.flow.content_candidates import ContentCandidateAssessment

from .content_contracts import ContentGuidedDependencies
from .content_plan_state import resolve_content_release_plan
from .fsm import StepOutcome, advance
from .menu_option import MenuOption
from .sessions import ContentReleaseSession


def run_content_candidates_step(
    *,
    deps: ContentGuidedDependencies,
    workspace_root: Path,
    console: ConsoleProtocol,
    dry_run: bool,
    session: ContentReleaseSession,
    release_repos: tuple[ReleaseRepo, ...],
) -> Result[StepOutcome[ContentReleaseSession], ReleaseError]:
    plan = resolve_content_release_plan(
        deps=deps,
        workspace_root=workspace_root,
        session=session,
        release_repos=release_repos,
    )
    if isinstance(plan, Err):
        return plan

    assessed = deps.assess_content_candidates(
        workspace_root=workspace_root,
        plan=plan.value,
    )
    if isinstance(assessed, Err):
        return assessed

    choice = deps.select_menu(
        title="Content Release Candidates",
        subtitle="Review candidate availability before final confirmation",
        options=_candidate_options(assessments=assessed.value),
        initial_index=session.idx_candidates,
        allow_back=True,
    )
    if choice.action == "cancel":
        return Err(ReleaseError(kind="invalid_input", message="release cancelled"))
    if choice.action == "back":
        return Ok(advance(replace(session, step="summary")))
    if choice.value is None:
        return Err(ReleaseError(kind="invalid_input", message="missing candidate action"))

    if choice.value.startswith("target:") or choice.value == "refresh":
        return Ok(advance(replace(session, idx_candidates=choice.index)))

    if choice.value == "ensure":
        ensured = deps.ensure_content_candidates(
            workspace_root=workspace_root,
            console=console,
            plan=plan.value,
            dry_run=dry_run,
        )
        if isinstance(ensured, Err):
            return ensured
        return Ok(advance(replace(session, idx_candidates=choice.index)))

    if choice.value == "continue":
        return Ok(advance(replace(session, step="confirm", idx_candidates=choice.index)))

    return Err(
        ReleaseError(kind="invalid_input", message=f"unknown candidate action: {choice.value}")
    )


def _candidate_options(
    *,
    assessments: tuple[ContentCandidateAssessment, ...],
) -> list[MenuOption[str]]:
    options = [
        MenuOption(
            value=f"target:{item.target.id}",
            label=_candidate_label(item),
            detail=item.target.candidate_tag,
        )
        for item in assessments
    ]
    missing = [item for item in assessments if not item.available]
    if missing:
        options.extend(
            [
                MenuOption(
                    value="refresh",
                    label="Refresh candidate status",
                    detail="Re-check candidate metadata",
                ),
                MenuOption(
                    value="ensure",
                    label=f"Build missing candidates ({len(missing)})",
                    detail="Dispatch missing candidate workflows and wait for completion",
                ),
            ]
        )
    else:
        options.append(
            MenuOption(
                value="continue",
                label="Continue to final confirmation",
                detail="All required candidates are available",
            )
        )
    return options


def _candidate_label(item: ContentCandidateAssessment) -> str:
    status = item.state.value
    return f"{status}: {item.target.label}"
