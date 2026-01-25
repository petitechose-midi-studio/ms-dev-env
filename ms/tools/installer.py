"""Archive extraction and installation.

This module provides an Installer class that:
- Extracts tar.gz, tar.xz, and zip archives
- Supports strip_components (removing leading path components)
- Handles file permissions on Unix
"""

from __future__ import annotations

import shutil
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

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

            files_count = 0

            # Open archive based on compression type
            if compression == "gz":
                tar = tarfile.open(archive, "r:gz")
            else:
                tar = tarfile.open(archive, "r:xz")

            try:
                for member in tar.getmembers():
                    # Skip directories at root level
                    if member.isdir() and "/" not in member.name:
                        continue

                    # Strip leading path components
                    parts = Path(member.name).parts
                    if len(parts) <= strip_components:
                        continue

                    new_path = Path(*parts[strip_components:])
                    member.name = str(new_path)

                    # Security check: prevent path traversal
                    full_path = install_dir / new_path
                    if not str(full_path.resolve()).startswith(str(install_dir.resolve())):
                        continue

                    tar.extract(member, install_dir, filter="data")
                    files_count += 1
            finally:
                tar.close()

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

            files_count = 0

            with zipfile.ZipFile(archive, "r") as zf:
                for info in zf.infolist():
                    # Skip directories
                    if info.is_dir():
                        continue

                    # Strip leading path components
                    parts = Path(info.filename).parts
                    if len(parts) <= strip_components:
                        continue

                    new_path = Path(*parts[strip_components:])

                    # Security check: prevent path traversal
                    full_path = install_dir / new_path
                    if not str(full_path.resolve()).startswith(str(install_dir.resolve())):
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
