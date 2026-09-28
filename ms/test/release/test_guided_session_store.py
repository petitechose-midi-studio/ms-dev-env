"""Tests for guided release session persistence boundary."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest

from ms.core.result import Err, Ok
from ms.release.flow.guided.session_app_store import load_app_session
from ms.release.flow.guided.session_content_store import load_content_session
from ms.release.flow.guided.session_models import new_app_session, new_content_session
from ms.release.flow.guided.session_paths import app_session_path, content_session_path
from ms.release.flow.guided.session_store import read_session, write_session


class TestReadSession:
    def test_missing_file_returns_none(self, tmp_path: Path) -> None:
        result = read_session(path=tmp_path / "session.json")
        assert isinstance(result, Ok)
        assert result.value is None

    def test_roundtrip(self, tmp_path: Path) -> None:
        path = tmp_path / "session.json"
        written = write_session(path=path, payload={"release_id": "app-abc"})
        assert isinstance(written, Ok)

        result = read_session(path=path)
        assert isinstance(result, Ok)
        assert result.value is not None
        assert result.value["release_id"] == "app-abc"

    def test_json_array_rejected(self, tmp_path: Path) -> None:
        path = tmp_path / "session.json"
        path.write_text("[]")

        result = read_session(path=path)

        assert isinstance(result, Err)
        assert result.error.kind == "invalid_input"


@pytest.mark.parametrize("product", ("app", "content"))
@pytest.mark.parametrize("obsolete_field", ("cursor", "pending_inputs", "malformed_inputs"))
def test_session_requires_current_persisted_shape(
    tmp_path: Path, product: str, obsolete_field: str,
) -> None:
    session = (
        new_app_session(created_by="test", notes_path=None) if product == "app"
        else new_content_session(created_by="test", notes_path=None)
    )
    payload = asdict(session)
    if obsolete_field == "malformed_inputs":
        payload["pending_inputs"] = [["tag"]]
    else:
        del payload[obsolete_field]
    path = (
        app_session_path(workspace_root=tmp_path) if product == "app"
        else content_session_path(workspace_root=tmp_path)
    )
    assert isinstance(write_session(path=path, payload=payload), Ok)
    original = path.read_bytes()
    result = (
        load_app_session(workspace_root=tmp_path) if product == "app"
        else load_content_session(workspace_root=tmp_path)
    )
    assert isinstance(result, Err)
    assert result.error.kind == "invalid_input"
    assert path.read_bytes() == original


def test_invalid_encoding_rejected(tmp_path: Path) -> None:
    path = tmp_path / "session.json"
    path.write_bytes(b"\xff\xfe\x00{")
    result = read_session(path=path)
    assert isinstance(result, Err)


def test_unknown_schema_rejected(tmp_path: Path) -> None:
    path = tmp_path / "session.json"
    path.write_text(json.dumps({"schema": 99}))
    result = read_session(path=path)
    assert isinstance(result, Err)
    assert result.error.kind == "invalid_input"
