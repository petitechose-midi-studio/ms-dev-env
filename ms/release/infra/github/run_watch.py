from __future__ import annotations

from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.output.console import ConsoleProtocol, Style
from ms.platform.process import run as run_process
from ms.release.errors import ReleaseError
from ms.release.infra.github.timeouts import GH_WATCH_TIMEOUT_SECONDS


def watch_run(
    *,
    workspace_root: Path,
    run_id: int,
    repo_slug: str,
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[None, ReleaseError]:
    if run_id <= 0:
        return Ok(None)
    cmd = ["gh", "run", "watch", "--repo", repo_slug, str(run_id), "--exit-status"]
    console.print(" ".join(cmd[:3]) + " ...", Style.DIM)
    if dry_run:
        return Ok(None)

    result = run_process(cmd, cwd=workspace_root, timeout=GH_WATCH_TIMEOUT_SECONDS)
    if isinstance(result, Err):
        e = result.error
        return Err(
            ReleaseError(
                kind="workflow_failed",
                message="workflow run failed",
                hint=e.stderr.strip() or None,
            )
        )
    return Ok(None)
