from __future__ import annotations

from pathlib import Path

import pytest

from ms.core.result import Err, Ok, Result
from ms.core.user_workspace import UserWorkspaceError
from ms.core.workspace import Workspace, WorkspaceInfo
from ms.output.console import ConsoleProtocol
from ms.platform.detection import Platform
from ms.platform.process import ProcessError


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

    def fake_cleanup_legacy_uv_tool(
        _root: Path, *, dry_run: bool, console: ConsoleProtocol
    ) -> None:
        del dry_run
        del console

    monkeypatch.setattr(self_cmd, "detect_workspace_info", fake_detect_workspace_info)
    monkeypatch.setattr(self_cmd, "detect_platform", lambda: Platform.WINDOWS)
    monkeypatch.setattr(self_cmd, "_uv_tool_bin_dir", fake_uv_tool_bin_dir)
    monkeypatch.setattr(self_cmd, "_cleanup_legacy_uv_tool", fake_cleanup_legacy_uv_tool)

    def fake_remember_default_workspace_root(_root: Path) -> Result[None, UserWorkspaceError]:
        return Ok(None)

    monkeypatch.setattr(
        self_cmd, "remember_default_workspace_root", fake_remember_default_workspace_root
    )

    self_cmd.install(editable=True, update_shell=False, remember_workspace=True, dry_run=False)

    ms_launcher = bin_dir / "ms.cmd"
    assert ms_launcher.exists()
    assert not stale_ms_exe.exists()
    assert f'uv run --project "{ws}" ms %*' in ms_launcher.read_text(encoding="utf-8")
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

    def fake_cleanup_legacy_uv_tool(
        _root: Path, *, dry_run: bool, console: ConsoleProtocol
    ) -> None:
        del dry_run
        del console

    monkeypatch.setattr(self_cmd, "_uv_tool_bin_dir", fake_uv_tool_bin_dir)
    monkeypatch.setattr(self_cmd, "_cleanup_legacy_uv_tool", fake_cleanup_legacy_uv_tool)

    result = self_cmd.install_repo_launchers(root, dry_run=False, console=self_cmd.RichConsole())

    assert isinstance(result, Ok)
    ms_launcher = bin_dir / "ms"
    assert ms_launcher.exists()
    assert "uv run --project" in ms_launcher.read_text(encoding="utf-8")
    assert str(root) in ms_launcher.read_text(encoding="utf-8")


def test_self_uninstall_runs_uv_tool_uninstall(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ms.cli.commands.self_cmd as self_cmd

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    launcher = bin_dir / "ms.cmd"
    launcher.write_text("old", encoding="utf-8")
    seen: dict[str, object] = {}

    def fake_tool_name_for_current_ms() -> str:
        return "my-tool"

    def fake_uv_tool_bin_dir(_root: Path) -> Ok[Path]:
        return Ok(bin_dir)

    monkeypatch.setattr(self_cmd, "_tool_name_for_current_ms", fake_tool_name_for_current_ms)
    monkeypatch.setattr(self_cmd, "detect_platform", lambda: Platform.WINDOWS)
    monkeypatch.setattr(self_cmd, "_uv_tool_bin_dir", fake_uv_tool_bin_dir)

    def fake_run_silent(
        cmd: list[str],
        cwd: Path,
        env: dict[str, str] | None = None,
        *,
        timeout: float | None = None,
    ) -> Result[None, ProcessError]:
        del env
        del timeout
        seen["cmd"] = cmd
        seen["cwd"] = cwd
        return Ok(None)

    monkeypatch.setattr(self_cmd, "run_silent", fake_run_silent)

    self_cmd.uninstall(name=None, dry_run=False)

    assert seen["cmd"] == ["uv", "tool", "uninstall", "my-tool"]
    assert not launcher.exists()


def test_self_uninstall_accepts_explicit_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ms.cli.commands.self_cmd as self_cmd

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    seen: dict[str, object] = {}

    def fake_tool_name_for_current_ms() -> str:
        return "ignored"

    def fake_uv_tool_bin_dir(_root: Path) -> Ok[Path]:
        return Ok(bin_dir)

    monkeypatch.setattr(self_cmd, "_tool_name_for_current_ms", fake_tool_name_for_current_ms)
    monkeypatch.setattr(self_cmd, "_uv_tool_bin_dir", fake_uv_tool_bin_dir)

    def fake_run_silent(
        cmd: list[str],
        cwd: Path,
        env: dict[str, str] | None = None,
        *,
        timeout: float | None = None,
    ) -> Result[None, ProcessError]:
        del env
        del timeout
        seen["cmd"] = cmd
        seen["cwd"] = cwd
        return Ok(None)

    monkeypatch.setattr(self_cmd, "run_silent", fake_run_silent)

    self_cmd.uninstall(name="explicit-tool", dry_run=False)

    assert seen["cmd"] == ["uv", "tool", "uninstall", "explicit-tool"]


def test_self_uninstall_ignores_missing_legacy_uv_tool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ms.cli.commands.self_cmd as self_cmd

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    def fake_uv_tool_bin_dir(_root: Path) -> Ok[Path]:
        return Ok(bin_dir)

    def fake_run_silent(
        cmd: list[str],
        cwd: Path,
        env: dict[str, str] | None = None,
        *,
        timeout: float | None = None,
    ) -> Result[None, ProcessError]:
        del cwd
        del env
        del timeout
        return Err(
            ProcessError(tuple(cmd), 2, "", "error: `midi-studio-ms-dev-env` is not installed")
        )

    def fake_resolve_tool_name(*, override: str | None) -> tuple[str, str]:
        del override
        return "tool", "test"

    monkeypatch.setattr(self_cmd, "_uv_tool_bin_dir", fake_uv_tool_bin_dir)
    monkeypatch.setattr(self_cmd, "_resolve_tool_name", fake_resolve_tool_name)
    monkeypatch.setattr(self_cmd, "run_silent", fake_run_silent)

    self_cmd.uninstall(name=None, dry_run=False)
