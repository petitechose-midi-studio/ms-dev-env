from __future__ import annotations

from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.output.console import ConsoleProtocol, Style
from ms.release.domain import config
from ms.release.errors import ReleaseError
from ms.release.infra.github.client import ensure_gh_auth, ensure_gh_available, viewer_permission

_ALLOWED_WRITE_PERMISSIONS = frozenset({"ADMIN", "MAINTAIN", "WRITE"})


def _ensure_repo_permissions(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    require_write: bool,
    repo_slug: str,
    denied_message: str,
    denied_hint: str,
) -> Result[None, ReleaseError]:
    available = ensure_gh_available()
    if isinstance(available, Err):
        return available

    auth = ensure_gh_auth(workspace_root=workspace_root)
    if isinstance(auth, Err):
        return auth

    if not require_write:
        return Ok(None)

    permission = viewer_permission(workspace_root=workspace_root, repo=repo_slug)
    if isinstance(permission, Err):
        return permission

    if permission.value not in _ALLOWED_WRITE_PERMISSIONS:
        console.print(f"permission: {permission.value}", Style.DIM)
        return Err(
            ReleaseError(
                kind="permission_denied",
                message=denied_message,
                hint=denied_hint,
            )
        )

    return Ok(None)


def ensure_release_permissions(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    require_write: bool,
) -> Result[None, ReleaseError]:
    return _ensure_repo_permissions(
        workspace_root=workspace_root,
        console=console,
        require_write=require_write,
        repo_slug=config.DIST_REPO_SLUG,
        denied_message="insufficient permission for distribution repo",
        denied_hint="You need WRITE/MAINTAIN/ADMIN on petitechose-midi-studio/distribution.",
    )


def ensure_app_release_permissions(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    require_write: bool,
) -> Result[None, ReleaseError]:
    return _ensure_repo_permissions(
        workspace_root=workspace_root,
        console=console,
        require_write=require_write,
        repo_slug=config.APP_REPO_SLUG,
        denied_message="insufficient permission for app repo",
        denied_hint=f"You need WRITE/MAINTAIN/ADMIN on {config.APP_REPO_SLUG}.",
    )
