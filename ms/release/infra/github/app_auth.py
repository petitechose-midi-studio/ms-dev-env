from __future__ import annotations

import base64
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

from ms.core.result import Err, Ok, Result
from ms.core.structured import as_str_dict
from ms.release.errors import ReleaseError
from ms.release.infra.github.gh_base import run_gh_process
from ms.release.infra.github.timeouts import GH_TIMEOUT_SECONDS

_APP_ID_ENV = "MS_RELEASE_GITHUB_APP_ID"
_APP_PRIVATE_KEY_PATH_ENV = "MS_RELEASE_GITHUB_APP_PRIVATE_KEY_PATH"


@dataclass(frozen=True, slots=True)
class GitHubAppCredentials:
    app_id: str
    private_key_path: Path


def release_app_token_for_repo(
    *,
    workspace_root: Path,
    repo_slug: str,
) -> Result[str | None, ReleaseError]:
    owner = _repo_owner(repo_slug)
    if owner is None:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"invalid GitHub repository slug: {repo_slug}",
                hint="Expected owner/name.",
            )
        )

    creds = _load_credentials(owner=owner)
    if isinstance(creds, Err):
        return creds
    if creds.value is None:
        return Ok(None)

    jwt = _create_app_jwt(credentials=creds.value)
    if isinstance(jwt, Err):
        return jwt

    installation_id = _repo_installation_id(
        workspace_root=workspace_root,
        repo_slug=repo_slug,
        jwt=jwt.value,
    )
    if isinstance(installation_id, Err):
        return installation_id

    token = _installation_token(
        workspace_root=workspace_root,
        installation_id=installation_id.value,
        jwt=jwt.value,
    )
    if isinstance(token, Err):
        return token

    return Ok(token.value)


def _repo_owner(repo_slug: str) -> str | None:
    parts = repo_slug.split("/", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return None
    return parts[0]


def _load_credentials(*, owner: str) -> Result[GitHubAppCredentials | None, ReleaseError]:
    app_id = _owner_env(owner=owner, base=_APP_ID_ENV)
    key_path = _owner_env(owner=owner, base=_APP_PRIVATE_KEY_PATH_ENV)

    if app_id is None and key_path is None:
        return Ok(None)
    if not app_id or not key_path:
        suffix = _owner_suffix(owner)
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"incomplete release GitHub App config for {owner}",
                hint=(
                    f"Set {_APP_ID_ENV}_{suffix} and "
                    f"{_APP_PRIVATE_KEY_PATH_ENV}_{suffix}, or set the unsuffixed defaults."
                ),
            )
        )

    return Ok(GitHubAppCredentials(app_id=app_id, private_key_path=Path(key_path)))


def _owner_env(*, owner: str, base: str) -> str | None:
    return os.environ.get(f"{base}_{_owner_suffix(owner)}") or os.environ.get(base)


def _owner_suffix(owner: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in owner.upper())


def _create_app_jwt(*, credentials: GitHubAppCredentials) -> Result[str, ReleaseError]:
    try:
        pem = credentials.private_key_path.read_bytes()
    except OSError as e:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message="failed to read release GitHub App private key",
                hint=f"{credentials.private_key_path}: {e}",
            )
        )

    try:
        key = serialization.load_pem_private_key(pem, password=None)
    except ValueError as e:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message="invalid release GitHub App private key",
                hint=str(e),
            )
        )

    if not isinstance(key, RSAPrivateKey):
        return Err(
            ReleaseError(
                kind="invalid_input",
                message="release GitHub App private key must be RSA",
                hint=str(credentials.private_key_path),
            )
        )

    now = int(time.time())
    header = {"alg": "RS256", "typ": "JWT"}
    payload = {
        "iat": now - 60,
        "exp": now + 9 * 60,
        "iss": credentials.app_id,
    }
    message = (
        _b64url(json.dumps(header, separators=(",", ":")).encode("utf-8"))
        + "."
        + _b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    ).encode("ascii")
    signature = key.sign(message, padding.PKCS1v15(), hashes.SHA256())
    return Ok(message.decode("ascii") + "." + _b64url(signature))


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _repo_installation_id(
    *,
    workspace_root: Path,
    repo_slug: str,
    jwt: str,
) -> Result[int, ReleaseError]:
    result = run_gh_process(
        ["gh", "api", f"/repos/{repo_slug}/installation"],
        cwd=workspace_root,
        timeout=GH_TIMEOUT_SECONDS,
        env={"GH_TOKEN": jwt},
    )
    if isinstance(result, Err):
        e = result.error
        return Err(
            ReleaseError(
                kind="permission_denied",
                message=f"release GitHub App is not installed on {repo_slug}",
                hint=e.stderr.strip() or "Install the release GitHub App on this repository.",
            )
        )

    parsed = _parse_json_object(payload=result.value, label=f"{repo_slug} installation")
    if isinstance(parsed, Err):
        return parsed

    installation_id = parsed.value.get("id")
    if not isinstance(installation_id, int):
        return Err(
            ReleaseError(
                kind="invalid_input",
                message="GitHub installation payload is missing id",
                hint=repo_slug,
            )
        )
    return Ok(installation_id)


def _installation_token(
    *,
    workspace_root: Path,
    installation_id: int,
    jwt: str,
) -> Result[str, ReleaseError]:
    result = run_gh_process(
        ["gh", "api", "--method", "POST", f"/app/installations/{installation_id}/access_tokens"],
        cwd=workspace_root,
        timeout=GH_TIMEOUT_SECONDS,
        env={"GH_TOKEN": jwt},
    )
    if isinstance(result, Err):
        e = result.error
        return Err(
            ReleaseError(
                kind="permission_denied",
                message="failed to mint release GitHub App installation token",
                hint=e.stderr.strip() or f"installation={installation_id}",
            )
        )

    parsed = _parse_json_object(payload=result.value, label="installation access token")
    if isinstance(parsed, Err):
        return parsed

    token = parsed.value.get("token")
    if not isinstance(token, str) or not token:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message="GitHub installation token payload is missing token",
                hint=f"installation={installation_id}",
            )
        )
    return Ok(token)


def _parse_json_object(*, payload: str, label: str) -> Result[dict[str, object], ReleaseError]:
    try:
        obj: object = json.loads(payload)
    except json.JSONDecodeError as e:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"invalid JSON from GitHub API: {label}",
                hint=str(e),
            )
        )

    data = as_str_dict(obj)
    if data is None:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"unexpected GitHub API payload: {label}",
            )
        )
    return Ok(data)
