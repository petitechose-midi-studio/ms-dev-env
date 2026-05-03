from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.git.repository import Repository
from ms.release.errors import ReleaseError

_SHA_RE = r"[0-9a-fA-F]{40}"
_MS_UI_RELEASE_RE = re.compile(
    rf"(?m)^(\s*ms-ui=https://github\.com/petitechose-midi-studio/ui\.git#)({_SHA_RE})(\s*)$"
)

_CI_ENV_REPOS: tuple[tuple[str, str], ...] = (
    ("MS_DEV_ENV_SHA", "."),
    ("OPEN_CONTROL_FRAMEWORK_SHA", "open-control/framework"),
    ("OPEN_CONTROL_NOTE_SHA", "open-control/note"),
    ("OPEN_CONTROL_HAL_MIDI_SHA", "open-control/hal-midi"),
    ("OPEN_CONTROL_HAL_NET_SHA", "open-control/hal-net"),
    ("OPEN_CONTROL_HAL_SDL_SHA", "open-control/hal-sdl"),
    ("OPEN_CONTROL_UI_LVGL_SHA", "open-control/ui-lvgl"),
    ("OPEN_CONTROL_UI_LVGL_COMPONENTS_SHA", "open-control/ui-lvgl-components"),
    ("MIDI_STUDIO_UI_SHA", "midi-studio/ui"),
)


@dataclass(frozen=True, slots=True)
class CoreDependencyPinItem:
    key: str
    path: Path
    from_sha: str | None
    to_sha: str
    changed: bool


@dataclass(frozen=True, slots=True)
class CoreDependencyPinPlan:
    items: tuple[CoreDependencyPinItem, ...]
    requires_write: bool


@dataclass(frozen=True, slots=True)
class CoreDependencyPinSyncResult:
    plan: CoreDependencyPinPlan
    written: tuple[Path, ...]


def plan_core_dependency_pin_sync(
    *, workspace_root: Path, core_root: Path | None = None
) -> Result[CoreDependencyPinPlan, ReleaseError]:
    core = core_root or workspace_root / "midi-studio" / "core"
    platformio = core / "platformio.ini"
    ci = core / ".github" / "workflows" / "ci.yml"

    shas = _workspace_shas(workspace_root=workspace_root)
    if isinstance(shas, Err):
        return shas

    platformio_text = _read_text(path=platformio)
    if isinstance(platformio_text, Err):
        return platformio_text
    ci_text = _read_text(path=ci)
    if isinstance(ci_text, Err):
        return ci_text

    ms_ui_sha = shas.value["midi-studio/ui"]
    ms_ui_current = _extract_ms_ui_release_pin(platformio_text.value)
    if ms_ui_current is None:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message="missing pinned ms-ui dependency in core/platformio.ini",
                hint="Expected: ms-ui=https://github.com/petitechose-midi-studio/ui.git#<sha>",
            )
        )

    items = [
        CoreDependencyPinItem(
            key="platformio.ms-ui",
            path=platformio,
            from_sha=ms_ui_current,
            to_sha=ms_ui_sha,
            changed=ms_ui_current != ms_ui_sha,
        )
    ]

    for env_key, repo_path in _CI_ENV_REPOS:
        current = _extract_ci_env_pin(ci_text.value, env_key)
        target = shas.value[repo_path]
        items.append(
            CoreDependencyPinItem(
                key=f"ci.{env_key}",
                path=ci,
                from_sha=current,
                to_sha=target,
                changed=current != target,
            )
        )

    return Ok(
        CoreDependencyPinPlan(
            items=tuple(items),
            requires_write=any(item.changed for item in items),
        )
    )


def sync_core_dependency_pins(
    *, workspace_root: Path, core_root: Path | None = None
) -> Result[CoreDependencyPinSyncResult, ReleaseError]:
    core = core_root or workspace_root / "midi-studio" / "core"
    plan = plan_core_dependency_pin_sync(workspace_root=workspace_root, core_root=core)
    if isinstance(plan, Err):
        return plan
    if not plan.value.requires_write:
        return Ok(CoreDependencyPinSyncResult(plan=plan.value, written=()))

    by_path: dict[Path, list[CoreDependencyPinItem]] = {}
    for item in plan.value.items:
        if item.changed:
            by_path.setdefault(item.path, []).append(item)

    written: list[Path] = []
    for path, items in by_path.items():
        text = _read_text(path=path)
        if isinstance(text, Err):
            return text
        rendered = _apply_items(text=text.value, items=tuple(items))
        write = _atomic_write_text(path=path, content=rendered)
        if isinstance(write, Err):
            return write
        written.append(path)

    verified = plan_core_dependency_pin_sync(workspace_root=workspace_root, core_root=core)
    if isinstance(verified, Err):
        return verified
    if verified.value.requires_write:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message="post-write verification failed for core dependency pins",
                hint=", ".join(item.key for item in verified.value.items if item.changed),
            )
        )

    return Ok(CoreDependencyPinSyncResult(plan=plan.value, written=tuple(written)))


def _workspace_shas(*, workspace_root: Path) -> Result[dict[str, str], ReleaseError]:
    paths = {repo_path for _, repo_path in _CI_ENV_REPOS}
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


def _read_text(*, path: Path) -> Result[str, ReleaseError]:
    try:
        return Ok(path.read_text(encoding="utf-8"))
    except OSError as error:
        return Err(
            ReleaseError(kind="invalid_input", message=f"failed to read {path}", hint=str(error))
        )


def _extract_ms_ui_release_pin(text: str) -> str | None:
    match = _MS_UI_RELEASE_RE.search(text)
    return match.group(2).lower() if match else None


def _extract_ci_env_pin(text: str, key: str) -> str | None:
    match = re.search(rf"(?m)^(\s*{re.escape(key)}:\s*)({_SHA_RE})(\s*)$", text)
    return match.group(2).lower() if match else None


def _apply_items(*, text: str, items: tuple[CoreDependencyPinItem, ...]) -> str:
    rendered = text
    for item in items:
        if item.key == "platformio.ms-ui":
            rendered = _MS_UI_RELEASE_RE.sub(rf"\g<1>{item.to_sha}\g<3>", rendered)
            continue
        if item.key.startswith("ci."):
            env_key = item.key.removeprefix("ci.")
            rendered, count = re.subn(
                rf"(?m)^(\s*{re.escape(env_key)}:\s*)({_SHA_RE})(\s*)$",
                rf"\g<1>{item.to_sha}\g<3>",
                rendered,
            )
            if count == 0:
                rendered = _insert_ci_env_pin(text=rendered, key=env_key, sha=item.to_sha)
    return rendered


def _insert_ci_env_pin(*, text: str, key: str, sha: str) -> str:
    had_trailing_newline = text.endswith("\n")
    lines = text.splitlines()
    entry = f"  {key}: {sha}"

    env_index = next(
        (index for index, line in enumerate(lines) if line == "env:"),
        None,
    )
    if env_index is None:
        lines = ["env:", entry, "", *lines]
    else:
        insert_at = env_index + 1
        while insert_at < len(lines):
            line = lines[insert_at]
            if line.strip() and not line.startswith((" ", "\t")):
                break
            insert_at += 1
        lines.insert(insert_at, entry)

    rendered = "\n".join(lines)
    if had_trailing_newline:
        rendered += "\n"
    return rendered


def _atomic_write_text(*, path: Path, content: str) -> Result[None, ReleaseError]:
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="\n",
            delete=False,
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        ) as handle:
            handle.write(content)
            tmp_path = Path(handle.name)
        os.replace(tmp_path, path)
    except OSError as error:
        return Err(
            ReleaseError(kind="invalid_input", message=f"failed to write {path}", hint=str(error))
        )
    return Ok(None)
