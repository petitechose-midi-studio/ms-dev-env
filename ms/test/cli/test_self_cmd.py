from __future__ import annotations

from pathlib import Path

import pytest

from ms.core.result import Ok, Result
from ms.core.user_workspace import UserWorkspaceError
from ms.core.workspace import Workspace, WorkspaceInfo
from ms.platform.detection import Platform


def test_self_install_writes_repo_launchers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ms.cli.commands.self_cmd as self_cmd

    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / ".ms-workspace").write_text("", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stale_ms_exe = bin_dir / "ms.exe"
    stale_ms_exe.write_text("old", encoding="utf-8")

    info = WorkspaceInfo(workspace=Workspace(root=ws), source="cwd")

    def fake_detect_workspace_info() -> Ok[WorkspaceInfo]:
        return Ok(info)

    def fake_uv_tool_bin_dir(_root: Path) -> Ok[Path]:
        return Ok(bin_dir)

    monkeypatch.setattr(self_cmd, "detect_workspace_info", fake_detect_workspace_info)
    monkeypatch.setattr(self_cmd, "detect_platform", lambda: Platform.WINDOWS)
    monkeypatch.setattr(self_cmd, "_uv_tool_bin_dir", fake_uv_tool_bin_dir)

    def fake_remember_default_workspace_root(_root: Path) -> Result[None, UserWorkspaceError]:
        return Ok(None)

    monkeypatch.setattr(
        self_cmd, "remember_default_workspace_root", fake_remember_default_workspace_root
    )

    self_cmd.install(update_shell=False, remember_workspace=True, dry_run=False)

    ms_launcher = bin_dir / "ms.cmd"
    assert ms_launcher.exists()
    assert not stale_ms_exe.exists()
    launcher_content = ms_launcher.read_text(encoding="utf-8")
    assert 'set "UV_EXE=%~dp0uv.exe"' in launcher_content
    assert 'if not exist "%UV_EXE%" set "UV_EXE=uv.exe"' in launcher_content
    assert f'"%UV_EXE%" run --project "{ws}" ms %*' in launcher_content
    assert (bin_dir / "oc-build.cmd").exists()


@pytest.mark.parametrize("platform", [Platform.LINUX, Platform.MACOS])
def test_install_repo_launchers_writes_posix_scripts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, platform: Platform
) -> None:
    import ms.cli.commands.self_cmd as self_cmd

    root = tmp_path / "repo with spaces"
    bin_dir = tmp_path / "bin"
    root.mkdir()

    monkeypatch.setattr(self_cmd, "detect_platform", lambda: platform)

    def fake_uv_tool_bin_dir(_root: Path) -> Ok[Path]:
        return Ok(bin_dir)

    monkeypatch.setattr(self_cmd, "_uv_tool_bin_dir", fake_uv_tool_bin_dir)

    result = self_cmd.install_repo_launchers(root, dry_run=False, console=self_cmd.RichConsole())

    assert isinstance(result, Ok)
    ms_launcher = bin_dir / "ms"
    assert ms_launcher.exists()
    assert "uv run --project" in ms_launcher.read_text(encoding="utf-8")
    assert str(root) in ms_launcher.read_text(encoding="utf-8")


def test_self_uninstall_removes_repo_launchers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ms.cli.commands.self_cmd as self_cmd

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    launcher = bin_dir / "ms.cmd"
    launcher.write_text("old", encoding="utf-8")

    def fake_uv_tool_bin_dir(_root: Path) -> Ok[Path]:
        return Ok(bin_dir)

    monkeypatch.setattr(self_cmd, "detect_platform", lambda: Platform.WINDOWS)
    monkeypatch.setattr(self_cmd, "_uv_tool_bin_dir", fake_uv_tool_bin_dir)

    self_cmd.uninstall(dry_run=False)

    assert not launcher.exists()
