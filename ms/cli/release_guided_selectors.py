from __future__ import annotations

from typing import Literal

from ms.cli.selector import SelectorOption, SelectorResult, select_one
from ms.output.console import ConsoleProtocol
from ms.release.domain.models import ReleaseBump, ReleaseChannel
from ms.release.flow.guided.bootstrap import ResumeChoice
from ms.release.flow.guided.selection import Selection
from ms.release.view.guided_console import print_notes_status as print_notes_status_view

NoteAction = Literal["keep", "clear"]


def to_guided_selection[T](choice: SelectorResult[T]) -> Selection[T]:
    return Selection(action=choice.action, value=choice.value, index=choice.index)


def select_channel(
    *, title: str, subtitle: str, initial_index: int, allow_back: bool
) -> SelectorResult[ReleaseChannel]:
    options: list[SelectorOption[ReleaseChannel]] = [
        SelectorOption(value="stable", label="stable", detail="Production release"),
        SelectorOption(value="beta", label="beta", detail="Pre-release channel"),
    ]
    return select_one(
        title=title,
        subtitle=subtitle,
        options=options,
        initial_index=initial_index,
        allow_back=allow_back,
    )


def select_bump(
    *, title: str, subtitle: str, initial_index: int, allow_back: bool
) -> SelectorResult[ReleaseBump]:
    options: list[SelectorOption[ReleaseBump]] = [
        SelectorOption(value="patch", label="patch", detail="Bug fixes and minor updates"),
        SelectorOption(value="minor", label="minor", detail="Feature release"),
        SelectorOption(value="major", label="major", detail="Breaking release"),
    ]
    return select_one(
        title=title,
        subtitle=subtitle,
        options=options,
        initial_index=initial_index,
        allow_back=allow_back,
    )


def select_resume_or_new(*, title: str, subtitle: str) -> SelectorResult[ResumeChoice]:
    options: list[SelectorOption[ResumeChoice]] = [
        SelectorOption(value="resume", label="Resume", detail="Continue previous selections"),
        SelectorOption(value="new", label="Start new", detail="Discard previous selections"),
    ]
    return select_one(
        title=title,
        subtitle=subtitle,
        options=options,
        allow_back=False,
    )


def notes_step_selector(
    *,
    has_notes: bool,
    notes_path: str | None,
    title: str,
    subtitle: str,
    clear_detail: str,
) -> SelectorResult[NoteAction]:
    options: list[SelectorOption[NoteAction]] = [
        SelectorOption(
            value="keep",
            label=("Keep notes" if has_notes else "No notes configured"),
            detail=(notes_path if notes_path is not None else "Provide --notes-file to set notes"),
        ),
    ]
    if has_notes:
        options.append(
            SelectorOption(
                value="clear",
                label="Remove notes",
                detail=clear_detail,
            )
        )

    return select_one(
        title=title,
        subtitle=subtitle,
        options=options,
        initial_index=0,
        allow_back=True,
    )


def print_notes_status(
    *,
    console: ConsoleProtocol,
    notes_markdown: str | None,
    notes_path: str | None,
    notes_sha256: str | None,
    auto_label: str,
) -> None:
    print_notes_status_view(
        console=console,
        notes_markdown=notes_markdown,
        notes_path=notes_path,
        notes_sha256=notes_sha256,
        auto_label=auto_label,
    )
