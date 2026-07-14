from __future__ import annotations

from pathlib import Path

from ms.core.result import Err, Ok
from ms.core.workspace import Workspace
from ms.output.console import MockConsole
from ms.platform.detection import detect
from ms.platform.process import ProcessError
from ms.services.ux_workflows import (
    UxRunFailed,
    UxWorkflowError,
    UxWorkflowNotFound,
    UxWorkflowRun,
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


def test_run_validates_semantic_facts_bound_to_named_captures(tmp_path: Path) -> None:
    _write_workflow(
        tmp_path,
        "gate9/cc-lane.ux",
        """
# Expect: semantic:armed:surface_context=true, semantic:armed:outcome=armed
# Expect: semantic:armed:activation_origin=track_paste, semantic:armed:activation_generation=42
# Expect: semantic:live:projection=live, semantic:live:resolved_value=96
10 capture screen armed
20 capture screen live
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
        (output / "binding-trace.ndjson").write_text('{"stage":"dispatch"}\n', encoding="utf-8")
        (output / "semantic-trace.ndjson").write_text(
            "\n".join(
                [
                    '{"seq":2,"ms":10,"kind":"capture","label":"armed",'
                    '"surface_context":true,"source_seq":1,"view":"sequencer",'
                    '"overlay":"seq_cc_lane","playing":false,"playhead":-1,'
                    '"page":0,"shared_track":0,"shared_mask":1,"outcome":"armed",'
                    '"activation_origin":"track_paste","activation_generation":42}',
                    '{"seq":4,"ms":20,"kind":"capture","label":"live",'
                    '"surface_context":true,"source_seq":3,"view":"sequencer",'
                    '"overlay":"seq_cc_lane","playing":true,"playhead":2,'
                    '"page":0,"shared_track":0,"shared_mask":1,'
                    '"projection":"live","resolved_value":96}',
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (output / "010_armed_screen.bmp").write_bytes(b"armed")
        (output / "020_live_screen.bmp").write_bytes(b"live")
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
            selections=("gate9/cc-lane",),
            all_workflows=False,
            skip_build=True,
            executable=exe,
        )
    )

    assert runs[0].ok
    assert runs[0].semantic_schema_valid
    assert runs[0].semantic_capture_count == 2
    assert runs[0].expected_semantic_capture_count == 2


def test_run_rejects_missing_semantic_fact(tmp_path: Path) -> None:
    _write_workflow(
        tmp_path,
        "gate9/missing.ux",
        "# Expect: semantic:preview:projection=preview\n10 capture screen preview\n",
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
        (output / "binding-trace.ndjson").write_text('{"stage":"dispatch"}\n', encoding="utf-8")
        (output / "semantic-trace.ndjson").write_text(
            '{"seq":2,"ms":10,"kind":"capture","label":"preview",'
            '"surface_context":true,"source_seq":1,"view":"sequencer",'
            '"overlay":"none","playing":false,"playhead":-1,"page":0,'
            '"shared_track":0,"shared_mask":1}\n',
            encoding="utf-8",
        )
        (output / "010_preview_screen.bmp").write_bytes(b"preview")
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
        selections=("gate9/missing",),
        all_workflows=False,
        skip_build=True,
        executable=exe,
    )

    assert isinstance(result, Err)
    assert isinstance(result.error, UxRunFailed)
    assert result.error.run is not None
    assert result.error.run.failed_expectations == ("semantic:preview:projection=preview",)


def test_run_rejects_malformed_semantic_capture_schema(tmp_path: Path) -> None:
    _write_workflow(
        tmp_path,
        "gate9/schema.ux",
        "# Expect: semantic:armed:outcome=armed\n10 capture screen armed\n",
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
        (output / "binding-trace.ndjson").write_text('{"stage":"dispatch"}\n', encoding="utf-8")
        # A capture without surface context cannot claim a binding source.
        (output / "semantic-trace.ndjson").write_text(
            '{"seq":2,"ms":10,"kind":"capture","label":"armed",'
            '"surface_context":false,"source_seq":1,"view":"sequencer",'
            '"overlay":"none","playing":false,"playhead":-1,"page":0,'
            '"shared_track":0,"shared_mask":1,"outcome":"armed"}\n',
            encoding="utf-8",
        )
        (output / "010_armed_screen.bmp").write_bytes(b"armed")
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
        selections=("gate9/schema",),
        all_workflows=False,
        skip_build=True,
        executable=exe,
    )

    assert isinstance(result, Err)
    assert isinstance(result.error, UxRunFailed)
    assert result.error.run is not None
    assert result.error.run.failed_expectations == ("semantic_trace_schema",)


def test_run_rejects_uncorrelated_activation_semantics(tmp_path: Path) -> None:
    _write_workflow(
        tmp_path,
        "gate9/activation-schema.ux",
        "# Expect: semantic:queued:outcome=queued\n10 capture screen queued\n",
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
        (output / "binding-trace.ndjson").write_text('{"stage":"dispatch"}\n', encoding="utf-8")
        # Origin and generation form one correlation tuple; neither is valid alone.
        (output / "semantic-trace.ndjson").write_text(
            '{"seq":2,"ms":10,"kind":"capture","label":"queued",'
            '"surface_context":true,"source_seq":1,"view":"sequencer",'
            '"overlay":"none","playing":true,"playhead":2,"page":0,'
            '"shared_track":0,"shared_mask":1,"outcome":"queued",'
            '"activation_origin":"track_paste"}\n',
            encoding="utf-8",
        )
        (output / "010_queued_screen.bmp").write_bytes(b"queued")
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
        selections=("gate9/activation-schema",),
        all_workflows=False,
        skip_build=True,
        executable=exe,
    )

    assert isinstance(result, Err)
    assert isinstance(result.error, UxRunFailed)
    assert result.error.run is not None
    assert result.error.run.failed_expectations == ("semantic_trace_schema",)


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


def _run_capture_changed_workflow(
    tmp_path: Path, *, changed_bytes: int
) -> Ok[tuple[UxWorkflowRun, ...]] | Err[UxWorkflowError]:
    _write_workflow(
        tmp_path,
        "changed.ux",
        "# Expect: capture_changed:before=after\n"
        "10 capture screen before\n"
        "20 capture screen after\n",
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
        (output / "binding-trace.ndjson").write_text('{"stage":"dispatch"}\n', encoding="utf-8")
        (output / "001_before_screen.bmp").write_bytes(b"A" * 10_000)
        (output / "002_after_screen.bmp").write_bytes(
            b"A" * (10_000 - changed_bytes) + b"B" * changed_bytes
        )
        return Ok(None)

    service = UxWorkflowService(
        workspace=Workspace(root=tmp_path),
        platform=detect(),
        config=None,
        console=MockConsole(),
        runner=runner,
    )
    return service.run(
        app_name="core",
        selections=("changed",),
        all_workflows=False,
        skip_build=True,
        executable=exe,
    )


def test_capture_changed_requires_a_meaningful_visual_difference(tmp_path: Path) -> None:
    result = _run_capture_changed_workflow(tmp_path, changed_bytes=100)

    runs = _ok(result)
    assert len(runs) == 1
    assert runs[0].failed_expectations == ()


def test_capture_changed_rejects_nearly_identical_captures(tmp_path: Path) -> None:
    result = _run_capture_changed_workflow(tmp_path, changed_bytes=5)

    assert isinstance(result, Err)
    assert isinstance(result.error, UxRunFailed)
    assert result.error.run is not None
    assert result.error.run.failed_expectations == ("capture_changed:before=after",)


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
