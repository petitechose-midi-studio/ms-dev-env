from __future__ import annotations

from pathlib import Path

import pytest
import typer

from ms.cli.context import CLIContext
from ms.core.errors import ErrorCode
from ms.core.result import Ok
from ms.core.workspace import Workspace
from ms.output.console import MockConsole
from ms.platform.detection import detect
from ms.release.domain import CANDIDATE_SCHEMA, CandidateInputRepo, CandidateManifest
from ms.release.flow.candidate_types import CandidateFetchResult


def _ctx(tmp_path: Path, console: MockConsole) -> CLIContext:
    (tmp_path / ".ms-workspace").write_text("", encoding="utf-8")
    return CLIContext(
        workspace=Workspace(root=tmp_path),
        platform=detect(),
        config=None,
        console=console,
    )


def test_fetch_candidate_cmd_prints_copied_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ms.cli.commands.release_candidate_commands as candidate_cmd

    console = MockConsole()
    copied = tmp_path / "dist" / "firmware.hex"
    copied.parent.mkdir(parents=True)
    copied.write_bytes(b"hex")

    def fake_fetch_candidate_assets(**_: object) -> Ok[CandidateFetchResult]:
        return Ok(
            CandidateFetchResult(
                producer_id="core-default-firmware",
                candidate_repo="petitechose-midi-studio/core",
                candidate_tag="rc-" + ("a" * 40),
                output_dir=copied.parent,
                copied_files=(copied,),
                manifest=CandidateManifest(
                    schema=CANDIDATE_SCHEMA,
                    producer_repo="petitechose-midi-studio/core",
                    producer_kind="core-default-firmware",
                    workflow_file=".github/workflows/candidate.yml",
                    run_id=1,
                    run_attempt=1,
                    generated_at="2026-04-18T10:00:00Z",
                    build_input_fingerprint="f" * 64,
                    recipe_fingerprint="r" * 64,
                    input_repos=(
                        CandidateInputRepo(
                            id="core",
                            repo="petitechose-midi-studio/core",
                            sha="a" * 40,
                        ),
                    ),
                    toolchain=(),
                    config=(),
                    artifacts=(),
                ),
            )
        )

    monkeypatch.setattr(candidate_cmd, "build_context", lambda: _ctx(tmp_path, console))
    monkeypatch.setattr(candidate_cmd, "fetch_candidate_assets", fake_fetch_candidate_assets)

    candidate_cmd.fetch_candidate_cmd(
        producer_id="core-default-firmware",
        candidate_tag="rc-" + ("a" * 40),
        out_dir=copied.parent,
        asset_filename=["firmware.hex"],
        input_repo=["core=petitechose-midi-studio/core=" + ("a" * 40)],
    )

    assert any("Candidate assets fetched" in message for message in console.messages)
    assert any(str(copied) in message for message in console.messages)


def test_fetch_candidate_cmd_rejects_invalid_input_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ms.cli.commands.release_candidate_commands as candidate_cmd

    console = MockConsole()
    monkeypatch.setattr(candidate_cmd, "build_context", lambda: _ctx(tmp_path, console))

    with pytest.raises(typer.Exit) as exc:
        candidate_cmd.fetch_candidate_cmd(
            producer_id="core-default-firmware",
            candidate_tag="rc-" + ("a" * 40),
            out_dir=tmp_path / "dist",
            asset_filename=["firmware.hex"],
            input_repo=["core=petitechose-midi-studio/core=not-a-sha"],
        )

    assert exc.value.exit_code == int(ErrorCode.USER_ERROR)
