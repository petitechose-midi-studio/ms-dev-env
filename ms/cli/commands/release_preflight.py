from __future__ import annotations

from ms.cli.commands.release_common import exit_release, release_error_code
from ms.cli.context import build_context
from ms.cli.release_guided_dependencies import run_dependencies_release
from ms.core.result import Err
from ms.output.console import Style
from ms.release.flow.permissions import ensure_full_release_permissions


def release_preflight_cmd() -> None:
    """Validate the complete release perimeter without mutating it."""
    ctx = build_context()
    ctx.console.header("Release preflight")

    permissions = ensure_full_release_permissions(
        workspace_root=ctx.workspace.root,
        console=ctx.console,
    )
    if isinstance(permissions, Err):
        exit_release(
            permissions.error.pretty(),
            code=release_error_code(permissions.error.kind),
        )

    dependencies = run_dependencies_release(
        workspace_root=ctx.workspace.root,
        console=ctx.console,
        watch=False,
        dry_run=True,
        promote=False,
        interactive=False,
        prepare=None,
    )
    if isinstance(dependencies, Err):
        ctx.console.print("rerun: uv run ms release preflight", Style.DIM)
        exit_release(
            dependencies.error.pretty(),
            code=release_error_code(dependencies.error.kind),
        )

    ctx.console.success("Release perimeter is ready")
