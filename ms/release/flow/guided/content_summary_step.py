from __future__ import annotations

from dataclasses import replace

from ms.core.result import Err, Ok, Result
from ms.release.domain.models import ReleaseRepo
from ms.release.errors import ReleaseError

from .content_contracts import ContentGuidedDependencies
from .content_repo_pins import sha_map
from .fsm import StepOutcome, advance
from .menu_option import MenuOption
from .sessions import ContentReleaseSession


def step_content_summary(
    *,
    deps: ContentGuidedDependencies,
    session: ContentReleaseSession,
    release_repos: tuple[ReleaseRepo, ...],
) -> Result[StepOutcome[ContentReleaseSession], ReleaseError]:
    sha_by_id = sha_map(session)
    notes_label = session.notes_path or "none"
    options: list[MenuOption[str]] = [
        MenuOption(value="channel", label=f"Channel: {session.channel}", detail="Edit channel"),
        MenuOption(value="bump", label=f"Bump: {session.bump}", detail="Edit semantic bump"),
    ]
    for idx, repo in enumerate(release_repos):
        options.append(
            MenuOption(
                value=f"repo:{idx}",
                label=f"{repo.id}: {(sha_by_id.get(repo.id, 'unset'))[:12]}",
                detail=repo.slug,
            )
        )
    options.extend(
        [
            MenuOption(value="tag", label=f"Tag: {session.tag}", detail="Computed release tag"),
            MenuOption(
                value="notes",
                label=f"Notes file: {notes_label}",
                detail="Optional release notes",
            ),
            MenuOption(
                value="start",
                label="Start release",
                detail="Continue to final confirmation",
            ),
        ]
    )

    choice = deps.select_menu(
        title="Content Release Summary",
        subtitle="Select an item to edit, or start release",
        options=options,
        initial_index=session.idx_summary,
        allow_back=True,
    )
    if choice.action == "cancel":
        return Err(ReleaseError(kind="invalid_input", message="release cancelled"))
    if choice.action == "back":
        return Ok(advance(replace(session, step="tag")))
    if choice.value is None:
        return Err(ReleaseError(kind="invalid_input", message="missing summary action"))

    if choice.value == "channel":
        return Ok(
            advance(
                replace(
                    session,
                    step="channel",
                    idx_summary=choice.index,
                    return_to_summary=True,
                )
            )
        )
    if choice.value == "bump":
        return Ok(
            advance(
                replace(
                    session,
                    step="bump",
                    idx_summary=choice.index,
                    return_to_summary=True,
                )
            )
        )
    if choice.value.startswith("repo:"):
        idx = int(choice.value.split(":", 1)[1])
        return Ok(
            advance(
                replace(
                    session,
                    step="repo",
                    repo_cursor=max(0, min(idx, len(release_repos) - 1)),
                    idx_summary=choice.index,
                    return_to_summary=True,
                )
            )
        )
    if choice.value == "tag":
        return Ok(
            advance(
                replace(
                    session,
                    step="tag",
                    idx_summary=choice.index,
                    return_to_summary=True,
                )
            )
        )
    if choice.value == "notes":
        return Ok(
            advance(
                replace(
                    session,
                    step="notes",
                    idx_summary=choice.index,
                    return_to_summary=True,
                )
            )
        )
    if choice.value == "start":
        if session.tag is None:
            return Ok(
                advance(
                    replace(
                        session,
                        step="tag",
                        idx_summary=choice.index,
                        return_to_summary=True,
                    )
                )
            )
        return Ok(
            advance(
                replace(
                    session,
                    step="confirm",
                    idx_summary=choice.index,
                    return_to_summary=False,
                )
            )
        )

    return Err(
        ReleaseError(kind="invalid_input", message=f"unknown summary action: {choice.value}")
    )
