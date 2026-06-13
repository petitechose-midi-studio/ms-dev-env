from __future__ import annotations

from pathlib import Path

from ms.core.result import Err, Ok
from ms.core.workspace import Workspace
from ms.output.console import MockConsole
from ms.platform.detection import detect
from ms.platform.process import ProcessError
from ms.services.ux_workflows import (
    UxRunFailed,
    UxWorkflowNotFound,
    UxWorkflowService,
    workflow_tree_lines,
)


def _service(tmp_path: Path) -> UxWorkflowService:
    return UxWorkflowService(
        workspace=Workspace(root=tmp_path),
        platform=detect(),
        config=None,
        console=MockConsole(),
    )


def _write_workflow(root: Path, rel: str, body: str = "") -> Path:
    path = root / "midi-studio" / "core" / "sdl" / "integration" / "workflows" / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body or "10 capture screen first\n", encoding="utf-8")
    return path


def _ok[T, E](value: Ok[T] | Err[E]) -> T:
    assert isinstance(value, Ok)
    return value.value


def test_catalog_discovers_nested_workflows_and_prints_tree(tmp_path: Path) -> None:
    _write_workflow(tmp_path, "sequencer/undo/step-toggle.ux")
    _write_workflow(tmp_path, "sequencer/undo/quick-controls.ux")
    _write_workflow(
        tmp_path,
        "overlay-exclusivity.ux",
        "# Expect: overlay_exclusive, playhead_progress\n10 capture screen first\n",
    )

    service = _service(tmp_path)
    catalog = _ok(service.catalog("core"))

    assert [workflow.relative_path for workflow in catalog.workflows] == [
        "overlay-exclusivity.ux",
        "sequencer/undo/quick-controls.ux",
        "sequencer/undo/step-toggle.ux",
    ]
    assert [group.path for group in service.groups(catalog)] == ["sequencer"]
    assert service.count_selection(catalog, "sequencer/undo") == 2
    assert workflow_tree_lines(catalog) == (
        "core (3 workflows)",
        "|-- sequencer/ (2)",
        "|   `-- undo/ (2)",
        "|       |-- quick-controls.ux",
        "|       `-- step-toggle.ux",
        "`-- overlay-exclusivity.ux expects=overlay_exclusive,playhead_progress",
    )


def test_resolve_selection_accepts_folder_file_and_unique_basename(tmp_path: Path) -> None:
    _write_workflow(tmp_path, "sequencer/undo/step-toggle.ux")
    _write_workflow(tmp_path, "sequencer/undo/quick-controls.ux")

    service = _service(tmp_path)
    catalog = _ok(service.catalog("core"))

    folder = _ok(service.resolve_selection(catalog, "sequencer/undo"))
    exact = _ok(service.resolve_selection(catalog, "sequencer/undo/step-toggle"))
    basename = _ok(service.resolve_selection(catalog, "quick-controls"))

    assert [workflow.relative_path for workflow in folder] == [
        "sequencer/undo/quick-controls.ux",
        "sequencer/undo/step-toggle.ux",
    ]
    assert exact[0].relative_path == "sequencer/undo/step-toggle.ux"
    assert basename[0].relative_path == "sequencer/undo/quick-controls.ux"


def test_resolve_selection_reports_missing_workflow(tmp_path: Path) -> None:
    _write_workflow(tmp_path, "sequencer/undo/step-toggle.ux")

    service = _service(tmp_path)
    catalog = _ok(service.catalog("core"))
    result = service.resolve_selection(catalog, "missing")

    assert isinstance(result, Err)
    assert isinstance(result.error, UxWorkflowNotFound)


def test_run_validates_trace_dispatch_captures_and_expectations(tmp_path: Path) -> None:
    _write_workflow(
        tmp_path,
        "sequencer/undo/step-toggle.ux",
        """
# Expect: playhead_progress, capture_match:first=second
10 capture screen first
20 capture screen second
""".lstrip(),
    )
    exe = tmp_path / "fake-midi-studio-core.exe"
    exe.write_text("", encoding="utf-8")

    def runner(
        cmd: list[str],
        cwd: Path,
        timeout: float | None,
    ) -> Ok[None] | Err[ProcessError]:
        del cwd, timeout
        output = Path(cmd[cmd.index("--ux-output") + 1])
        (output / "trace.ndjson").write_text(
            "\n".join(
                [
                    '{"event":"action","playing":true,"playhead_step":0}',
                    '{"event":"action","playing":true,"playhead_step":1}',
                    '{"event":"run_end"}',
                ]
            ),
            encoding="utf-8",
        )
        (output / "binding-trace.ndjson").write_text(
            '{"stage":"dispatch"}\n',
            encoding="utf-8",
        )
        payload = b"same"
        (output / "001_first_screen.bmp").write_bytes(payload)
        (output / "002_second_screen.bmp").write_bytes(payload)
        return Ok(None)

    service = UxWorkflowService(
        workspace=Workspace(root=tmp_path),
        platform=detect(),
        config=None,
        console=MockConsole(),
        runner=runner,
    )

    result = service.run(
        app_name="core",
        selections=("sequencer/undo/step-toggle",),
        all_workflows=False,
        skip_build=True,
        executable=exe,
    )

    runs = _ok(result)
    assert len(runs) == 1
    assert runs[0].ok
    assert runs[0].capture_count == 2
    assert runs[0].expected_capture_count == 2
    assert runs[0].expectations == ("capture_match:first=second", "playhead_progress")


def test_overlay_exclusive_tolerates_small_animated_regions(tmp_path: Path) -> None:
    _write_workflow(
        tmp_path,
        "smoke/overlay-exclusivity.ux",
        """
# Expect: overlay_exclusive
10 capture screen selector_open_early
20 capture screen selector_open_late
""".lstrip(),
    )
    exe = tmp_path / "fake-midi-studio-core.exe"
    exe.write_text("", encoding="utf-8")

    def runner(
        cmd: list[str],
        cwd: Path,
        timeout: float | None,
    ) -> Ok[None] | Err[ProcessError]:
        del cwd, timeout
        output = Path(cmd[cmd.index("--ux-output") + 1])
        (output / "trace.ndjson").write_text('{"event":"run_end"}\n', encoding="utf-8")
        (output / "binding-trace.ndjson").write_text(
            '{"stage":"dispatch"}\n',
            encoding="utf-8",
        )
        early = bytearray(b"\x00" * 1000)
        late = bytearray(early)
        late[:10] = b"\x01" * 10
        (output / "001_selector_open_early_screen.bmp").write_bytes(early)
        (output / "002_selector_open_late_screen.bmp").write_bytes(late)
        return Ok(None)

    service = UxWorkflowService(
        workspace=Workspace(root=tmp_path),
        platform=detect(),
        config=None,
        console=MockConsole(),
        runner=runner,
    )

    runs = _ok(
        service.run(
            app_name="core",
            selections=("smoke/overlay-exclusivity",),
            all_workflows=False,
            skip_build=True,
            executable=exe,
        )
    )

    assert len(runs) == 1
    assert runs[0].ok
    assert runs[0].expectations == ("overlay_exclusive",)


def test_overlay_exclusive_rejects_large_capture_changes(tmp_path: Path) -> None:
    _write_workflow(
        tmp_path,
        "smoke/overlay-exclusivity.ux",
        """
# Expect: overlay_exclusive
10 capture screen selector_open_early
20 capture screen selector_open_late
""".lstrip(),
    )
    exe = tmp_path / "fake-midi-studio-core.exe"
    exe.write_text("", encoding="utf-8")

    def runner(
        cmd: list[str],
        cwd: Path,
        timeout: float | None,
    ) -> Ok[None] | Err[ProcessError]:
        del cwd, timeout
        output = Path(cmd[cmd.index("--ux-output") + 1])
        (output / "trace.ndjson").write_text('{"event":"run_end"}\n', encoding="utf-8")
        (output / "binding-trace.ndjson").write_text(
            '{"stage":"dispatch"}\n',
            encoding="utf-8",
        )
        early = bytearray(b"\x00" * 1000)
        late = bytearray(early)
        late[:30] = b"\x01" * 30
        (output / "001_selector_open_early_screen.bmp").write_bytes(early)
        (output / "002_selector_open_late_screen.bmp").write_bytes(late)
        return Ok(None)

    service = UxWorkflowService(
        workspace=Workspace(root=tmp_path),
        platform=detect(),
        config=None,
        console=MockConsole(),
        runner=runner,
    )

    result = service.run(
        app_name="core",
        selections=("smoke/overlay-exclusivity",),
        all_workflows=False,
        skip_build=True,
        executable=exe,
    )

    assert isinstance(result, Err)
    assert isinstance(result.error, UxRunFailed)
    assert result.error.run is not None
    assert result.error.run.failed_expectations == ("overlay_exclusive",)


def test_run_all_removes_stale_workflow_outputs(tmp_path: Path) -> None:
    _write_workflow(tmp_path, "smoke/current.ux", "10 capture screen first\n")
    exe = tmp_path / "fake-midi-studio-core.exe"
    exe.write_text("", encoding="utf-8")
    output_root = tmp_path / "midi-studio" / "core" / ".captures" / "ux" / "workflows"
    stale = output_root / "smoke" / "removed-workflow"
    stale.mkdir(parents=True)
    (stale / "old_screen.bmp").write_bytes(b"old")
    log_file = output_root / "full-core-run.log"
    log_file.write_text("keep me\n", encoding="utf-8")
    report = output_root / "report.md"
    report.write_text("old report\n", encoding="utf-8")

    def runner(
        cmd: list[str],
        cwd: Path,
        timeout: float | None,
    ) -> Ok[None] | Err[ProcessError]:
        del cwd, timeout
        output = Path(cmd[cmd.index("--ux-output") + 1])
        (output / "trace.ndjson").write_text('{"event":"run_end"}\n', encoding="utf-8")
        (output / "binding-trace.ndjson").write_text(
            '{"stage":"dispatch"}\n',
            encoding="utf-8",
        )
        (output / "001_first_screen.bmp").write_bytes(b"bmp")
        return Ok(None)

    service = UxWorkflowService(
        workspace=Workspace(root=tmp_path),
        platform=detect(),
        config=None,
        console=MockConsole(),
        runner=runner,
    )

    result = service.run(
        app_name="core",
        selections=(),
        all_workflows=True,
        skip_build=True,
        executable=exe,
    )

    runs = _ok(result)
    assert len(runs) == 1
    assert runs[0].ok
    assert not stale.exists()
    assert log_file.read_text(encoding="utf-8") == "keep me\n"
    assert not report.exists()


def test_write_report_uses_existing_capture_outputs(tmp_path: Path) -> None:
    _write_workflow(tmp_path, "overlay-exclusivity.ux", "10 capture screen first\n")
    output = tmp_path / "midi-studio" / "core" / ".captures" / "ux" / "workflows"
    out_dir = output / "overlay-exclusivity"
    out_dir.mkdir(parents=True)
    (out_dir / "trace.ndjson").write_text('{"event":"run_end"}\n', encoding="utf-8")
    (out_dir / "binding-trace.ndjson").write_text('{"stage":"dispatch"}\n', encoding="utf-8")
    (out_dir / "001_first_screen.bmp").write_bytes(b"bmp")

    report = _ok(
        _service(tmp_path).write_report(
            app_name="core",
            selections=(),
            all_workflows=True,
        )
    )

    text = report.read_text(encoding="utf-8")
    assert "overlay-exclusivity.ux" in text
    assert "001_first_screen.bmp" in text
