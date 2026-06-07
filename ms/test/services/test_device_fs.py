from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.services import device_fs_codec as codec
from ms.services.device_fs import DeviceFileSystemClient, DeviceFsError
from ms.services.device_fs_codec import FsFileType, FsMessageId, FsStatus


@dataclass(frozen=True, slots=True)
class CapturedRpc:
    payload: bytes
    expected_response_id: FsMessageId
    timeout_ms: int


class FakeBridge:
    def __init__(self, responses: tuple[bytes, ...]) -> None:
        self._responses = list(responses)
        self.captured: list[CapturedRpc] = []

    def controller_rpc(
        self,
        payload: bytes,
        *,
        expected_response_id: FsMessageId,
        timeout_ms: int = 2_000,
    ) -> Result[bytes, DeviceFsError]:
        self.captured.append(CapturedRpc(payload, expected_response_id, timeout_ms))
        if not self._responses:
            return Err(DeviceFsError("test", "no fake response available"))
        return Ok(self._responses.pop(0))


def test_list_accumulates_paginated_entries() -> None:
    bridge = FakeBridge(
        (
            _list_response(
                1,
                start_index=0,
                has_more=True,
                entries=(("a.bin", FsFileType.FILE, 1),),
            ),
            _list_response(
                2,
                start_index=1,
                has_more=False,
                entries=(("b.bin", FsFileType.FILE, 2),),
            ),
        )
    )
    client = DeviceFileSystemClient(bridge, initial_request_id=1)

    result = client.list("/")

    assert isinstance(result, Ok)
    assert [entry.name for entry in result.value] == ["a.bin", "b.bin"]
    assert [call.expected_response_id for call in bridge.captured] == [
        FsMessageId.LIST_RESPONSE,
        FsMessageId.LIST_RESPONSE,
    ]
    first_request = codec.decode_frame(bridge.captured[0].payload)
    second_request = codec.decode_frame(bridge.captured[1].payload)
    assert first_request.payload[0:2] == (0).to_bytes(2, "little")
    assert first_request.payload[2] == 1
    assert second_request.payload[0:2] == (1).to_bytes(2, "little")
    assert second_request.payload[2] == 1


def test_push_chunks_file_and_commits(tmp_path: Path) -> None:
    local = tmp_path / "payload.bin"
    local.write_bytes(b"a" * 513)
    bridge = FakeBridge(
        (
            _write_response(FsMessageId.WRITE_BEGIN_RESPONSE, 2, session_id=1, written=0),
            _write_response(FsMessageId.WRITE_CHUNK_RESPONSE, 3, session_id=1, written=512),
            _write_response(FsMessageId.WRITE_CHUNK_RESPONSE, 4, session_id=1, written=1),
            _write_response(FsMessageId.WRITE_COMMIT_RESPONSE, 5, session_id=1, written=0),
        )
    )
    client = DeviceFileSystemClient(bridge, initial_request_id=1)

    result = client.push(local, "projects/payload.bin")

    assert isinstance(result, Ok)
    assert result.value.size_bytes == 513
    assert [call.expected_response_id for call in bridge.captured] == [
        FsMessageId.WRITE_BEGIN_RESPONSE,
        FsMessageId.WRITE_CHUNK_RESPONSE,
        FsMessageId.WRITE_CHUNK_RESPONSE,
        FsMessageId.WRITE_COMMIT_RESPONSE,
    ]
    chunk_frame = codec.decode_frame(bridge.captured[1].payload)
    assert chunk_frame.message_id == FsMessageId.WRITE_CHUNK_REQUEST
    assert len(chunk_frame.payload) == 2 + 4 + 2 + 512


def test_read_file_rejects_non_file() -> None:
    bridge = FakeBridge((_stat_response(1, FsStatus.OK, FsFileType.DIRECTORY, 0),))
    client = DeviceFileSystemClient(bridge, initial_request_id=1)

    result = client.read_file("/")

    assert isinstance(result, Err)
    assert result.error.kind == "not_file"


def _frame(message_id: FsMessageId, request_id: int) -> bytes:
    names = {
        FsMessageId.STAT_RESPONSE: b"FsStatResponse",
        FsMessageId.LIST_RESPONSE: b"FsListResponse",
        FsMessageId.WRITE_BEGIN_RESPONSE: b"FsWriteBeginResponse",
        FsMessageId.WRITE_CHUNK_RESPONSE: b"FsWriteChunkResponse",
        FsMessageId.WRITE_COMMIT_RESPONSE: b"FsWriteCommitResponse",
    }
    name = names[message_id]
    return bytes([message_id, len(name)]) + name + bytes([1]) + request_id.to_bytes(2, "little")


def _stat_response(
    request_id: int,
    status: FsStatus,
    file_type: FsFileType,
    size: int,
) -> bytes:
    return (
        _frame(FsMessageId.STAT_RESPONSE, request_id)
        + bytes([status, file_type])
        + size.to_bytes(4, "little")
    )


def _list_response(
    request_id: int,
    *,
    start_index: int,
    has_more: bool,
    entries: tuple[tuple[str, FsFileType, int], ...],
) -> bytes:
    payload = (
        _frame(FsMessageId.LIST_RESPONSE, request_id)
        + bytes([FsStatus.OK])
        + start_index.to_bytes(2, "little")
        + bytes([len(entries), 1 if has_more else 0])
    )
    for name, file_type, size in entries:
        encoded = name.encode("utf-8")
        payload += bytes([len(encoded)]) + encoded + bytes([file_type]) + size.to_bytes(
            4,
            "little",
        ) + bytes([0])
    return payload


def _write_response(
    message_id: FsMessageId,
    request_id: int,
    *,
    session_id: int,
    written: int,
) -> bytes:
    return (
        _frame(message_id, request_id)
        + bytes([FsStatus.OK])
        + session_id.to_bytes(2, "little")
        + written.to_bytes(2, "little")
    )
