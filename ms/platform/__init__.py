"""Platform abstraction layer."""

from .detection import (
    Arch,
    LinuxDistro,
    Platform,
    PlatformInfo,
    detect,
    detect_linux_distro,
    is_linux,
    is_macos,
    is_windows,
)
from .paths import (
    home,
    user_config_dir,
)

__all__ = [
    # detection
    "Arch",
    "LinuxDistro",
    "Platform",
    "PlatformInfo",
    "detect",
    "detect_linux_distro",
    "is_linux",
    "is_macos",
    "is_windows",
    # paths
    "home",
    "user_config_dir",
]
