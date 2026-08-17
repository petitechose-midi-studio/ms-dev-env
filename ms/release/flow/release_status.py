from __future__ import annotations

from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.output.console import ConsoleProtocol, Style
from ms.release.errors import ReleaseError
from ms.release.flow.guided.sessions import load_app_session, load_content_session


def print_release_status(
    *, workspace_root: Path, console: ConsoleProtocol
) -> Result[None, ReleaseError]:
    app = load_app_session(workspace_root=workspace_root)
    if isinstance(app, Err):
        return app
    content = load_content_session(workspace_root=workspace_root)
    if isinstance(content, Err):
        return content

    sessions = tuple(session for session in (app.value, content.value) if session is not None)
    if not sessions:
        console.success("No unfinished guided release session")
        return Ok(None)

    console.header("Unfinished release sessions")
    for session in sessions:
        channel = session.channel or "unset"
        tag = session.tag or "unset"
        if session.product == "app":
            detail = f"source {(session.repo_sha or 'unset')[:12]}"
        else:
            detail = f"pins {len(session.repo_shas)}"
        console.print(
            f"{session.product}: {tag} | {channel} | step {session.step} | {detail}",
            Style.DEFAULT,
        )
        console.print(
            f"  id {session.release_id} | created {session.created_at}",
            Style.DIM,
        )
    console.print("resume: uv run ms release --watch", Style.DIM)
    return Ok(None)
