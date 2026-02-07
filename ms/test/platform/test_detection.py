"""Tests for ms.platform.detection module."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from ms.platform.detection import (
    Arch,
    LinuxDistro,
    Platform,
    PlatformInfo,
    detect,
    detect_arch,
    detect_linux_distro,
    detect_platform,
    is_linux,
    is_macos,
    is_windows,
)


class TestPlatformEnum:
    """Test Platform enum properties."""

    def test_str_linux(self) -> None:
        assert str(Platform.LINUX) == "linux"

    def test_str_macos(self) -> None:
        assert str(Platform.MACOS) == "macos"

    def test_str_windows(self) -> None:
        assert str(Platform.WINDOWS) == "windows"

    def test_str_unknown(self) -> None:
        assert str(Platform.UNKNOWN) == "unknown"

    def test_is_unix_linux(self) -> None:
        assert Platform.LINUX.is_unix is True

    def test_is_unix_macos(self) -> None:
        assert Platform.MACOS.is_unix is True

    def test_is_unix_windows(self) -> None:
        assert Platform.WINDOWS.is_unix is False

    def test_is_unix_unknown(self) -> None:
        assert Platform.UNKNOWN.is_unix is False

    def test_exe_suffix_windows(self) -> None:
        assert Platform.WINDOWS.exe_suffix == ".exe"

    def test_exe_suffix_linux(self) -> None:
        assert Platform.LINUX.exe_suffix == ""

    def test_exe_suffix_macos(self) -> None:
        assert Platform.MACOS.exe_suffix == ""

    def test_script_suffix_windows(self) -> None:
        assert Platform.WINDOWS.script_suffix == ".cmd"

    def test_script_suffix_linux(self) -> None:
        assert Platform.LINUX.script_suffix == ".sh"

    def test_script_suffix_macos(self) -> None:
        assert Platform.MACOS.script_suffix == ".sh"


class TestArchEnum:
    """Test Arch enum properties."""

    def test_str_x64(self) -> None:
        assert str(Arch.X64) == "x64"

    def test_str_arm64(self) -> None:
        assert str(Arch.ARM64) == "arm64"

    def test_str_unknown(self) -> None:
        assert str(Arch.UNKNOWN) == "unknown"


class TestLinuxDistroEnum:
    """Test LinuxDistro enum properties."""

    def test_str_debian(self) -> None:
        assert str(LinuxDistro.DEBIAN) == "debian"

    def test_str_fedora(self) -> None:
        assert str(LinuxDistro.FEDORA) == "fedora"

    def test_str_arch(self) -> None:
        assert str(LinuxDistro.ARCH) == "arch"

    def test_str_suse(self) -> None:
        assert str(LinuxDistro.SUSE) == "suse"

    def test_package_manager_debian(self) -> None:
        assert LinuxDistro.DEBIAN.package_manager == "apt"

    def test_package_manager_fedora(self) -> None:
        assert LinuxDistro.FEDORA.package_manager == "dnf"

    def test_package_manager_arch(self) -> None:
        assert LinuxDistro.ARCH.package_manager == "pacman"

    def test_package_manager_suse(self) -> None:
        assert LinuxDistro.SUSE.package_manager == "zypper"

    def test_package_manager_unknown(self) -> None:
        assert LinuxDistro.UNKNOWN.package_manager == "unknown"


class TestPlatformInfo:
    """Test PlatformInfo dataclass."""

    def test_frozen(self) -> None:
        """PlatformInfo should be immutable."""
        info = PlatformInfo(Platform.LINUX, Arch.X64, LinuxDistro.DEBIAN)
        with pytest.raises(AttributeError):
            info.platform = Platform.WINDOWS  # type: ignore[misc]

    def test_is_windows(self) -> None:
        info = PlatformInfo(Platform.WINDOWS, Arch.X64, LinuxDistro.UNKNOWN)
        assert info.is_windows is True
        assert info.is_linux is False
        assert info.is_macos is False

    def test_is_linux(self) -> None:
        info = PlatformInfo(Platform.LINUX, Arch.X64, LinuxDistro.DEBIAN)
        assert info.is_linux is True
        assert info.is_windows is False
        assert info.is_macos is False

    def test_is_macos(self) -> None:
        info = PlatformInfo(Platform.MACOS, Arch.ARM64, LinuxDistro.UNKNOWN)
        assert info.is_macos is True
        assert info.is_windows is False
        assert info.is_linux is False

    def test_is_unix(self) -> None:
        linux = PlatformInfo(Platform.LINUX, Arch.X64, LinuxDistro.DEBIAN)
        macos = PlatformInfo(Platform.MACOS, Arch.ARM64, LinuxDistro.UNKNOWN)
        windows = PlatformInfo(Platform.WINDOWS, Arch.X64, LinuxDistro.UNKNOWN)

        assert linux.is_unix is True
        assert macos.is_unix is True
        assert windows.is_unix is False

    def test_is_x64(self) -> None:
        info = PlatformInfo(Platform.LINUX, Arch.X64, LinuxDistro.DEBIAN)
        assert info.is_x64 is True
        assert info.is_arm64 is False

    def test_is_arm64(self) -> None:
        info = PlatformInfo(Platform.MACOS, Arch.ARM64, LinuxDistro.UNKNOWN)
        assert info.is_arm64 is True
        assert info.is_x64 is False

    def test_str_linux_with_distro(self) -> None:
        info = PlatformInfo(Platform.LINUX, Arch.X64, LinuxDistro.DEBIAN)
        assert str(info) == "linux-debian-x64"

    def test_str_linux_unknown_distro(self) -> None:
        info = PlatformInfo(Platform.LINUX, Arch.ARM64, LinuxDistro.UNKNOWN)
        assert str(info) == "linux-arm64"

    def test_str_windows(self) -> None:
        info = PlatformInfo(Platform.WINDOWS, Arch.X64, LinuxDistro.UNKNOWN)
        assert str(info) == "windows-x64"

    def test_str_macos(self) -> None:
        info = PlatformInfo(Platform.MACOS, Arch.ARM64, LinuxDistro.UNKNOWN)
        assert str(info) == "macos-arm64"


class TestPlatformDetection:
    """Test platform detection with mocking."""

    def test_detect_linux(self) -> None:
        with patch("sys.platform", "linux"):
            detect_platform.cache_clear()
            assert detect_platform() == Platform.LINUX

    def test_detect_darwin_as_macos(self) -> None:
        with patch("sys.platform", "darwin"):
            detect_platform.cache_clear()
            assert detect_platform() == Platform.MACOS

    def test_detect_windows(self) -> None:
        with patch("sys.platform", "win32"):
            detect_platform.cache_clear()
            assert detect_platform() == Platform.WINDOWS

    def test_detect_cygwin_as_windows(self) -> None:
        with patch("sys.platform", "cygwin"):
            detect_platform.cache_clear()
            assert detect_platform() == Platform.WINDOWS

    def test_detect_msys_as_windows(self) -> None:
        with patch("sys.platform", "msys"):
            detect_platform.cache_clear()
            assert detect_platform() == Platform.WINDOWS

    def test_detect_unknown(self) -> None:
        with patch("sys.platform", "freebsd"):
            detect_platform.cache_clear()
            assert detect_platform() == Platform.UNKNOWN


class TestArchDetection:
    """Test architecture detection with mocking."""

    def test_detect_x86_64(self) -> None:
        with patch("sys.platform", "linux"), patch("platform.machine", return_value="x86_64"):
            detect_arch.cache_clear()
            assert detect_arch() == Arch.X64

    def test_detect_amd64(self) -> None:
        with patch("sys.platform", "linux"), patch("platform.machine", return_value="AMD64"):
            detect_arch.cache_clear()
            assert detect_arch() == Arch.X64

    def test_detect_aarch64(self) -> None:
        with patch("sys.platform", "linux"), patch("platform.machine", return_value="aarch64"):
            detect_arch.cache_clear()
            assert detect_arch() == Arch.ARM64

    def test_detect_arm64(self) -> None:
        with patch("sys.platform", "linux"), patch("platform.machine", return_value="arm64"):
            detect_arch.cache_clear()
            assert detect_arch() == Arch.ARM64

    def test_detect_unknown_arch(self) -> None:
        with patch("sys.platform", "linux"), patch("platform.machine", return_value="riscv64"):
            detect_arch.cache_clear()
            assert detect_arch() == Arch.UNKNOWN

    def test_windows_env_arch_fallback(self) -> None:
        with (
            patch("sys.platform", "win32"),
            patch.dict(
                "os.environ",
                {"PROCESSOR_ARCHITECTURE": "AMD64"},
                clear=False,
            ),
        ):
            detect_platform.cache_clear()
            detect_arch.cache_clear()
            assert detect_platform() == Platform.WINDOWS
            assert detect_arch() == Arch.X64


class TestLinuxDistroDetection:
    """Test Linux distribution detection."""

    def test_not_linux_returns_unknown(self) -> None:
        with patch("sys.platform", "win32"):
            detect_platform.cache_clear()
            detect_linux_distro.cache_clear()
            assert detect_linux_distro() == LinuxDistro.UNKNOWN

    def test_detect_ubuntu(self) -> None:
        os_release = 'NAME="Ubuntu"\nID=ubuntu\nVERSION_ID="22.04"'
        from ms.platform import detection

        with patch("sys.platform", "linux"):
            detect_platform.cache_clear()
            detect_linux_distro.cache_clear()
            with patch.object(detection, "_read_os_release", return_value=os_release.lower()):
                detect_linux_distro.cache_clear()
                assert detect_linux_distro() == LinuxDistro.DEBIAN

    def test_detect_fedora(self) -> None:
        os_release = 'NAME="Fedora Linux"\nID=fedora\nVERSION_ID="39"'
        from ms.platform import detection

        with patch("sys.platform", "linux"):
            detect_platform.cache_clear()
            with patch.object(detection, "_read_os_release", return_value=os_release.lower()):
                detect_linux_distro.cache_clear()
                assert detect_linux_distro() == LinuxDistro.FEDORA

    def testdetect_arch(self) -> None:
        os_release = 'NAME="Arch Linux"\nID=arch'
        from ms.platform import detection

        with patch("sys.platform", "linux"):
            detect_platform.cache_clear()
            with patch.object(detection, "_read_os_release", return_value=os_release.lower()):
                detect_linux_distro.cache_clear()
                assert detect_linux_distro() == LinuxDistro.ARCH

    def test_detect_opensuse(self) -> None:
        os_release = 'NAME="openSUSE Tumbleweed"\nID=opensuse-tumbleweed'
        from ms.platform import detection

        with patch("sys.platform", "linux"):
            detect_platform.cache_clear()
            with patch.object(detection, "_read_os_release", return_value=os_release.lower()):
                detect_linux_distro.cache_clear()
                assert detect_linux_distro() == LinuxDistro.SUSE

    def test_file_not_found_returns_unknown(self) -> None:
        from ms.platform import detection

        with patch("sys.platform", "linux"):
            detect_platform.cache_clear()
            with patch.object(detection, "_read_os_release", return_value=None):
                detect_linux_distro.cache_clear()
                assert detect_linux_distro() == LinuxDistro.UNKNOWN


class TestConvenienceFunctions:
    """Test convenience functions for current platform."""

    def test_is_windows_on_windows(self) -> None:
        with patch("sys.platform", "win32"):
            detect_platform.cache_clear()
            assert is_windows() is True
            assert is_linux() is False
            assert is_macos() is False

    def test_is_linux_on_linux(self) -> None:
        with patch("sys.platform", "linux"):
            detect_platform.cache_clear()
            assert is_linux() is True
            assert is_windows() is False
            assert is_macos() is False

    def test_is_macos_on_macos(self) -> None:
        with patch("sys.platform", "darwin"):
            detect_platform.cache_clear()
            assert is_macos() is True
            assert is_windows() is False
            assert is_linux() is False


class TestDetectFunction:
    """Test the main detect() function."""

    def test_returns_platform_info(self) -> None:
        info = detect()
        assert isinstance(info, PlatformInfo)

    def test_detect_is_cached(self) -> None:
        """Calling detect() multiple times returns same object."""
        detect.cache_clear()
        info1 = detect()
        info2 = detect()
        assert info1 is info2

    def test_current_platform_is_known(self) -> None:
        """We should detect the current platform correctly."""
        # Clear all caches to get fresh detection
        detect_platform.cache_clear()
        detect_arch.cache_clear()
        detect_linux_distro.cache_clear()
        detect.cache_clear()

        info = detect()
        # At minimum, platform should not be UNKNOWN on any CI
        assert info.platform != Platform.UNKNOWN
        # Arch can be unknown on exotic platforms, but x64/arm64 should work
        # We only assert platform is known since that's most critical
