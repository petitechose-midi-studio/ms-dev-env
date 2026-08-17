from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from ms.core.result import Ok
from ms.output.console import MockConsole
from ms.release.flow.guided.sessions import (
    new_app_session,
    new_content_session,
    save_app_session,
    save_content_session,
)
from ms.release.flow.release_status import print_release_status


def test_release_status_reports_no_unfinished_session(tmp_path: Path) -> None:
    console = MockConsole()

    result = print_release_status(workspace_root=tmp_path, console=console)

    assert isinstance(result, Ok)
    assert console.text == "OK No unfinished guided release session"


def test_release_status_summarizes_both_sessions_and_resume_command(tmp_path: Path) -> None:
    app = replace(
        new_app_session(created_by="maintainer", notes_path=None),
        step="confirm",
        channel="stable",
        tag="v0.2.0",
        repo_sha="a" * 40,
    )
    content = replace(
        new_content_session(created_by="maintainer", notes_path=None),
        step="candidates",
        channel="beta",
        tag="v0.3.0-beta.1",
        repo_shas=(("core", "b" * 40), ("plugin-bitwig", "c" * 40)),
    )
    assert isinstance(save_app_session(workspace_root=tmp_path, session=app), Ok)
    assert isinstance(save_content_session(workspace_root=tmp_path, session=content), Ok)
    console = MockConsole()

    result = print_release_status(workspace_root=tmp_path, console=console)

    assert isinstance(result, Ok)
    assert "app: v0.2.0 | stable | step confirm | source aaaaaaaaaaaa" in console.text
    assert "content: v0.3.0-beta.1 | beta | step candidates | pins 2" in console.text
    assert "resume: uv run ms release --watch" in console.text
