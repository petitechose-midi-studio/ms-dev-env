"""Archive extraction and installation.

This module provides an Installer class that:
- Extracts tar.gz, tar.xz, and zip archives
- Supports strip_components (removing leading path components)
- Handles file permissions on Unix
"""

from __future__ import annotations

import contextlib
import os
import shutil
import stat
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from ms.core.result import Err, Ok, Result

__all__ = ["Installer", "InstallResult", "InstallError"]


@dataclass(frozen=True, slots=True)
class InstallError:
    """Installation error details.

    Attributes:
        archive: Path to the archive that failed
        message: Human-readable error message
    """

    archive: Path
    message: str

    def __str__(self) -> str:
        return f"{self.message}: {self.archive}"


@dataclass(frozen=True, slots=True)
class InstallResult:
    """Result of an installation operation.

    Attributes:
        install_dir: Path to the installation directory
        files_count: Number of files extracted
    """

    install_dir: Path
    files_count: int


class Installer:
    """Archive extractor for tool installation.

    Supports:
    - .tar.gz and .tgz archives
    - .tar.xz and .txz archives
    - .zip archives

    Usage:
        installer = Installer()
        result = installer.install(archive_path, install_dir, strip_components=1)
        if is_ok(result):
            print(f"Installed {result.value.files_count} files")
    """

    def install(
        self,
        archive: Path,
        install_dir: Path,
        *,
        strip_components: int = 0,
    ) -> Result[InstallResult, InstallError]:
        """Extract archive to installation directory.

        Args:
            archive: Path to archive file
            install_dir: Directory to extract to
            strip_components: Number of leading path components to remove

        Returns:
            Ok with InstallResult, or Err with InstallError
        """
        if not archive.exists():
            return Err(InstallError(archive=archive, message="Archive not found"))

        name = archive.name.lower()

        # Determine archive type.
        # NOTE: Path.suffixes is not reliable for names like "cmake-4.2.2-...zip"
        # because it splits on every dot and produces misleading composite suffixes.
        if name.endswith((".tar.gz", ".tgz")):
            return self._extract_tar(archive, install_dir, strip_components, "gz")
        elif name.endswith((".tar.xz", ".txz")):
            return self._extract_tar(archive, install_dir, strip_components, "xz")
        elif name.endswith(".zip"):
            return self._extract_zip(archive, install_dir, strip_components)
        else:
            return Err(
                InstallError(
                    archive=archive, message=f"Unsupported archive format: {archive.suffix}"
                )
            )

    def _safe_relative_path(self, member_name: str, strip_components: int) -> Path | None:
        """Return a sanitized relative extraction path, or None if unsafe."""
        normalized = member_name.replace("\\", "/")
        if normalized.startswith("/"):
            return None

        posix = PurePosixPath(normalized)
        parts = posix.parts
        if len(parts) <= strip_components:
            return None

        kept = parts[strip_components:]
        if not kept:
            return None
        if any(part in {"", ".", ".."} for part in kept):
            return None
        if kept[0].endswith(":"):
            return None

        return Path(*kept)

    def _is_within_root(self, root: Path, target: Path) -> bool:
        """Check whether target resolves under root."""
        try:
            return target.resolve().is_relative_to(root.resolve())
        except OSError:
            return False

    def _extract_tar(
        self,
        archive: Path,
        install_dir: Path,
        strip_components: int,
        compression: str,
    ) -> Result[InstallResult, InstallError]:
        """Extract tar archive.

        Args:
            archive: Path to archive
            install_dir: Destination directory
            strip_components: Path components to strip
            compression: Compression type ('gz' or 'xz')

        Returns:
            Ok with InstallResult, or Err with InstallError
        """
        try:
            # Clean up existing installation
            if install_dir.exists():
                shutil.rmtree(install_dir)
            install_dir.mkdir(parents=True, exist_ok=True)
            install_root = install_dir.resolve()

            files_count = 0

            mode = "r:gz" if compression == "gz" else "r:xz"
            with tarfile.open(archive, mode) as tar:
                for member in tar.getmembers():
                    # Skip directories and non-regular entries (symlink, hardlink, device, fifo)
                    if member.isdir() or not member.isreg():
                        continue

                    rel_path = self._safe_relative_path(member.name, strip_components)
                    if rel_path is None:
                        continue

                    full_path = install_dir / rel_path
                    if not self._is_within_root(install_root, full_path):
                        continue

                    src = tar.extractfile(member)
                    if src is None:
                        continue

                    full_path.parent.mkdir(parents=True, exist_ok=True)
                    with src, open(full_path, "wb") as dst:
                        shutil.copyfileobj(src, dst)

                    mode = member.mode & 0o777
                    if mode:
                        with contextlib.suppress(OSError):
                            os.chmod(full_path, mode)

                    files_count += 1

            return Ok(InstallResult(install_dir=install_dir, files_count=files_count))

        except tarfile.TarError as e:
            return Err(InstallError(archive=archive, message=f"Tar extraction failed: {e}"))
        except OSError as e:
            return Err(InstallError(archive=archive, message=f"IO error: {e}"))

    def _extract_zip(
        self,
        archive: Path,
        install_dir: Path,
        strip_components: int,
    ) -> Result[InstallResult, InstallError]:
        """Extract zip archive.

        Args:
            archive: Path to archive
            install_dir: Destination directory
            strip_components: Path components to strip

        Returns:
            Ok with InstallResult, or Err with InstallError
        """
        try:
            # Clean up existing installation
            if install_dir.exists():
                shutil.rmtree(install_dir)
            install_dir.mkdir(parents=True, exist_ok=True)
            install_root = install_dir.resolve()

            files_count = 0

            with zipfile.ZipFile(archive, "r") as zf:
                for info in zf.infolist():
                    # Skip directories
                    if info.is_dir():
                        continue

                    rel_path = self._safe_relative_path(info.filename, strip_components)
                    if rel_path is None:
                        continue

                    # Skip symlinks in zip archives
                    file_type_bits = (info.external_attr >> 16) & 0o170000
                    if file_type_bits == stat.S_IFLNK:
                        continue

                    full_path = install_dir / rel_path
                    if not self._is_within_root(install_root, full_path):
                        continue

                    # Create parent directories
                    full_path.parent.mkdir(parents=True, exist_ok=True)

                    # Extract file
                    with zf.open(info) as src, open(full_path, "wb") as dst:
                        shutil.copyfileobj(src, dst)

                    # Preserve Unix permissions if available
                    unix_attrs = info.external_attr >> 16
                    if unix_attrs:
                        full_path.chmod(unix_attrs)

                    files_count += 1

            return Ok(InstallResult(install_dir=install_dir, files_count=files_count))

        except zipfile.BadZipFile as e:
            return Err(InstallError(archive=archive, message=f"Invalid zip file: {e}"))
        except OSError as e:
            return Err(InstallError(archive=archive, message=f"IO error: {e}"))

    def cleanup(self, install_dir: Path) -> bool:
        """Remove installation directory.

        Args:
            install_dir: Directory to remove

        Returns:
            True if removed, False if didn't exist
        """
        if install_dir.exists():
            shutil.rmtree(install_dir)
            return True
        return False
