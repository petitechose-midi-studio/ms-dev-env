"""Platform and architecture detection.

This module provides enums and functions for detecting the current operating
system, CPU architecture, and Linux distribution. All detection is done lazily
and cached for performance.
"""

from __future__ import annotations

import os as _os
import platform as _platform
import sys as _sys
from dataclasses import dataclass
from enum import Enum, auto
from functools import lru_cache
from pathlib import Path

__all__ = [
    "Platform",
    "Arch",
    "LinuxDistro",
    "PlatformInfo",
    "detect",
    "detect_arch",
    "detect_linux_distro",
    "detect_platform",
    "is_windows",
    "is_linux",
    "is_macos",
]


class Platform(Enum):
    """Operating system platform."""

    LINUX = auto()
    MACOS = auto()
    WINDOWS = auto()
    UNKNOWN = auto()

    def __str__(self) -> str:
        return self.name.lower()

    @property
    def is_unix(self) -> bool:
        """Check if this is a Unix-like platform (Linux or macOS)."""
        return self in (Platform.LINUX, Platform.MACOS)

    @property
    def exe_suffix(self) -> str:
        """Get executable file suffix for this platform."""
        return ".exe" if self == Platform.WINDOWS else ""

    @property
    def script_suffix(self) -> str:
        """Get shell script suffix for this platform."""
        return ".cmd" if self == Platform.WINDOWS else ".sh"

    def exe_name(self, name: str) -> str:
        """Get executable name with platform-appropriate suffix.

        Example: exe_name("ninja") -> "ninja.exe" on Windows, "ninja" elsewhere.
        """
        return f"{name}{self.exe_suffix}"


class Arch(Enum):
    """CPU architecture."""

    X64 = auto()
    ARM64 = auto()
    UNKNOWN = auto()

    def __str__(self) -> str:
        return self.name.lower()


class LinuxDistro(Enum):
    """Linux distribution family."""

    DEBIAN = auto()  # Debian, Ubuntu, Mint, Pop!_OS, etc.
    FEDORA = auto()  # Fedora, RHEL, CentOS, Rocky, etc.
    ARCH = auto()  # Arch, Manjaro, EndeavourOS, etc.
    SUSE = auto()  # openSUSE, SLES, etc.
    UNKNOWN = auto()

    def __str__(self) -> str:
        return self.name.lower()

    @property
    def package_manager(self) -> str:
        """Get the package manager command for this distro."""
        return {
            LinuxDistro.DEBIAN: "apt",
            LinuxDistro.FEDORA: "dnf",
            LinuxDistro.ARCH: "pacman",
            LinuxDistro.SUSE: "zypper",
            LinuxDistro.UNKNOWN: "unknown",
        }[self]


@dataclass(frozen=True, slots=True)
class PlatformInfo:
    """Complete platform information.

    This is an immutable dataclass containing all detected platform info.
    Use the `detect()` function to get an instance.
    """

    platform: Platform
    arch: Arch
    distro: LinuxDistro

    @property
    def is_windows(self) -> bool:
        return self.platform == Platform.WINDOWS

    @property
    def is_linux(self) -> bool:
        return self.platform == Platform.LINUX

    @property
    def is_macos(self) -> bool:
        return self.platform == Platform.MACOS

    @property
    def is_unix(self) -> bool:
        return self.platform.is_unix

    @property
    def is_x64(self) -> bool:
        return self.arch == Arch.X64

    @property
    def is_arm64(self) -> bool:
        return self.arch == Arch.ARM64

    def __str__(self) -> str:
        if self.platform == Platform.LINUX and self.distro != LinuxDistro.UNKNOWN:
            return f"{self.platform}-{self.distro}-{self.arch}"
        return f"{self.platform}-{self.arch}"


@lru_cache(maxsize=1)
def detect_platform() -> Platform:
    """Detect the current operating system (cached)."""
    # NOTE: avoid platform.system() on Windows.
    # Python's platform.system() may query WMI (slow/hangs on some machines).
    system = _sys.platform.lower()
    if system.startswith("linux"):
        return Platform.LINUX
    if system.startswith("darwin"):
        return Platform.MACOS
    if system.startswith(("win32", "cygwin", "msys")):
        return Platform.WINDOWS
    return Platform.UNKNOWN


@lru_cache(maxsize=1)
def detect_arch() -> Arch:
    """Detect the current CPU architecture (cached)."""
    # NOTE: avoid platform.machine() on Windows.
    # Python's platform.machine() may call platform.uname() which may query WMI
    # (slow/hangs on some machines).
    if detect_platform() == Platform.WINDOWS:
        env_arch = (
            _os.environ.get("PROCESSOR_ARCHITEW6432")
            or _os.environ.get("PROCESSOR_ARCHITECTURE")
            or ""
        )
        machine = env_arch.lower()
    else:
        machine = _platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        return Arch.X64
    if machine in ("aarch64", "arm64"):
        return Arch.ARM64
    return Arch.UNKNOWN


def _read_os_release() -> str | None:
    """Read /etc/os-release if available."""
    try:
        return Path("/etc/os-release").read_text().lower()
    except (FileNotFoundError, PermissionError, OSError):
        return None


@lru_cache(maxsize=1)
def detect_linux_distro() -> LinuxDistro:
    """Detect Linux distribution family (cached).

    Returns LinuxDistro.UNKNOWN if:
    - Not running on Linux
    - /etc/os-release is not readable
    - Distribution is not recognized
    """
    if detect_platform() != Platform.LINUX:
        return LinuxDistro.UNKNOWN

    content = _read_os_release()
    if content is None:
        return LinuxDistro.UNKNOWN

    # Check for distro families (order matters for some edge cases)
    if any(x in content for x in ("fedora", "rhel", "centos", "rocky", "almalinux")):
        return LinuxDistro.FEDORA
    if any(x in content for x in ("ubuntu", "debian", "mint", "pop")):
        return LinuxDistro.DEBIAN
    if any(x in content for x in ("arch", "manjaro", "endeavour")):
        return LinuxDistro.ARCH
    if any(x in content for x in ("opensuse", "suse", "sles")):
        return LinuxDistro.SUSE

    return LinuxDistro.UNKNOWN


@lru_cache(maxsize=1)
def detect() -> PlatformInfo:
    """Detect complete platform information (cached).

    Returns a PlatformInfo dataclass with platform, architecture, and
    Linux distribution (if applicable).
    """
    return PlatformInfo(
        platform=detect_platform(),
        arch=detect_arch(),
        distro=detect_linux_distro(),
    )


def is_windows() -> bool:
    """Check if running on Windows."""
    return detect_platform() == Platform.WINDOWS


def is_linux() -> bool:
    """Check if running on Linux."""
    return detect_platform() == Platform.LINUX


def is_macos() -> bool:
    """Check if running on macOS."""
    return detect_platform() == Platform.MACOS
