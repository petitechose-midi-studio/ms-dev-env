from __future__ import annotations

import configparser
import re
from dataclasses import dataclass
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.platform.process import run as run_process
from ms.services.release.errors import ReleaseError
from ms.services.release.gh import run_gh_read
from ms.services.release.timeouts import GH_TIMEOUT_SECONDS, GIT_TIMEOUT_SECONDS

OC_SDK_REPOS: tuple[str, ...] = (
    "framework",
    "hal-common",
    "hal-teensy",
    "ui-lvgl",
    "ui-lvgl-components",
)

OC_SDK_LOCK_FILE = "oc-sdk.ini"

_OC_GIT_URL_RE = re.compile(
    r"^https://github\.com/open-control/(?P<repo>[^/]+)\.git#(?P<sha>[0-9a-fA-F]{40})$"
)


@dataclass(frozen=True, slots=True)
class OcSdkPin:
    repo: str
    sha: str


@dataclass(frozen=True, slots=True)
class OcSdkLock:
    version: str
    pins: tuple[OcSdkPin, ...]

    def pins_by_repo(self) -> dict[str, str]:
        return {p.repo: p.sha for p in self.pins}


@dataclass(frozen=True, slots=True)
class OcSdkLoad:
    lock: OcSdkLock | None
    source: str | None  # "git" | "gh"
    error: str | None


@dataclass(frozen=True, slots=True)
class OpenControlRepoState:
    repo: str
    path: Path
    exists: bool
    head_sha: str | None
    dirty: bool


@dataclass(frozen=True, slots=True)
class OcSdkMismatch:
    repo: str
    pinned_sha: str
    local_sha: str


@dataclass(frozen=True, slots=True)
class OpenControlPreflightReport:
    oc_sdk: OcSdkLoad
    repos: tuple[OpenControlRepoState, ...]
    mismatches: tuple[OcSdkMismatch, ...]

    def dirty_repos(self) -> tuple[OpenControlRepoState, ...]:
        return tuple(r for r in self.repos if r.exists and r.dirty)


def parse_oc_sdk_ini(*, text: str) -> Result[OcSdkLock, ReleaseError]:
    cfg = configparser.ConfigParser(interpolation=None)
    try:
        cfg.read_string(text)
    except (configparser.Error, ValueError) as e:
        return Err(ReleaseError(kind="invalid_input", message=f"invalid {OC_SDK_LOCK_FILE}: {e}"))

    if not cfg.has_section("oc_sdk"):
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"missing [oc_sdk] in {OC_SDK_LOCK_FILE}",
            )
        )
    if not cfg.has_section("oc_sdk_deps"):
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"missing [oc_sdk_deps] in {OC_SDK_LOCK_FILE}",
            )
        )

    version = cfg.get("oc_sdk", "version", fallback="").strip()
    if not version:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"missing oc_sdk.version in {OC_SDK_LOCK_FILE}",
            )
        )

    lib_deps_raw = cfg.get("oc_sdk_deps", "lib_deps", fallback="")
    lines = [ln.strip() for ln in lib_deps_raw.splitlines() if ln.strip()]
    if not lines:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"missing oc_sdk_deps.lib_deps in {OC_SDK_LOCK_FILE}",
            )
        )

    pins: dict[str, str] = {}
    for ln in lines:
        if "=" not in ln:
            continue
        _, url = ln.split("=", 1)
        url = url.strip()
        m = _OC_GIT_URL_RE.match(url)
        if not m:
            continue
        repo = m.group("repo")
        sha = m.group("sha").lower()
        pins[repo] = sha

    missing = [r for r in OC_SDK_REPOS if r not in pins]
    if missing:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"oc-sdk lock missing pins: {', '.join(missing)}",
                hint=OC_SDK_LOCK_FILE,
            )
        )

    ordered = tuple(OcSdkPin(repo=r, sha=pins[r]) for r in OC_SDK_REPOS)
    return Ok(OcSdkLock(version=version, pins=ordered))


def _load_oc_sdk_from_git(*, repo_root: Path, core_sha: str) -> Result[str, ReleaseError]:
    r = run_process(
        ["git", "show", f"{core_sha}:{OC_SDK_LOCK_FILE}"],
        cwd=repo_root,
        timeout=GIT_TIMEOUT_SECONDS,
    )
    if isinstance(r, Err):
        e = r.error
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"failed to read {OC_SDK_LOCK_FILE} from core@{core_sha}",
                hint=e.stderr.strip() or e.stdout.strip() or None,
            )
        )
    return Ok(r.value)


def _load_oc_sdk_from_gh(*, workspace_root: Path, core_sha: str) -> Result[str, ReleaseError]:
    endpoint = f"repos/petitechose-midi-studio/core/contents/{OC_SDK_LOCK_FILE}?ref={core_sha}"
    r = run_gh_read(
        workspace_root=workspace_root,
        cmd=["gh", "api", "-H", "Accept: application/vnd.github.raw", endpoint],
        kind="invalid_input",
        message=f"failed to download {OC_SDK_LOCK_FILE} from core@{core_sha}",
        hint=endpoint,
        timeout=GH_TIMEOUT_SECONDS,
    )
    if isinstance(r, Err):
        return r
    return Ok(r.value)


def load_oc_sdk_lock(*, workspace_root: Path, core_sha: str) -> OcSdkLoad:
    # Prefer a local workspace checkout if present (no network).
    local_core = workspace_root / "midi-studio" / "core"
    if local_core.is_dir() and (local_core / ".git").exists():
        raw = _load_oc_sdk_from_git(repo_root=local_core, core_sha=core_sha)
        if isinstance(raw, Ok):
            parsed = parse_oc_sdk_ini(text=raw.value)
            if isinstance(parsed, Ok):
                return OcSdkLoad(lock=parsed.value, source="git", error=None)
            return OcSdkLoad(lock=None, source="git", error=parsed.error.message)
        # Keep going: fall back to gh.

    raw = _load_oc_sdk_from_gh(workspace_root=workspace_root, core_sha=core_sha)
    if isinstance(raw, Ok):
        parsed = parse_oc_sdk_ini(text=raw.value)
        if isinstance(parsed, Ok):
            return OcSdkLoad(lock=parsed.value, source="gh", error=None)
        return OcSdkLoad(lock=None, source="gh", error=parsed.error.message)

    return OcSdkLoad(lock=None, source=None, error=raw.error.message)


def _is_git_repo(path: Path) -> bool:
    return (path / ".git").exists() or (path / ".git").is_file()


def _git_head_sha(*, repo_root: Path) -> str | None:
    r = run_process(["git", "rev-parse", "HEAD"], cwd=repo_root, timeout=GIT_TIMEOUT_SECONDS)
    if isinstance(r, Err):
        return None
    sha = r.value.strip()
    if len(sha) != 40:
        return None
    return sha


def _git_is_dirty(*, repo_root: Path) -> bool:
    r = run_process(["git", "status", "--porcelain"], cwd=repo_root, timeout=GIT_TIMEOUT_SECONDS)
    if isinstance(r, Err):
        return False
    return r.value.strip() != ""


def collect_open_control_repos(*, workspace_root: Path) -> tuple[OpenControlRepoState, ...]:
    base = workspace_root / "open-control"
    states: list[OpenControlRepoState] = []
    for repo in OC_SDK_REPOS:
        path = base / repo
        exists = path.is_dir() and _is_git_repo(path)
        if not exists:
            states.append(
                OpenControlRepoState(repo=repo, path=path, exists=False, head_sha=None, dirty=False)
            )
            continue
        head = _git_head_sha(repo_root=path)
        dirty = _git_is_dirty(repo_root=path)
        states.append(
            OpenControlRepoState(repo=repo, path=path, exists=True, head_sha=head, dirty=dirty)
        )
    return tuple(states)


def preflight_open_control(*, workspace_root: Path, core_sha: str) -> OpenControlPreflightReport:
    repos = collect_open_control_repos(workspace_root=workspace_root)
    oc_sdk = load_oc_sdk_lock(workspace_root=workspace_root, core_sha=core_sha)

    mismatches: list[OcSdkMismatch] = []
    if oc_sdk.lock is not None:
        pins = oc_sdk.lock.pins_by_repo()
        for r in repos:
            if not r.exists or r.head_sha is None:
                continue
            pinned = pins.get(r.repo)
            if pinned is None:
                continue
            if pinned != r.head_sha:
                mismatches.append(
                    OcSdkMismatch(repo=r.repo, pinned_sha=pinned, local_sha=r.head_sha)
                )

    return OpenControlPreflightReport(
        oc_sdk=oc_sdk,
        repos=repos,
        mismatches=tuple(mismatches),
    )
