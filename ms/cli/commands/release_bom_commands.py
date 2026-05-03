from __future__ import annotations

import time

import typer

from ms.cli.commands.release_common import exit_release, release_error_code
from ms.cli.context import build_context
from ms.core.errors import ErrorCode
from ms.core.result import Err
from ms.output.console import ConsoleProtocol, Style
from ms.release.domain.open_control_models import OPEN_CONTROL_NATIVE_CI_REPOS, BomRepoState
from ms.release.flow.bom_validation import (
    BomValidationTarget,
    validate_workspace_bom_targets,
)
from ms.release.flow.bom_workflow import (
    BomSyncPreview,
    BomSyncResult,
    BomWorkspaceState,
    plan_workspace_bom_sync,
    sync_workspace_bom,
    verify_workspace_bom_files,
)


def register_bom_commands(*, namespace: typer.Typer) -> None:
    namespace.command("verify-bom")(verify_bom_cmd)
    namespace.command("validate-bom-targets")(validate_bom_targets_cmd)
    namespace.command("sync-bom")(sync_bom_cmd)


def verify_bom_cmd(
    allow_dirty_workspace: bool = typer.Option(
        False,
        "--allow-dirty-workspace",
        help="Allow dirty open-control workspace repos during comparison.",
    ),
) -> None:
    ctx = build_context()
    verified = verify_workspace_bom_files(
        workspace_root=ctx.workspace.root,
        allow_dirty_workspace=allow_dirty_workspace,
    )
    if isinstance(verified, Err):
        exit_release(verified.error.pretty(), code=release_error_code(verified.error.kind))

    _print_bom_state(console=ctx.console, state=verified.value)
    if verified.value.comparison.status != "aligned":
        _print_bom_blockers(console=ctx.console, state=verified.value)
        exit_release("OpenControl BOM is not aligned", code=ErrorCode.USER_ERROR)

    ctx.console.success("OpenControl BOM verified")


def validate_bom_targets_cmd(
    allow_dirty_workspace: bool = typer.Option(
        False,
        "--allow-dirty-workspace",
        help="Allow dirty open-control workspace repos during comparison.",
    ),
    include_plugin_release: bool = typer.Option(
        True,
        "--include-plugin-release/--no-plugin-release",
        help="Include plugin-bitwig release validation.",
    ),
) -> None:
    ctx = build_context()
    started_at = time.perf_counter()
    verified = verify_workspace_bom_files(
        workspace_root=ctx.workspace.root,
        allow_dirty_workspace=allow_dirty_workspace,
    )
    if isinstance(verified, Err):
        exit_release(verified.error.pretty(), code=release_error_code(verified.error.kind))
    verify_elapsed = time.perf_counter() - started_at

    _print_bom_state(console=ctx.console, state=verified.value)
    if verified.value.comparison.status != "aligned":
        _print_bom_blockers(console=ctx.console, state=verified.value)
        exit_release("OpenControl BOM is not aligned", code=ErrorCode.USER_ERROR)

    validation_started_at = time.perf_counter()
    validated = validate_workspace_bom_targets(
        workspace_root=ctx.workspace.root,
        include_plugin_release=include_plugin_release,
        console=ctx.console,
    )
    if isinstance(validated, Err):
        exit_release(validated.error.pretty(), code=release_error_code(validated.error.kind))
    validation_elapsed = time.perf_counter() - validation_started_at

    _print_validation_summary(console=ctx.console, validations=validated.value)
    ctx.console.print(f"verify-bom: {verify_elapsed:.1f}s", Style.DIM)
    ctx.console.print(f"validate-targets: {validation_elapsed:.1f}s", Style.DIM)
    ctx.console.success("OpenControl BOM targets validated")


def sync_bom_cmd(
    write: bool = typer.Option(
        False,
        "--write",
        help="Write updated oc-sdk.ini and oc-native-sdk.ini.",
    ),
    allow_dirty_workspace: bool = typer.Option(
        False,
        "--allow-dirty-workspace",
        help="Allow dirty open-control workspace repos during comparison.",
    ),
    validate_targets: bool = typer.Option(
        True,
        "--validate-targets/--no-validate-targets",
        help="Run build/test validations after sync.",
    ),
    include_plugin_release: bool = typer.Option(
        True,
        "--include-plugin-release/--no-plugin-release",
        help="Include plugin-bitwig release validation.",
    ),
) -> None:
    ctx = build_context()
    preview = plan_workspace_bom_sync(
        workspace_root=ctx.workspace.root,
        allow_dirty_workspace=allow_dirty_workspace,
    )
    if isinstance(preview, Err):
        exit_release(preview.error.pretty(), code=release_error_code(preview.error.kind))

    _print_bom_state(console=ctx.console, state=preview.value.state)
    _print_sync_plan(console=ctx.console, preview=preview.value)

    if not write:
        if preview.value.plan.requires_write:
            ctx.console.warning("BOM promotion planned; rerun with --write to apply it")
        else:
            ctx.console.success("OpenControl BOM already aligned")
        return

    synced = sync_workspace_bom(
        workspace_root=ctx.workspace.root,
        allow_dirty_workspace=allow_dirty_workspace,
        validate_targets=validate_targets,
        include_plugin_release=include_plugin_release,
        console=ctx.console,
    )
    if isinstance(synced, Err):
        exit_release(synced.error.pretty(), code=release_error_code(synced.error.kind))

    _print_sync_result(console=ctx.console, result=synced.value)
    ctx.console.success("OpenControl BOM synchronized")


def _print_bom_state(*, console: ConsoleProtocol, state: BomWorkspaceState) -> None:
    console.header("OpenControl BOM")
    console.print(f"core: {state.core_root}", Style.DIM)
    console.print(f"canonical: {state.core_root / 'oc-sdk.ini'}", Style.DIM)
    derived = state.core_root / "oc-native-sdk.ini"
    console.print(f"native_ci: {derived}", Style.DIM)

    changed = 0
    for repo_state in state.comparison.repos:
        if _repo_is_aligned(repo_state=repo_state):
            continue
        changed += 1
        console.print(_format_repo_state(repo_state=repo_state), Style.WARNING)

    if changed == 0:
        console.print("all BOM pins aligned", Style.DIM)


def _print_bom_blockers(*, console: ConsoleProtocol, state: BomWorkspaceState) -> None:
    for blocker in state.comparison.blockers:
        console.warning(blocker)


def _print_sync_plan(*, console: ConsoleProtocol, preview: BomSyncPreview) -> None:
    if not preview.plan.requires_write:
        console.print("no pin changes required", Style.DIM)
        return

    console.header("BOM Promotion Plan")
    console.print(
        f"version: {preview.plan.current_version} -> {preview.plan.next_version}",
        Style.DIM,
    )
    for item in preview.plan.items:
        if not item.changed:
            continue
        console.print(f"{item.repo}: {item.from_sha} -> {item.to_sha}")


def _print_sync_result(*, console: ConsoleProtocol, result: BomSyncResult) -> None:
    if result.written:
        console.header("Written Files")
        for path in result.written:
            console.print(str(path), Style.DIM)
    _print_validation_summary(console=console, validations=result.validations)


def _print_validation_summary(
    *, console: ConsoleProtocol, validations: tuple[BomValidationTarget, ...]
) -> None:
    if not validations:
        return
    console.header("Validation")
    for validation in validations:
        console.success(validation.label)


def _repo_is_aligned(*, repo_state: BomRepoState) -> bool:
    workspace_matches = repo_state.workspace_sha == repo_state.bom_sha
    if repo_state.repo in OPEN_CONTROL_NATIVE_CI_REPOS:
        return workspace_matches and repo_state.derived_sha == repo_state.bom_sha
    return workspace_matches


def _format_repo_state(*, repo_state: BomRepoState) -> str:
    parts = [f"{repo_state.repo}:"]
    if repo_state.workspace_sha != repo_state.bom_sha:
        parts.append(f"workspace {repo_state.workspace_sha} != bom {repo_state.bom_sha}")
    if (
        repo_state.repo in OPEN_CONTROL_NATIVE_CI_REPOS
        and repo_state.derived_sha != repo_state.bom_sha
    ):
        parts.append(f"native_ci {repo_state.derived_sha} != bom {repo_state.bom_sha}")
    return " ".join(parts)
