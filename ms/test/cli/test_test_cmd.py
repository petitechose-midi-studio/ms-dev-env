from __future__ import annotations

from pathlib import Path

import pytest
import typer

from ms.cli.context import CLIContext
from ms.core.errors import ErrorCode
from ms.core.result import Err, Ok
from ms.core.workspace import Workspace
from ms.output.console import MockConsole
from ms.platform.detection import detect
from ms.services.unit_tests import UnitTestTargetNotFound


def _ctx(tmp_path: Path) -> CLIContext:
    (tmp_path / ".ms-workspace").write_text("", encoding="utf-8")
    return CLIContext(
        workspace=Workspace(root=tmp_path),
        platform=detect(),
        config=None,
        console=MockConsole(),
    )


def test_unit_test_command_reports_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ms.cli.commands.test_cmd as test_cmd

    monkeypatch.setattr(test_cmd, "build_context", lambda: _ctx(tmp_path))

    class FakeUnitTestService:
        def __init__(self, **_: object) -> None:
            pass

        def run(
            self,
            *,
            target: str,
            dry_run: bool = False,
            verbose: bool = False,
        ) -> Ok[tuple[object, ...]]:
            assert target == "core"
            assert dry_run is True
            assert verbose is False
            return Ok(())

    monkeypatch.setattr(test_cmd, "UnitTestService", FakeUnitTestService)

    test_cmd.test(target="core", dry_run=True, verbose=False)


def test_unit_test_command_exits_on_unknown_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ms.cli.commands.test_cmd as test_cmd

    monkeypatch.setattr(test_cmd, "build_context", lambda: _ctx(tmp_path))

    class FakeUnitTestService:
        def __init__(self, **_: object) -> None:
            pass

        def run(
            self,
            *,
            target: str,
            dry_run: bool = False,
            verbose: bool = False,
        ) -> Err[UnitTestTargetNotFound]:
            del dry_run, verbose
            return Err(UnitTestTargetNotFound(name=target, available=("all", "core")))

    monkeypatch.setattr(test_cmd, "UnitTestService", FakeUnitTestService)

    with pytest.raises(typer.Exit) as exc:
        test_cmd.test(target="missing")

    assert exc.value.exit_code == int(ErrorCode.USER_ERROR)
