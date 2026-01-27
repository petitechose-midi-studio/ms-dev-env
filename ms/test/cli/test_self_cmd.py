from __future__ import annotations

from pathlib import Path

import pytest

from ms.core.result import Ok
from ms.core.workspace import Workspace, WorkspaceInfo


def test_self_install_runs_uv_tool_install(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from ms.cli.commands.self_cmd import install

    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / ".ms-workspace").write_text("", encoding="utf-8")

    info = WorkspaceInfo(workspace=Workspace(root=ws), source="cwd")
    monkeypatch.setattr("ms.cli.commands.self_cmd.detect_workspace_info", lambda: Ok(info))

    seen: dict[str, object] = {}

    def fake_run_silent(cmd: list[str], cwd: Path, env: dict[str, str] | None = None):
        seen["cmd"] = cmd
        seen["cwd"] = cwd
        return Ok(None)

    monkeypatch.setattr("ms.cli.commands.self_cmd.run_silent", fake_run_silent)
    monkeypatch.setattr("ms.cli.commands.self_cmd.run", lambda *a, **k: Ok(""))
    monkeypatch.setattr(
        "ms.cli.commands.self_cmd.remember_default_workspace_root",
        lambda *_: Ok(None),
    )

    install(editable=False, update_shell=False, remember_workspace=True, dry_run=False)

    assert seen["cmd"] == ["uv", "tool", "install", str(ws)]
    assert seen["cwd"] == ws


def test_self_uninstall_runs_uv_tool_uninstall(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ms.cli.commands.self_cmd import uninstall

    seen: dict[str, object] = {}

    monkeypatch.setattr("ms.cli.commands.self_cmd._tool_name_for_current_ms", lambda: "my-tool")

    def fake_run_silent(cmd: list[str], cwd: Path, env: dict[str, str] | None = None):
        seen["cmd"] = cmd
        seen["cwd"] = cwd
        return Ok(None)

    monkeypatch.setattr("ms.cli.commands.self_cmd.run_silent", fake_run_silent)

    uninstall(dry_run=False)

    assert seen["cmd"] == ["uv", "tool", "uninstall", "my-tool"]
