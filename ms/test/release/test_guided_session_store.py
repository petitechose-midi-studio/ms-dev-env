"""Tests for guided release session persistence boundary."""

from __future__ import annotations

import json
from pathlib import Path

from ms.core.result import Err, Ok
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

    def test_invalid_encoding_rejected(self, tmp_path: Path) -> None:
        path = tmp_path / "session.json"
        path.write_bytes(b"\xff\xfe\x00{")

        result = read_session(path=path)

        assert isinstance(result, Err)

    def test_unknown_schema_rejected(self, tmp_path: Path) -> None:
        path = tmp_path / "session.json"
        path.write_text(json.dumps({"schema": 99}))

        result = read_session(path=path)

        assert isinstance(result, Err)
        assert result.error.kind == "invalid_input"
