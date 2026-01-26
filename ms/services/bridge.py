from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ms.core.config import Config
from ms.core.errors import ErrorCode
from ms.core.result import Err, Ok, Result
from ms.core.workspace import Workspace
from ms.output.console import ConsoleProtocol, Style
from ms.platform.detection import PlatformInfo
from ms.platform.process import run_silent

# -----------------------------------------------------------------------------
# Error Types
# -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BridgeError:
    """Error from bridge operations."""

    kind: Literal["dir_missing", "cargo_missing", "linker_missing", "build_failed", "binary_missing"]
    message: str
    hint: str | None = None


def _get_linker_hint(platform: PlatformInfo) -> str:
    """Get platform-specific hint for installing C linker."""
    from ms.platform.detection import LinuxDistro, Platform

    if platform.platform == Platform.WINDOWS:
        return "Install Build Tools: https://visualstudio.microsoft.com/visual-cpp-build-tools/"
    if platform.platform == Platform.MACOS:
        return "Run: xcode-select --install"
    # Linux - check distro
    if platform.distro == LinuxDistro.FEDORA:
        return "Run: sudo dnf install gcc"
    if platform.distro == LinuxDistro.ARCH:
        return "Run: sudo pacman -S base-devel"
    # Default to Debian/Ubuntu
    return "Run: sudo apt install build-essential"


def _has_c_linker() -> bool:
    """Check if a C compiler/linker is available."""
    return shutil.which("cc") is not None or shutil.which("gcc") is not None


class BridgeService:
    def __init__(
        self,
        *,
        workspace: Workspace,
        platform: PlatformInfo,
        config: Config | None,
        console: ConsoleProtocol,
    ) -> None:
        self._workspace = workspace
        self._platform = platform
        self._config = config
        self._console = console

    def build(
        self, *, release: bool = True, dry_run: bool = False
    ) -> Result[Path, BridgeError]:
        bridge_dir = self._bridge_dir()
        if not bridge_dir.is_dir():
            return Err(
                BridgeError(
                    kind="dir_missing",
                    message=f"bridge dir missing: {bridge_dir}",
                    hint="Run: uv run ms repos sync",
                )
            )

        if shutil.which("cargo") is None:
            return Err(
                BridgeError(
                    kind="cargo_missing",
                    message="cargo: missing",
                    hint="Install rustup: https://rustup.rs",
                )
            )

        # Rust needs a C linker (cc/gcc) to link binaries
        if not _has_c_linker():
            return Err(
                BridgeError(
                    kind="linker_missing",
                    message="C linker (cc/gcc): missing",
                    hint=_get_linker_hint(self._platform),
                )
            )

        cmd = ["cargo", "build"]
        if release:
            cmd.append("--release")

        self._console.print(" ".join(cmd), Style.DIM)
        dst = self._installed_bridge_bin()
        if dry_run:
            self._console.print(f"would install bridge -> {dst}", Style.DIM)
            return Ok(dst)

        result = run_silent(cmd, cwd=bridge_dir)
        if isinstance(result, Err):
            return Err(
                BridgeError(kind="build_failed", message="bridge build failed")
            )

        built = self._built_bridge_bin(bridge_dir, release=release)
        if not built.exists():
            return Err(
                BridgeError(
                    kind="binary_missing",
                    message=f"bridge binary missing: {built}",
                )
            )

        self._console.print(f"install bridge -> {dst}", Style.DIM)

        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(built, dst)
        if self._platform.platform.is_unix:
            dst.chmod(0o755)

        src_config = bridge_dir / "config"
        if src_config.is_dir():
            shutil.copytree(src_config, dst.parent / "config", dirs_exist_ok=True)

        self._console.success(str(dst))
        return Ok(dst)

    def run(self, *, args: list[str]) -> int:
        exe = self._installed_bridge_bin()
        if not exe.exists():
            # Fall back to build output.
            bridge_dir = self._bridge_dir()
            exe = self._built_bridge_bin(bridge_dir, release=True)

        if not exe.exists():
            self._console.error(f"oc-bridge not found: {exe}")
            self._console.print("hint: Run: uv run ms bridge build", Style.DIM)
            return int(ErrorCode.ENV_ERROR)

        cmd = [str(exe), *args]
        self._console.print(" ".join(cmd), Style.DIM)
        result = run_silent(cmd, cwd=self._workspace.root)
        match result:
            case Ok(_):
                return 0
            case Err(e):
                return e.returncode

    def _bridge_dir(self) -> Path:
        rel = self._config.paths.bridge if self._config is not None else "open-control/bridge"
        return self._workspace.root / rel

    def _built_bridge_bin(self, bridge_dir: Path, *, release: bool) -> Path:
        profile = "release" if release else "debug"
        exe_name = self._platform.platform.exe_name("oc-bridge")
        return bridge_dir / "target" / profile / exe_name

    def _installed_bridge_bin(self) -> Path:
        exe_name = self._platform.platform.exe_name("oc-bridge")
        return self._workspace.bin_dir / "bridge" / exe_name

    def is_installed(self) -> bool:
        """Check if bridge binary is installed."""
        return self._installed_bridge_bin().exists()
