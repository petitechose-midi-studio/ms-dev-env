from __future__ import annotations

import json
from pathlib import Path

import typer

from ms.cli.commands.release_common import exit_release, release_error_code
from ms.cli.context import build_context
from ms.core.result import Err
from ms.release.flow.candidate_workflow import CandidateFetchRequest, fetch_candidate_assets
from ms.release.flow.content_candidate_planning import plan_content_candidates
from ms.release.flow.content_spec import load_content_plan_from_spec


def export_content_spec_cmd(
    spec: Path = typer.Option(..., "--spec", help="Release spec JSON path."),
    github_output: Path = typer.Option(..., "--github-output", help="GitHub output file path."),
    repo_id: list[str] = typer.Option([], "--repo-id", help="Repo id to export as repo_<id>_sha."),
    include_tooling: bool = typer.Option(False, "--include-tooling", help="Export tooling_sha."),
) -> None:
    plan = _load_plan(spec)
    pinned_by_id = {pin.repo.id: pin for pin in plan.pinned}

    lines: list[str] = []
    if include_tooling:
        lines.append(f"tooling_sha={plan.tooling.sha}")

    for current_repo_id in repo_id:
        pin = pinned_by_id.get(current_repo_id)
        if pin is None:
            exit_release(
                f"missing repo id in spec: {current_repo_id}",
                code=release_error_code("invalid_input"),
            )
        output_name = current_repo_id.replace("-", "_")
        lines.append(f"repo_{output_name}_sha={pin.sha}")

    github_output.parent.mkdir(parents=True, exist_ok=True)
    with github_output.open("a", encoding="utf-8") as fh:
        for line in lines:
            fh.write(f"{line}\n")


def fetch_content_candidate_cmd(
    spec: Path = typer.Option(..., "--spec", help="Release spec JSON path."),
    target_id: str = typer.Option(..., "--target-id", help="Content candidate target id."),
    out_dir: Path = typer.Option(..., "--out-dir", help="Output directory for fetched assets."),
    asset_filename: list[str] = typer.Option(
        [], "--asset-filename", help="Candidate asset filename to copy into --out-dir."
    ),
) -> None:
    ctx = build_context()
    plan = _load_plan(spec)

    planned = plan_content_candidates(
        workspace_root=ctx.workspace.root,
        pinned=plan.pinned,
        tooling=plan.tooling,
    )
    if isinstance(planned, Err):
        exit_release(planned.error.pretty(), code=release_error_code(planned.error.kind))

    target = next((item for item in planned.value if item.id == target_id), None)
    if target is None:
        exit_release(
            f"unknown content candidate target: {target_id}",
            code=release_error_code("invalid_input"),
        )

    fetched = fetch_candidate_assets(
        workspace_root=ctx.workspace.root,
        request=CandidateFetchRequest(
            producer_id=target.producer_id,
            candidate_tag=target.candidate_tag,
            output_dir=out_dir,
            asset_filenames=tuple(asset_filename),
            expected_input_repos=target.expected_input_repos,
        ),
    )
    if isinstance(fetched, Err):
        exit_release(fetched.error.pretty(), code=release_error_code(fetched.error.kind))

    ctx.console.success("Candidate assets fetched")
    ctx.console.print(json.dumps({"target_id": target.id, "candidate_tag": target.candidate_tag}))


def _load_plan(spec: Path):
    plan = load_content_plan_from_spec(spec_path=spec)
    if isinstance(plan, Err):
        exit_release(plan.error.pretty(), code=release_error_code(plan.error.kind))
    return plan.value
