from __future__ import annotations

from pathlib import Path

import pytest
import typer

from ms.cli.context import CLIContext
from ms.core.errors import ErrorCode
from ms.core.result import Ok
from ms.core.workspace import Workspace
from ms.output.console import MockConsole
from ms.platform.detection import detect
from ms.services.ux_workflows import UxWorkflow, UxWorkflowApp, UxWorkflowCatalog


def _ctx(tmp_path: Path) -> CLIContext:
    (tmp_path / ".ms-workspace").write_text("", encoding="utf-8")
    return CLIContext(
        workspace=Workspace(root=tmp_path),
        platform=detect(),
        config=None,
        console=MockConsole(),
    )


def _catalog(tmp_path: Path) -> UxWorkflowCatalog:
    app = UxWorkflowApp(
        name="core",
        repo_dir=tmp_path / "midi-studio" / "core",
        workflow_dir=tmp_path / "midi-studio" / "core" / "sdl" / "integration" / "workflows",
        output_root=tmp_path / "midi-studio" / "core" / ".captures" / "ux" / "workflows",
        executable=tmp_path / "bin" / "core" / "native" / "midi_studio_core.exe",
    )
    return UxWorkflowCatalog(
        app=app,
        workflows=(
            UxWorkflow(path=app.workflow_dir / "overlay.ux", relative_path="overlay.ux"),
            UxWorkflow(
                path=app.workflow_dir / "sequencer" / "undo" / "step-toggle.ux",
                relative_path="sequencer/undo/step-toggle.ux",
            ),
        ),
    )


def test_ux_list_prints_workflow_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ms.cli.commands.ux as ux_cmd

    ctx = _ctx(tmp_path)
    monkeypatch.setattr(ux_cmd, "build_context", lambda: ctx)

    class FakeUxWorkflowService:
        def __init__(self, **_: object) -> None:
            pass

        def catalog(self, app_name: str) -> Ok[UxWorkflowCatalog]:
            assert app_name == "core"
            return Ok(_catalog(tmp_path))

    monkeypatch.setattr(ux_cmd, "UxWorkflowService", FakeUxWorkflowService)

    ux_cmd.list_cmd(app_name="core")

    console = ctx.console
    assert isinstance(console, MockConsole)
    assert "core (2 workflows)" in console.text
    assert "sequencer/" in console.text
    assert "step-toggle.ux" in console.text


def test_ux_run_requires_explicit_selection_when_not_interactive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ms.cli.commands.ux as ux_cmd

    ctx = _ctx(tmp_path)
    monkeypatch.setattr(ux_cmd, "build_context", lambda: ctx)
    monkeypatch.setattr(ux_cmd, "is_interactive_terminal", lambda: False)

    class FakeUxWorkflowService:
        def __init__(self, **_: object) -> None:
            pass

        def catalog(self, app_name: str) -> Ok[UxWorkflowCatalog]:
            assert app_name == "core"
            return Ok(_catalog(tmp_path))

    monkeypatch.setattr(ux_cmd, "UxWorkflowService", FakeUxWorkflowService)

    with pytest.raises(typer.Exit) as exc:
        ux_cmd.run_cmd(
            app_name="core",
            select=None,
            all_workflows=False,
            no_interactive=False,
        )

    assert exc.value.exit_code == int(ErrorCode.USER_ERROR)
    console = ctx.console
    assert isinstance(console, MockConsole)
    assert "choose workflows" in console.text


def test_ux_run_passes_selection_to_service(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ms.cli.commands.ux as ux_cmd

    ctx = _ctx(tmp_path)
    monkeypatch.setattr(ux_cmd, "build_context", lambda: ctx)
    calls: list[tuple[str, tuple[str, ...], bool]] = []

    class FakeUxWorkflowService:
        def __init__(self, **_: object) -> None:
            pass

        def catalog(self, app_name: str) -> Ok[UxWorkflowCatalog]:
            assert app_name == "core"
            return Ok(_catalog(tmp_path))

        def run(
            self,
            *,
            app_name: str,
            selections: tuple[str, ...],
            all_workflows: bool,
            skip_build: bool,
            executable: Path | None,
            output_root: Path | None,
        ) -> Ok[tuple[object, ...]]:
            del skip_build, executable, output_root
            calls.append((app_name, selections, all_workflows))
            return Ok(())

    monkeypatch.setattr(ux_cmd, "UxWorkflowService", FakeUxWorkflowService)

    ux_cmd.run_cmd(
        app_name="core",
        select=["sequencer/undo"],
        all_workflows=False,
        report=False,
    )

    assert calls == [("core", ("sequencer/undo",), False)]


def test_ux_report_defaults_to_all_workflows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ms.cli.commands.ux as ux_cmd

    ctx = _ctx(tmp_path)
    monkeypatch.setattr(ux_cmd, "build_context", lambda: ctx)
    report = tmp_path / "report.md"
    calls: list[bool] = []

    class FakeUxWorkflowService:
        def __init__(self, **_: object) -> None:
            pass

        def write_report(
            self,
            *,
            app_name: str,
            selections: tuple[str, ...],
            all_workflows: bool,
            output_root: Path | None,
            report_path: Path | None,
        ) -> Ok[Path]:
            del app_name, selections, output_root, report_path
            calls.append(all_workflows)
            return Ok(report)

    monkeypatch.setattr(ux_cmd, "UxWorkflowService", FakeUxWorkflowService)

    ux_cmd.report_cmd(app_name="core", select=None, all_workflows=True)

    assert calls == [True]
    console = ctx.console
    assert isinstance(console, MockConsole)
    assert str(report) in console.text
