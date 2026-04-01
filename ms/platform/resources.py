from __future__ import annotations

import ctypes
import os

_GIB = 1024**3


def logical_cpu_count() -> int:
    return max(1, os.cpu_count() or 1)


def available_physical_memory_bytes() -> int | None:
    if os.name == "nt":
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MEMORYSTATUSEX()
        status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return int(status.ullAvailPhys)
        return None

    try:
        page_size = os.sysconf("SC_PAGE_SIZE")
        avail_pages = os.sysconf("SC_AVPHYS_PAGES")
        if isinstance(page_size, int) and isinstance(avail_pages, int):
            return page_size * avail_pages
    except (AttributeError, ValueError, OSError):
        return None

    return None


def recommended_parallel_jobs(
    *,
    cpu_divisor: int = 2,
    safe_cap: int = 32,
    reserved_memory_gib: int = 6,
    gib_per_job: int = 4,
    fallback_jobs: int = 4,
) -> int:
    logical_cores = logical_cpu_count()
    cpu_budget = max(1, logical_cores // max(1, cpu_divisor))
    jobs = min(safe_cap, cpu_budget)

    available_memory = available_physical_memory_bytes()
    if available_memory is None:
        return max(1, fallback_jobs if logical_cores <= 0 else jobs)

    usable_memory = max(0, available_memory - (reserved_memory_gib * _GIB))
    memory_budget = max(1, usable_memory // max(1, gib_per_job * _GIB))
    return max(1, min(jobs, int(memory_budget), safe_cap))
