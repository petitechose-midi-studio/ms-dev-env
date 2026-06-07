from __future__ import annotations

from ms.services import device_fs_codec as codec
from ms.services.device_fs_codec import FsFileType, FsMessageId, FsStatus


def test_encode_stat_request_matches_firmware_wire_format() -> None:
    payload = codec.encode_stat_request(7, "projects/demo.bin")

    expected = (
        bytes([0xE0, len("FsStatRequest")])
        + b"FsStatRequest"
        + bytes([1])
        + (7).to_bytes(2, "little")
        + bytes([len("projects/demo.bin")])
        + b"projects/demo.bin"
    )
    assert payload == expected


def test_decode_stat_response() -> None:
    payload = (
        _frame(FsMessageId.STAT_RESPONSE, 8)
        + bytes([FsStatus.OK, FsFileType.FILE])
        + (1234).to_bytes(4, "little")
    )

    response = codec.decode_stat_response(payload)

    assert response.request_id == 8
    assert response.status == FsStatus.OK
    assert response.file_type == FsFileType.FILE
    assert response.size_bytes == 1234


def test_decode_list_response_entries() -> None:
    payload = (
        _frame(FsMessageId.LIST_RESPONSE, 9)
        + bytes([FsStatus.OK])
        + (0).to_bytes(2, "little")
        + bytes([2, 0])
        + _entry("projects", FsFileType.DIRECTORY, 0)
        + _entry("demo.bin", FsFileType.FILE, 32)
    )

    response = codec.decode_list_response(payload)

    assert response.request_id == 9
    assert response.status == FsStatus.OK
    assert response.has_more is False
    assert [entry.name for entry in response.entries] == ["projects", "demo.bin"]
    assert response.entries[1].size_bytes == 32


def test_expected_response_id_maps_request_to_response() -> None:
    assert codec.expected_response_id(FsMessageId.READ_REQUEST) == FsMessageId.READ_RESPONSE
    assert (
        codec.expected_response_id(FsMessageId.WRITE_COMMIT_REQUEST)
        == FsMessageId.WRITE_COMMIT_RESPONSE
    )


def _frame(message_id: FsMessageId, request_id: int) -> bytes:
    name = {
        FsMessageId.STAT_RESPONSE: b"FsStatResponse",
        FsMessageId.LIST_RESPONSE: b"FsListResponse",
    }[message_id]
    return bytes([message_id, len(name)]) + name + bytes([1]) + request_id.to_bytes(2, "little")


def _entry(name: str, file_type: FsFileType, size: int) -> bytes:
    encoded = name.encode("utf-8")
    return (
        bytes([len(encoded)])
        + encoded
        + bytes([file_type])
        + size.to_bytes(4, "little")
        + bytes([0])
    )
