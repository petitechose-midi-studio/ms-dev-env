from __future__ import annotations

import base64
import os
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from ms.core.result import Err, Ok, Result
from ms.release.errors import ReleaseError

_CANDIDATE_SECRET_ENV = "MS_CANDIDATE_ED25519_SK"
_CANDIDATE_PUBLIC_ENV = "MS_CANDIDATE_ED25519_PK"


def sign_candidate_manifest(
    *,
    workspace_root: Path,
    manifest_path: Path,
    sig_path: Path,
    key_env: str = _CANDIDATE_SECRET_ENV,
) -> Result[None, ReleaseError]:
    del workspace_root
    signing_key = _load_signing_key(key_env=key_env)
    if isinstance(signing_key, Err):
        return signing_key

    manifest_bytes = _read_bytes(manifest_path=manifest_path)
    if isinstance(manifest_bytes, Err):
        return manifest_bytes

    signature = signing_key.value.sign(manifest_bytes.value)
    sig_b64 = base64.b64encode(signature).decode("ascii")
    try:
        sig_path.write_text(f"{sig_b64}\n", encoding="utf-8")
    except OSError as exc:
        return Err(
            ReleaseError(
                kind="verification_failed",
                message="failed to write candidate signature",
                hint=str(exc),
            )
        )
    return Ok(None)


def verify_candidate_manifest(
    *,
    workspace_root: Path,
    manifest_path: Path,
    sig_path: Path,
    pk_env: str = _CANDIDATE_PUBLIC_ENV,
) -> Result[None, ReleaseError]:
    del workspace_root
    public_key = _load_public_key(pk_env=pk_env)
    if isinstance(public_key, Err):
        return public_key
    return _verify_with_key(
        manifest_path=manifest_path,
        sig_path=sig_path,
        public_key=public_key.value,
    )


def derive_candidate_public_key(
    *,
    workspace_root: Path,
    key_env: str = _CANDIDATE_SECRET_ENV,
) -> Result[str, ReleaseError]:
    del workspace_root
    signing_key = _load_signing_key(key_env=key_env)
    if isinstance(signing_key, Err):
        return signing_key
    encoded = base64.b64encode(
        signing_key.value.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    ).decode("ascii")
    return Ok(encoded)


def verify_candidate_manifest_with_public_key(
    *,
    workspace_root: Path,
    manifest_path: Path,
    sig_path: Path,
    public_key_b64: str,
) -> Result[None, ReleaseError]:
    del workspace_root
    public_key = _decode_public_key(public_key_b64)
    if isinstance(public_key, Err):
        return public_key
    return _verify_with_key(
        manifest_path=manifest_path,
        sig_path=sig_path,
        public_key=public_key.value,
    )


def _verify_with_key(
    *,
    manifest_path: Path,
    sig_path: Path,
    public_key: Ed25519PublicKey,
) -> Result[None, ReleaseError]:
    manifest_bytes = _read_bytes(manifest_path=manifest_path)
    if isinstance(manifest_bytes, Err):
        return manifest_bytes
    signature = _read_signature(sig_path=sig_path)
    if isinstance(signature, Err):
        return signature
    try:
        public_key.verify(signature.value, manifest_bytes.value)
    except InvalidSignature:
        return Err(
            ReleaseError(
                kind="verification_failed",
                message="candidate signature verify failed",
            )
        )
    return Ok(None)


def _load_signing_key(*, key_env: str) -> Result[Ed25519PrivateKey, ReleaseError]:
    seed = _load_b64_env(env_name=key_env)
    if isinstance(seed, Err):
        return seed
    try:
        return Ok(Ed25519PrivateKey.from_private_bytes(seed.value))
    except ValueError as exc:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message="invalid candidate signing key bytes",
                hint=str(exc),
            )
        )


def _load_public_key(*, pk_env: str) -> Result[Ed25519PublicKey, ReleaseError]:
    public_key_b64 = os.environ.get(pk_env)
    if not public_key_b64:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message="candidate public key env var missing",
                hint=pk_env,
            )
        )
    return _decode_public_key(public_key_b64)


def _decode_public_key(public_key_b64: str) -> Result[Ed25519PublicKey, ReleaseError]:
    public_key_raw = _decode_b64_32(public_key_b64, label="candidate public key")
    if isinstance(public_key_raw, Err):
        return public_key_raw
    try:
        return Ok(Ed25519PublicKey.from_public_bytes(public_key_raw.value))
    except ValueError as exc:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message="invalid candidate public key bytes",
                hint=str(exc),
            )
        )


def _load_b64_env(*, env_name: str) -> Result[bytes, ReleaseError]:
    value = os.environ.get(env_name)
    if not value:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message="candidate signing key env var missing",
                hint=env_name,
            )
        )
    return _decode_b64_32(value, label="candidate signing key")


def _decode_b64_32(value: str, *, label: str) -> Result[bytes, ReleaseError]:
    try:
        decoded = base64.b64decode(value.strip(), validate=True)
    except ValueError as exc:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"{label} is not valid base64",
                hint=str(exc),
            )
        )
    if len(decoded) != 32:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"{label} must be 32 bytes",
                hint=f"got {len(decoded)} bytes",
            )
        )
    return Ok(decoded)


def _read_bytes(*, manifest_path: Path) -> Result[bytes, ReleaseError]:
    try:
        return Ok(manifest_path.read_bytes())
    except OSError as exc:
        return Err(
            ReleaseError(
                kind="verification_failed",
                message="failed to read candidate manifest",
                hint=str(exc),
            )
        )


def _read_signature(*, sig_path: Path) -> Result[bytes, ReleaseError]:
    try:
        encoded = sig_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        return Err(
            ReleaseError(
                kind="verification_failed",
                message="failed to read candidate signature",
                hint=str(exc),
            )
        )
    try:
        return Ok(base64.b64decode(encoded, validate=True))
    except ValueError as exc:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message="candidate signature is not valid base64",
                hint=str(exc),
            )
        )
