from __future__ import annotations

from pathlib import Path

from pytest import MonkeyPatch

from ms.core.result import Err
from ms.core.workspace import Workspace
from ms.output.console import MockConsole
from ms.platform.detection import detect
from ms.services import unit_tests
from ms.services.unit_tests import UnitTestDependencyError, UnitTestService


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
    monkeypatch.setattr(unit_tests, "_TEST_DEPENDENCIES_PATH", manifest)

    result = unit_tests.load_test_dependency_pin("unity")

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
    monkeypatch.setattr(unit_tests, "_TEST_DEPENDENCIES_PATH", manifest)

    result = unit_tests.load_test_dependency_pin("unity")

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

    entries = {
        name: kind
        for name, kind, _detail in service.list_entries()
        if kind != "group"
    }

    assert entries["ms-manager-svelte"] == "npm"
    assert entries["ms-manager-node"] == "npm"
    assert entries["ms-manager-core"] == "cargo"
    assert entries["ms-manager-tauri"] == "cargo-check"
