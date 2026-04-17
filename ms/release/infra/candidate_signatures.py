from __future__ import annotations

import os
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.platform.process import run as run_process
from ms.release.errors import ReleaseError

_CANDIDATE_SIGN_TIMEOUT_SECONDS = 120.0
_CANDIDATE_SECRET_ENV = "MS_CANDIDATE_ED25519_SK"
_CANDIDATE_PUBLIC_ENV = "MS_CANDIDATE_ED25519_PK"
_CANDIDATE_TMP_PUBLIC_ENV = "MS_CANDIDATE_TMP_PK"


def sign_candidate_manifest(
    *,
    workspace_root: Path,
    manifest_path: Path,
    sig_path: Path,
    key_env: str = _CANDIDATE_SECRET_ENV,
) -> Result[None, ReleaseError]:
    return _run_detached_signature_tool(
        workspace_root=workspace_root,
        args=[
            "sign",
            "--in",
            str(manifest_path),
            "--out",
            str(sig_path),
            "--key-env",
            key_env,
        ],
    )


def verify_candidate_manifest(
    *,
    workspace_root: Path,
    manifest_path: Path,
    sig_path: Path,
    pk_env: str = _CANDIDATE_PUBLIC_ENV,
) -> Result[None, ReleaseError]:
    return _run_detached_signature_tool(
        workspace_root=workspace_root,
        args=[
            "verify",
            "--in",
            str(manifest_path),
            "--sig",
            str(sig_path),
            "--pk-env",
            pk_env,
        ],
    )


def derive_candidate_public_key(
    *,
    workspace_root: Path,
    key_env: str = _CANDIDATE_SECRET_ENV,
) -> Result[str, ReleaseError]:
    distribution_root = workspace_root / "distribution"
    cargo_toml = distribution_root / "Cargo.toml"
    if not cargo_toml.exists():
        return Err(
            ReleaseError(
                kind="invalid_input",
                message="distribution repo missing; cannot derive candidate public key",
                hint=str(cargo_toml),
            )
        )

    env = os.environ.copy()
    cmd = ["cargo", "run", "-p", "ms-dist-manifest", "--", "pubkey", "--key-env", key_env]
    result = run_process(
        cmd,
        cwd=distribution_root,
        env=env,
        timeout=_CANDIDATE_SIGN_TIMEOUT_SECONDS,
    )
    if isinstance(result, Err):
        return Err(
            ReleaseError(
                kind="verification_failed",
                message="candidate public key derivation failed",
                hint=result.error.stderr.strip() or None,
            )
        )
    return Ok(result.value.strip())


def verify_candidate_manifest_with_public_key(
    *,
    workspace_root: Path,
    manifest_path: Path,
    sig_path: Path,
    public_key_b64: str,
) -> Result[None, ReleaseError]:
    return _run_detached_signature_tool(
        workspace_root=workspace_root,
        args=[
            "verify",
            "--in",
            str(manifest_path),
            "--sig",
            str(sig_path),
            "--pk-env",
            _CANDIDATE_TMP_PUBLIC_ENV,
        ],
        env_overrides={_CANDIDATE_TMP_PUBLIC_ENV: public_key_b64},
    )


def _run_detached_signature_tool(
    *,
    workspace_root: Path,
    args: list[str],
    env_overrides: dict[str, str] | None = None,
) -> Result[None, ReleaseError]:
    distribution_root = workspace_root / "distribution"
    cargo_toml = distribution_root / "Cargo.toml"
    if not cargo_toml.exists():
        return Err(
            ReleaseError(
                kind="invalid_input",
                message="distribution repo missing; cannot run candidate signature backend",
                hint=str(cargo_toml),
            )
        )

    env = os.environ.copy()
    if env_overrides is not None:
        env.update(env_overrides)
    cmd = ["cargo", "run", "-p", "ms-dist-manifest", "--", *args]
    result = run_process(
        cmd,
        cwd=distribution_root,
        env=env,
        timeout=_CANDIDATE_SIGN_TIMEOUT_SECONDS,
    )
    if isinstance(result, Err):
        return Err(
            ReleaseError(
                kind="verification_failed",
                message="candidate signature command failed",
                hint=result.error.stderr.strip() or None,
            )
        )
    return Ok(None)
