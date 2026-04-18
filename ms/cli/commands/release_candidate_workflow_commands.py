from __future__ import annotations

from pathlib import Path

import typer

from ms.cli.commands.release_common import exit_release, release_error_code
from ms.cli.context import build_context
from ms.core.result import Err
from ms.release.domain.config import MS_DEFAULT_BRANCH, MS_REPO_SLUG, RELEASE_REPOS
from ms.release.domain.models import PinnedRepo, ReleaseTooling
from ms.release.flow.content_candidate_planning import resolve_core_ui_sha


def export_plugin_bitwig_firmware_cmd(
    source_sha: str = typer.Option(..., "--source-sha", help="Plugin-bitwig source commit SHA."),
    core_sha: str = typer.Option(..., "--core-sha", help="Core source commit SHA."),
    tooling_sha: str = typer.Option(..., "--tooling-sha", help="ms-dev-env tooling SHA."),
    github_output: Path = typer.Option(..., "--github-output", help="GitHub output file path."),
) -> None:
    ctx = build_context()
    repo_by_id = {repo.id: repo for repo in RELEASE_REPOS}
    core_repo = repo_by_id["core"]

    ui_sha = resolve_core_ui_sha(
        workspace_root=ctx.workspace.root,
        core_pin=PinnedRepo(repo=core_repo, sha=core_sha),
    )
    if isinstance(ui_sha, Err):
        exit_release(ui_sha.error.pretty(), code=release_error_code(ui_sha.error.kind))

    tooling = ReleaseTooling(repo=MS_REPO_SLUG, ref=MS_DEFAULT_BRANCH, sha=tooling_sha)
    candidate_tag = (
        f"rc-plugin-bitwig-firmware-{core_sha}-{source_sha}-tooling-{tooling.sha}"
    )

    github_output.parent.mkdir(parents=True, exist_ok=True)
    with github_output.open("a", encoding="utf-8") as fh:
        fh.write(f"ui_sha={ui_sha.value}\n")
        fh.write(f"candidate_tag={candidate_tag}\n")
