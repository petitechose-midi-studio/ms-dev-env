from __future__ import annotations

import re

from ms.core.workspace import Workspace
from ms.platform.detection import Platform

from .models import UnitTestRunner, UnitTestTarget


def toolchain_build_id(platform: Platform) -> str:
    return "zig-windows-gnu" if platform.is_windows else "host"


def target_map(workspace: Workspace, platform: Platform) -> dict[str, UnitTestTarget]:
    build_root = workspace.build_dir / "tests" / toolchain_build_id(platform)
    return {
        "ms-dev-env": UnitTestTarget(
            name="ms-dev-env",
            runner=UnitTestRunner.PYTEST,
            source_dir=workspace.root,
            build_dir=build_root / "ms-dev-env",
            label="ms-dev-env",
            env_vars=(("MS_ARCH_CHECKS", "1"),),
        ),
        "protocol-codegen": UnitTestTarget(
            name="protocol-codegen",
            runner=UnitTestRunner.PYTEST,
            source_dir=workspace.open_control_dir / "protocol-codegen",
            build_dir=build_root / "protocol-codegen",
            label="protocol-codegen",
        ),
        "open-control-bridge": UnitTestTarget(
            name="open-control-bridge",
            runner=UnitTestRunner.CARGO,
            source_dir=workspace.open_control_dir / "bridge",
            build_dir=build_root / "open-control-bridge",
            label="open-control-bridge",
        ),
        "midi-studio-loader": UnitTestTarget(
            name="midi-studio-loader",
            runner=UnitTestRunner.CARGO,
            source_dir=workspace.midi_studio_dir / "loader",
            build_dir=build_root / "midi-studio-loader",
            label="midi-studio-loader",
        ),
        "ms-manager-svelte": UnitTestTarget(
            name="ms-manager-svelte",
            runner=UnitTestRunner.NPM,
            source_dir=workspace.root / "ms-manager",
            build_dir=build_root / "ms-manager-svelte",
            label="ms-manager-svelte",
            runner_args=("run", "check"),
        ),
        "ms-manager-node": UnitTestTarget(
            name="ms-manager-node",
            runner=UnitTestRunner.NPM,
            source_dir=workspace.root / "ms-manager",
            build_dir=build_root / "ms-manager-node",
            label="ms-manager-node",
            runner_args=("run", "test:tauri-versioning"),
        ),
        "ms-manager-core": UnitTestTarget(
            name="ms-manager-core",
            runner=UnitTestRunner.CARGO,
            source_dir=workspace.root / "ms-manager" / "crates" / "ms-manager-core",
            build_dir=build_root / "ms-manager-core",
            label="ms-manager-core",
        ),
        "ms-manager-tauri": UnitTestTarget(
            name="ms-manager-tauri",
            runner=UnitTestRunner.CARGO_CHECK,
            source_dir=workspace.root / "ms-manager" / "src-tauri",
            build_dir=build_root / "ms-manager-tauri",
            label="ms-manager-tauri",
            runner_args=("check", "--locked"),
        ),
        "open-control-framework": UnitTestTarget(
            name="open-control-framework",
            runner=UnitTestRunner.CMAKE,
            source_dir=workspace.open_control_dir / "framework",
            build_dir=build_root / "open-control-framework",
            label="open-control-framework",
        ),
        "open-control-note": UnitTestTarget(
            name="open-control-note",
            runner=UnitTestRunner.CMAKE,
            source_dir=workspace.open_control_dir / "note",
            build_dir=build_root / "open-control-note",
            label="open-control-note",
            dependencies=("open-control-framework",),
        ),
        "open-control-hal-midi": UnitTestTarget(
            name="open-control-hal-midi",
            runner=UnitTestRunner.CMAKE,
            source_dir=workspace.open_control_dir / "hal-midi",
            build_dir=build_root / "open-control-hal-midi",
            label="open-control-hal-midi",
        ),
        "core": UnitTestTarget(
            name="core",
            runner=UnitTestRunner.CMAKE,
            source_dir=workspace.midi_studio_dir / "core",
            build_dir=build_root / "midi-studio-core",
            label="core",
            dependencies=("open-control-framework", "open-control-note"),
        ),
        "plugin-bitwig": UnitTestTarget(
            name="plugin-bitwig",
            runner=UnitTestRunner.CMAKE,
            source_dir=workspace.midi_studio_dir / "plugin-bitwig",
            build_dir=build_root / "midi-studio-plugin-bitwig",
            label="plugin-bitwig",
        ),
    }


def target_groups() -> dict[str, tuple[str, ...]]:
    firmware = (
        "open-control-framework",
        "open-control-hal-midi",
        "open-control-note",
        "core",
        "plugin-bitwig",
    )
    app = (
        "open-control-bridge",
        "midi-studio-loader",
        "ms-manager-svelte",
        "ms-manager-node",
        "ms-manager-core",
        "ms-manager-tauri",
    )
    env = ("ms-dev-env", "protocol-codegen")
    return {"all": (*env, *app, *firmware), "env": env, "app": app, "firmware": firmware}


def normalize_cmake_test_targets(names: tuple[str, ...]) -> tuple[str, ...] | None:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_name in names:
        name = raw_name.strip()
        if not name:
            return None
        if not name.startswith("test_"):
            name = f"test_{name}"
        if re.fullmatch(r"[A-Za-z0-9_.+-]+", name) is None:
            return None
        if name in seen:
            continue
        seen.add(name)
        normalized.append(name)
    return tuple(normalized)


def topological_targets(targets: dict[str, UnitTestTarget]) -> tuple[UnitTestTarget, ...]:
    ordered: list[UnitTestTarget] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(name: str) -> None:
        if name in visited:
            return
        if name in visiting:
            raise ValueError(f"cycle in unit test target dependencies: {name}")
        visiting.add(name)
        target = targets[name]
        for dependency in target.dependencies:
            visit(dependency)
        visiting.remove(name)
        visited.add(name)
        ordered.append(target)

    for name in targets:
        visit(name)
    return tuple(ordered)
