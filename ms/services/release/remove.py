from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.output.console import ConsoleProtocol, Style
from ms.platform.process import run as run_process
from ms.services.release import config
from ms.services.release.dist_repo import (
    checkout_main_and_pull,
    commit_and_push,
    create_branch,
    ensure_clean_git_repo,
    ensure_distribution_repo,
    merge_pr,
    open_pr,
)
from ms.services.release.errors import ReleaseError
from ms.services.release.semver import parse_stable_tag
from ms.services.release.timeouts import GH_TIMEOUT_SECONDS, GIT_TIMEOUT_SECONDS


@dataclass(frozen=True, slots=True)
class RemovePlan:
    tags: tuple[str, ...]
    deleted_files: tuple[Path, ...]


def validate_remove_tags(*, tags: list[str], force: bool) -> Result[tuple[str, ...], ReleaseError]:
    cleaned: list[str] = []
    for t in tags:
        t2 = t.strip()
        if not t2:
            continue
        cleaned.append(t2)

    if not cleaned:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message="no tags provided",
                hint="Pass one or more --tag values.",
            )
        )

    if not force:
        stable = [t for t in cleaned if parse_stable_tag(t) is not None]
        if stable:
            return Err(
                ReleaseError(
                    kind="invalid_input",
                    message="refusing to delete stable tags without --force",
                    hint="Tags: " + ", ".join(stable),
                )
            )

    # Deduplicate while preserving order.
    seen: set[str] = set()
    unique: list[str] = []
    for t in cleaned:
        if t in seen:
            continue
        seen.add(t)
        unique.append(t)

    return Ok(tuple(unique))


def _has_git_changes(repo_root: Path) -> bool:
    result = run_process(
        ["git", "status", "--porcelain"], cwd=repo_root, timeout=GIT_TIMEOUT_SECONDS
    )
    if isinstance(result, Err):
        return False
    return bool(result.value.strip())


def _delete_if_exists(path: Path) -> bool:
    try:
        if path.exists():
            path.unlink()
            return True
    except OSError:
        return False
    return False


def remove_distribution_artifacts(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    tags: tuple[str, ...],
    dry_run: bool,
) -> Result[RemovePlan, ReleaseError]:
    dist = ensure_distribution_repo(workspace_root=workspace_root, console=console, dry_run=dry_run)
    if isinstance(dist, Err):
        return dist
    dist_root = dist.value.root

    if not dry_run:
        clean = ensure_clean_git_repo(repo_root=dist_root)
        if isinstance(clean, Err):
            return clean

    pull = checkout_main_and_pull(repo_root=dist_root, console=console, dry_run=dry_run)
    if isinstance(pull, Err):
        return pull

    deleted: list[Path] = []

    for tag in tags:
        spec = dist_root / f"{config.DIST_SPEC_DIR}/{tag}.json"
        notes = dist_root / f"{config.DIST_NOTES_DIR}/{tag}.md"

        if not dry_run and _delete_if_exists(spec):
            deleted.append(spec)
        if not dry_run and _delete_if_exists(notes):
            deleted.append(notes)

    if dry_run:
        # In dry-run, still report the target paths.
        for tag in tags:
            deleted.append(dist_root / f"{config.DIST_SPEC_DIR}/{tag}.json")
            deleted.append(dist_root / f"{config.DIST_NOTES_DIR}/{tag}.md")
        return Ok(RemovePlan(tags=tags, deleted_files=tuple(deleted)))

    if not _has_git_changes(dist_root):
        return Ok(RemovePlan(tags=tags, deleted_files=tuple(deleted)))

    # Commit via PR.
    first = tags[0] if tags else "unknown"
    branch = f"cleanup/remove-{first}" + ("-and-more" if len(tags) > 1 else "")
    br = create_branch(repo_root=dist_root, branch=branch, console=console, dry_run=dry_run)
    if isinstance(br, Err):
        return br

    changed_paths = list({*deleted})
    msg = "cleanup: remove test releases" if len(tags) > 1 else f"cleanup: remove {first}"
    committed = commit_and_push(
        repo_root=dist_root,
        branch=branch,
        paths=changed_paths,
        message=msg,
        console=console,
        dry_run=dry_run,
    )
    if isinstance(committed, Err):
        return committed

    title = "cleanup: remove releases" if len(tags) > 1 else f"cleanup: remove {first}"
    body = "\n".join(["Remove artifacts for:", *[f"- {t}" for t in tags]])
    pr = open_pr(
        workspace_root=workspace_root,
        branch=branch,
        title=title,
        body=body,
        console=console,
        dry_run=dry_run,
    )
    if isinstance(pr, Err):
        return pr

    merged = merge_pr(
        workspace_root=workspace_root, pr_url=pr.value, console=console, dry_run=dry_run
    )
    if isinstance(merged, Err):
        return Err(
            ReleaseError(
                kind=merged.error.kind,
                message=merged.error.message,
                hint=f"PR: {pr.value}\n{merged.error.hint or ''}".strip(),
            )
        )

    console.success(f"PR merged: {pr.value}")
    return Ok(RemovePlan(tags=tags, deleted_files=tuple(deleted)))


def delete_github_releases(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    tags: tuple[str, ...],
    ignore_missing: bool,
    dry_run: bool,
) -> Result[None, ReleaseError]:
    for tag in tags:
        cmd = [
            "gh",
            "release",
            "delete",
            tag,
            "--repo",
            config.DIST_REPO_SLUG,
            "--cleanup-tag",
            "--yes",
        ]
        console.print(" ".join(cmd[:3]) + f" {tag}", Style.DIM)
        if dry_run:
            continue

        result = run_process(cmd, cwd=workspace_root, timeout=GH_TIMEOUT_SECONDS)
        if isinstance(result, Err):
            e = result.error
            msg = e.stderr.strip() or str(e)
            if ignore_missing and ("could not find" in msg.lower() or "not found" in msg.lower()):
                continue
            return Err(
                ReleaseError(
                    kind="dist_repo_failed",
                    message=f"failed to delete release: {tag}",
                    hint=msg,
                )
            )

    return Ok(None)
