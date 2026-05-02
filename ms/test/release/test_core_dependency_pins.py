from __future__ import annotations

import subprocess
from pathlib import Path

from ms.core.result import Ok
from ms.release.flow.core_dependency_pins import (
    plan_core_dependency_pin_sync,
    sync_core_dependency_pins,
)


def _git_repo(path: Path) -> str:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)
    (path / "README.md").write_text(path.name, encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=path, check=True)
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=path, text=True).strip()


_CI_ENV_KEYS = (
    "MS_DEV_ENV_SHA",
    "OPEN_CONTROL_FRAMEWORK_SHA",
    "OPEN_CONTROL_NOTE_SHA",
    "OPEN_CONTROL_HAL_MIDI_SHA",
    "OPEN_CONTROL_HAL_NET_SHA",
    "OPEN_CONTROL_HAL_SDL_SHA",
    "OPEN_CONTROL_UI_LVGL_SHA",
    "OPEN_CONTROL_UI_LVGL_COMPONENTS_SHA",
    "MIDI_STUDIO_UI_SHA",
)


def _write_core_files(core_root: Path, *, ci_keys: tuple[str, ...] = _CI_ENV_KEYS) -> None:
    old = "0" * 40
    (core_root / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    (core_root / "platformio.ini").write_text(
        "\n".join(
            (
                "[env:release]",
                "lib_deps =",
                f"    ms-ui=https://github.com/petitechose-midi-studio/ui.git#{old}",
                "    ${oc_sdk_deps.lib_deps}",
                "",
            )
        ),
        encoding="utf-8",
    )
    (core_root / ".github" / "workflows" / "ci.yml").write_text(
        "\n".join(("env:", *(f"  {key}: {old}" for key in ci_keys), "")),
        encoding="utf-8",
    )


def test_sync_core_dependency_pins_updates_platformio_and_ci_env(tmp_path: Path) -> None:
    workspace = tmp_path
    shas = {
        ".": _git_repo(workspace),
        "open-control/framework": _git_repo(workspace / "open-control" / "framework"),
        "open-control/note": _git_repo(workspace / "open-control" / "note"),
        "open-control/hal-midi": _git_repo(workspace / "open-control" / "hal-midi"),
        "open-control/hal-net": _git_repo(workspace / "open-control" / "hal-net"),
        "open-control/hal-sdl": _git_repo(workspace / "open-control" / "hal-sdl"),
        "open-control/ui-lvgl": _git_repo(workspace / "open-control" / "ui-lvgl"),
        "open-control/ui-lvgl-components": _git_repo(
            workspace / "open-control" / "ui-lvgl-components"
        ),
        "midi-studio/ui": _git_repo(workspace / "midi-studio" / "ui"),
    }
    core_root = workspace / "midi-studio" / "core"
    _write_core_files(core_root)

    planned = plan_core_dependency_pin_sync(workspace_root=workspace, core_root=core_root)

    assert isinstance(planned, Ok)
    assert planned.value.requires_write

    synced = sync_core_dependency_pins(workspace_root=workspace, core_root=core_root)

    assert isinstance(synced, Ok)
    assert {path.name for path in synced.value.written} == {"platformio.ini", "ci.yml"}
    assert shas["midi-studio/ui"] in (core_root / "platformio.ini").read_text(encoding="utf-8")
    ci = (core_root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert f"MS_DEV_ENV_SHA: {shas['.']}" in ci
    assert f"OPEN_CONTROL_HAL_SDL_SHA: {shas['open-control/hal-sdl']}" in ci

    verified = plan_core_dependency_pin_sync(workspace_root=workspace, core_root=core_root)
    assert isinstance(verified, Ok)
    assert not verified.value.requires_write


def test_sync_core_dependency_pins_inserts_missing_ci_env_pins(tmp_path: Path) -> None:
    workspace = tmp_path
    shas = {
        ".": _git_repo(workspace),
        "open-control/framework": _git_repo(workspace / "open-control" / "framework"),
        "open-control/note": _git_repo(workspace / "open-control" / "note"),
        "open-control/hal-midi": _git_repo(workspace / "open-control" / "hal-midi"),
        "open-control/hal-net": _git_repo(workspace / "open-control" / "hal-net"),
        "open-control/hal-sdl": _git_repo(workspace / "open-control" / "hal-sdl"),
        "open-control/ui-lvgl": _git_repo(workspace / "open-control" / "ui-lvgl"),
        "open-control/ui-lvgl-components": _git_repo(
            workspace / "open-control" / "ui-lvgl-components"
        ),
        "midi-studio/ui": _git_repo(workspace / "midi-studio" / "ui"),
    }
    core_root = workspace / "midi-studio" / "core"
    _write_core_files(
        core_root,
        ci_keys=tuple(
            key
            for key in _CI_ENV_KEYS
            if key not in {"OPEN_CONTROL_HAL_MIDI_SHA", "MIDI_STUDIO_UI_SHA"}
        ),
    )

    planned = plan_core_dependency_pin_sync(workspace_root=workspace, core_root=core_root)

    assert isinstance(planned, Ok)
    missing = {item.key: item for item in planned.value.items if item.from_sha is None}
    assert set(missing) == {"ci.OPEN_CONTROL_HAL_MIDI_SHA", "ci.MIDI_STUDIO_UI_SHA"}

    synced = sync_core_dependency_pins(workspace_root=workspace, core_root=core_root)

    assert isinstance(synced, Ok)
    ci = (core_root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert f"OPEN_CONTROL_HAL_MIDI_SHA: {shas['open-control/hal-midi']}" in ci
    assert f"MIDI_STUDIO_UI_SHA: {shas['midi-studio/ui']}" in ci

    verified = plan_core_dependency_pin_sync(workspace_root=workspace, core_root=core_root)
    assert isinstance(verified, Ok)
    assert not verified.value.requires_write
