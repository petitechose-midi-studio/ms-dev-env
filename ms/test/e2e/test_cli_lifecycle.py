from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

from ms.core.result import Ok
from ms.release.flow.guided.session_models import new_app_session
from ms.release.flow.guided.sessions import save_app_session


def _run_ms(workspace: Path, cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    executable = Path(sys.executable).with_name("ms.exe" if os.name == "nt" else "ms")
    assert executable.is_file(), f"ms launcher not found beside {sys.executable}"

    env = os.environ.copy()
    env.pop("WORKSPACE_ROOT", None)
    env["COLUMNS"] = "240"
    env["NO_COLOR"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        [str(executable), "--workspace", str(workspace), *args],
        cwd=cwd,
        env=env,
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, (
        f"ms {' '.join(args)} failed with {result.returncode}\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
    return result


def test_cli_workspace_setup_release_status_and_clean(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    nested = workspace / "nested"
    nested.mkdir(parents=True)
    (workspace / ".ms-workspace").write_text("", encoding="utf-8")

    help_result = _run_ms(workspace, nested, "--help")
    assert "Setup dev workspace" in help_result.stdout
    assert "Release orchestration" in help_result.stdout

    where = _run_ms(workspace, nested, "where")
    assert f"workspace: {workspace.resolve()}" in where.stdout.replace("\n", "")
    assert "source: env" in where.stdout

    setup = _run_ms(
        workspace,
        nested,
        "setup",
        "--dry-run",
        "--skip-prereqs",
        "--skip-check",
        "--yes",
    )
    assert "Setup complete" in setup.stdout
    assert not (workspace / ".ms").exists()
    assert not (workspace / "tools").exists()
    assert not (workspace / "midi-studio").exists()

    empty_status = _run_ms(workspace, nested, "release", "status")
    assert "No unfinished guided release session" in empty_status.stdout

    session = replace(
        new_app_session(created_by="e2e", notes_path=None),
        step="summary",
        channel="stable",
        tag="v1.2.3",
        repo_sha="a" * 40,
    )
    saved = save_app_session(workspace_root=workspace, session=session)
    assert isinstance(saved, Ok)

    resumed_status = _run_ms(workspace, nested, "release", "status")
    assert "app: v1.2.3 | stable | step summary | source aaaaaaaaaaaa" in resumed_status.stdout
    assert "resume: uv run ms release --watch" in resumed_status.stdout

    sentinel = workspace / ".build" / "sentinel"
    sentinel.parent.mkdir()
    sentinel.write_text("keep until execute", encoding="utf-8")

    dry_clean = _run_ms(workspace, nested, "clean")
    assert "DRY-RUN" in dry_clean.stdout
    assert sentinel.exists()

    execute_clean = _run_ms(workspace, nested, "clean", "--yes")
    assert "Removed 1 directories" in execute_clean.stdout
    assert not sentinel.parent.exists()
