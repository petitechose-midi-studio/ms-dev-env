from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from time import monotonic, sleep
from typing import cast

from ms.core.result import Err, Ok, Result
from ms.output.console import ConsoleProtocol, Style
from ms.release.errors import ReleaseError
from ms.release.infra.github.gh_base import run_gh_process
from ms.release.infra.github.timeouts import GH_TIMEOUT_SECONDS, GH_WATCH_TIMEOUT_SECONDS

_POLL_INTERVAL_SECONDS = 15.0
_HEARTBEAT_SECONDS = 60.0
_SUCCESS_CONCLUSIONS = frozenset({"success", "skipped", "neutral"})
_ACTIVE_STATUSES = frozenset({"queued", "in_progress", "requested", "waiting", "pending"})

_SleepFn = Callable[[float], None]
_ClockFn = Callable[[], float]
_ProgressKey = tuple[str, int, int, tuple[str, ...], tuple[str, ...], str | None]


@dataclass(frozen=True, slots=True)
class _RunJob:
    name: str
    status: str
    conclusion: str | None


@dataclass(frozen=True, slots=True)
class _RunSnapshot:
    status: str
    conclusion: str | None
    jobs: tuple[_RunJob, ...]


def watch_run(
    *,
    workspace_root: Path,
    run_id: int,
    repo_slug: str,
    console: ConsoleProtocol,
    dry_run: bool,
    poll_interval_seconds: float = _POLL_INTERVAL_SECONDS,
    timeout_seconds: float = GH_WATCH_TIMEOUT_SECONDS,
    sleep_fn: _SleepFn = sleep,
    clock_fn: _ClockFn = monotonic,
) -> Result[None, ReleaseError]:
    if run_id <= 0:
        return Ok(None)

    run_url = f"https://github.com/{repo_slug}/actions/runs/{run_id}"
    console.print(f"watching: {run_url}", Style.DIM)
    if dry_run:
        return Ok(None)

    deadline = clock_fn() + timeout_seconds
    last_key: _ProgressKey | None = None
    last_printed_at = 0.0
    while True:
        snapshot = _fetch_run_snapshot(
            workspace_root=workspace_root,
            repo_slug=repo_slug,
            run_id=run_id,
        )
        if isinstance(snapshot, Err):
            return snapshot

        now = clock_fn()
        key = _progress_key(snapshot.value)
        if key != last_key:
            console.print(_progress_line(snapshot.value), Style.DIM)
            last_key = key
            last_printed_at = now
        elif now - last_printed_at >= _HEARTBEAT_SECONDS:
            console.print(_heartbeat_line(snapshot.value), Style.DIM)
            last_printed_at = now

        if snapshot.value.status == "completed":
            conclusion = (snapshot.value.conclusion or "").lower()
            if conclusion in _SUCCESS_CONCLUSIONS:
                return Ok(None)
            return Err(
                ReleaseError(
                    kind="workflow_failed",
                    message="workflow run failed",
                    hint=_failure_hint(
                        stderr="",
                        repo_slug=repo_slug,
                        run_id=run_id,
                        failed_jobs=_failed_job_names(snapshot.value),
                    ),
                )
            )

        if now >= deadline:
            return Err(
                ReleaseError(
                    kind="workflow_failed",
                    message="workflow run timed out",
                    hint=_failure_hint(stderr="", repo_slug=repo_slug, run_id=run_id),
                )
            )

        sleep_fn(max(0.1, poll_interval_seconds))


def _fetch_run_snapshot(
    *, workspace_root: Path, repo_slug: str, run_id: int
) -> Result[_RunSnapshot, ReleaseError]:
    cmd = [
        "gh",
        "run",
        "view",
        str(run_id),
        "--repo",
        repo_slug,
        "--json",
        "status,conclusion,jobs",
    ]
    result = run_gh_process(cmd, cwd=workspace_root, timeout=GH_TIMEOUT_SECONDS)
    if isinstance(result, Err):
        e = result.error
        return Err(
            ReleaseError(
                kind="workflow_failed",
                message="failed to inspect workflow run",
                hint=_failure_hint(stderr=e.stderr, repo_slug=repo_slug, run_id=run_id),
            )
        )

    try:
        obj: object = json.loads(result.value)
    except json.JSONDecodeError as error:
        return Err(
            ReleaseError(
                kind="workflow_failed",
                message="gh run view returned invalid JSON",
                hint=f"{error}\n{_failure_hint(stderr='', repo_slug=repo_slug, run_id=run_id)}",
            )
        )

    if not isinstance(obj, dict):
        return Err(
            ReleaseError(
                kind="workflow_failed",
                message="gh run view returned unexpected payload",
                hint=_failure_hint(stderr="", repo_slug=repo_slug, run_id=run_id),
            )
        )
    data = cast("dict[str, object]", obj)

    return Ok(
        _RunSnapshot(
            status=_as_str(data.get("status")) or "unknown",
            conclusion=_as_optional_str(data.get("conclusion")),
            jobs=_parse_jobs(data.get("jobs")),
        )
    )


def _parse_jobs(raw: object) -> tuple[_RunJob, ...]:
    if not isinstance(raw, list):
        return ()

    jobs: list[_RunJob] = []
    for item in cast("list[object]", raw):
        if not isinstance(item, dict):
            continue
        data = cast("dict[str, object]", item)
        name = _as_str(data.get("name")) or "<unnamed>"
        status = _as_str(data.get("status")) or "unknown"
        conclusion = _as_optional_str(data.get("conclusion"))
        jobs.append(_RunJob(name=name, status=status, conclusion=conclusion))
    return tuple(jobs)


def _progress_line(snapshot: _RunSnapshot) -> str:
    jobs = snapshot.jobs
    if not jobs:
        return f"progress: {snapshot.status}"

    done = sum(1 for job in jobs if job.status == "completed")
    active = [job.name for job in jobs if job.status in _ACTIVE_STATUSES]
    failed = _failed_job_names(snapshot)

    parts = [f"progress: {snapshot.status}", f"jobs {done}/{len(jobs)}"]
    if failed:
        parts.append(f"failed: {_join_names(failed)}")
    elif active:
        parts.append(f"active: {_join_names(active)}")
    elif snapshot.conclusion:
        parts.append(f"result: {snapshot.conclusion}")
    return " | ".join(parts)


def _heartbeat_line(snapshot: _RunSnapshot) -> str:
    progress = _progress_line(snapshot)
    if progress.startswith("progress: "):
        return "still: " + progress.removeprefix("progress: ")
    return "still: " + progress


def _progress_key(snapshot: _RunSnapshot) -> _ProgressKey:
    jobs = snapshot.jobs
    done = sum(1 for job in jobs if job.status == "completed")
    active = tuple(job.name for job in jobs if job.status in _ACTIVE_STATUSES)
    failed = _failed_job_names(snapshot)
    return (snapshot.status, done, len(jobs), active, failed, snapshot.conclusion)


def _failed_job_names(snapshot: _RunSnapshot) -> tuple[str, ...]:
    return tuple(
        job.name
        for job in snapshot.jobs
        if job.status == "completed"
        and (job.conclusion or "").lower() not in _SUCCESS_CONCLUSIONS
    )


def _join_names(names: tuple[str, ...] | list[str]) -> str:
    visible = tuple(names[:3])
    suffix = "" if len(names) <= 3 else f", +{len(names) - 3} more"
    return ", ".join(visible) + suffix


def _as_str(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _as_optional_str(value: object) -> str | None:
    if value is None:
        return None
    return _as_str(value)


def _failure_hint(
    *, stderr: str, repo_slug: str, run_id: int, failed_jobs: tuple[str, ...] = ()
) -> str:
    lines: list[str] = []
    if stderr.strip():
        lines.append(stderr.strip())
    if failed_jobs:
        lines.append(f"failed jobs: {_join_names(failed_jobs)}")
    lines.append(f"https://github.com/{repo_slug}/actions/runs/{run_id}")
    lines.append(f"Inspect failed logs: gh run view {run_id} --repo {repo_slug} --log-failed")
    return "\n".join(lines)
