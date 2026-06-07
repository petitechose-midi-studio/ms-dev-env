from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

FILESYSTEM_RPC_SCHEMA = 1
FILESYSTEM_RPC_MAX_CHUNK_SIZE = 512
FILESYSTEM_RPC_MAX_LIST_ENTRIES = 8


class FsMessageId(IntEnum):
    STAT_REQUEST = 0xE0
    STAT_RESPONSE = 0xE1
    LIST_REQUEST = 0xE2
    LIST_RESPONSE = 0xE3
    READ_REQUEST = 0xE4
    READ_RESPONSE = 0xE5
    WRITE_BEGIN_REQUEST = 0xE6
    WRITE_BEGIN_RESPONSE = 0xE7
    WRITE_CHUNK_REQUEST = 0xE8
    WRITE_CHUNK_RESPONSE = 0xE9
    WRITE_COMMIT_REQUEST = 0xEA
    WRITE_COMMIT_RESPONSE = 0xEB
    WRITE_ABORT_REQUEST = 0xEC
    WRITE_ABORT_RESPONSE = 0xED
    ERROR_RESPONSE = 0xEF


class FsStatus(IntEnum):
    OK = 0
    INVALID_MESSAGE = 1
    INVALID_ARGUMENT = 2
    NOT_FOUND = 3
    BUSY = 4
    TOO_LARGE = 5
    STORAGE_ERROR = 6
    INVALID_STATE = 7
    UNSUPPORTED = 8


class FsFileType(IntEnum):
    MISSING = 0
    FILE = 1
    DIRECTORY = 2
    OTHER = 3


@dataclass(frozen=True, slots=True)
class FsFrame:
    message_id: FsMessageId
    schema: int
    request_id: int
    payload: bytes


@dataclass(frozen=True, slots=True)
class FsStatResponse:
    request_id: int
    status: FsStatus
    file_type: FsFileType
    size_bytes: int


@dataclass(frozen=True, slots=True)
class FsListEntry:
    name: str
    file_type: FsFileType
    size_bytes: int
    name_truncated: bool


@dataclass(frozen=True, slots=True)
class FsListResponse:
    request_id: int
    status: FsStatus
    start_index: int
    has_more: bool
    entries: tuple[FsListEntry, ...]


@dataclass(frozen=True, slots=True)
class FsReadResponse:
    request_id: int
    status: FsStatus
    offset: int
    data: bytes


@dataclass(frozen=True, slots=True)
class FsWriteResponse:
    request_id: int
    status: FsStatus
    session_id: int
    bytes_written: int


class FsCodecError(ValueError):
    pass


_MESSAGE_NAMES: dict[FsMessageId, str] = {
    FsMessageId.STAT_REQUEST: "FsStatRequest",
    FsMessageId.STAT_RESPONSE: "FsStatResponse",
    FsMessageId.LIST_REQUEST: "FsListRequest",
    FsMessageId.LIST_RESPONSE: "FsListResponse",
    FsMessageId.READ_REQUEST: "FsReadRequest",
    FsMessageId.READ_RESPONSE: "FsReadResponse",
    FsMessageId.WRITE_BEGIN_REQUEST: "FsWriteBeginRequest",
    FsMessageId.WRITE_BEGIN_RESPONSE: "FsWriteBeginResponse",
    FsMessageId.WRITE_CHUNK_REQUEST: "FsWriteChunkRequest",
    FsMessageId.WRITE_CHUNK_RESPONSE: "FsWriteChunkResponse",
    FsMessageId.WRITE_COMMIT_REQUEST: "FsWriteCommitRequest",
    FsMessageId.WRITE_COMMIT_RESPONSE: "FsWriteCommitResponse",
    FsMessageId.WRITE_ABORT_REQUEST: "FsWriteAbortRequest",
    FsMessageId.WRITE_ABORT_RESPONSE: "FsWriteAbortResponse",
    FsMessageId.ERROR_RESPONSE: "FsErrorResponse",
}


def encode_stat_request(request_id: int, path: str) -> bytes:
    return _frame(FsMessageId.STAT_REQUEST, request_id, _string(path))


def encode_list_request(
    request_id: int,
    path: str,
    *,
    start_index: int,
    max_entries: int,
) -> bytes:
    payload = _u16(start_index) + bytes([max_entries]) + _string(path)
    return _frame(FsMessageId.LIST_REQUEST, request_id, payload)


def encode_read_request(
    request_id: int,
    path: str,
    *,
    offset: int,
    size: int,
) -> bytes:
    if size > FILESYSTEM_RPC_MAX_CHUNK_SIZE:
        raise FsCodecError("read size exceeds filesystem rpc chunk limit")
    payload = _u32(offset) + _u16(size) + _string(path)
    return _frame(FsMessageId.READ_REQUEST, request_id, payload)


def encode_write_begin_request(
    request_id: int,
    session_id: int,
    path: str,
    *,
    expected_size: int,
) -> bytes:
    payload = _u16(session_id) + _u32(expected_size) + _string(path)
    return _frame(FsMessageId.WRITE_BEGIN_REQUEST, request_id, payload)


def encode_write_chunk_request(
    request_id: int,
    session_id: int,
    *,
    offset: int,
    data: bytes,
) -> bytes:
    if len(data) > FILESYSTEM_RPC_MAX_CHUNK_SIZE:
        raise FsCodecError("write chunk exceeds filesystem rpc chunk limit")
    payload = _u16(session_id) + _u32(offset) + _u16(len(data)) + data
    return _frame(FsMessageId.WRITE_CHUNK_REQUEST, request_id, payload)


def encode_write_commit_request(request_id: int, session_id: int) -> bytes:
    return _frame(FsMessageId.WRITE_COMMIT_REQUEST, request_id, _u16(session_id))


def encode_write_abort_request(request_id: int, session_id: int) -> bytes:
    return _frame(FsMessageId.WRITE_ABORT_REQUEST, request_id, _u16(session_id))


def decode_frame(data: bytes) -> FsFrame:
    reader = _Reader(data)
    raw_id = reader.u8()
    try:
        message_id = FsMessageId(raw_id)
    except ValueError as exc:
        raise FsCodecError(f"unknown filesystem rpc message id: 0x{raw_id:02x}") from exc
    name_len = reader.u8()
    _ = reader.bytes(name_len)
    schema = reader.u8()
    request_id = reader.u16()
    return FsFrame(
        message_id=message_id,
        schema=schema,
        request_id=request_id,
        payload=reader.remaining_bytes(),
    )


def decode_stat_response(data: bytes) -> FsStatResponse:
    frame = _response_frame(data, FsMessageId.STAT_RESPONSE)
    reader = _Reader(frame.payload)
    status = _status(reader.u8())
    file_type = FsFileType.MISSING
    size_bytes = 0
    if status == FsStatus.OK:
        file_type = _file_type(reader.u8())
        size_bytes = reader.u32()
    return FsStatResponse(frame.request_id, status, file_type, size_bytes)


def decode_list_response(data: bytes) -> FsListResponse:
    frame = _response_frame(data, FsMessageId.LIST_RESPONSE)
    reader = _Reader(frame.payload)
    status = _status(reader.u8())
    if status != FsStatus.OK:
        return FsListResponse(frame.request_id, status, 0, False, ())

    start_index = reader.u16()
    entry_count = reader.u8()
    has_more = reader.bool()
    if entry_count > FILESYSTEM_RPC_MAX_LIST_ENTRIES:
        raise FsCodecError("filesystem rpc list response entry count exceeds limit")

    entries: list[FsListEntry] = []
    for _ in range(entry_count):
        name = reader.string()
        entries.append(
            FsListEntry(
                name=name,
                file_type=_file_type(reader.u8()),
                size_bytes=reader.u32(),
                name_truncated=reader.bool(),
            )
        )
    return FsListResponse(frame.request_id, status, start_index, has_more, tuple(entries))


def decode_read_response(data: bytes) -> FsReadResponse:
    frame = _response_frame(data, FsMessageId.READ_RESPONSE)
    reader = _Reader(frame.payload)
    status = _status(reader.u8())
    if status != FsStatus.OK:
        return FsReadResponse(frame.request_id, status, 0, b"")

    offset = reader.u32()
    size = reader.u16()
    return FsReadResponse(frame.request_id, status, offset, reader.bytes(size))


def decode_write_response(data: bytes) -> FsWriteResponse:
    frame = decode_frame(data)
    if frame.message_id not in (
        FsMessageId.WRITE_BEGIN_RESPONSE,
        FsMessageId.WRITE_CHUNK_RESPONSE,
        FsMessageId.WRITE_COMMIT_RESPONSE,
        FsMessageId.WRITE_ABORT_RESPONSE,
    ):
        raise FsCodecError(f"not a write response: {frame.message_id.name}")

    reader = _Reader(frame.payload)
    return FsWriteResponse(
        request_id=frame.request_id,
        status=_status(reader.u8()),
        session_id=reader.u16(),
        bytes_written=reader.u16(),
    )


def expected_response_id(request_id: FsMessageId) -> FsMessageId:
    match request_id:
        case FsMessageId.STAT_REQUEST:
            return FsMessageId.STAT_RESPONSE
        case FsMessageId.LIST_REQUEST:
            return FsMessageId.LIST_RESPONSE
        case FsMessageId.READ_REQUEST:
            return FsMessageId.READ_RESPONSE
        case FsMessageId.WRITE_BEGIN_REQUEST:
            return FsMessageId.WRITE_BEGIN_RESPONSE
        case FsMessageId.WRITE_CHUNK_REQUEST:
            return FsMessageId.WRITE_CHUNK_RESPONSE
        case FsMessageId.WRITE_COMMIT_REQUEST:
            return FsMessageId.WRITE_COMMIT_RESPONSE
        case FsMessageId.WRITE_ABORT_REQUEST:
            return FsMessageId.WRITE_ABORT_RESPONSE
        case _:
            raise FsCodecError(f"message id is not a request: {request_id.name}")


def status_label(status: FsStatus) -> str:
    return status.name.lower().replace("_", "-")


def file_type_label(file_type: FsFileType) -> str:
    return file_type.name.lower()


def _response_frame(data: bytes, expected: FsMessageId) -> FsFrame:
    frame = decode_frame(data)
    if frame.message_id != expected:
        raise FsCodecError(f"expected {expected.name}, got {frame.message_id.name}")
    if frame.schema != FILESYSTEM_RPC_SCHEMA:
        raise FsCodecError(f"unsupported filesystem rpc schema: {frame.schema}")
    return frame


def _frame(message_id: FsMessageId, request_id: int, payload: bytes) -> bytes:
    return (
        bytes([message_id])
        + _string(_MESSAGE_NAMES[message_id])
        + bytes([FILESYSTEM_RPC_SCHEMA])
        + _u16(request_id)
        + payload
    )


def _string(value: str) -> bytes:
    encoded = value.encode("utf-8")
    if len(encoded) > 255:
        raise FsCodecError("filesystem rpc string exceeds 255 bytes")
    return bytes([len(encoded)]) + encoded


def _u16(value: int) -> bytes:
    if value < 0 or value > 0xFFFF:
        raise FsCodecError("u16 value out of range")
    return value.to_bytes(2, "little")


def _u32(value: int) -> bytes:
    if value < 0 or value > 0xFFFFFFFF:
        raise FsCodecError("u32 value out of range")
    return value.to_bytes(4, "little")


def _status(value: int) -> FsStatus:
    try:
        return FsStatus(value)
    except ValueError as exc:
        raise FsCodecError(f"unknown filesystem rpc status: {value}") from exc


def _file_type(value: int) -> FsFileType:
    try:
        return FsFileType(value)
    except ValueError as exc:
        raise FsCodecError(f"unknown filesystem rpc file type: {value}") from exc


class _Reader:
    def __init__(self, data: bytes) -> None:
        self._data = data
        self._offset = 0

    def u8(self) -> int:
        return self.bytes(1)[0]

    def bool(self) -> bool:
        return self.u8() != 0

    def u16(self) -> int:
        return int.from_bytes(self.bytes(2), "little")

    def u32(self) -> int:
        return int.from_bytes(self.bytes(4), "little")

    def string(self) -> str:
        length = self.u8()
        try:
            return self.bytes(length).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise FsCodecError("filesystem rpc string is not valid utf-8") from exc

    def bytes(self, size: int) -> bytes:
        if size < 0:
            raise FsCodecError("negative read size")
        end = self._offset + size
        if end > len(self._data):
            raise FsCodecError("truncated filesystem rpc payload")
        out = self._data[self._offset : end]
        self._offset = end
        return out

    def remaining_bytes(self) -> bytes:
        out = self._data[self._offset :]
        self._offset = len(self._data)
        return out
