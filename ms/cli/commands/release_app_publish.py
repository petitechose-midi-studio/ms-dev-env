from __future__ import annotations

from pathlib import Path

import typer

from ms.cli.commands.release_common import ensure_release_permissions_or_exit, exit_release
from ms.cli.context import build_context
from ms.core.errors import ErrorCode
from ms.core.result import Err
from ms.output.console import Style
from ms.release.domain import ReleaseBump, ReleaseChannel
from ms.release.flow.app_publish import publish_app_release, resolve_app_publish_notes
from ms.release.flow.permissions import ensure_app_release_permissions
from ms.release.view.app_console import print_app_notes_attachment

from .release_app_prepare import prepare_app_release


def app_publish_cmd(
    channel: ReleaseChannel | None = typer.Option(None, "--channel", help="stable or beta"),
    bump: ReleaseBump = typer.Option("patch", "--bump", help="major/minor/patch"),
    tag: str | None = typer.Option(None, "--tag", help="Override tag"),
    auto: bool = typer.Option(False, "--auto", help="Auto-select pins (strict)"),
    repo: list[str] = typer.Option([], "--repo", help="Override repo SHA (id=sha)"),
    ref: list[str] = typer.Option([], "--ref", help="Override repo ref (id=ref)"),
    plan: Path | None = typer.Option(None, "--plan", help="Use a previously saved plan JSON"),
    allow_non_green: bool = typer.Option(False, "--allow-non-green", help="Allow non-green SHAs"),
    confirm_tag: str | None = typer.Option(
        None, "--confirm-tag", help="Skip confirmation prompt by providing the tag"
    ),
    no_interactive: bool = typer.Option(
        False, "--no-interactive", help="Require explicit --repo overrides"
    ),
    watch: bool = typer.Option(False, "--watch", help="Watch workflow run until completion"),
    notes_file: Path | None = typer.Option(
        None, "--notes-file", help="Optional markdown notes file"
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print actions without mutating"),
) -> None:
    """Prepare app version PR + reuse or dispatch the exact ms-manager candidate, then Release."""
    ctx = build_context()

    ensure_release_permissions_or_exit(
        workspace_root=ctx.workspace.root,
        console=ctx.console,
        permission_check=ensure_app_release_permissions,
        require_write=True,
        failure_code=ErrorCode.USER_ERROR,
    )

    prepared = prepare_app_release(
        ctx=ctx,
        channel=channel,
        bump=bump,
        tag=tag,
        auto=auto,
        repo=repo,
        ref=ref,
        plan_file=plan,
        allow_non_green=allow_non_green,
        confirm_tag=confirm_tag,
        no_interactive=no_interactive,
        dry_run=dry_run,
    )

    notes = resolve_app_publish_notes(
        notes_file=notes_file,
    )
    if isinstance(notes, Err):
        exit_release(notes.error.message, code=ErrorCode.USER_ERROR)

    print_app_notes_attachment(console=ctx.console, notes=notes.value)

    ctx.console.success(f"PR merged: {prepared.pr}")
    ctx.console.print(f"source sha: {prepared.source_sha}", Style.DIM)

    run = publish_app_release(
        workspace_root=ctx.workspace.root,
        console=ctx.console,
        tag=prepared.plan.tag,
        source_sha=prepared.source_sha,
        tooling_sha=prepared.plan.tooling.sha,
        notes_markdown=notes.value.markdown,
        notes_source_path=notes.value.source_path,
        watch=watch,
        dry_run=dry_run,
    )
    if isinstance(run, Err):
        exit_release(run.error.message, code=ErrorCode.NETWORK_ERROR)

    if run.value.candidate.run is None:
        ctx.console.success(f"Candidate ready: {run.value.candidate.release_url}")
    else:
        ctx.console.success(f"Candidate run: {run.value.candidate.run.url}")
    ctx.console.success(f"Release run: {run.value.release.url}")
    ctx.console.print(
        "Next: approve the 'app-release' environment in GitHub Actions to publish.",
        Style.DIM,
    )
