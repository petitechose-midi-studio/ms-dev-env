from __future__ import annotations

from pathlib import Path

from ms.cli.release_guided_green_commit import select_green_commit
from ms.cli.selector import SelectorOption, SelectorResult, confirm_yn, select_one
from ms.core.result import Err, Ok, Result
from ms.output.console import ConsoleProtocol
from ms.release.domain.models import PinnedRepo, ReleaseBump, ReleaseChannel
from ms.release.errors import ReleaseError
from ms.release.flow.ci_gate import ensure_ci_green
from ms.release.flow.guided.bootstrap import ResumeChoice
from ms.release.flow.guided.menu_option import MenuOption
from ms.release.flow.guided.selection import Selection
from ms.release.view.guided_console import print_notes_status as print_notes_status_view


def to_guided_selection[T](choice: SelectorResult[T]) -> Selection[T]:
    return Selection(action=choice.action, value=choice.value, index=choice.index)


def select_menu[T](
    *,
    title: str,
    subtitle: str,
    options: list[MenuOption[T]],
    initial_index: int,
    allow_back: bool,
) -> SelectorResult[T]:
    return select_one(
        title=title,
        subtitle=subtitle,
        options=[
            SelectorOption(value=option.value, label=option.label, detail=option.detail)
            for option in options
        ],
        initial_index=initial_index,
        allow_back=allow_back,
    )


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


class GuidedCliDependencies:
    """CLI adapters shared by the app, content, and top-level release flows."""

    def select_channel(
        self, *, title: str, subtitle: str, initial_index: int, allow_back: bool
    ) -> Selection[ReleaseChannel]:
        return to_guided_selection(
            select_channel(
                title=title,
                subtitle=subtitle,
                initial_index=initial_index,
                allow_back=allow_back,
            )
        )

    def select_bump(
        self, *, title: str, subtitle: str, initial_index: int, allow_back: bool
    ) -> Selection[ReleaseBump]:
        return to_guided_selection(
            select_bump(
                title=title,
                subtitle=subtitle,
                initial_index=initial_index,
                allow_back=allow_back,
            )
        )

    def select_green_commit(
        self,
        *,
        workspace_root: Path,
        repo_slug: str,
        ref: str,
        workflow_file: str | None,
        title: str,
        subtitle: str,
        current_sha: str | None,
        initial_index: int,
        allow_back: bool,
    ) -> Result[Selection[str], ReleaseError]:
        selected = select_green_commit(
            workspace_root=workspace_root,
            repo_slug=repo_slug,
            ref=ref,
            workflow_file=workflow_file,
            title=title,
            subtitle=subtitle,
            current_sha=current_sha,
            initial_index=initial_index,
            allow_back=allow_back,
        )
        if isinstance(selected, Err):
            return selected
        return Ok(to_guided_selection(selected.value))

    def select_menu(
        self,
        *,
        title: str,
        subtitle: str,
        options: list[MenuOption[str]],
        initial_index: int,
        allow_back: bool,
    ) -> Selection[str]:
        return to_guided_selection(
            select_menu(
                title=title,
                subtitle=subtitle,
                options=options,
                initial_index=initial_index,
                allow_back=allow_back,
            )
        )

    def confirm(self, *, prompt: str) -> bool:
        return confirm_yn(prompt=prompt)

    def ensure_ci_green(
        self,
        *,
        workspace_root: Path,
        pinned: tuple[PinnedRepo, ...],
        allow_non_green: bool,
    ) -> Result[None, ReleaseError]:
        return ensure_ci_green(
            workspace_root=workspace_root,
            pinned=pinned,
            allow_non_green=allow_non_green,
        )

    def print_notes_status(
        self,
        *,
        console: ConsoleProtocol,
        notes_markdown: str | None,
        notes_path: str | None,
        notes_sha256: str | None,
        auto_label: str,
    ) -> None:
        print_notes_status(
            console=console,
            notes_markdown=notes_markdown,
            notes_path=notes_path,
            notes_sha256=notes_sha256,
            auto_label=auto_label,
        )
