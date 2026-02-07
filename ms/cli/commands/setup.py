from __future__ import annotations

import typer

from ms.cli.context import build_context
from ms.core.errors import ErrorCode
from ms.core.result import Err, Ok
from ms.core.user_workspace import remember_default_workspace_root
from ms.output.console import Style
from ms.platform.process import run_silent
from ms.services.repo_profiles import RepoProfile
from ms.services.setup import SetupService

_UV_TOOL_TIMEOUT_SECONDS = 10 * 60.0


def setup(
    mode: str = typer.Option("dev", "--mode", help="Setup mode (dev only)"),
    profile: RepoProfile = typer.Option(
        RepoProfile.dev,
        "--profile",
        help="Repo profile (dev | maintainer)",
    ),
    skip_repos: bool = typer.Option(False, "--skip-repos", help="Skip repository sync"),
    skip_tools: bool = typer.Option(False, "--skip-tools", help="Skip toolchain sync"),
    skip_python: bool = typer.Option(False, "--skip-python", help="Skip Python deps sync"),
    skip_check: bool = typer.Option(False, "--skip-check", help="Skip final check"),
    install_cli: bool = typer.Option(
        False,
        "--install-cli",
        help="Install ms/oc-* globally via `uv tool` (editable)",
    ),
    update_shell: bool = typer.Option(
        False,
        "--update-shell",
        help="Ensure the uv tool bin directory is on PATH",
    ),
    remember_workspace: bool = typer.Option(
        False,
        "--remember-workspace",
        help="Remember this workspace as the default",
    ),
    skip_prereqs: bool = typer.Option(
        False,
        "--skip-prereqs",
        "--skip-system-deps",
        help="Skip prerequisites check/install",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be done"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Auto-confirm (do not prompt)"),
) -> None:
    """Setup dev workspace.

    Checks and installs prerequisites, syncs repositories,
    installs toolchains, and validates the environment.

    Installs prompt for confirmation unless --yes is passed.
    """
    ctx = build_context()
    service = SetupService(
        workspace=ctx.workspace,
        platform=ctx.platform,
        config=ctx.config,
        console=ctx.console,
        confirm=lambda msg: typer.confirm(msg, default=False),
    )

    result = service.setup_dev(
        mode=mode,
        repo_profile=profile,
        skip_repos=skip_repos,
        skip_tools=skip_tools,
        skip_python=skip_python,
        skip_check=skip_check,
        skip_prereqs=skip_prereqs,
        dry_run=dry_run,
        assume_yes=yes,
    )
    match result:
        case Ok(_):
            # Optional post-setup helpers
            if remember_workspace:
                if dry_run:
                    ctx.console.print(
                        f"would set default workspace: {ctx.workspace.root}",
                        Style.DIM,
                    )
                else:
                    saved = remember_default_workspace_root(ctx.workspace.root)
                    if isinstance(saved, Err):
                        ctx.console.error(saved.error.message)
                        raise typer.Exit(code=int(ErrorCode.IO_ERROR))
                    ctx.console.success(f"default workspace set: {ctx.workspace.root}")

            if install_cli:
                cmd = ["uv", "tool", "install", "-e", str(ctx.workspace.root)]
                ctx.console.print(" ".join(cmd), Style.DIM)
                if not dry_run:
                    ires = run_silent(cmd, cwd=ctx.workspace.root, timeout=_UV_TOOL_TIMEOUT_SECONDS)
                    if isinstance(ires, Err):
                        ctx.console.error(str(ires.error))
                        raise typer.Exit(code=int(ErrorCode.ENV_ERROR))
                    ctx.console.success("installed global CLI")

            if update_shell:
                cmd = ["uv", "tool", "update-shell"]
                ctx.console.print(" ".join(cmd), Style.DIM)
                if not dry_run:
                    ures = run_silent(cmd, cwd=ctx.workspace.root, timeout=_UV_TOOL_TIMEOUT_SECONDS)
                    if isinstance(ures, Err):
                        ctx.console.error(str(ures.error))
                        raise typer.Exit(code=int(ErrorCode.ENV_ERROR))
                    ctx.console.success("PATH updated (restart your shell)")

            ctx.console.newline()
            ctx.console.success("Setup complete")
        case Err(e):
            ctx.console.error(f"setup failed: {e.message}")
            if e.hint:
                ctx.console.print(e.hint)
            raise typer.Exit(code=int(ErrorCode.ENV_ERROR))
