from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ms.core.result import Err, Ok, Result
from ms.git.repository import Repository
from ms.release.domain.config import MS_DEFAULT_BRANCH, MS_REPO_SLUG
from ms.release.errors import ReleaseError
from ms.release.infra.github.client import get_ref_head_sha

DependencyPinSource = Literal["workspace", "github"]
RefResolver = Callable[[str, str], Result[str, ReleaseError]]


@dataclass(frozen=True, slots=True)
class CoreDependencyRepo:
    env_key: str
    repo_path: str
    repo_slug: str


CI_ENV_REPOS: tuple[CoreDependencyRepo, ...] = (
    CoreDependencyRepo("MS_DEV_ENV_SHA", ".", MS_REPO_SLUG),
    CoreDependencyRepo(
        "OPEN_CONTROL_FRAMEWORK_SHA", "open-control/framework", "open-control/framework"
    ),
    CoreDependencyRepo("OPEN_CONTROL_NOTE_SHA", "open-control/note", "open-control/note"),
    CoreDependencyRepo(
        "OPEN_CONTROL_HAL_MIDI_SHA", "open-control/hal-midi", "open-control/hal-midi"
    ),
    CoreDependencyRepo("OPEN_CONTROL_HAL_NET_SHA", "open-control/hal-net", "open-control/hal-net"),
    CoreDependencyRepo("OPEN_CONTROL_HAL_SDL_SHA", "open-control/hal-sdl", "open-control/hal-sdl"),
    CoreDependencyRepo("OPEN_CONTROL_UI_LVGL_SHA", "open-control/ui-lvgl", "open-control/ui-lvgl"),
    CoreDependencyRepo(
        "OPEN_CONTROL_UI_LVGL_COMPONENTS_SHA",
        "open-control/ui-lvgl-components",
        "open-control/ui-lvgl-components",
    ),
    CoreDependencyRepo("MIDI_STUDIO_UI_SHA", "midi-studio/ui", "petitechose-midi-studio/ui"),
)


def dependency_shas(
    *,
    workspace_root: Path,
    source: DependencyPinSource,
    ref_resolver: RefResolver | None,
) -> Result[dict[str, str], ReleaseError]:
    if source == "github":
        return _github_shas(workspace_root=workspace_root, ref_resolver=ref_resolver)
    return _workspace_shas(workspace_root=workspace_root)


def _workspace_shas(*, workspace_root: Path) -> Result[dict[str, str], ReleaseError]:
    paths = {repo.repo_path for repo in CI_ENV_REPOS}
    paths.add("midi-studio/ui")

    shas: dict[str, str] = {}
    for repo_path in sorted(paths):
        repo_root = workspace_root if repo_path == "." else workspace_root / repo_path
        repo = Repository(repo_root)
        if not repo.exists():
            return Err(
                ReleaseError(
                    kind="invalid_input",
                    message=f"dependency repo unavailable: {repo_path}",
                    hint="Run: uv run ms sync --repos",
                )
            )
        head = repo.head_sha()
        if isinstance(head, Err):
            return Err(
                ReleaseError(
                    kind="repo_failed",
                    message=f"failed to read dependency SHA: {repo_path}",
                    hint=head.error.message,
                )
            )
        shas[repo_path] = head.value
    return Ok(shas)


def _github_shas(
    *,
    workspace_root: Path,
    ref_resolver: RefResolver | None,
) -> Result[dict[str, str], ReleaseError]:
    resolver = ref_resolver or _github_ref_resolver(workspace_root=workspace_root)
    shas: dict[str, str] = {}
    for repo in CI_ENV_REPOS:
        resolved = resolver(repo.repo_slug, MS_DEFAULT_BRANCH)
        if isinstance(resolved, Err):
            return resolved
        shas[repo.repo_path] = resolved.value
    return Ok(shas)


def _github_ref_resolver(*, workspace_root: Path) -> RefResolver:
    def resolve(repo: str, ref: str) -> Result[str, ReleaseError]:
        return get_ref_head_sha(workspace_root=workspace_root, repo=repo, ref=ref)

    return resolve
