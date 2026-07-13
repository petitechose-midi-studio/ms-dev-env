from __future__ import annotations

import json
from pathlib import Path

import pytest
from pytest import MonkeyPatch

from ms.core.result import Err, Ok
from ms.release.domain.models import DistributionRelease
from ms.release.resolve.auto import carry_prev_pins


def _spec_text(*, schema: int) -> str:
    return json.dumps(
        {
            "schema": schema,
            "channel": "beta",
            "tag": "v1.2.3-beta.4",
            "repos": [
                {"id": "core", "ref": "main", "sha": "a" * 40},
                {"id": "plugin-bitwig", "ref": "release", "sha": "b" * 40},
            ],
            "tooling": {
                "repo": "petitechose-midi-studio/ms-dev-env",
                "ref": "main",
                "sha": "f" * 40,
            },
            "assets": [],
            "install_sets": [],
        }
    )


def _stub_previous_beta(
    *,
    monkeypatch: MonkeyPatch,
    schema: int,
) -> None:
    def fake_list_distribution_releases(
        *, workspace_root: Path, repo: str, limit: int
    ) -> Ok[list[DistributionRelease]]:
        del workspace_root, repo, limit
        return Ok([DistributionRelease(tag="v1.2.3-beta.4", prerelease=True)])

    def fake_get_repo_file_text(
        *, workspace_root: Path, repo: str, path: str, ref: str
    ) -> Ok[str]:
        del workspace_root, repo, ref
        assert path == "release-specs/v1.2.3-beta.4.json"
        return Ok(_spec_text(schema=schema))

    monkeypatch.setattr(
        carry_prev_pins,
        "list_distribution_releases",
        fake_list_distribution_releases,
    )
    monkeypatch.setattr(carry_prev_pins, "get_repo_file_text", fake_get_repo_file_text)


@pytest.mark.parametrize("schema", (1, 2))
def test_load_previous_channel_pins_accepts_supported_spec_schemas(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    schema: int,
) -> None:
    _stub_previous_beta(monkeypatch=monkeypatch, schema=schema)

    parsed = carry_prev_pins.load_previous_channel_pins(
        workspace_root=tmp_path,
        channel="beta",
        dist_repo="petitechose-midi-studio/distribution",
    )

    assert isinstance(parsed, Ok)
    assert parsed.value == {
        "core": ("a" * 40, "main"),
        "plugin-bitwig": ("b" * 40, "release"),
    }


def test_load_previous_channel_pins_rejects_unknown_spec_schema(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    _stub_previous_beta(monkeypatch=monkeypatch, schema=3)

    parsed = carry_prev_pins.load_previous_channel_pins(
        workspace_root=tmp_path,
        channel="beta",
        dist_repo="petitechose-midi-studio/distribution",
    )

    assert isinstance(parsed, Err)
    assert parsed.error == (
        "failed to load previous pins for v1.2.3-beta.4: unsupported spec schema: 3"
    )
