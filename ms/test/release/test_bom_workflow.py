from __future__ import annotations

from pathlib import Path

from pytest import MonkeyPatch

from ms.core.platformio_runtime import PlatformioRuntime
from ms.core.result import Err, Ok
from ms.platform.process import ProcessError
from ms.release.flow.bom_workflow import validate_workspace_bom_targets


def test_validate_workspace_bom_targets_runs_expected_steps(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    import ms.release.flow.bom_workflow as workflow

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
    python_cmd = str(Path("/tmp/python"))
    assert [target.key for target in validated.value] == ["core-release", "core-native-ci"]
    core_root = tmp_path / "midi-studio" / "core"
    assert calls == [
        ((python_cmd, "-m", "platformio", "run", "-e", "release"), core_root),
        ((python_cmd, "-m", "platformio", "test", "-e", "native_ci"), core_root),
    ]


def test_validate_workspace_bom_targets_returns_repo_failed_on_build_error(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    import ms.release.flow.bom_workflow as workflow

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
