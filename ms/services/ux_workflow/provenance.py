from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from ms.core.hashing import sha256_file
from ms.platform.files import atomic_write_text

from .models import UxWorkflow, UxWorkflowApp, UxWorkflowRun

_RUN_MANIFEST_NAME = "run-manifest.json"


def write_run_manifest(
    *, app: UxWorkflowApp, workflow: UxWorkflow, executable: Path,
    executable_sha256: str, output_dir: Path, run: UxWorkflowRun, run_utc: str,
) -> None:
    captures = sorted(output_dir.glob("*.bmp"))
    manifest = {
        "schema": 1,
        "app": app.name,
        "workflow": workflow.relative_path,
        "workflow_sha256": sha256_file(workflow.path),
        "executable": executable.name,
        "executable_sha256": executable_sha256,
        "run_utc": run_utc,
        "exit_code": run.exit_code,
        "verified": run.ok,
        "captures": [path.name for path in captures],
        "capture_sha256": {path.name: sha256_file(path) for path in captures},
    }
    atomic_write_text(
        output_dir / _RUN_MANIFEST_NAME,
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )


def read_run_manifest(output_dir: Path) -> dict[str, object] | None:
    try:
        payload = json.loads((output_dir / _RUN_MANIFEST_NAME).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    manifest = cast(dict[str, object], payload)
    if manifest.get("schema") != 1:
        return None
    required = (
        "workflow", "workflow_sha256", "captures", "capture_sha256",
        "executable", "executable_sha256", "run_utc", "verified",
    )
    if any(field not in manifest for field in required):
        return None
    return manifest


def run_manifest_provenance(
    *, workflow: UxWorkflow, output_dir: Path, manifest: dict[str, object] | None,
) -> str:
    if manifest is None:
        return "missing"
    if manifest["verified"] is not True:
        return "failed"
    captures = sorted(output_dir.glob("*.bmp"))
    capture_names = [path.name for path in captures]
    expected_capture_hashes = manifest["capture_sha256"]
    if not isinstance(expected_capture_hashes, dict):
        return "stale"
    capture_hashes = cast(dict[str, object], expected_capture_hashes)
    if (
        manifest["workflow"] != workflow.relative_path
        or manifest["workflow_sha256"] != sha256_file(workflow.path)
        or manifest["captures"] != capture_names
        or any(capture_hashes.get(path.name) != sha256_file(path) for path in captures)
    ):
        return "stale"
    return "verified"
