from __future__ import annotations

import json
import secrets
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

from ms.core.result import Err, Ok, Result
from ms.services import device_fs_codec as codec
from ms.services.device_fs_codec import (
    FILESYSTEM_RPC_MAX_CHUNK_SIZE,
    FILESYSTEM_RPC_MAX_LIST_ENTRIES,
    FsFileType,
    FsListEntry,
    FsMessageId,
    FsStatResponse,
    FsStatus,
    FsWriteResponse,
)

DEFAULT_BRIDGE_CONTROL_PORT = 7999
DEFAULT_CONTROL_TIMEOUT_SECONDS = 2.0
DEFAULT_RPC_TIMEOUT_MS = 2_000
DEVICE_FS_LIST_PAGE_ENTRIES = 1


@dataclass(frozen=True, slots=True)
class DeviceFsError:
    kind: str
    message: str
    hint: str | None = None


@dataclass(frozen=True, slots=True)
class DeviceFsPullResult:
    remote_path: str
    local_path: Path
    size_bytes: int


@dataclass(frozen=True, slots=True)
class DeviceFsPushResult:
    local_path: Path
    remote_path: str
    size_bytes: int


class BridgeControlClient:
    def __init__(
        self,
        *,
        port: int = DEFAULT_BRIDGE_CONTROL_PORT,
        timeout_seconds: float = DEFAULT_CONTROL_TIMEOUT_SECONDS,
    ) -> None:
        self._port = port
        self._timeout_seconds = timeout_seconds

    def controller_rpc(
        self,
        payload: bytes,
        *,
        expected_response_id: FsMessageId,
        timeout_ms: int = DEFAULT_RPC_TIMEOUT_MS,
    ) -> Result[bytes, DeviceFsError]:
        request: dict[str, object] = {
            "schema": 1,
            "cmd": "controller-rpc",
            "payload_hex": payload.hex(),
            "expected_response_id": int(expected_response_id),
            "timeout_ms": timeout_ms,
        }

        try:
            with socket.create_connection(
                ("127.0.0.1", self._port),
                timeout=self._timeout_seconds,
            ) as stream:
                stream.settimeout(self._timeout_seconds + (timeout_ms / 1000.0))
                stream.sendall(json.dumps(request, separators=(",", ":")).encode("utf-8") + b"\n")
                chunks: list[bytes] = []
                while True:
                    chunk = stream.recv(4096)
                    if not chunk:
                        break
                    chunks.append(chunk)
        except OSError as exc:
            return Err(
                DeviceFsError(
                    kind="bridge_unavailable",
                    message=f"cannot reach oc-bridge control port {self._port}: {exc}",
                    hint="Start oc-bridge in hardware mode and keep the controller connected.",
                )
            )

        try:
            decoded_json = json.loads(b"".join(chunks).decode("utf-8").strip())
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return Err(
                DeviceFsError(
                    kind="bridge_protocol",
                    message=f"invalid oc-bridge control response: {exc}",
                )
            )
        if not isinstance(decoded_json, dict):
            return Err(DeviceFsError("bridge_protocol", "oc-bridge response is not an object"))
        response_obj = cast(dict[str, object], decoded_json)

        ok = response_obj.get("ok")
        if ok is not True:
            message = response_obj.get("message")
            return Err(
                DeviceFsError(
                    kind="controller_rpc_failed",
                    message=str(message) if message else "controller rpc failed",
                    hint="Check that the bridge is attached to the hardware controller.",
                )
            )

        payload_hex = response_obj.get("payload_hex")
        if not isinstance(payload_hex, str):
            return Err(
                DeviceFsError(
                    kind="bridge_protocol",
                    message="oc-bridge response missing payload_hex",
                )
            )
        try:
            return Ok(bytes.fromhex(payload_hex))
        except ValueError as exc:
            return Err(
                DeviceFsError(
                    kind="bridge_protocol",
                    message=f"invalid payload_hex from oc-bridge: {exc}",
                )
            )


class ControllerRpcTransport(Protocol):
    def controller_rpc(
        self,
        payload: bytes,
        *,
        expected_response_id: FsMessageId,
        timeout_ms: int = DEFAULT_RPC_TIMEOUT_MS,
    ) -> Result[bytes, DeviceFsError]:
        ...


class DeviceFileSystemClient:
    def __init__(
        self,
        bridge: ControllerRpcTransport,
        *,
        initial_request_id: int | None = None,
    ) -> None:
        self._bridge = bridge
        self._next_request_id = initial_request_id or (secrets.randbelow(0xFFFF) + 1)

    def stat(self, path: str) -> Result[FsStatResponse, DeviceFsError]:
        request_id = self._request_id()
        payload = codec.encode_stat_request(request_id, path)
        response = self._rpc(payload, FsMessageId.STAT_RESPONSE)
        if isinstance(response, Err):
            return response
        try:
            decoded = codec.decode_stat_response(response.value)
        except codec.FsCodecError as exc:
            return Err(DeviceFsError("codec_error", str(exc)))
        return self._checked_request(decoded.request_id, request_id, decoded)

    def list(self, path: str) -> Result[tuple[FsListEntry, ...], DeviceFsError]:
        start_index = 0
        entries: list[FsListEntry] = []
        while True:
            request_id = self._request_id()
            payload = codec.encode_list_request(
                request_id,
                path,
                start_index=start_index,
                max_entries=min(DEVICE_FS_LIST_PAGE_ENTRIES, FILESYSTEM_RPC_MAX_LIST_ENTRIES),
            )
            response = self._rpc(payload, FsMessageId.LIST_RESPONSE)
            if isinstance(response, Err):
                return response
            try:
                decoded = codec.decode_list_response(response.value)
            except codec.FsCodecError as exc:
                return Err(DeviceFsError("codec_error", str(exc)))
            checked = self._checked_request(decoded.request_id, request_id, decoded)
            if isinstance(checked, Err):
                return checked
            if decoded.status != FsStatus.OK:
                return Err(_status_error("list", path, decoded.status))

            entries.extend(decoded.entries)
            if not decoded.has_more:
                return Ok(tuple(entries))
            start_index += len(decoded.entries)
            if not decoded.entries:
                return Err(
                    DeviceFsError(
                        "invalid_state",
                        "filesystem list response has_more without entries",
                    )
                )

    def read_file(self, path: str) -> Result[bytes, DeviceFsError]:
        stat = self.stat(path)
        if isinstance(stat, Err):
            return stat
        if stat.value.status != FsStatus.OK:
            return Err(_status_error("stat", path, stat.value.status))
        if stat.value.file_type != FsFileType.FILE:
            return Err(DeviceFsError("not_file", f"remote path is not a file: {path}"))

        offset = 0
        chunks: list[bytes] = []
        while offset < stat.value.size_bytes:
            request_id = self._request_id()
            size = min(FILESYSTEM_RPC_MAX_CHUNK_SIZE, stat.value.size_bytes - offset)
            payload = codec.encode_read_request(request_id, path, offset=offset, size=size)
            response = self._rpc(payload, FsMessageId.READ_RESPONSE)
            if isinstance(response, Err):
                return response
            try:
                decoded = codec.decode_read_response(response.value)
            except codec.FsCodecError as exc:
                return Err(DeviceFsError("codec_error", str(exc)))
            checked = self._checked_request(decoded.request_id, request_id, decoded)
            if isinstance(checked, Err):
                return checked
            if decoded.status != FsStatus.OK:
                return Err(_status_error("read", path, decoded.status))
            if decoded.offset != offset:
                return Err(
                    DeviceFsError(
                        "invalid_state",
                        f"read response offset mismatch: expected {offset}, got {decoded.offset}",
                    )
                )
            if not decoded.data and offset < stat.value.size_bytes:
                return Err(DeviceFsError("invalid_state", "read returned no data before EOF"))
            chunks.append(decoded.data)
            offset += len(decoded.data)

        return Ok(b"".join(chunks))

    def write_file(self, path: str, data: bytes) -> Result[None, DeviceFsError]:
        if not data:
            return Err(DeviceFsError("invalid_input", "zero-byte writes are not supported yet"))

        session_id = self._request_id()
        begin_id = self._request_id()
        begin = codec.encode_write_begin_request(
            begin_id,
            session_id,
            path,
            expected_size=len(data),
        )
        begin_response = self._write_rpc(begin, FsMessageId.WRITE_BEGIN_RESPONSE, begin_id)
        if isinstance(begin_response, Err):
            return begin_response
        if begin_response.value.status != FsStatus.OK:
            return Err(_status_error("write-begin", path, begin_response.value.status))

        offset = 0
        while offset < len(data):
            chunk = data[offset : offset + FILESYSTEM_RPC_MAX_CHUNK_SIZE]
            chunk_id = self._request_id()
            payload = codec.encode_write_chunk_request(
                chunk_id,
                session_id,
                offset=offset,
                data=chunk,
            )
            chunk_response = self._write_rpc(payload, FsMessageId.WRITE_CHUNK_RESPONSE, chunk_id)
            if isinstance(chunk_response, Err):
                self.abort_write(session_id)
                return chunk_response
            if chunk_response.value.status != FsStatus.OK:
                self.abort_write(session_id)
                return Err(_status_error("write-chunk", path, chunk_response.value.status))
            if chunk_response.value.bytes_written != len(chunk):
                self.abort_write(session_id)
                return Err(
                    DeviceFsError(
                        "invalid_state",
                        "write chunk response byte count mismatch",
                    )
                )
            offset += len(chunk)

        commit_id = self._request_id()
        commit = codec.encode_write_commit_request(commit_id, session_id)
        commit_response = self._write_rpc(commit, FsMessageId.WRITE_COMMIT_RESPONSE, commit_id)
        if isinstance(commit_response, Err):
            return commit_response
        if commit_response.value.status != FsStatus.OK:
            return Err(_status_error("write-commit", path, commit_response.value.status))
        return Ok(None)

    def abort_write(self, session_id: int) -> Result[None, DeviceFsError]:
        request_id = self._request_id()
        payload = codec.encode_write_abort_request(request_id, session_id)
        response = self._write_rpc(payload, FsMessageId.WRITE_ABORT_RESPONSE, request_id)
        if isinstance(response, Err):
            return response
        return Ok(None)

    def pull(self, remote_path: str, local_path: Path) -> Result[DeviceFsPullResult, DeviceFsError]:
        data = self.read_file(remote_path)
        if isinstance(data, Err):
            return data
        try:
            local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_bytes(data.value)
        except OSError as exc:
            return Err(DeviceFsError("local_io", f"failed to write {local_path}: {exc}"))
        return Ok(DeviceFsPullResult(remote_path, local_path, len(data.value)))

    def push(self, local_path: Path, remote_path: str) -> Result[DeviceFsPushResult, DeviceFsError]:
        try:
            data = local_path.read_bytes()
        except OSError as exc:
            return Err(DeviceFsError("local_io", f"failed to read {local_path}: {exc}"))
        write = self.write_file(remote_path, data)
        if isinstance(write, Err):
            return write
        return Ok(DeviceFsPushResult(local_path, remote_path, len(data)))

    def _write_rpc(
        self,
        payload: bytes,
        expected: FsMessageId,
        request_id: int,
    ) -> Result[FsWriteResponse, DeviceFsError]:
        response = self._rpc(payload, expected)
        if isinstance(response, Err):
            return response
        try:
            decoded = codec.decode_write_response(response.value)
        except codec.FsCodecError as exc:
            return Err(DeviceFsError("codec_error", str(exc)))
        return self._checked_request(decoded.request_id, request_id, decoded)

    def _rpc(self, payload: bytes, expected: FsMessageId) -> Result[bytes, DeviceFsError]:
        return self._bridge.controller_rpc(
            payload,
            expected_response_id=expected,
            timeout_ms=DEFAULT_RPC_TIMEOUT_MS,
        )

    def _request_id(self) -> int:
        value = self._next_request_id
        self._next_request_id += 1
        if self._next_request_id > 0xFFFF:
            self._next_request_id = 1
        return value

    def _checked_request[T](
        self,
        actual: int,
        expected: int,
        value: T,
    ) -> Result[T, DeviceFsError]:
        if actual != expected:
            return Err(
                DeviceFsError(
                    "invalid_state",
                    f"request id mismatch: expected {expected}, got {actual}",
                )
            )
        return Ok(value)


def normalize_remote_path(path: str) -> str:
    value = path.strip()
    if value in ("", "/"):
        return "/"
    return value.replace("\\", "/")


def _status_error(action: str, path: str, status: FsStatus) -> DeviceFsError:
    return DeviceFsError(
        "remote_status",
        f"{action} failed for {path}: {codec.status_label(status)}",
    )
