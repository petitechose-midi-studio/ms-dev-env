from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import NoReturn

import pytest

from ms.cli.context import CLIContext
from ms.core.errors import ErrorCode
from ms.core.result import Err, Ok
from ms.core.workspace import Workspace
from ms.output.console import MockConsole
from ms.platform.detection import detect
from ms.release.errors import ReleaseError


class ExitCaptured(Exception):
    pass


def _ctx(tmp_path: Path, console: MockConsole) -> CLIContext:
    return CLIContext(
        workspace=Workspace(root=tmp_path),
        platform=detect(),
        config=None,
        console=console,
    )


def _capture_exit(captured: dict[str, object]):
    def fake_exit(err: str, *, code: ErrorCode) -> NoReturn:
        captured["err"] = err
        captured["code"] = code
        raise ExitCaptured

    return fake_exit


def _workflow_error() -> ReleaseError:
    return ReleaseError(
        kind="workflow_failed",
        message="workflow run failed",
        hint="gh run view 42 --log",
    )


def test_guided_release_command_preserves_error_hint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ms.cli.commands.release_cmd as cmd

    captured: dict[str, object] = {}

    def fake_run_guided_release(**_: object) -> Err[ReleaseError]:
        return Err(_workflow_error())

    monkeypatch.setattr(cmd, "build_context", lambda: _ctx(tmp_path, MockConsole()))
    monkeypatch.setattr(cmd, "run_guided_release", fake_run_guided_release)
    monkeypatch.setattr(cmd, "exit_release", _capture_exit(captured))

    with pytest.raises(ExitCaptured):
        cmd.guided_release_cmd(notes_file=None, watch=True, dry_run=False)

    assert captured["err"] == "workflow run failed (hint: gh run view 42 --log)"
    assert captured["code"] == ErrorCode.NETWORK_ERROR


def test_app_publish_command_preserves_error_hint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ms.cli.commands.release_app_publish as cmd

    captured: dict[str, object] = {}
    prepared = SimpleNamespace(
        pr="merged",
        source_sha="a" * 40,
        plan=SimpleNamespace(
            tag="v0.1.2-beta.1",
            tooling=SimpleNamespace(sha="b" * 40),
        ),
    )
    notes = SimpleNamespace(markdown="notes", source_path=None)

    def fake_permission(**_: object) -> None:
        return None

    def fake_prepare(**_: object) -> SimpleNamespace:
        return prepared

    def fake_resolve_notes(**_: object) -> Ok[SimpleNamespace]:
        return Ok(notes)

    def fake_print_notes(**_: object) -> None:
        return None

    def fake_publish(**_: object) -> Err[ReleaseError]:
        return Err(_workflow_error())

    monkeypatch.setattr(cmd, "build_context", lambda: _ctx(tmp_path, MockConsole()))
    monkeypatch.setattr(cmd, "ensure_release_permissions_or_exit", fake_permission)
    monkeypatch.setattr(cmd, "prepare_app_release", fake_prepare)
    monkeypatch.setattr(cmd, "resolve_app_publish_notes", fake_resolve_notes)
    monkeypatch.setattr(cmd, "print_app_notes_attachment", fake_print_notes)
    monkeypatch.setattr(cmd, "publish_app_release", fake_publish)
    monkeypatch.setattr(cmd, "exit_release", _capture_exit(captured))

    with pytest.raises(ExitCaptured):
        cmd.app_publish_cmd(
            channel=None,
            bump="patch",
            tag=None,
            auto=False,
            repo=[],
            ref=[],
            plan=None,
            allow_non_green=False,
            confirm_tag=None,
            no_interactive=True,
            watch=True,
            notes_file=None,
            dry_run=False,
        )

    assert captured["err"] == "workflow run failed (hint: gh run view 42 --log)"
    assert captured["code"] == ErrorCode.NETWORK_ERROR


def test_content_publish_command_preserves_error_hint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ms.cli.commands.release_content_publish as cmd

    captured: dict[str, object] = {}
    prepared = SimpleNamespace(pr="merged", plan=SimpleNamespace(tag="v0.1.2-beta.1"))

    def fake_permission(**_: object) -> None:
        return None

    def fake_prepare(**_: object) -> SimpleNamespace:
        return prepared

    def fake_publish(**_: object) -> Err[ReleaseError]:
        return Err(_workflow_error())

    monkeypatch.setattr(cmd, "build_context", lambda: _ctx(tmp_path, MockConsole()))
    monkeypatch.setattr(cmd, "ensure_release_permissions_or_exit", fake_permission)
    monkeypatch.setattr(cmd, "prepare_content_release", fake_prepare)
    monkeypatch.setattr(cmd, "publish_distribution_release", fake_publish)
    monkeypatch.setattr(cmd, "exit_release", _capture_exit(captured))

    with pytest.raises(ExitCaptured):
        cmd.publish_cmd(
            channel=None,
            bump="patch",
            tag=None,
            auto=False,
            repo=[],
            ref=[],
            plan=None,
            notes=None,
            notes_file=None,
            allow_non_green=False,
            allow_open_control_dirty=False,
            confirm_tag=None,
            no_interactive=True,
            watch=True,
            dry_run=False,
        )

    assert captured["err"] == "workflow run failed (hint: gh run view 42 --log)"
    assert captured["code"] == ErrorCode.NETWORK_ERROR
