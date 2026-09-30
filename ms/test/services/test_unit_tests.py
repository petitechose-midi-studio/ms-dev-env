from __future__ import annotations

import os
from pathlib import Path

from pytest import MonkeyPatch

from ms.core.result import Err, Ok
from ms.core.workspace import Workspace
from ms.output.console import MockConsole
from ms.platform.detection import Arch, LinuxDistro, Platform, PlatformInfo, detect
from ms.services.unit_testing import catalog, dependencies, execution
from ms.services.unit_testing.models import (
    UnitTestDependencyError,
    UnitTestRunner,
    UnitTestSelectionInvalid,
)
from ms.services.unit_tests import UnitTestService


def test_target_catalog_is_stable(tmp_path: Path) -> None:
    targets = catalog.target_map(Workspace(root=tmp_path), detect().platform)

    assert {"ms-dev-env", "open-control-framework", "core", "plugin-bitwig"} <= set(targets)
    assert targets["ms-dev-env"].runner is UnitTestRunner.PYTEST
    assert targets["core"].runner is UnitTestRunner.CMAKE
    assert targets["ms-dev-env"].env_vars == (("MS_ARCH_CHECKS", "1"),)


def test_windows_compiler_paths_are_safe_for_cmake_cache(
    tmp_path: Path, monkeypatch: MonkeyPatch,
) -> None:
    service = UnitTestService(
        workspace=Workspace(root=tmp_path),
        platform=PlatformInfo(
            platform=Platform.WINDOWS, arch=Arch.X64, distro=LinuxDistro.UNKNOWN,
        ),
        config=None,
        console=MockConsole(),
    )
    wrapper_dir = tmp_path / "tool wrappers"
    wrapper_dir.mkdir()

    def wrapper(name: str) -> Path:
        path = wrapper_dir / f"{name}.cmd"
        path.touch()
        return path

    monkeypatch.setattr(service._registry, "get_zig_wrapper", wrapper)  # pyright: ignore[reportPrivateUsage]
    result = service._executor._compiler_args()  # pyright: ignore[reportPrivateUsage]
    assert isinstance(result, Ok)
    assert len(result.value) == 5
    assert all(":FILEPATH=" in arg and "\\" not in arg for arg in result.value)
    assert f"-DCMAKE_RC_COMPILER:FILEPATH={wrapper('zig-rc').as_posix()}" in result.value


def test_load_test_dependency_pin_reads_manifest(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    manifest = tmp_path / "test_dependencies.toml"
    manifest.write_text(
        """
[unity]
version = "2.6.1"
url = "https://example.test/unity.zip"
sha256 = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
strip_components = 1
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(dependencies, "_TEST_DEPENDENCIES_PATH", manifest)

    result = dependencies.load_test_dependency_pin("unity")

    assert not isinstance(result, Err)
    assert result.value.version == "2.6.1"
    assert result.value.url == "https://example.test/unity.zip"
    assert result.value.sha256 == "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    assert result.value.strip_components == 1


def test_load_test_dependency_pin_rejects_invalid_manifest(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    manifest = tmp_path / "test_dependencies.toml"
    manifest.write_text(
        """
[unity]
version = "2.6.1"
url = "https://example.test/unity.zip"
sha256 = "not-a-sha"
strip_components = 1
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(dependencies, "_TEST_DEPENDENCIES_PATH", manifest)

    result = dependencies.load_test_dependency_pin("unity")

    assert isinstance(result, Err)
    assert isinstance(result.error, UnitTestDependencyError)
    assert "invalid [unity] entry" in result.error.message


def test_unit_test_groups_are_intentional_without_aliases(tmp_path: Path) -> None:
    service = UnitTestService(
        workspace=Workspace(root=tmp_path),
        platform=detect(),
        config=None,
        console=MockConsole(),
    )

    groups = service.target_groups()

    assert tuple(groups) == ("all", "env", "app", "firmware")
    assert groups["env"] == ("ms-dev-env", "protocol-codegen")
    assert groups["firmware"] == (
        "open-control-framework",
        "open-control-hal-midi",
        "open-control-note",
        "core",
        "plugin-bitwig",
    )
    assert "ms-manager-svelte" in groups["app"]
    assert "ms-manager-tauri" in groups["app"]


def test_ms_manager_targets_cover_svelte_node_and_tauri(tmp_path: Path) -> None:
    service = UnitTestService(
        workspace=Workspace(root=tmp_path),
        platform=detect(),
        config=None,
        console=MockConsole(),
    )

    entries = {name: kind for name, kind, _detail in service.list_entries() if kind != "group"}

    assert entries["ms-manager-svelte"] == "npm"
    assert entries["ms-manager-node"] == "npm"
    assert entries["ms-manager-core"] == "cargo"
    assert entries["ms-manager-tauri"] == "cargo-check"


def test_ms_dev_env_target_enables_strict_architecture_checks(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    service = UnitTestService(
        workspace=Workspace(root=tmp_path),
        platform=detect(),
        config=None,
        console=MockConsole(),
    )
    captured_env: dict[str, str] = {}

    def fake_which(name: str) -> str | None:
        return name if name == "uv" else None

    monkeypatch.setattr(execution.shutil, "which", fake_which)

    def fake_run(
        _cmd: list[str],
        *,
        cwd: Path,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> Ok[str]:
        del cwd, timeout
        if env is not None:
            captured_env.update(env)
        return Ok("============================== 6 passed in 1.23s ==============================")

    monkeypatch.setattr(execution, "run", fake_run)

    result = service.run(target="ms-dev-env")

    assert not isinstance(result, Err)
    assert captured_env["MS_ARCH_CHECKS"] == "1"


def test_ctest_path_filter_removes_workspace_venv(tmp_path: Path) -> None:
    venv_scripts = tmp_path / ".venv" / "Scripts"
    other = tmp_path / "tools" / "bin"
    value = os.pathsep.join((str(venv_scripts), str(other)))

    filtered = execution.remove_env_path_entry(value, venv_scripts)

    assert filtered == str(other)


def test_cmake_test_selection_normalizes_prefix_and_deduplicates() -> None:
    normalized = catalog.normalize_cmake_test_targets(
        (
            "RealtimeMidiQueue",
            "test_RealtimeMidiProducerEnvelope",
            "RealtimeMidiQueue",
        )
    )

    assert normalized == (
        "test_RealtimeMidiQueue",
        "test_RealtimeMidiProducerEnvelope",
    )


def test_cmake_test_selection_rejects_groups(tmp_path: Path) -> None:
    service = UnitTestService(
        workspace=Workspace(root=tmp_path),
        platform=detect(),
        config=None,
        console=MockConsole(),
    )

    result = service.run(target="firmware", tests=("RealtimeMidiQueue",), dry_run=True)

    assert isinstance(result, Err)
    assert isinstance(result.error, UnitTestSelectionInvalid)
    assert "not a group" in result.error.message
