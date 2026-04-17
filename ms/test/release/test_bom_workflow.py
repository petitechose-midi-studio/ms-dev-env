from __future__ import annotations

from pathlib import Path

from ms.core.platformio_runtime import PlatformioRuntime
from ms.core.result import Err, Ok
from ms.platform.process import ProcessError
from ms.release.flow.bom_workflow import validate_workspace_bom_targets


def test_validate_workspace_bom_targets_runs_expected_steps(
    tmp_path: Path, monkeypatch
) -> None:
    import ms.release.flow.bom_workflow as workflow

    calls: list[tuple[tuple[str, ...], Path]] = []

    monkeypatch.setattr(
        workflow,
        "resolve_platformio_runtime",
        lambda _: Ok(
            PlatformioRuntime(
                python_executable=Path("/tmp/python"),
                env={"A": "B"},
                source="current_python",
                workspace_root=None,
            )
        ),
    )

    def fake_run_process(cmd, cwd, env, timeout):
        del env, timeout
        calls.append((tuple(cmd), cwd))
        return Ok("")

    monkeypatch.setattr(workflow, "run_process", fake_run_process)

    validated = validate_workspace_bom_targets(
        workspace_root=tmp_path,
        include_plugin_release=False,
    )

    assert validated.is_ok()
    python_cmd = str(Path("/tmp/python"))
    assert [target.key for target in validated.unwrap()] == ["core-release", "core-native-ci"]
    assert calls == [
        ((python_cmd, "-m", "platformio", "run", "-e", "release"), tmp_path / "midi-studio" / "core"),
        ((python_cmd, "-m", "platformio", "test", "-e", "native_ci"), tmp_path / "midi-studio" / "core"),
    ]


def test_validate_workspace_bom_targets_returns_repo_failed_on_build_error(
    tmp_path: Path, monkeypatch
) -> None:
    import ms.release.flow.bom_workflow as workflow

    monkeypatch.setattr(
        workflow,
        "resolve_platformio_runtime",
        lambda _: Ok(
            PlatformioRuntime(
                python_executable=Path("/tmp/python"),
                env={},
                source="current_python",
                workspace_root=None,
            )
        ),
    )
    monkeypatch.setattr(
        workflow,
        "run_process",
        lambda cmd, cwd, env, timeout: Err(
            ProcessError(
                command=tuple(cmd),
                returncode=1,
                stdout="",
                stderr="boom",
            )
        ),
    )

    validated = validate_workspace_bom_targets(workspace_root=tmp_path)

    assert isinstance(validated, Err)
    assert validated.error.kind == "repo_failed"
    assert "core release failed" == validated.error.message
