from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from ms.output.console import ConsoleProtocol, Style
from ms.release.domain.diagnostics import AutoSuggestion, RepoReadiness
from ms.release.domain.models import ReleasePlan
from ms.release.domain.open_control_models import OpenControlPreflightReport


def _gh_repo_url(slug: str) -> str:
    return f"https://github.com/{slug}"


def _gh_actions_workflow_url(slug: str, workflow_file: str) -> str:
    return f"https://github.com/{slug}/actions/workflows/{workflow_file}"


def _gh_blob_url(slug: str, ref: str, path: str) -> str:
    return f"https://github.com/{slug}/blob/{ref}/{path}"


def _gh_compare_url(slug: str, base: str, head: str) -> str:
    return f"https://github.com/{slug}/compare/{base}...{head}"


def print_release_preflight_issues(
    *,
    console: ConsoleProtocol,
    issues: Sequence[RepoReadiness],
) -> None:
    if not issues:
        return

    console.header("Release preflight")
    console.print("Non-blocking warnings (interactive mode).", Style.DIM)
    console.print("Use --auto to enforce strict readiness.", Style.DIM)

    for readiness in issues:
        repo = readiness.repo
        console.print(f"- {repo.id}: {_gh_repo_url(repo.slug)}", Style.DIM)

        if not readiness.local_exists:
            console.print(f"  missing checkout: {readiness.local_path}", Style.DIM)
            continue

        status = readiness.status
        if status is None:
            console.print("  status unavailable", Style.DIM)
            continue

        if not status.is_clean:
            console.print("  dirty", Style.DIM)
            for entry in status.entries[:10]:
                console.print(f"    {entry.pretty_xy()} {entry.path}", Style.DIM)
                if status.upstream is not None and status.ahead == 0 and status.behind == 0:
                    console.print(
                        f"      {_gh_blob_url(repo.slug, status.branch, entry.path)}",
                        Style.DIM,
                    )

        if status.upstream is None:
            console.print("  no upstream", Style.DIM)
        else:
            if status.ahead:
                console.print(f"  ahead {status.ahead} (push)", Style.DIM)
                base = status.upstream.split("/", 1)[-1]
                console.print(_gh_compare_url(repo.slug, base, status.branch), Style.DIM)
            if status.behind:
                console.print(f"  behind {status.behind} (pull)", Style.DIM)

        if (
            readiness.local_head_sha is not None
            and readiness.remote_head_sha is not None
            and readiness.local_head_sha != readiness.remote_head_sha
        ):
            console.print(
                f"  local {readiness.local_head_sha[:7]} != remote {readiness.remote_head_sha[:7]}",
                Style.DIM,
            )

        if repo.required_ci_workflow_file is None:
            console.print("  not CI-gated (auto will refuse)", Style.DIM)
        else:
            console.print(
                _gh_actions_workflow_url(repo.slug, repo.required_ci_workflow_file),
                Style.DIM,
            )
            if readiness.remote_head_sha is not None and readiness.head_green is not True:
                console.print("  ci: HEAD not green", Style.DIM)

    console.newline()


def print_auto_blockers(*, console: ConsoleProtocol, blockers: Sequence[RepoReadiness]) -> None:
    console.header("Auto Release Blocked")
    console.print("--auto is strict by default.", Style.DIM)
    console.print("Fix the issues below, then rerun.", Style.DIM)
    console.newline()

    for readiness in blockers:
        repo = readiness.repo
        console.header(f"{repo.id} ({repo.slug})")
        console.print(_gh_repo_url(repo.slug), Style.DIM)
        console.print(str(readiness.local_path), Style.DIM)
        console.print(f"ref: {readiness.ref}", Style.DIM)

        if readiness.error is not None:
            console.error(readiness.error)
            continue

        if not readiness.local_exists:
            console.error("repo not found in workspace")
            console.print("hint: run `ms sync --repos --profile maintainer`", Style.DIM)
            continue

        status = readiness.status
        if status is None:
            console.error("repo status unavailable")
            continue

        if not status.is_clean:
            console.error("working tree is dirty")
            for entry in status.entries[:20]:
                console.print(
                    f"- {entry.pretty_xy()} {Path(readiness.local_path, entry.path)}", Style.DIM
                )
                if status.upstream is not None and status.ahead == 0 and status.behind == 0:
                    console.print(
                        f"  {_gh_blob_url(repo.slug, status.branch, entry.path)}",
                        Style.DIM,
                    )
            if len(status.entries) > 20:
                console.print(f"... ({len(status.entries) - 20} more)", Style.DIM)
            console.print("hint: commit/stash changes before auto release", Style.DIM)

        if status.upstream is None:
            console.error("no upstream configured")
            console.print("hint: set upstream and push the branch", Style.DIM)
        else:
            if status.ahead:
                console.error(f"ahead of upstream by {status.ahead} commit(s)")
                console.print("hint: push to remote and wait for CI", Style.DIM)
                base = status.upstream.split("/", 1)[-1]
                console.print(_gh_compare_url(repo.slug, base, status.branch), Style.DIM)
            if status.behind:
                console.error(f"behind upstream by {status.behind} commit(s)")
                console.print("hint: pull/rebase to sync before auto release", Style.DIM)

        if (
            readiness.local_head_sha is not None
            and readiness.remote_head_sha is not None
            and readiness.local_head_sha != readiness.remote_head_sha
        ):
            console.error(
                "local HEAD "
                f"{readiness.local_head_sha[:7]} != remote HEAD "
                f"{readiness.remote_head_sha[:7]}"
            )
            console.print("hint: push/pull so local matches remote", Style.DIM)

        if repo.required_ci_workflow_file is None:
            console.error("repo is not CI-gated")
            console.print(
                "hint: add a CI workflow to the repo and set "
                "required_ci_workflow_file in ms release config",
                Style.DIM,
            )
        else:
            console.print(
                _gh_actions_workflow_url(repo.slug, repo.required_ci_workflow_file),
                Style.DIM,
            )
            if readiness.remote_head_sha is not None and readiness.head_green is not True:
                console.error("remote HEAD is not green")
                console.print("hint: wait for CI success on the branch HEAD", Style.DIM)


def print_auto_suggestions(
    *, console: ConsoleProtocol, suggestions: Sequence[AutoSuggestion]
) -> None:
    if not suggestions:
        return

    console.header("Optional bumps")
    for suggestion in suggestions:
        repo = suggestion.repo
        if suggestion.kind == "bump":
            console.print(
                (
                    f"- {repo.id} ({repo.slug}): "
                    f"{suggestion.from_sha[:7]} -> {suggestion.to_sha[:7]} ({suggestion.reason})"
                ),
                Style.DIM,
            )
            if not suggestion.applyable:
                console.print(
                    "  note: local repo not clean/synced; bump will be safer after cleanup/push",
                    Style.DIM,
                )
            continue

        console.print(
            (
                f"- {repo.id} ({repo.slug}): "
                f"local state ({suggestion.reason}); auto keeps {suggestion.from_sha[:7]}"
            ),
            Style.DIM,
        )


def print_content_plan(*, plan: ReleasePlan, console: ConsoleProtocol) -> None:
    console.header("Release Plan")
    console.print(f"channel: {plan.channel}")
    console.print(f"tag: {plan.tag}")
    console.print("repos:")
    for pinned_repo in plan.pinned:
        console.print(f"- {pinned_repo.repo.id}: {pinned_repo.sha}")
    console.print(f"spec: {plan.spec_path}")
    if plan.notes_path is not None:
        console.print(f"notes: {plan.notes_path}")


def print_content_replay(
    *,
    plan: ReleasePlan,
    console: ConsoleProtocol,
    plan_file: Path | None,
) -> None:
    repo_args = " ".join([f"--repo {p.repo.id}={p.sha}" for p in plan.pinned])
    console.newline()
    console.print("Replay:", Style.DIM)
    if plan_file is not None:
        console.print(f"ms release content publish --plan {plan_file}", Style.DIM)
    console.print(
        f"ms release content publish --channel {plan.channel} --tag {plan.tag} "
        f"--no-interactive {repo_args}",
        Style.DIM,
    )


def print_open_control_preflight(
    *, console: ConsoleProtocol, report: OpenControlPreflightReport
) -> None:
    if not any(repo.exists for repo in report.repos):
        console.header("OpenControl preflight")
        console.print("skip (no open-control workspace)", Style.DIM)
        return

    console.header("OpenControl preflight")
    if report.oc_sdk.lock is None:
        err = report.oc_sdk.error or "oc-sdk lock unavailable"
        console.print(f"oc-sdk: unavailable ({err})", Style.DIM)
    else:
        src = report.oc_sdk.source or "?"
        console.print(f"oc-sdk: v{report.oc_sdk.lock.version} ({src})", Style.DIM)

    dirty_repos = tuple(report.dirty_repos())
    if dirty_repos:
        console.print(f"dirty: {len(dirty_repos)} repo(s)", Style.DIM)
        for repo in dirty_repos:
            console.print(f"- open-control/{repo.repo}", Style.DIM)

    if report.mismatches:
        console.print(f"mismatch: {len(report.mismatches)} repo(s)", Style.DIM)
        for mismatch in report.mismatches:
            console.print(
                f"- {mismatch.repo}: "
                f"local {mismatch.local_sha[:7]} != pinned {mismatch.pinned_sha[:7]}",
                Style.DIM,
            )
