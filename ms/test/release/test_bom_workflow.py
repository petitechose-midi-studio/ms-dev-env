from __future__ import annotations

import sys
from pathlib import Path

from pytest import MonkeyPatch

from ms.core.platformio_runtime import PlatformioRuntime
from ms.core.result import Err, Ok
from ms.platform.process import ProcessError
from ms.release.flow.bom_validation import (
    validate_workspace_bom_targets,
    validate_workspace_dev_targets,
)


def test_validate_workspace_bom_targets_runs_expected_steps(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    import ms.release.flow.bom_validation as workflow

    calls: list[tuple[tuple[str, ...], Path]] = []

    def fake_resolve_platformio_runtime(
        _: Path,
    ) -> Ok[PlatformioRuntime]:
        return Ok(
            PlatformioRuntime(
                python_executable=Path("/tmp/python"),
                env={"A": "B"},
                source="current_python",
                workspace_root=None,
            )
        )

    def fake_run_process(
        cmd: list[str],
        cwd: Path,
        env: dict[str, str] | None,
        *,
        timeout: float | None,
    ) -> Ok[str]:
        del env, timeout
        calls.append((tuple(cmd), cwd))
        return Ok("")

    monkeypatch.setattr(workflow, "resolve_platformio_runtime", fake_resolve_platformio_runtime)
    monkeypatch.setattr(workflow, "run_process", fake_run_process)

    validated = validate_workspace_bom_targets(
        workspace_root=tmp_path,
        include_plugin_release=False,
    )

    assert isinstance(validated, Ok)
    platformio_python_cmd = str(Path("/tmp/python"))
    ms_python_cmd = sys.executable
    assert [target.key for target in validated.value] == ["core-release", "core-unit-tests"]
    core_root = tmp_path / "midi-studio" / "core"
    assert calls == [
        ((platformio_python_cmd, "-m", "platformio", "run", "-e", "release"), core_root),
        (
            (
                ms_python_cmd,
                "-c",
                "from ms.cli.app import main; main()",
                "test",
                "core",
            ),
            tmp_path,
        ),
    ]


def test_validate_workspace_bom_targets_returns_repo_failed_on_build_error(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    import ms.release.flow.bom_validation as workflow

    def fake_resolve_platformio_runtime(
        _: Path,
    ) -> Ok[PlatformioRuntime]:
        return Ok(
            PlatformioRuntime(
                python_executable=Path("/tmp/python"),
                env={},
                source="current_python",
                workspace_root=None,
            )
        )

    def fake_run_process(
        cmd: list[str],
        cwd: Path,
        env: dict[str, str] | None,
        *,
        timeout: float | None,
    ) -> Err[ProcessError]:
        del cwd, env, timeout
        return Err(
            ProcessError(
                command=tuple(cmd),
                returncode=1,
                stdout="",
                stderr="boom",
            )
        )

    monkeypatch.setattr(workflow, "resolve_platformio_runtime", fake_resolve_platformio_runtime)
    monkeypatch.setattr(workflow, "run_process", fake_run_process)

    validated = validate_workspace_bom_targets(workspace_root=tmp_path)

    assert isinstance(validated, Err)
    assert validated.error.kind == "repo_failed"
    assert validated.error.message == "core release failed"


def test_validate_workspace_dev_targets_runs_core_dev_build(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    import ms.release.flow.bom_validation as workflow

    calls: list[tuple[tuple[str, ...], Path]] = []

    def fake_resolve_platformio_runtime(
        _: Path,
    ) -> Ok[PlatformioRuntime]:
        return Ok(
            PlatformioRuntime(
                python_executable=Path("/tmp/python"),
                env={"A": "B"},
                source="current_python",
                workspace_root=None,
            )
        )

    def fake_run_process(
        cmd: list[str],
        cwd: Path,
        env: dict[str, str] | None,
        *,
        timeout: float | None,
    ) -> Ok[str]:
        del env, timeout
        calls.append((tuple(cmd), cwd))
        return Ok("")

    monkeypatch.setattr(workflow, "resolve_platformio_runtime", fake_resolve_platformio_runtime)
    monkeypatch.setattr(workflow, "run_process", fake_run_process)

    validated = validate_workspace_dev_targets(workspace_root=tmp_path)

    assert isinstance(validated, Ok)
    assert [target.key for target in validated.value] == ["core-dev"]
    assert calls == [
        (
            (str(Path("/tmp/python")), "-m", "platformio", "run", "-e", "dev"),
            tmp_path / "midi-studio" / "core",
        )
    ]
