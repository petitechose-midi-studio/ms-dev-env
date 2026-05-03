from __future__ import annotations

from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.output.console import ConsoleProtocol, Style
from ms.release.errors import ReleaseError
from ms.release.infra.github.gh_base import run_gh_process
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

    result = run_gh_process(cmd, cwd=workspace_root, timeout=GH_WATCH_TIMEOUT_SECONDS)
    if isinstance(result, Err):
        e = result.error
        return Err(
            ReleaseError(
                kind="workflow_failed",
                message="workflow run failed",
                hint=_failure_hint(stderr=e.stderr, repo_slug=repo_slug, run_id=run_id),
            )
        )
    return Ok(None)


def _failure_hint(*, stderr: str, repo_slug: str, run_id: int) -> str:
    lines: list[str] = []
    if stderr.strip():
        lines.append(stderr.strip())
    lines.append(f"https://github.com/{repo_slug}/actions/runs/{run_id}")
    lines.append(f"Inspect failed logs: gh run view {run_id} --repo {repo_slug} --log-failed")
    return "\n".join(lines)
