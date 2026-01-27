from __future__ import annotations

from pathlib import Path

import pytest

from ms.core.result import Ok, Result
from ms.core.user_workspace import UserWorkspaceError
from ms.platform.process import ProcessError
from ms.core.workspace import Workspace, WorkspaceInfo


def test_self_install_runs_uv_tool_install(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import ms.cli.commands.self_cmd as self_cmd

    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / ".ms-workspace").write_text("", encoding="utf-8")

    info = WorkspaceInfo(workspace=Workspace(root=ws), source="cwd")

    def fake_detect_workspace_info() -> Ok[WorkspaceInfo]:
        return Ok(info)

    monkeypatch.setattr(self_cmd, "detect_workspace_info", fake_detect_workspace_info)

    seen: dict[str, object] = {}

    def fake_run_silent(
        cmd: list[str],
        cwd: Path,
        env: dict[str, str] | None = None,
    ) -> Result[None, ProcessError]:
        seen["cmd"] = cmd
        seen["cwd"] = cwd
        return Ok(None)

    def fake_run(
        cmd: list[str],
        cwd: Path,
        env: dict[str, str] | None = None,
        *,
        timeout: float | None = None,
    ) -> Result[str, ProcessError]:
        return Ok("")

    def fake_remember_default_workspace_root(_root: Path) -> Result[None, UserWorkspaceError]:
        return Ok(None)

    monkeypatch.setattr(self_cmd, "run_silent", fake_run_silent)
    monkeypatch.setattr(self_cmd, "run", fake_run)
    monkeypatch.setattr(
        self_cmd, "remember_default_workspace_root", fake_remember_default_workspace_root
    )

    self_cmd.install(editable=False, update_shell=False, remember_workspace=True, dry_run=False)

    assert seen["cmd"] == ["uv", "tool", "install", str(ws)]
    assert seen["cwd"] == ws


def test_self_uninstall_runs_uv_tool_uninstall(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ms.cli.commands.self_cmd as self_cmd

    seen: dict[str, object] = {}

    def fake_tool_name_for_current_ms() -> str:
        return "my-tool"

    monkeypatch.setattr(self_cmd, "_tool_name_for_current_ms", fake_tool_name_for_current_ms)

    def fake_run_silent(
        cmd: list[str],
        cwd: Path,
        env: dict[str, str] | None = None,
    ) -> Result[None, ProcessError]:
        seen["cmd"] = cmd
        seen["cwd"] = cwd
        return Ok(None)

    monkeypatch.setattr(self_cmd, "run_silent", fake_run_silent)

    self_cmd.uninstall(name=None, dry_run=False)

    assert seen["cmd"] == ["uv", "tool", "uninstall", "my-tool"]


def test_self_uninstall_accepts_explicit_name(monkeypatch: pytest.MonkeyPatch) -> None:
    import ms.cli.commands.self_cmd as self_cmd

    seen: dict[str, object] = {}

    def fake_tool_name_for_current_ms() -> str:
        return "ignored"

    monkeypatch.setattr(self_cmd, "_tool_name_for_current_ms", fake_tool_name_for_current_ms)

    def fake_run_silent(
        cmd: list[str],
        cwd: Path,
        env: dict[str, str] | None = None,
    ) -> Result[None, ProcessError]:
        seen["cmd"] = cmd
        seen["cwd"] = cwd
        return Ok(None)

    monkeypatch.setattr(self_cmd, "run_silent", fake_run_silent)

    self_cmd.uninstall(name="explicit-tool", dry_run=False)

    assert seen["cmd"] == ["uv", "tool", "uninstall", "explicit-tool"]
