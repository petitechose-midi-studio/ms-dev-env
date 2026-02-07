"""Tests for tools/installer.py - Archive extraction."""

import io
import tarfile
import zipfile
from pathlib import Path

from ms.core.result import Err, Ok
from ms.tools.installer import Installer, InstallError, InstallResult

# =============================================================================
# Test fixtures for creating archives
# =============================================================================


def create_tar_gz(path: Path, files: dict[str, bytes], *, prefix: str = "") -> None:
    """Create a .tar.gz archive with the given files.

    Args:
        path: Path to create archive at
        files: Dict of filename -> content
        prefix: Optional directory prefix for all files
    """
    with tarfile.open(path, "w:gz") as tar:
        for name, content in files.items():
            full_name = f"{prefix}/{name}" if prefix else name
            info = tarfile.TarInfo(name=full_name)
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))


def create_tar_xz(path: Path, files: dict[str, bytes], *, prefix: str = "") -> None:
    """Create a .tar.xz archive with the given files."""
    with tarfile.open(path, "w:xz") as tar:
        for name, content in files.items():
            full_name = f"{prefix}/{name}" if prefix else name
            info = tarfile.TarInfo(name=full_name)
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))


def create_zip(path: Path, files: dict[str, bytes], *, prefix: str = "") -> None:
    """Create a .zip archive with the given files."""
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in files.items():
            full_name = f"{prefix}/{name}" if prefix else name
            zf.writestr(full_name, content)


# =============================================================================
# InstallError tests
# =============================================================================


class TestInstallError:
    """Tests for InstallError dataclass."""

    def test_create(self) -> None:
        """Create InstallError."""
        error = InstallError(archive=Path("/path/to/file.zip"), message="Bad archive")
        assert error.archive == Path("/path/to/file.zip")
        assert error.message == "Bad archive"

    def test_str(self) -> None:
        """String representation."""
        error = InstallError(archive=Path("/path/file.zip"), message="Extraction failed")
        # Path separator varies by OS
        assert "Extraction failed:" in str(error)
        assert "file.zip" in str(error)


class TestInstallResult:
    """Tests for InstallResult dataclass."""

    def test_create(self) -> None:
        """Create InstallResult."""
        result = InstallResult(install_dir=Path("/opt/tool"), files_count=5)
        assert result.install_dir == Path("/opt/tool")
        assert result.files_count == 5


# =============================================================================
# Installer tests - tar.gz
# =============================================================================


class TestInstallerTarGz:
    """Tests for .tar.gz extraction."""

    def test_extract_simple(self, tmp_path: Path) -> None:
        """Extract simple tar.gz archive."""
        archive = tmp_path / "test.tar.gz"
        create_tar_gz(archive, {"file1.txt": b"content1", "file2.txt": b"content2"})

        installer = Installer()
        install_dir = tmp_path / "install"
        result = installer.install(archive, install_dir)

        assert isinstance(result, Ok)
        assert result.value.install_dir == install_dir
        assert result.value.files_count == 2
        assert (install_dir / "file1.txt").read_bytes() == b"content1"
        assert (install_dir / "file2.txt").read_bytes() == b"content2"

    def test_extract_with_strip_components(self, tmp_path: Path) -> None:
        """Extract with strip_components=1."""
        archive = tmp_path / "test.tar.gz"
        create_tar_gz(
            archive,
            {"bin/tool": b"binary", "lib/lib.so": b"library"},
            prefix="tool-1.0.0",
        )

        installer = Installer()
        install_dir = tmp_path / "install"
        result = installer.install(archive, install_dir, strip_components=1)

        assert isinstance(result, Ok)
        assert (install_dir / "bin" / "tool").read_bytes() == b"binary"
        assert (install_dir / "lib" / "lib.so").read_bytes() == b"library"

    def test_extract_nested_directories(self, tmp_path: Path) -> None:
        """Extract archive with nested directories."""
        archive = tmp_path / "test.tar.gz"
        create_tar_gz(archive, {"a/b/c/deep.txt": b"deep content"})

        installer = Installer()
        install_dir = tmp_path / "install"
        result = installer.install(archive, install_dir)

        assert isinstance(result, Ok)
        assert (install_dir / "a" / "b" / "c" / "deep.txt").read_bytes() == b"deep content"


# =============================================================================
# Installer tests - tar.xz
# =============================================================================


class TestInstallerTarXz:
    """Tests for .tar.xz extraction."""

    def test_extract_simple(self, tmp_path: Path) -> None:
        """Extract simple tar.xz archive."""
        archive = tmp_path / "test.tar.xz"
        create_tar_xz(archive, {"file.txt": b"content"})

        installer = Installer()
        install_dir = tmp_path / "install"
        result = installer.install(archive, install_dir)

        assert isinstance(result, Ok)
        assert (install_dir / "file.txt").read_bytes() == b"content"

    def test_extract_with_strip(self, tmp_path: Path) -> None:
        """Extract tar.xz with strip_components."""
        archive = tmp_path / "test.tar.xz"
        create_tar_xz(archive, {"zig": b"zig binary"}, prefix="zig-0.13.0")

        installer = Installer()
        install_dir = tmp_path / "install"
        result = installer.install(archive, install_dir, strip_components=1)

        assert isinstance(result, Ok)
        assert (install_dir / "zig").read_bytes() == b"zig binary"


# =============================================================================
# Installer tests - zip
# =============================================================================


class TestInstallerZip:
    """Tests for .zip extraction."""

    def test_extract_simple(self, tmp_path: Path) -> None:
        """Extract simple zip archive."""
        archive = tmp_path / "test.zip"
        create_zip(archive, {"ninja": b"ninja binary", "readme.txt": b"readme"})

        installer = Installer()
        install_dir = tmp_path / "install"
        result = installer.install(archive, install_dir)

        assert isinstance(result, Ok)
        assert result.value.files_count == 2
        assert (install_dir / "ninja").read_bytes() == b"ninja binary"
        assert (install_dir / "readme.txt").read_bytes() == b"readme"

    def test_extract_with_strip_components(self, tmp_path: Path) -> None:
        """Extract zip with strip_components."""
        archive = tmp_path / "test.zip"
        create_zip(archive, {"bin/cmake": b"cmake binary"}, prefix="cmake-3.28")

        installer = Installer()
        install_dir = tmp_path / "install"
        result = installer.install(archive, install_dir, strip_components=1)

        assert isinstance(result, Ok)
        assert (install_dir / "bin" / "cmake").read_bytes() == b"cmake binary"

    def test_extract_nested(self, tmp_path: Path) -> None:
        """Extract zip with nested directories."""
        archive = tmp_path / "test.zip"
        create_zip(archive, {"a/b/file.txt": b"nested"})

        installer = Installer()
        install_dir = tmp_path / "install"
        result = installer.install(archive, install_dir)

        assert isinstance(result, Ok)
        assert (install_dir / "a" / "b" / "file.txt").read_bytes() == b"nested"


# =============================================================================
# Installer tests - error handling
# =============================================================================


class TestInstallerErrors:
    """Tests for error handling."""

    def test_archive_not_found(self, tmp_path: Path) -> None:
        """Error when archive doesn't exist."""
        installer = Installer()
        install_dir = tmp_path / "install"
        result = installer.install(tmp_path / "missing.zip", install_dir)

        assert isinstance(result, Err)
        assert "not found" in result.error.message.lower()

    def test_unsupported_format(self, tmp_path: Path) -> None:
        """Error for unsupported archive format."""
        archive = tmp_path / "test.rar"
        archive.write_bytes(b"fake rar content")

        installer = Installer()
        install_dir = tmp_path / "install"
        result = installer.install(archive, install_dir)

        assert isinstance(result, Err)
        assert "unsupported" in result.error.message.lower()

    def test_corrupt_tar_gz(self, tmp_path: Path) -> None:
        """Error for corrupt tar.gz."""
        archive = tmp_path / "corrupt.tar.gz"
        archive.write_bytes(b"not a valid tar.gz")

        installer = Installer()
        install_dir = tmp_path / "install"
        result = installer.install(archive, install_dir)

        assert isinstance(result, Err)

    def test_corrupt_zip(self, tmp_path: Path) -> None:
        """Error for corrupt zip."""
        archive = tmp_path / "corrupt.zip"
        archive.write_bytes(b"not a valid zip")

        installer = Installer()
        install_dir = tmp_path / "install"
        result = installer.install(archive, install_dir)

        assert isinstance(result, Err)


class TestInstallerSecurity:
    """Security hardening tests for archive extraction."""

    def test_zip_blocks_prefix_collision_traversal(self, tmp_path: Path) -> None:
        """Zip member cannot escape install root via ../install-evil path."""
        archive = tmp_path / "evil.zip"
        create_zip(
            archive,
            {
                "../install-evil/pwn.txt": b"bad",
                "ok.txt": b"good",
            },
        )

        installer = Installer()
        install_dir = tmp_path / "install"
        outside = tmp_path / "install-evil" / "pwn.txt"
        result = installer.install(archive, install_dir)

        assert isinstance(result, Ok)
        assert result.value.files_count == 1
        assert (install_dir / "ok.txt").read_bytes() == b"good"
        assert not outside.exists()

    def test_tar_blocks_prefix_collision_traversal(self, tmp_path: Path) -> None:
        """Tar member cannot escape install root via ../install-evil path."""
        archive = tmp_path / "evil.tar.gz"
        create_tar_gz(
            archive,
            {
                "../install-evil/pwn.txt": b"bad",
                "ok.txt": b"good",
            },
        )

        installer = Installer()
        install_dir = tmp_path / "install"
        outside = tmp_path / "install-evil" / "pwn.txt"
        result = installer.install(archive, install_dir)

        assert isinstance(result, Ok)
        assert result.value.files_count == 1
        assert (install_dir / "ok.txt").read_bytes() == b"good"
        assert not outside.exists()

    def test_tar_skips_symlink_entries(self, tmp_path: Path) -> None:
        """Tar symlink entries are ignored."""
        archive = tmp_path / "symlink.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            link = tarfile.TarInfo(name="link-out")
            link.type = tarfile.SYMTYPE
            link.linkname = "../outside.txt"
            tar.addfile(link)

            info = tarfile.TarInfo(name="ok.txt")
            content = b"good"
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))

        installer = Installer()
        install_dir = tmp_path / "install"
        result = installer.install(archive, install_dir)

        assert isinstance(result, Ok)
        assert result.value.files_count == 1
        assert (install_dir / "ok.txt").read_bytes() == b"good"
        assert not (install_dir / "link-out").exists()
        assert not (tmp_path / "outside.txt").exists()


# =============================================================================
# Installer tests - overwrite behavior
# =============================================================================


class TestInstallerOverwrite:
    """Tests for overwrite behavior."""

    def test_overwrites_existing(self, tmp_path: Path) -> None:
        """Existing installation is removed."""
        archive = tmp_path / "test.zip"
        create_zip(archive, {"new_file.txt": b"new content"})

        install_dir = tmp_path / "install"
        install_dir.mkdir()
        (install_dir / "old_file.txt").write_bytes(b"old content")

        installer = Installer()
        result = installer.install(archive, install_dir)

        assert isinstance(result, Ok)
        assert (install_dir / "new_file.txt").exists()
        assert not (install_dir / "old_file.txt").exists()


# =============================================================================
# Installer cleanup tests
# =============================================================================


class TestInstallerCleanup:
    """Tests for cleanup method."""

    def test_cleanup_existing(self, tmp_path: Path) -> None:
        """Cleanup removes existing directory."""
        install_dir = tmp_path / "install"
        install_dir.mkdir()
        (install_dir / "file.txt").write_bytes(b"content")

        installer = Installer()
        result = installer.cleanup(install_dir)

        assert result is True
        assert not install_dir.exists()

    def test_cleanup_nonexistent(self, tmp_path: Path) -> None:
        """Cleanup returns False for nonexistent directory."""
        installer = Installer()
        result = installer.cleanup(tmp_path / "nonexistent")

        assert result is False
