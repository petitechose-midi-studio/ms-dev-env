from __future__ import annotations

from pathlib import Path

import pytest
import typer

from ms.cli.context import CLIContext
from ms.core.errors import ErrorCode
from ms.core.workspace import Workspace
from ms.output.console import MockConsole
from ms.platform.detection import detect
from ms.services.check import CheckReport
from ms.services.checkers import CheckResult


def _ctx(tmp_path: Path) -> CLIContext:
    (tmp_path / ".ms-workspace").write_text("", encoding="utf-8")
    return CLIContext(
        workspace=Workspace(root=tmp_path),
        platform=detect(),
        config=None,
        console=MockConsole(),
    )


def _patch_report(
    monkeypatch: pytest.MonkeyPatch,
    *,
    report: CheckReport,
) -> None:
    import ms.cli.commands.check as check_cmd

    class FakeCheckService:
        def __init__(self, **_: object) -> None:
            pass

        def run(self) -> CheckReport:
            return report

    monkeypatch.setattr(check_cmd, "CheckService", FakeCheckService)


def test_check_strict_exits_on_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import ms.cli.commands.check as check_cmd

    monkeypatch.setattr(check_cmd, "build_context", lambda: _ctx(tmp_path))
    _patch_report(
        monkeypatch,
        report=CheckReport(
            workspace=[CheckResult.error("open-control", "missing")],
            tools=[],
            system=[],
            runtime=[],
        ),
    )

    with pytest.raises(typer.Exit) as exc:
        check_cmd.check(strict=True)

    assert exc.value.exit_code == int(ErrorCode.ENV_ERROR)


def test_check_no_strict_allows_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import ms.cli.commands.check as check_cmd

    monkeypatch.setattr(check_cmd, "build_context", lambda: _ctx(tmp_path))
    _patch_report(
        monkeypatch,
        report=CheckReport(
            workspace=[CheckResult.error("open-control", "missing")],
            tools=[],
            system=[],
            runtime=[],
        ),
    )

    check_cmd.check(strict=False)


def test_check_strict_succeeds_when_clean(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import ms.cli.commands.check as check_cmd

    monkeypatch.setattr(check_cmd, "build_context", lambda: _ctx(tmp_path))
    _patch_report(
        monkeypatch,
        report=CheckReport(
            workspace=[CheckResult.success("open-control", "ok")],
            tools=[CheckResult.success("git", "ok")],
            system=[],
            runtime=[],
        ),
    )

    check_cmd.check(strict=True)
