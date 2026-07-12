from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.release.errors import ReleaseError
from ms.release.infra.atomic_text_file import read_utf8_text, write_utf8_text_atomic
from ms.release.flow.core_dependency_pin_sources import (
    CI_ENV_REPOS,
    DependencyPinSource,
    RefResolver,
    dependency_shas,
)

_SHA_RE = r"[0-9a-fA-F]{40}"
_MS_UI_RELEASE_RE = re.compile(
    rf"(?m)^(\s*ms-ui=https://github\.com/petitechose-midi-studio/ui\.git#)({_SHA_RE})(\s*)$"
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
    *,
    workspace_root: Path,
    core_root: Path | None = None,
    source: DependencyPinSource = "workspace",
    ref_resolver: RefResolver | None = None,
) -> Result[CoreDependencyPinPlan, ReleaseError]:
    core = core_root or workspace_root / "midi-studio" / "core"
    platformio = core / "platformio.ini"
    ci = core / ".github" / "workflows" / "ci.yml"

    shas = dependency_shas(
        workspace_root=workspace_root,
        source=source,
        ref_resolver=ref_resolver,
    )
    if isinstance(shas, Err):
        return shas

    platformio_text = read_utf8_text(path=platformio)
    if isinstance(platformio_text, Err):
        return platformio_text
    ci_text = read_utf8_text(path=ci)
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

    for repo in CI_ENV_REPOS:
        current = _extract_ci_env_pin(ci_text.value, repo.env_key)
        target = shas.value[repo.repo_path]
        items.append(
            CoreDependencyPinItem(
                key=f"ci.{repo.env_key}",
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
    *,
    workspace_root: Path,
    core_root: Path | None = None,
    source: DependencyPinSource = "workspace",
    ref_resolver: RefResolver | None = None,
) -> Result[CoreDependencyPinSyncResult, ReleaseError]:
    core = core_root or workspace_root / "midi-studio" / "core"
    plan = plan_core_dependency_pin_sync(
        workspace_root=workspace_root,
        core_root=core,
        source=source,
        ref_resolver=ref_resolver,
    )
    if isinstance(plan, Err):
        return plan
    synced = sync_core_dependency_pin_plan(plan=plan.value)
    if isinstance(synced, Err):
        return synced

    verified = plan_core_dependency_pin_sync(
        workspace_root=workspace_root,
        core_root=core,
        source=source,
        ref_resolver=ref_resolver,
    )
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

    return synced


def sync_core_dependency_pin_plan(
    *, plan: CoreDependencyPinPlan
) -> Result[CoreDependencyPinSyncResult, ReleaseError]:
    if not plan.requires_write:
        return Ok(CoreDependencyPinSyncResult(plan=plan, written=()))

    by_path: dict[Path, list[CoreDependencyPinItem]] = {}
    for item in plan.items:
        if item.changed:
            by_path.setdefault(item.path, []).append(item)

    written: list[Path] = []
    for path, items in by_path.items():
        text = read_utf8_text(path=path)
        if isinstance(text, Err):
            return text
        rendered = _apply_items(text=text.value, items=tuple(items))
        write = write_utf8_text_atomic(path=path, content=rendered)
        if isinstance(write, Err):
            return write
        written.append(path)

    verified = _verify_written_plan(plan=plan)
    if isinstance(verified, Err):
        return verified

    return Ok(CoreDependencyPinSyncResult(plan=plan, written=tuple(written)))


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


def _verify_written_plan(*, plan: CoreDependencyPinPlan) -> Result[None, ReleaseError]:
    for item in plan.items:
        if not item.changed:
            continue
        text = read_utf8_text(path=item.path)
        if isinstance(text, Err):
            return text
        current = _extract_item_pin(text=text.value, key=item.key)
        if current != item.to_sha:
            return Err(
                ReleaseError(
                    kind="invalid_input",
                    message="post-write verification failed for core dependency pins",
                    hint=f"{item.key}: expected {item.to_sha}, found {current or 'unset'}",
                )
            )
    return Ok(None)


def _extract_item_pin(*, text: str, key: str) -> str | None:
    if key == "platformio.ms-ui":
        return _extract_ms_ui_release_pin(text)
    if key.startswith("ci."):
        return _extract_ci_env_pin(text, key.removeprefix("ci."))
    return None


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
