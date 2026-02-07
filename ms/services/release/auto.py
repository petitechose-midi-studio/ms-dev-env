from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ms.core.result import Err, Ok, Result
from ms.core.structured import as_obj_list, as_str_dict, get_int, get_list, get_str
from ms.git.repository import GitError, GitStatus, Repository
from ms.platform.process import run as run_process
from ms.services.release import config
from ms.services.release.ci import fetch_green_head_shas, is_ci_green_for_sha
from ms.services.release.errors import ReleaseError
from ms.services.release.gh import (
    compare_commits,
    get_ref_head_sha,
    get_repo_file_text,
    list_distribution_releases,
    list_recent_commits,
)
from ms.services.release.model import PinnedRepo, ReleaseChannel, ReleaseRepo
from ms.services.release.planner import ReleaseHistory, compute_history
from ms.services.release.semver import format_beta_tag
from ms.services.release.timeouts import GIT_TIMEOUT_SECONDS


@dataclass(frozen=True, slots=True)
class RepoReadiness:
    repo: ReleaseRepo
    ref: str
    local_path: Path
    local_exists: bool
    status: GitStatus | None
    local_head_sha: str | None
    remote_head_sha: str | None
    head_green: bool | None
    error: str | None

    def is_ready(self) -> bool:
        if self.error is not None:
            return False
        if not self.local_exists:
            return False
        if self.status is None:
            return False
        if not self.status.is_clean:
            return False
        if self.status.upstream is None:
            return False
        if self.status.ahead != 0 or self.status.behind != 0:
            return False
        if self.local_head_sha is None or self.remote_head_sha is None:
            return False
        if self.local_head_sha != self.remote_head_sha:
            return False
        if self.repo.required_ci_workflow_file is None:
            return False
        return self.head_green is True


@dataclass(frozen=True, slots=True)
class AutoSuggestion:
    repo: ReleaseRepo
    from_sha: str
    to_sha: str
    kind: Literal["bump", "local"]
    reason: str
    applyable: bool


def _local_issue_reason(r: RepoReadiness) -> str:
    st = r.status
    if st is None:
        return "repo status unavailable"
    if not st.is_clean:
        return "working tree is dirty"
    if st.upstream is None:
        return "no upstream configured"
    if st.ahead:
        return f"ahead of upstream by {st.ahead}"
    if st.behind:
        return f"behind upstream by {st.behind}"
    return "repo not ready"


def _local_repo_path(*, workspace_root: Path, repo: ReleaseRepo) -> Path:
    name = repo.slug.split("/", 1)[-1]
    if repo.slug == config.APP_REPO_SLUG:
        return workspace_root / config.APP_LOCAL_DIR
    if repo.slug.startswith("petitechose-midi-studio/"):
        return workspace_root / "midi-studio" / name
    if repo.slug.startswith("open-control/"):
        return workspace_root / "open-control" / name
    return workspace_root / name


def _resolve_repo_ref(*, repo: ReleaseRepo, ref_overrides: dict[str, str]) -> str:
    override = ref_overrides.get(repo.id)
    return override if override is not None else repo.ref


def _git_head_sha(*, repo_root: Path) -> str | None:
    r = run_process(["git", "rev-parse", "HEAD"], cwd=repo_root, timeout=GIT_TIMEOUT_SECONDS)
    if isinstance(r, Err):
        return None
    sha = r.value.strip()
    return sha if len(sha) == 40 else None


def probe_release_readiness(
    *,
    workspace_root: Path,
    repo: ReleaseRepo,
    ref: str,
) -> Result[RepoReadiness, ReleaseError]:
    local_path = _local_repo_path(workspace_root=workspace_root, repo=repo)
    local_repo = Repository(local_path)
    if not local_repo.exists():
        return Ok(
            RepoReadiness(
                repo=repo,
                ref=ref,
                local_path=local_path,
                local_exists=False,
                status=None,
                local_head_sha=None,
                remote_head_sha=None,
                head_green=None,
                error=None,
            )
        )

    st = local_repo.status()
    if isinstance(st, Err):
        e: GitError = st.error
        return Ok(
            RepoReadiness(
                repo=repo,
                ref=ref,
                local_path=local_path,
                local_exists=True,
                status=None,
                local_head_sha=None,
                remote_head_sha=None,
                head_green=None,
                error=f"git status failed: {e.message}",
            )
        )

    local_head = _git_head_sha(repo_root=local_path)

    remote_head_r = get_ref_head_sha(workspace_root=workspace_root, repo=repo.slug, ref=ref)
    if isinstance(remote_head_r, Err):
        return Ok(
            RepoReadiness(
                repo=repo,
                ref=ref,
                local_path=local_path,
                local_exists=True,
                status=st.value,
                local_head_sha=local_head,
                remote_head_sha=None,
                head_green=None,
                error=remote_head_r.error.message,
            )
        )

    remote_head = remote_head_r.value

    head_green: bool | None = None
    if repo.required_ci_workflow_file is not None:
        green_r = fetch_green_head_shas(
            workspace_root=workspace_root,
            repo=repo.slug,
            workflow_file=repo.required_ci_workflow_file,
            branch=ref,
            limit=30,
        )
        if isinstance(green_r, Err):
            return Ok(
                RepoReadiness(
                    repo=repo,
                    ref=ref,
                    local_path=local_path,
                    local_exists=True,
                    status=st.value,
                    local_head_sha=local_head,
                    remote_head_sha=remote_head,
                    head_green=None,
                    error=green_r.error.message,
                )
            )
        head_green = green_r.value.is_green(remote_head)

    return Ok(
        RepoReadiness(
            repo=repo,
            ref=ref,
            local_path=local_path,
            local_exists=True,
            status=st.value,
            local_head_sha=local_head,
            remote_head_sha=remote_head,
            head_green=head_green,
            error=None,
        )
    )


def resolve_pinned_auto_strict(
    *,
    workspace_root: Path,
    repos: tuple[ReleaseRepo, ...],
    ref_overrides: dict[str, str],
) -> Result[tuple[PinnedRepo, ...], tuple[RepoReadiness, ...]]:
    checked: list[RepoReadiness] = []
    pinned: list[PinnedRepo] = []

    for r in repos:
        ref = _resolve_repo_ref(repo=r, ref_overrides=ref_overrides)
        rr = probe_release_readiness(workspace_root=workspace_root, repo=r, ref=ref)
        if isinstance(rr, Err):
            # This means we could not even probe; represent as an error entry.
            checked.append(
                RepoReadiness(
                    repo=r,
                    ref=ref,
                    local_path=_local_repo_path(workspace_root=workspace_root, repo=r),
                    local_exists=False,
                    status=None,
                    local_head_sha=None,
                    remote_head_sha=None,
                    head_green=None,
                    error=rr.error.message,
                )
            )
            continue
        checked.append(rr.value)
        if rr.value.remote_head_sha is not None:
            pinned.append(PinnedRepo(repo=r, sha=rr.value.remote_head_sha))

    blockers = tuple(r for r in checked if not r.is_ready())
    if blockers:
        return Err(blockers)

    # Preserve repo order from config.
    by_id = {p.repo.id: p for p in pinned}
    out = tuple(by_id[r.id] for r in repos if r.id in by_id)
    return Ok(out)


def _latest_beta_tag(history: ReleaseHistory) -> str | None:
    base = history.latest_beta_base
    if base is None:
        return None
    n = history.beta_max_by_base.get(base)
    if n is None:
        return None
    return format_beta_tag(base, n)


def _prev_dist_tag_for_channel(
    *,
    channel: ReleaseChannel,
    history: ReleaseHistory,
) -> str | None:
    latest_beta = _latest_beta_tag(history)
    latest_stable = history.latest_stable.to_tag() if history.latest_stable is not None else None

    # Prefer same-channel; fall back to the other channel if needed.
    if channel == "stable":
        return latest_stable or latest_beta
    return latest_beta or latest_stable


def _parse_spec_pins(text: str) -> Result[dict[str, tuple[str, str]], ReleaseError]:
    try:
        obj: object = json.loads(text)
    except json.JSONDecodeError as e:
        return Err(ReleaseError(kind="invalid_input", message=f"invalid spec JSON: {e}"))

    root = as_str_dict(obj)
    if root is None:
        return Err(ReleaseError(kind="invalid_input", message="invalid spec JSON: expected object"))

    schema = get_int(root, "schema")
    if schema != 1:
        return Err(ReleaseError(kind="invalid_input", message=f"unsupported spec schema: {schema}"))

    repos_any = get_list(root, "repos")
    if repos_any is None:
        return Err(ReleaseError(kind="invalid_input", message="invalid spec.repos"))
    repos = as_obj_list(repos_any)
    if repos is None:
        return Err(ReleaseError(kind="invalid_input", message="invalid spec.repos"))

    out: dict[str, tuple[str, str]] = {}
    for item in repos:
        r = as_str_dict(item)
        if r is None:
            continue
        rid = get_str(r, "id")
        sha = get_str(r, "sha")
        ref = get_str(r, "ref")
        if rid is None or sha is None or ref is None:
            continue
        if len(sha) != 40:
            continue
        out[rid] = (sha, ref)
    return Ok(out)


def _load_prev_pins(
    *,
    workspace_root: Path,
    dist_repo: str,
    tag: str,
) -> Result[dict[str, tuple[str, str]], ReleaseError]:
    rel_path = f"release-specs/{tag}.json"
    text = get_repo_file_text(
        workspace_root=workspace_root, repo=dist_repo, path=rel_path, ref="main"
    )
    if isinstance(text, Err):
        return text
    parsed = _parse_spec_pins(text.value)
    if isinstance(parsed, Err):
        return parsed
    return Ok(parsed.value)


def _find_latest_green_sha(
    *,
    workspace_root: Path,
    repo: ReleaseRepo,
    limit_commits: int,
    limit_runs: int,
) -> Result[str | None, ReleaseError]:
    wf = repo.required_ci_workflow_file
    if wf is None:
        return Ok(None)

    commits_r = list_recent_commits(
        workspace_root=workspace_root,
        repo=repo.slug,
        ref=repo.ref,
        limit=limit_commits,
    )
    if isinstance(commits_r, Err):
        return commits_r

    green_r = fetch_green_head_shas(
        workspace_root=workspace_root,
        repo=repo.slug,
        workflow_file=wf,
        branch=repo.ref,
        limit=limit_runs,
    )
    if isinstance(green_r, Err):
        return green_r

    green = green_r.value
    for c in commits_r.value:
        if green.is_green(c.sha):
            return Ok(c.sha)
    return Ok(None)


def _is_applyable_locally(r: RepoReadiness) -> bool:
    if not r.local_exists or r.status is None:
        return False
    if not r.status.is_clean:
        return False
    if r.status.upstream is None:
        return False
    return r.status.ahead == 0 and r.status.behind == 0


def _diag_blocker(
    *,
    workspace_root: Path,
    repo: ReleaseRepo,
    ref: str,
    diag: RepoReadiness | None,
    error: str,
) -> RepoReadiness:
    return RepoReadiness(
        repo=repo,
        ref=ref,
        local_path=_local_repo_path(workspace_root=workspace_root, repo=repo),
        local_exists=(diag.local_exists if diag else False),
        status=(diag.status if diag else None),
        local_head_sha=(diag.local_head_sha if diag else None),
        remote_head_sha=(diag.remote_head_sha if diag else None),
        head_green=(diag.head_green if diag else None),
        error=error,
    )


def _dist_blocker(
    *, workspace_root: Path, dist_repo_entry: ReleaseRepo, error: str
) -> RepoReadiness:
    return RepoReadiness(
        repo=dist_repo_entry,
        ref=dist_repo_entry.ref,
        local_path=workspace_root / "distribution",
        local_exists=False,
        status=None,
        local_head_sha=None,
        remote_head_sha=None,
        head_green=None,
        error=error,
    )


def _repo_with_ref(*, repo: ReleaseRepo, ref: str) -> ReleaseRepo:
    return ReleaseRepo(
        id=repo.id,
        slug=repo.slug,
        ref=ref,
        required_ci_workflow_file=repo.required_ci_workflow_file,
    )


def _is_head_mode_repo(
    *,
    repo: ReleaseRepo,
    ref: str,
    ref_overrides: dict[str, str],
    head_repo_ids: frozenset[str],
) -> bool:
    explicit_ref = (repo.id in ref_overrides) and (ref != repo.ref)
    return (repo.id in head_repo_ids) or explicit_ref


def _resolve_head_mode_pin(
    *,
    workspace_root: Path,
    repo: ReleaseRepo,
    ref: str,
    repo_sel: ReleaseRepo,
    diag: RepoReadiness | None,
) -> Result[PinnedRepo, RepoReadiness]:
    if diag is None or not diag.is_ready():
        return Err(
            diag
            if diag is not None
            else _diag_blocker(
                workspace_root=workspace_root,
                repo=repo,
                ref=ref,
                diag=None,
                error="missing repo diagnostics",
            )
        )

    assert diag.remote_head_sha is not None
    return Ok(PinnedRepo(repo=repo_sel, sha=diag.remote_head_sha))


def _collect_carry_mode_suggestions(
    *,
    workspace_root: Path,
    repo: ReleaseRepo,
    repo_sel: ReleaseRepo,
    diag: RepoReadiness | None,
    carried_sha: str,
) -> tuple[AutoSuggestion, ...]:
    if repo.id not in {"loader", "oc-bridge"}:
        return ()

    suggestions: list[AutoSuggestion] = []
    latest_r = _find_latest_green_sha(
        workspace_root=workspace_root,
        repo=repo_sel,
        limit_commits=30,
        limit_runs=200,
    )
    if isinstance(latest_r, Ok):
        latest = latest_r.value
        if latest is not None and latest != carried_sha:
            cmp_r = compare_commits(
                workspace_root=workspace_root,
                repo=repo.slug,
                base=carried_sha,
                head=latest,
            )
            if isinstance(cmp_r, Ok) and cmp_r.value.status == "ahead":
                suggestions.append(
                    AutoSuggestion(
                        repo=repo_sel,
                        from_sha=carried_sha,
                        to_sha=latest,
                        kind="bump",
                        reason="newer green commit available",
                        applyable=(diag is not None and _is_applyable_locally(diag)),
                    )
                )

    if diag is not None and not _is_applyable_locally(diag):
        suggestions.append(
            AutoSuggestion(
                repo=repo_sel,
                from_sha=carried_sha,
                to_sha=carried_sha,
                kind="local",
                reason=_local_issue_reason(diag),
                applyable=False,
            )
        )

    return tuple(suggestions)


def _resolve_previous_carry_pin(
    *,
    workspace_root: Path,
    repo: ReleaseRepo,
    ref: str,
    repo_sel: ReleaseRepo,
    diag: RepoReadiness | None,
    prev_sha: str,
    prev_ref: str,
) -> Result[tuple[PinnedRepo, tuple[AutoSuggestion, ...]], RepoReadiness]:
    wf = repo.required_ci_workflow_file
    if wf is None:
        return Err(
            _diag_blocker(
                workspace_root=workspace_root,
                repo=repo,
                ref=ref,
                diag=diag,
                error="repo is not CI-gated (auto is strict)",
            )
        )

    ok = is_ci_green_for_sha(
        workspace_root=workspace_root,
        repo=repo.slug,
        workflow=wf,
        sha=prev_sha,
    )
    if isinstance(ok, Err):
        return Err(
            _diag_blocker(
                workspace_root=workspace_root,
                repo=repo,
                ref=ref,
                diag=diag,
                error=ok.error.message,
            )
        )
    if not ok.value:
        return Err(
            _diag_blocker(
                workspace_root=workspace_root,
                repo=repo,
                ref=ref,
                diag=diag,
                error=f"previous pin is not CI green: {repo.slug}@{prev_sha}",
            )
        )

    repo_carried = _repo_with_ref(repo=repo, ref=prev_ref)
    suggestions = _collect_carry_mode_suggestions(
        workspace_root=workspace_root,
        repo=repo,
        repo_sel=repo_sel,
        diag=diag,
        carried_sha=prev_sha,
    )
    return Ok((PinnedRepo(repo=repo_carried, sha=prev_sha), suggestions))


def _resolve_latest_green_carry_pin(
    *,
    workspace_root: Path,
    repo: ReleaseRepo,
    ref: str,
    repo_sel: ReleaseRepo,
    diag: RepoReadiness | None,
) -> Result[PinnedRepo, RepoReadiness]:
    latest_r = _find_latest_green_sha(
        workspace_root=workspace_root,
        repo=repo_sel,
        limit_commits=30,
        limit_runs=200,
    )
    if isinstance(latest_r, Err):
        return Err(
            _diag_blocker(
                workspace_root=workspace_root,
                repo=repo,
                ref=ref,
                diag=diag,
                error=latest_r.error.message,
            )
        )

    latest = latest_r.value
    if latest is None:
        return Err(
            _diag_blocker(
                workspace_root=workspace_root,
                repo=repo,
                ref=ref,
                diag=diag,
                error=f"no green commits found on {repo.slug}@{ref}",
            )
        )

    return Ok(PinnedRepo(repo=repo_sel, sha=latest))


def _resolve_carry_mode_pin(
    *,
    workspace_root: Path,
    repo: ReleaseRepo,
    ref: str,
    repo_sel: ReleaseRepo,
    diag: RepoReadiness | None,
    prev_pins: dict[str, tuple[str, str]],
) -> Result[tuple[PinnedRepo, tuple[AutoSuggestion, ...]], RepoReadiness]:
    prev = prev_pins.get(repo.id)
    if prev is not None:
        prev_sha, prev_ref = prev
        return _resolve_previous_carry_pin(
            workspace_root=workspace_root,
            repo=repo,
            ref=ref,
            repo_sel=repo_sel,
            diag=diag,
            prev_sha=prev_sha,
            prev_ref=prev_ref,
        )

    latest_pin = _resolve_latest_green_carry_pin(
        workspace_root=workspace_root,
        repo=repo,
        ref=ref,
        repo_sel=repo_sel,
        diag=diag,
    )
    if isinstance(latest_pin, Err):
        return latest_pin
    return Ok((latest_pin.value, ()))


def _probe_repo_diagnostics(
    *,
    workspace_root: Path,
    repos: tuple[ReleaseRepo, ...],
    ref_overrides: dict[str, str],
) -> dict[str, RepoReadiness]:
    diagnostics: dict[str, RepoReadiness] = {}
    for repo in repos:
        ref = _resolve_repo_ref(repo=repo, ref_overrides=ref_overrides)
        rr = probe_release_readiness(workspace_root=workspace_root, repo=repo, ref=ref)
        if isinstance(rr, Ok):
            diagnostics[repo.id] = rr.value
    return diagnostics


def _load_previous_channel_pins(
    *,
    workspace_root: Path,
    channel: ReleaseChannel,
    dist_repo: str,
) -> Result[dict[str, tuple[str, str]], str]:
    releases_r = list_distribution_releases(
        workspace_root=workspace_root,
        repo=dist_repo,
        limit=100,
    )
    if isinstance(releases_r, Err):
        return Err(releases_r.error.message)

    history = compute_history(releases_r.value)
    prev_tag = _prev_dist_tag_for_channel(channel=channel, history=history)
    if prev_tag is None:
        return Ok({})

    prev_pins_r = _load_prev_pins(workspace_root=workspace_root, dist_repo=dist_repo, tag=prev_tag)
    if isinstance(prev_pins_r, Err):
        return Err(f"failed to load previous pins for {prev_tag}: {prev_pins_r.error.message}")
    return Ok(prev_pins_r.value)


def resolve_pinned_auto_smart(
    *,
    workspace_root: Path,
    channel: ReleaseChannel,
    dist_repo: str,
    repos: tuple[ReleaseRepo, ...],
    ref_overrides: dict[str, str],
    head_repo_ids: frozenset[str],
) -> Result[tuple[tuple[PinnedRepo, ...], tuple[AutoSuggestion, ...]], tuple[RepoReadiness, ...]]:
    dist_repo_entry = ReleaseRepo(
        id="distribution",
        slug=dist_repo,
        ref="main",
        required_ci_workflow_file=None,
    )

    diagnostics = _probe_repo_diagnostics(
        workspace_root=workspace_root,
        repos=repos,
        ref_overrides=ref_overrides,
    )

    prev_pins_r = _load_previous_channel_pins(
        workspace_root=workspace_root,
        channel=channel,
        dist_repo=dist_repo,
    )
    if isinstance(prev_pins_r, Err):
        return Err(
            (
                _dist_blocker(
                    workspace_root=workspace_root,
                    dist_repo_entry=dist_repo_entry,
                    error=prev_pins_r.error,
                ),
            )
        )
    prev_pins = prev_pins_r.value

    pinned: list[PinnedRepo] = []
    suggestions: list[AutoSuggestion] = []
    blockers: list[RepoReadiness] = []

    for repo in repos:
        ref = _resolve_repo_ref(repo=repo, ref_overrides=ref_overrides)
        repo_sel = _repo_with_ref(repo=repo, ref=ref)
        diag = diagnostics.get(repo.id)

        if _is_head_mode_repo(
            repo=repo,
            ref=ref,
            ref_overrides=ref_overrides,
            head_repo_ids=head_repo_ids,
        ):
            head_pin = _resolve_head_mode_pin(
                workspace_root=workspace_root,
                repo=repo,
                ref=ref,
                repo_sel=repo_sel,
                diag=diag,
            )
            if isinstance(head_pin, Err):
                blockers.append(head_pin.error)
                continue
            pinned.append(head_pin.value)
            continue

        carry_pin = _resolve_carry_mode_pin(
            workspace_root=workspace_root,
            repo=repo,
            ref=ref,
            repo_sel=repo_sel,
            diag=diag,
            prev_pins=prev_pins,
        )
        if isinstance(carry_pin, Err):
            blockers.append(carry_pin.error)
            continue

        selected, carry_suggestions = carry_pin.value
        pinned.append(selected)
        suggestions.extend(carry_suggestions)

    if blockers:
        return Err(tuple(blockers))

    # Preserve repo order from config.
    by_id = {p.repo.id: p for p in pinned}
    pinned_out = tuple(by_id[r.id] for r in repos if r.id in by_id)
    return Ok((pinned_out, tuple(suggestions)))
