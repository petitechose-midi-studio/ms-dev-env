from __future__ import annotations

from pathlib import Path

from pytest import MonkeyPatch

from ms.core.result import Err, Ok
from ms.platform.process import ProcessError
from ms.release.flow.release_tooling import ensure_release_tooling_on_main


def test_ensure_release_tooling_on_main_checks_remote_main(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    import ms.release.flow.release_tooling as release_tooling

    commands: list[tuple[str, ...]] = []

    def fake_run_git_command(*, cmd: list[str], repo_root: Path, network: bool = False) -> Ok[str]:
        del repo_root, network
        commands.append(tuple(cmd))
        return Ok("")

    monkeypatch.setattr(release_tooling, "run_git_command", fake_run_git_command)

    result = ensure_release_tooling_on_main(workspace_root=tmp_path, tooling_sha="a" * 40)

    assert isinstance(result, Ok)
    assert commands == [
        (
            "git",
            "fetch",
            "--no-tags",
            "origin",
            "+refs/heads/main:refs/remotes/origin/main",
        ),
        ("git", "merge-base", "--is-ancestor", "a" * 40, "refs/remotes/origin/main"),
    ]


def test_ensure_release_tooling_on_main_fails_when_sha_is_not_reachable(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    import ms.release.flow.release_tooling as release_tooling

    def fake_run_git_command(*, cmd: list[str], repo_root: Path, network: bool = False):
        del repo_root, network
        if cmd[1] == "fetch":
            return Ok("")
        return Err(ProcessError(command=tuple(cmd), returncode=1, stdout="", stderr=""))

    monkeypatch.setattr(release_tooling, "run_git_command", fake_run_git_command)

    result = ensure_release_tooling_on_main(workspace_root=tmp_path, tooling_sha="b" * 40)

    assert isinstance(result, Err)
    assert result.error.kind == "invalid_input"
    assert result.error.message == "release tooling SHA is not reachable from ms-dev-env main"
    assert "Merge this ms-dev-env commit to main" in (result.error.hint or "")
