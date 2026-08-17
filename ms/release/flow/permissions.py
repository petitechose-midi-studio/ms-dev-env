from __future__ import annotations

from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.core.structured import as_str_dict, get_str
from ms.output.console import ConsoleProtocol, Style
from ms.release.domain import config
from ms.release.errors import ReleaseError
from ms.release.infra.github.client import viewer_permission
from ms.release.infra.github.gh_base import ensure_gh_auth, ensure_gh_available, gh_api_json

_ALLOWED_WRITE_PERMISSIONS = frozenset({"ADMIN", "MAINTAIN", "WRITE"})


def _ensure_repo_permissions(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    require_write: bool,
    repo_slug: str,
    release_environment: str | None,
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

    return _ensure_repo_write_contract(
        workspace_root=workspace_root,
        console=console,
        repo_slug=repo_slug,
        release_environment=release_environment,
        denied_message=denied_message,
        denied_hint=denied_hint,
    )


def _ensure_repo_write_contract(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    repo_slug: str,
    release_environment: str | None,
    denied_message: str,
    denied_hint: str,
) -> Result[None, ReleaseError]:
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

    ready = _ensure_release_repo_settings(
        workspace_root=workspace_root,
        repo_slug=repo_slug,
        release_environment=release_environment,
    )
    if isinstance(ready, Err):
        return ready

    return Ok(None)


def _ensure_release_repo_settings(
    *,
    workspace_root: Path,
    repo_slug: str,
    release_environment: str | None,
) -> Result[None, ReleaseError]:
    repo = gh_api_json(workspace_root=workspace_root, endpoint=f"repos/{repo_slug}")
    if isinstance(repo, Err):
        return repo

    settings = as_str_dict(repo.value)
    if settings is None:
        return Err(
            ReleaseError(
                kind="repo_failed",
                message=f"unexpected repository settings payload: {repo_slug}",
            )
        )
    if settings.get("allow_auto_merge") is not True:
        return Err(
            ReleaseError(
                kind="repo_failed",
                message=f"auto-merge is disabled for {repo_slug}",
                hint="Enable Settings > General > Allow auto-merge, then rerun.",
            )
        )
    if settings.get("allow_rebase_merge") is not True:
        return Err(
            ReleaseError(
                kind="repo_failed",
                message=f"rebase merge is disabled for {repo_slug}",
                hint="Enable Settings > General > Allow rebase merging, then rerun.",
            )
        )

    if release_environment is None:
        return Ok(None)

    environment = gh_api_json(
        workspace_root=workspace_root,
        endpoint=f"repos/{repo_slug}/environments/{release_environment}",
    )
    if isinstance(environment, Err):
        return Err(
            ReleaseError(
                kind="repo_failed",
                message=(
                    f"release environment is missing or inaccessible: "
                    f"{repo_slug}/{release_environment}"
                ),
                hint=environment.error.hint,
            )
        )
    environment_data = as_str_dict(environment.value)
    if environment_data is None or get_str(environment_data, "name") != release_environment:
        return Err(
            ReleaseError(
                kind="repo_failed",
                message=f"unexpected release environment payload: {repo_slug}",
                hint=release_environment,
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
        release_environment=config.DIST_RELEASE_ENV,
        denied_message="insufficient permission for distribution repo",
        denied_hint="You need WRITE/MAINTAIN/ADMIN on petitechose-midi-studio/distribution.",
    )


def ensure_core_release_permissions(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    require_write: bool,
) -> Result[None, ReleaseError]:
    return _ensure_repo_permissions(
        workspace_root=workspace_root,
        console=console,
        require_write=require_write,
        repo_slug=config.CORE_REPO_SLUG,
        release_environment=None,
        denied_message="insufficient permission for core repo",
        denied_hint=f"You need WRITE/MAINTAIN/ADMIN on {config.CORE_REPO_SLUG}.",
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
        release_environment=config.APP_RELEASE_ENV,
        denied_message="insufficient permission for app repo",
        denied_hint=f"You need WRITE/MAINTAIN/ADMIN on {config.APP_REPO_SLUG}.",
    )


def ensure_full_release_permissions(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
) -> Result[None, ReleaseError]:
    available = ensure_gh_available()
    if isinstance(available, Err):
        return available
    auth = ensure_gh_auth(workspace_root=workspace_root)
    if isinstance(auth, Err):
        return auth

    repos = (
        (
            config.CORE_REPO_SLUG,
            None,
            "insufficient permission for core repo",
            f"You need WRITE/MAINTAIN/ADMIN on {config.CORE_REPO_SLUG}.",
        ),
        (
            config.APP_REPO_SLUG,
            config.APP_RELEASE_ENV,
            "insufficient permission for app repo",
            f"You need WRITE/MAINTAIN/ADMIN on {config.APP_REPO_SLUG}.",
        ),
        (
            config.DIST_REPO_SLUG,
            config.DIST_RELEASE_ENV,
            "insufficient permission for distribution repo",
            "You need WRITE/MAINTAIN/ADMIN on petitechose-midi-studio/distribution.",
        ),
    )
    for repo_slug, environment, denied_message, denied_hint in repos:
        checked = _ensure_repo_write_contract(
            workspace_root=workspace_root,
            console=console,
            repo_slug=repo_slug,
            release_environment=environment,
            denied_message=denied_message,
            denied_hint=denied_hint,
        )
        if isinstance(checked, Err):
            return checked
    return Ok(None)
