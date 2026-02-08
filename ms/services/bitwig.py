from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ms.core.result import Err, Ok, Result
from ms.output.console import Style
from ms.platform.detection import Platform
from ms.platform.paths import home
from ms.platform.process import run_silent
from ms.services.base import BaseService

_MAVEN_BUILD_TIMEOUT_SECONDS = 30 * 60.0

# -----------------------------------------------------------------------------
# Error Types
# -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BitwigError:
    """Error from Bitwig extension operations."""

    kind: Literal[
        "host_missing",
        "maven_missing",
        "build_failed",
        "extension_not_found",
        "dir_not_configured",
    ]
    message: str
    hint: str | None = None


class BitwigService(BaseService):
    """Service for building and deploying Bitwig extensions."""

    def build(self, *, dry_run: bool = False) -> Result[Path, BitwigError]:
        host_dir = self._host_dir()
        if not (host_dir / "pom.xml").exists():
            return Err(
                BitwigError(
                    kind="host_missing",
                    message=f"bitwig host missing: {host_dir}",
                    hint="Run: uv run ms sync --repos",
                )
            )

        mvn = self._mvn_path()
        if mvn is None:
            return Err(
                BitwigError(
                    kind="maven_missing",
                    message="maven: missing",
                    hint="Run: uv run ms sync --tools",
                )
            )

        env = self._build_env()
        cmd = [
            str(mvn),
            "package",
            "-Pmanual",
            "-Dmaven.compiler.release=21",
        ]
        self._console.print(" ".join(cmd), Style.DIM)
        if dry_run:
            built = host_dir / "target" / "midi_studio.bwextension"
            return Ok(built)

        result = run_silent(cmd, cwd=host_dir, env=env, timeout=_MAVEN_BUILD_TIMEOUT_SECONDS)
        if isinstance(result, Err):
            return Err(BitwigError(kind="build_failed", message="maven build failed"))

        built = host_dir / "target" / "midi_studio.bwextension"
        if not built.exists():
            return Err(
                BitwigError(
                    kind="extension_not_found",
                    message=f"extension not found: {built}",
                )
            )

        self._copy_to_bin(built)
        self._console.success(str(built))
        return Ok(built)

    def deploy(
        self, *, extensions_dir: Path | None = None, dry_run: bool = False
    ) -> Result[Path, BitwigError]:
        host_dir = self._host_dir()
        if not (host_dir / "pom.xml").exists():
            return Err(
                BitwigError(
                    kind="host_missing",
                    message=f"bitwig host missing: {host_dir}",
                    hint="Run: uv run ms sync --repos",
                )
            )

        mvn = self._mvn_path()
        if mvn is None:
            return Err(
                BitwigError(
                    kind="maven_missing",
                    message="maven: missing",
                    hint="Run: uv run ms sync --tools",
                )
            )

        install_dir = extensions_dir or self._resolve_extensions_dir()
        if install_dir is None:
            return Err(
                BitwigError(
                    kind="dir_not_configured",
                    message="bitwig extensions dir not configured",
                )
            )

        self._console.print(f"extensions dir: {install_dir}", Style.DIM)
        if not dry_run:
            install_dir.mkdir(parents=True, exist_ok=True)

        env = self._build_env()
        cmd = [
            str(mvn),
            "package",
            "-Dmaven.compiler.release=21",
            f"-Dbitwig.extensions.dir={install_dir}",
        ]
        self._console.print(" ".join(cmd), Style.DIM)
        if dry_run:
            deployed = install_dir / "midi_studio.bwextension"
            return Ok(deployed)

        result = run_silent(cmd, cwd=host_dir, env=env, timeout=_MAVEN_BUILD_TIMEOUT_SECONDS)
        if isinstance(result, Err):
            return Err(BitwigError(kind="build_failed", message="maven build failed"))

        deployed = install_dir / "midi_studio.bwextension"
        if not deployed.exists():
            # Fallback: find any .bwextension file.
            matches = list(install_dir.glob("*.bwextension"))
            deployed = max(matches, key=lambda p: p.stat().st_mtime) if matches else deployed

        if not deployed.exists():
            return Err(
                BitwigError(
                    kind="extension_not_found",
                    message=f"extension not found: {deployed}",
                )
            )

        self._copy_to_bin(deployed)
        self._console.success(str(deployed))
        return Ok(deployed)

    def _host_dir(self) -> Path:
        rel = (
            self._config.paths.extension
            if self._config is not None
            else "midi-studio/plugin-bitwig/host"
        )
        return self._workspace.root / rel

    def _resolve_extensions_dir(self) -> Path | None:
        platform = self._platform.platform
        platform_key = str(platform)
        configured = self._config.bitwig.as_dict().get(platform_key) if self._config else None

        if configured:
            p = _expand_user_vars(configured)
            if not p.is_absolute():
                p = self._workspace.root / p
            return p

        h = home()
        match platform:
            case Platform.LINUX:
                return _first_existing_or_default(
                    [h / "Bitwig Studio" / "Extensions", h / ".BitwigStudio" / "Extensions"],
                )
            case Platform.MACOS:
                return h / "Documents" / "Bitwig Studio" / "Extensions"
            case Platform.WINDOWS:
                return h / "Documents" / "Bitwig Studio" / "Extensions"
            case _:
                return None

    def _mvn_path(self) -> Path | None:
        mvn = self._registry.get_bin_path("maven")
        if mvn is not None and mvn.exists():
            return mvn
        found = shutil.which("mvn")
        if found:
            return Path(found)
        return None

    def _build_env(self) -> dict[str, str]:
        env = os.environ.copy()
        # Don't inherit MAVEN_OPTS - build uses bundled JDK with known options
        env.pop("MAVEN_OPTS", None)
        env.update(self._registry.get_env_vars())
        return env

    def _copy_to_bin(self, src: Path) -> None:
        dst_dir = self._workspace.bin_dir / "bitwig"
        dst_dir.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(src, dst_dir / src.name)
        except OSError as e:
            self._console.print(f"failed to copy {src.name} to bin: {e}", Style.WARNING)


def _expand_user_vars(value: str) -> Path:
    return Path(os.path.expandvars(value)).expanduser()


def _first_existing_or_default(candidates: list[Path]) -> Path:
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]
