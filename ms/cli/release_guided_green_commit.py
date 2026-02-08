from __future__ import annotations

from pathlib import Path

from ms.cli.selector import SelectorOption, SelectorResult, select_one
from ms.core.result import Err, Ok, Result
from ms.release.errors import ReleaseError
from ms.release.infra.github.ci import fetch_green_head_shas
from ms.release.infra.github.client import list_recent_commits


def select_green_commit(
    *,
    workspace_root: Path,
    repo_slug: str,
    ref: str,
    workflow_file: str | None,
    title: str,
    subtitle: str,
    current_sha: str | None,
    initial_index: int,
    allow_back: bool,
) -> Result[SelectorResult[str], ReleaseError]:
    commits_r = list_recent_commits(
        workspace_root=workspace_root,
        repo=repo_slug,
        ref=ref,
        limit=40,
    )
    if isinstance(commits_r, Err):
        return commits_r

    green_shas: set[str] | None = None
    if workflow_file is not None:
        green_r = fetch_green_head_shas(
            workspace_root=workspace_root,
            repo=repo_slug,
            workflow_file=workflow_file,
            branch=ref,
            limit=200,
        )
        if isinstance(green_r, Err):
            return green_r
        green_shas = set(green_r.value.green_head_shas)

    options: list[SelectorOption[str]] = []
    for commit in commits_r.value:
        if green_shas is not None and commit.sha not in green_shas:
            continue
        options.append(
            SelectorOption(
                value=commit.sha,
                label=f"{commit.short_sha}  {commit.message}",
                detail=(commit.date_utc or ""),
            )
        )

    if not options:
        return Err(
            ReleaseError(
                kind="ci_not_green",
                message=f"no green commits available for {repo_slug}@{ref}",
                hint="Wait for CI green or investigate failed runs.",
            )
        )

    idx = max(0, min(initial_index, len(options) - 1))
    if current_sha is not None:
        for i, opt in enumerate(options):
            if opt.value == current_sha:
                idx = i
                break

    return Ok(
        select_one(
            title=title,
            subtitle=subtitle,
            options=options,
            initial_index=idx,
            allow_back=allow_back,
        )
    )
