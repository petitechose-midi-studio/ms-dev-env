from __future__ import annotations

import ctypes
import os
from collections.abc import Mapping
from ctypes import wintypes
from dataclasses import dataclass

SAFE_PARALLEL_JOBS = 1
_RELATION_PROCESSOR_CORE = 0
_RELATION_ALL = 0xFFFF
_ERROR_INSUFFICIENT_BUFFER = 122


@dataclass(frozen=True, slots=True)
class ParallelJobSelection:
    jobs: int
    source: str


def logical_cpu_count() -> int:
    return max(1, os.cpu_count() or 1)


def physical_cpu_count() -> int | None:
    if os.name != "nt":
        return None

    class SYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX(ctypes.Structure):
        _fields_ = [
            ("Relationship", wintypes.DWORD),
            ("Size", wintypes.DWORD),
        ]

    kernel32 = ctypes.windll.kernel32
    get_info = kernel32.GetLogicalProcessorInformationEx
    get_info.argtypes = [
        wintypes.DWORD,
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.DWORD),
    ]
    get_info.restype = wintypes.BOOL

    needed = wintypes.DWORD(0)
    get_info(_RELATION_ALL, None, ctypes.byref(needed))
    if ctypes.GetLastError() != _ERROR_INSUFFICIENT_BUFFER or needed.value <= 0:
        return None

    buffer = ctypes.create_string_buffer(needed.value)
    if not get_info(_RELATION_ALL, ctypes.byref(buffer), ctypes.byref(needed)):
        return None

    count = 0
    offset = 0
    while offset < needed.value:
        info = SYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX.from_buffer(buffer, offset)
        if info.Relationship == _RELATION_PROCESSOR_CORE:
            count += 1
        if info.Size <= 0:
            return None
        offset += info.Size

    return max(1, count) if count > 0 else None


def recommended_parallel_jobs(
    *,
    cpu_divisor: int = 2,
    fallback_jobs: int = SAFE_PARALLEL_JOBS,
) -> int:
    physical_cores = physical_cpu_count()
    if physical_cores is None:
        return max(1, fallback_jobs)
    return max(1, physical_cores // max(1, cpu_divisor))


def resolve_parallel_jobs(
    *,
    env: Mapping[str, str] | None = None,
    jobs_env_var: str,
    cpu_divisor: int = 2,
    fallback_jobs: int = SAFE_PARALLEL_JOBS,
) -> ParallelJobSelection:
    env_map = os.environ if env is None else env
    jobs_raw = env_map.get(jobs_env_var)
    if jobs_raw is not None:
        try:
            return ParallelJobSelection(max(1, int(jobs_raw)), "override")
        except ValueError:
            pass

    physical_cores = physical_cpu_count()
    if physical_cores is None:
        return ParallelJobSelection(max(1, fallback_jobs), "safe_fallback")

    return ParallelJobSelection(
        max(1, physical_cores // max(1, cpu_divisor)),
        "physical_auto",
    )


def parallel_jobs_warning(*, selection: ParallelJobSelection, jobs_env_var: str) -> str | None:
    if selection.source == "override":
        return None

    override_hint = (
        f"If RAM pressure hurts build throughput, fine-tune with "
        f"`$env:{jobs_env_var}='<jobs>'` before rerunning."
    )
    if selection.source == "safe_fallback":
        return (
            f"Could not detect physical CPU cores on Windows, falling back to safe "
            f"`-j{selection.jobs}`. {override_hint}"
        )

    return (
        f"Using fastest Windows build concurrency `-j{selection.jobs}` "
        f"(physical cores / 2). {override_hint}"
    )
