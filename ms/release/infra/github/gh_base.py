from __future__ import annotations

import json
import shutil
from pathlib import Path
from time import sleep
from typing import Literal

from ms.core.result import Err, Ok, Result
from ms.platform.process import ProcessError
from ms.platform.process import run as run_process
from ms.release.errors import ReleaseError
from ms.release.infra.github.timeouts import (
    GH_READ_RETRY_ATTEMPTS,
    GH_READ_RETRY_DELAY_SECONDS,
    GH_TIMEOUT_SECONDS,
)

_ReleaseErrorKind = Literal[
    "gh_missing",
    "gh_auth_required",
    "permission_denied",
    "invalid_input",
    "invalid_tag",
    "tag_exists",
    "ci_not_green",
    "repo_dirty",
    "repo_failed",
    "workflow_failed",
]


def _is_transient_gh_error(error: ProcessError) -> bool:
    text = f"{error.stderr}\n{error.stdout}".lower()
    markers = (
        "timed out",
        "timeout",
        "connection reset",
        "connection refused",
        "temporarily unavailable",
        "service unavailable",
        "bad gateway",
        "gateway timeout",
        "tls handshake timeout",
        "network is unreachable",
        "remote end hung up unexpectedly",
        "http 429",
        "http 500",
        "http 502",
        "http 503",
        "http 504",
    )
    if error.returncode == -1 and "timed out" in text:
        return True
    return any(marker in text for marker in markers)


def run_gh_read(
    *,
    workspace_root: Path,
    cmd: list[str],
    kind: _ReleaseErrorKind,
    message: str,
    hint: str | None = None,
    timeout: float = GH_TIMEOUT_SECONDS,
    retry_attempts: int = GH_READ_RETRY_ATTEMPTS,
) -> Result[str, ReleaseError]:
    attempts = max(1, retry_attempts)
    for attempt in range(attempts):
        result = run_process(cmd, cwd=workspace_root, timeout=timeout)
        if isinstance(result, Ok):
            return result

        error = result.error
        if attempt < attempts - 1 and _is_transient_gh_error(error):
            sleep(GH_READ_RETRY_DELAY_SECONDS * (attempt + 1))
            continue

        return Err(
            ReleaseError(
                kind=kind,
                message=message,
                hint=error.stderr.strip() or hint,
            )
        )

    return Err(ReleaseError(kind=kind, message=message, hint=hint))


def ensure_gh_available() -> Result[None, ReleaseError]:
    if shutil.which("gh") is None:
        return Err(
            ReleaseError(
                kind="gh_missing",
                message="gh: missing",
                hint="Install GitHub CLI: https://cli.github.com/",
            )
        )
    return Ok(None)


def ensure_gh_auth(*, workspace_root: Path) -> Result[None, ReleaseError]:
    result = run_process(["gh", "auth", "status"], cwd=workspace_root, timeout=GH_TIMEOUT_SECONDS)
    if isinstance(result, Err):
        return Err(
            ReleaseError(
                kind="gh_auth_required",
                message="gh auth required",
                hint="Run: gh auth login",
            )
        )
    return Ok(None)


def gh_api_json(*, workspace_root: Path, endpoint: str) -> Result[object, ReleaseError]:
    result = run_gh_read(
        workspace_root=workspace_root,
        cmd=["gh", "api", endpoint],
        kind="invalid_input",
        message=f"gh api failed: {endpoint}",
        hint=endpoint,
    )
    if isinstance(result, Err):
        return result

    try:
        obj: object = json.loads(result.value)
    except json.JSONDecodeError as e:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"gh api returned invalid JSON: {e}",
                hint=endpoint,
            )
        )

    return Ok(obj)
