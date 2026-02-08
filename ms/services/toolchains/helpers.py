from __future__ import annotations

import sys
from pathlib import Path

from ms.core.result import Err, Ok
from ms.output.console import Style
from ms.platform.process import run as run_process
from ms.platform.process import run_silent
from ms.tools.download import Downloader
from ms.tools.http import RealHttpClient
from ms.tools.installer import Installer
from ms.tools.pins import ToolPins
from ms.tools.state import get_installed_version, set_installed_version
from ms.tools.wrapper import (
    WrapperGenerator,
    WrapperSpec,
    create_emscripten_wrappers,
    create_zig_wrappers,
)

from ._context import ToolchainContextBase
from .checksum import sha256_file
from .models import git_install_commands

_LOCAL_TOOL_TIMEOUT_SECONDS = 2 * 60.0
_NETWORK_TOOL_TIMEOUT_SECONDS = 20 * 60.0


class ToolchainHelpersMixin(ToolchainContextBase):
    def _run_tool_cmd(self, cmd: list[str], *, cwd: Path, network: bool = False):
        timeout = _NETWORK_TOOL_TIMEOUT_SECONDS if network else _LOCAL_TOOL_TIMEOUT_SECONDS
        return run_process(cmd, cwd=cwd, timeout=timeout)

    def _run_tool_cmd_silent(self, cmd: list[str], *, cwd: Path, network: bool = False):
        timeout = _NETWORK_TOOL_TIMEOUT_SECONDS if network else _LOCAL_TOOL_TIMEOUT_SECONDS
        return run_silent(cmd, cwd=cwd, timeout=timeout)

    def _is_installed_at_version(self, tool_id: str, version: str) -> bool:
        current = get_installed_version(self._paths.tools_dir, tool_id)
        return current == version

    def _generate_wrappers(self, wrapper_gen: WrapperGenerator, *, dry_run: bool) -> None:
        if dry_run:
            return

        emsdk_dir = self._paths.tools_dir / "emsdk"
        if emsdk_dir.exists():
            create_emscripten_wrappers(emsdk_dir, self._paths.bin_dir, self._platform.platform)

        if self._platform.platform.is_windows:
            zig_dir = self._paths.tools_dir / "zig"
            if zig_dir.exists():
                create_zig_wrappers(zig_dir, self._paths.bin_dir, self._platform.platform)

    def _install_git_tool(self, tool: object, *, dry_run: bool) -> bool:
        commands = git_install_commands(
            tool,
            tools_dir=self._paths.tools_dir,
            platform=self._platform.platform,
        )
        if not commands:
            return False
        if dry_run:
            return True

        for cmd in commands:
            if not cmd:
                continue
            result = self._run_tool_cmd(cmd, cwd=self._paths.tools_dir, network=True)
            match result:
                case Err(error):
                    self._console.print(f"install failed: {' '.join(cmd)}", Style.ERROR)
                    stderr = error.stderr.strip()
                    if stderr:
                        self._console.print(stderr, Style.DIM)
                    return False
                case Ok(_):
                    pass

        return True

    def _ensure_platformio(self, version: str, *, dry_run: bool) -> bool:
        venv_dir = self._paths.tools_dir / "platformio" / "venv"
        pio = self._platformio_bin(venv_dir)

        env = self._workspace.platformio_env_vars()

        if not dry_run:
            wrapper = WrapperSpec(name="pio", target=pio, env=env)
            WrapperGenerator(self._paths.bin_dir).generate(wrapper, self._platform.platform)
            wrapper2 = WrapperSpec(name="platformio", target=pio, env=env)
            WrapperGenerator(self._paths.bin_dir).generate(wrapper2, self._platform.platform)

        if pio.exists() and self._is_installed_at_version("platformio", version):
            return True

        self._console.print(f"install platformio {version} (venv)", Style.DIM)
        if dry_run:
            return True

        venv_dir.parent.mkdir(parents=True, exist_ok=True)
        if not venv_dir.exists():
            result = self._run_tool_cmd(
                [sys.executable, "-m", "venv", str(venv_dir)],
                cwd=venv_dir.parent,
                network=False,
            )
            if isinstance(result, Err):
                self._console.print("platformio: venv creation failed", Style.ERROR)
                return False

        py = self._platformio_python(venv_dir)

        run_pip_upgrade = self._run_tool_cmd_silent(
            [str(py), "-m", "pip", "install", "-U", "pip"],
            cwd=venv_dir,
            network=True,
        )
        if isinstance(run_pip_upgrade, Err):
            self._console.print("platformio: pip bootstrap failed", Style.ERROR)
            return False

        result = self._run_tool_cmd(
            [str(py), "-m", "pip", "install", f"platformio=={version}"],
            cwd=venv_dir,
            network=True,
        )
        match result:
            case Err(error):
                self._console.print("platformio: pip install failed", Style.ERROR)
                stderr = error.stderr.strip()
                if stderr:
                    self._console.print(stderr, Style.DIM)
                return False
            case Ok(_):
                pass

        set_installed_version(self._paths.tools_dir, "platformio", version)
        return True

    def _install_jdk(
        self,
        *,
        http: RealHttpClient,
        downloader: Downloader,
        installer: Installer,
        pins: ToolPins,
    ) -> bool:
        from ms.tools.api import adoptium_jdk_url
        from ms.tools.definitions.jdk import DEFAULT_JDK_MAJOR, JdkTool

        tool = JdkTool()
        tool.major_version = pins.jdk_major if pins.jdk_major is not None else DEFAULT_JDK_MAJOR
        os_map = {
            "windows": "windows",
            "linux": "linux",
            "macos": "mac",
        }
        arch_map = {
            "x64": "x64",
            "arm64": "aarch64",
        }
        os_str = os_map.get(str(self._platform.platform), "windows")
        arch_str = arch_map.get(str(self._platform.arch), "x64")

        link_res = adoptium_jdk_url(http, tool.major_version, os_str, arch_str)
        if isinstance(link_res, Err):
            self._console.print("jdk: download failed", Style.ERROR)
            self._console.print(str(link_res.error), Style.DIM)
            return False

        url, resolved_version = link_res.value

        dres = downloader.download(url)
        if isinstance(dres, Err):
            self._console.print("jdk: download failed", Style.ERROR)
            self._console.print(str(dres.error), Style.DIM)
            return False

        if not self.verify_download_checksum(
            tool_id=tool.spec.id,
            version=resolved_version,
            archive_path=dres.value.path,
            pins=pins,
        ):
            return False

        install_dir = self._paths.tools_dir / tool.install_dir_name()
        ires = installer.install(
            dres.value.path, install_dir, strip_components=tool.strip_components()
        )
        if isinstance(ires, Err):
            self._console.print("jdk: install failed", Style.ERROR)
            self._console.print(str(ires.error), Style.DIM)
            return False

        tool.post_install(install_dir, self._platform.platform)
        set_installed_version(self._paths.tools_dir, tool.spec.id, resolved_version)
        return True

    def _platformio_python(self, venv_dir: Path) -> Path:
        if self._platform.platform.is_windows:
            return venv_dir / "Scripts" / "python.exe"
        return venv_dir / "bin" / "python"

    def _platformio_bin(self, venv_dir: Path) -> Path:
        if self._platform.platform.is_windows:
            return venv_dir / "Scripts" / "pio.exe"
        return venv_dir / "bin" / "pio"

    def verify_download_checksum(
        self,
        *,
        tool_id: str,
        version: str,
        archive_path: Path,
        pins: ToolPins,
    ) -> bool:
        expected = pins.checksum_for(
            tool_id=tool_id,
            version=version,
            platform=str(self._platform.platform),
            arch=str(self._platform.arch),
        )
        if expected is None:
            return True

        actual = sha256_file(archive_path)
        if actual != expected:
            self._console.print(f"{tool_id}: checksum verification failed", Style.ERROR)
            self._console.print(f"expected {expected[:12]}..., got {actual[:12]}...", Style.DIM)
            return False

        self._console.print(f"{tool_id}: checksum verified", Style.DIM)
        return True
