from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, NoReturn

import typer

from ms.core.errors import ErrorCode
from ms.core.result import Err, Result
from ms.output.console import ConsoleProtocol, Style
from ms.services.release.ci import fetch_green_head_shas
from ms.services.release.errors import ReleaseError
from ms.services.release.gh import current_user, list_recent_commits
from ms.services.release.model import PinnedRepo, ReleaseChannel, ReleaseRepo
from ms.services.release.plan_file import PlanInput, read_plan_file

ReleaseProduct = Literal["content", "app"]
PermissionCheck = Callable[..., Result[None, ReleaseError]]


@dataclass(frozen=True, slots=True)
class ResolvedReleaseInputs:
    channel: ReleaseChannel
    tag: str | None
    pinned: tuple[PinnedRepo, ...]


def exit_release(err: str, *, code: ErrorCode) -> NoReturn:
    typer.echo(f"error: {err}", err=True)
    raise typer.Exit(code=int(code))


def confirm_tag(tag: str, *, confirm_tag: str | None) -> None:
    if confirm_tag is not None:
        if confirm_tag.strip() != tag:
            exit_release("confirmation mismatch", code=ErrorCode.USER_ERROR)
        return

    typed = typer.prompt("Type the tag to confirm", default="")
    if typed.strip() != tag:
        exit_release("confirmation mismatch", code=ErrorCode.USER_ERROR)


def release_error_code(kind: str) -> ErrorCode:
    if kind in {"gh_missing", "gh_auth_required", "permission_denied"}:
        return ErrorCode.ENV_ERROR
    if kind in {"workflow_failed"}:
        return ErrorCode.NETWORK_ERROR
    if kind in {"dist_repo_failed", "dist_repo_dirty"}:
        return ErrorCode.IO_ERROR
    return ErrorCode.USER_ERROR


def ensure_release_permissions_or_exit(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    permission_check: PermissionCheck,
    require_write: bool,
    failure_code: ErrorCode,
) -> None:
    ok = permission_check(
        workspace_root=workspace_root,
        console=console,
        require_write=require_write,
    )
    if isinstance(ok, Err):
        exit_release(ok.error.message, code=failure_code)


def print_current_release_user(*, workspace_root: Path, console: ConsoleProtocol) -> str:
    who = current_user(workspace_root=workspace_root)
    if isinstance(who, Err):
        exit_release(who.error.message, code=ErrorCode.NETWORK_ERROR)
    login = who.value.login
    console.print(f"gh user: {login}", Style.DIM)
    return login


def parse_overrides(items: list[str], *, flag: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            exit_release(f"invalid {flag} (expected id=value): {item}", code=ErrorCode.USER_ERROR)
        k, v = item.split("=", 1)
        k = k.strip()
        v = v.strip()
        if not k or not v:
            exit_release(f"invalid {flag} (expected id=value): {item}", code=ErrorCode.USER_ERROR)
        out[k] = v
    return out


def enforce_auto_constraints(
    *, auto: bool, overrides: dict[str, str], allow_non_green: bool
) -> None:
    if not auto:
        return

    if overrides:
        exit_release("--auto cannot be combined with --repo overrides", code=ErrorCode.USER_ERROR)

    if allow_non_green:
        exit_release("--auto is strict: remove --allow-non-green", code=ErrorCode.USER_ERROR)


def pick_pinned_repo_interactive(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    repo: ReleaseRepo,
    ref: str,
    allow_non_green: bool,
) -> PinnedRepo:
    console.header(f"Select commit: {repo.id} ({repo.slug})")
    commits_r = list_recent_commits(
        workspace_root=workspace_root,
        repo=repo.slug,
        ref=ref,
        limit=20,
    )
    if isinstance(commits_r, Err):
        exit_release(commits_r.error.message, code=ErrorCode.NETWORK_ERROR)
    commits = commits_r.value
    if not commits:
        exit_release(f"no commits found for {repo.slug}", code=ErrorCode.NETWORK_ERROR)

    green = None
    if repo.required_ci_workflow_file is not None:
        green_r = fetch_green_head_shas(
            workspace_root=workspace_root,
            repo=repo.slug,
            workflow_file=repo.required_ci_workflow_file,
            branch=ref,
            limit=100,
        )
        if isinstance(green_r, Err):
            exit_release(green_r.error.message, code=ErrorCode.NETWORK_ERROR)
        green = green_r.value

    default_idx = 1
    if green is not None:
        for i, c in enumerate(commits, start=1):
            if green.is_green(c.sha):
                default_idx = i
                break

    for i, c in enumerate(commits, start=1):
        status = "NA" if green is None else ("OK" if green.is_green(c.sha) else "--")
        date = c.date_utc or ""
        console.print(f"{i:2}. [{status}] {c.short_sha} {date} {c.message}", Style.DIM)

    while True:
        raw = typer.prompt("Pick commit number", default=str(default_idx))
        try:
            idx = int(raw)
        except ValueError:
            console.error("invalid number")
            continue
        if idx < 1 or idx > len(commits):
            console.error("out of range")
            continue

        chosen = commits[idx - 1]
        if green is not None and (not green.is_green(chosen.sha)) and (not allow_non_green):
            console.error("selected commit CI is not green (use --allow-non-green to override)")
            continue

        console.success(f"{repo.id}={chosen.sha} (ref={ref})")
        return PinnedRepo(repo=repo, sha=chosen.sha)


def read_plan_for_product(*, path: Path, product: ReleaseProduct) -> PlanInput:
    plan_in = read_plan_file(path=path)
    if isinstance(plan_in, Err):
        exit_release(plan_in.error.message, code=ErrorCode.USER_ERROR)

    if plan_in.value.product != product:
        exit_release(
            f"--plan product mismatch: expected {product} plan",
            code=ErrorCode.USER_ERROR,
        )

    return plan_in.value


def resolve_release_inputs(
    *,
    product: ReleaseProduct,
    plan: Path | None,
    channel: ReleaseChannel | None,
    tag: str | None,
    auto: bool,
    repo: list[str],
    ref: list[str],
    resolve_pinned: Callable[[ReleaseChannel], tuple[PinnedRepo, ...]],
) -> ResolvedReleaseInputs:
    if plan is not None:
        if auto or repo or ref:
            exit_release(
                "--plan cannot be combined with --auto/--repo/--ref", code=ErrorCode.USER_ERROR
            )

        plan_in = read_plan_for_product(path=plan, product=product)
        return ResolvedReleaseInputs(
            channel=plan_in.channel,
            tag=plan_in.tag,
            pinned=plan_in.pinned,
        )

    if channel is None:
        exit_release("missing --channel (or pass --plan)", code=ErrorCode.USER_ERROR)

    return ResolvedReleaseInputs(
        channel=channel,
        tag=tag,
        pinned=resolve_pinned(channel),
    )
