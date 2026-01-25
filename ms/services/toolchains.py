from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from ms.core.config import Config
from ms.core.workspace import Workspace
from ms.output.console import ConsoleProtocol, Style
from ms.platform.detection import PlatformInfo
from ms.platform.shell import generate_activation_scripts
from ms.tools.download import Downloader
from ms.tools.http import RealHttpClient
from ms.tools.installer import Installer
from ms.tools.pins import ToolPins
from ms.tools.registry import ToolRegistry
from ms.core.result import Err
from ms.tools.state import get_installed_version, set_installed_version
from ms.tools.wrapper import (
    WrapperGenerator,
    WrapperSpec,
    create_emscripten_wrappers,
    create_zig_wrappers,
)


@runtime_checkable
class _SystemTool(Protocol):
    def is_system_tool(self) -> bool: ...


@runtime_checkable
class _GitInstallTool(Protocol):
    def uses_git_install(self) -> bool: ...

    def get_install_commands(self, tools_dir: Path, platform: object) -> list[list[str]]: ...


@dataclass(frozen=True, slots=True)
class ToolchainPaths:
    tools_dir: Path
    bin_dir: Path
    cache_downloads: Path

    @classmethod
    def from_workspace(cls, workspace: Workspace, config: Config | None) -> ToolchainPaths:
        tools_dir = workspace.root / (config.paths.tools if config else "tools")
        return cls(
            tools_dir=tools_dir,
            bin_dir=tools_dir / "bin",
            cache_downloads=workspace.download_cache_dir,
        )


class ToolchainService:
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

        self._paths = ToolchainPaths.from_workspace(workspace, config)
        self._registry = ToolRegistry(
            tools_dir=self._paths.tools_dir,
            platform=platform.platform,
            arch=platform.arch,
        )

    def sync_dev(self, *, dry_run: bool = False, force: bool = False) -> bool:
        pins_path = Path(__file__).parent.parent / "data" / "toolchains.toml"
        pins = ToolPins.load(pins_path)

        self._paths.tools_dir.mkdir(parents=True, exist_ok=True)
        self._paths.bin_dir.mkdir(parents=True, exist_ok=True)

        ok = True

        http = RealHttpClient()
        downloader = Downloader(http, self._paths.cache_downloads)
        installer = Installer()
        wrapper_gen = WrapperGenerator(self._paths.bin_dir)

        # Install bundled tools
        for tool in self._registry.tools_for_mode("dev"):
            if isinstance(tool, _SystemTool) and tool.is_system_tool():
                continue

            if tool.spec.id == "platformio":
                if not self._ensure_platformio(pins.platformio_version, dry_run=dry_run):
                    ok = False
                continue

            # Special-case JDK: install via Adoptium direct link.
            if tool.spec.id == "jdk":
                if dry_run:
                    self._console.print("install jdk latest", Style.DIM)
                    continue

                if (
                    not force
                    and tool.is_installed(self._paths.tools_dir, self._platform.platform)
                    and get_installed_version(self._paths.tools_dir, tool.spec.id) is not None
                ):
                    continue

                if not self._install_jdk(http=http, downloader=downloader, installer=installer):
                    ok = False
                continue

            version = pins.versions.get(tool.spec.id, "latest")
            if version == "latest":
                if dry_run:
                    # Avoid network calls in dry-run.
                    version = "latest"
                else:
                    vres = tool.latest_version(http)
                    if isinstance(vres, Err):
                        self._console.print(
                            f"{tool.spec.id}: failed to resolve version", Style.ERROR
                        )
                        self._console.print(str(vres.error), Style.DIM)
                        ok = False
                        continue
                    version = vres.value

            if (
                not force
                and self._is_installed_at_version(tool.spec.id, version)
                and tool.is_installed(self._paths.tools_dir, self._platform.platform)
            ):
                continue

            self._console.print(f"install {tool.spec.id} {version}", Style.DIM)
            if dry_run:
                continue

            try:
                url = tool.download_url(version, self._platform.platform, self._platform.arch)
            except Exception as e:  # noqa: BLE001
                self._console.print(f"{tool.spec.id}: download URL error: {e}", Style.ERROR)
                ok = False
                continue

            # Git-based install (emsdk)
            if isinstance(tool, _GitInstallTool) and tool.uses_git_install():
                if not self._install_git_tool(tool, dry_run=dry_run):
                    ok = False
                else:
                    set_installed_version(self._paths.tools_dir, tool.spec.id, version)
                continue

            # Standard download + extract
            dres = downloader.download(url)
            if isinstance(dres, Err):
                self._console.print(f"{tool.spec.id}: download failed", Style.ERROR)
                self._console.print(str(dres.error), Style.DIM)
                ok = False
                continue

            install_dir = self._paths.tools_dir / tool.install_dir_name()
            ires = installer.install(
                dres.value.path,
                install_dir,
                strip_components=tool.strip_components(),
            )
            if isinstance(ires, Err):
                self._console.print(f"{tool.spec.id}: install failed", Style.ERROR)
                self._console.print(str(ires.error), Style.DIM)
                ok = False
                continue

            tool.post_install(install_dir, self._platform.platform)
            set_installed_version(self._paths.tools_dir, tool.spec.id, version)

        # Generate wrappers for special tools
        self._generate_wrappers(wrapper_gen, dry_run=dry_run)

        # Activation scripts
        if not dry_run:
            env_vars = self._registry.get_env_vars()
            env_vars.update(self._platformio_env_vars())
            path_additions = [self._paths.bin_dir, *self._registry.get_path_additions()]
            generate_activation_scripts(
                self._paths.tools_dir,
                env_vars,
                path_additions,
                self._platform.platform,
            )

        return ok

    def _is_installed_at_version(self, tool_id: str, version: str) -> bool:
        current = get_installed_version(self._paths.tools_dir, tool_id)
        return current == version

    def _generate_wrappers(self, wrapper_gen: WrapperGenerator, *, dry_run: bool) -> None:
        if dry_run:
            return

        # zig-cc / zig-cxx
        zig = self._registry.get_tool("zig")
        if zig and zig.is_installed(self._paths.tools_dir, self._platform.platform):
            zig_path = zig.bin_path(self._paths.tools_dir, self._platform.platform)
            if zig_path is not None:
                create_zig_wrappers(zig_path, self._paths.bin_dir, self._platform.platform)

        # emcc/emcmake wrappers
        emsdk_dir = self._paths.tools_dir / "emsdk"
        if emsdk_dir.exists():
            create_emscripten_wrappers(emsdk_dir, self._paths.bin_dir, self._platform.platform)

    def _install_git_tool(self, tool: _GitInstallTool, *, dry_run: bool) -> bool:
        cmds = tool.get_install_commands(self._paths.tools_dir, self._platform.platform)
        if dry_run:
            return True

        for cmd in cmds:
            if not cmd:
                continue
            proc = subprocess.run(
                cmd,
                cwd=str(self._paths.tools_dir),
                text=True,
                capture_output=True,
                check=False,
            )
            if proc.returncode != 0:
                self._console.print(f"install failed: {' '.join(cmd)}", Style.ERROR)
                stderr = (proc.stderr or "").strip()
                if stderr:
                    self._console.print(stderr, Style.DIM)
                return False

        return True

    def _ensure_platformio(self, version: str, *, dry_run: bool) -> bool:
        venv_dir = self._paths.tools_dir / "platformio" / "venv"
        pio = self._platformio_bin(venv_dir)

        env = self._platformio_env_vars()

        # Wrapper always points at venv pio and enforces PLATFORMIO_* dirs.
        if not dry_run:
            wrapper = WrapperSpec(
                name="pio",
                target=pio,
                env=env,
            )
            WrapperGenerator(self._paths.bin_dir).generate(wrapper, self._platform.platform)
            wrapper2 = WrapperSpec(
                name="platformio",
                target=pio,
                env=env,
            )
            WrapperGenerator(self._paths.bin_dir).generate(wrapper2, self._platform.platform)

        if pio.exists() and self._is_installed_at_version("platformio", version):
            return True

        self._console.print(f"install platformio {version} (venv)", Style.DIM)
        if dry_run:
            return True

        venv_dir.parent.mkdir(parents=True, exist_ok=True)
        if not venv_dir.exists():
            proc = subprocess.run(
                [sys.executable, "-m", "venv", str(venv_dir)],
                text=True,
                capture_output=True,
                check=False,
            )
            if proc.returncode != 0:
                self._console.print("platformio: venv creation failed", Style.ERROR)
                return False

        py = self._platformio_python(venv_dir)

        # Ensure pip
        subprocess.run([str(py), "-m", "pip", "install", "-U", "pip"], check=False)
        proc = subprocess.run(
            [str(py), "-m", "pip", "install", f"platformio=={version}"],
            text=True,
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0:
            self._console.print("platformio: pip install failed", Style.ERROR)
            stderr = (proc.stderr or "").strip()
            if stderr:
                self._console.print(stderr, Style.DIM)
            return False

        set_installed_version(self._paths.tools_dir, "platformio", version)
        return True

    def _install_jdk(
        self,
        *,
        http: RealHttpClient,
        downloader: Downloader,
        installer: Installer,
    ) -> bool:
        from ms.tools.api import adoptium_jdk_url
        from ms.tools.definitions.jdk import JdkTool

        tool = JdkTool()
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

        # Always fetch a direct download link from Adoptium.
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
        if self._platform.platform == self._platform.platform.WINDOWS:
            return venv_dir / "Scripts" / "python.exe"
        return venv_dir / "bin" / "python"

    def _platformio_bin(self, venv_dir: Path) -> Path:
        if self._platform.platform == self._platform.platform.WINDOWS:
            return venv_dir / "Scripts" / "pio.exe"
        return venv_dir / "bin" / "pio"

    def _platformio_env_vars(self) -> dict[str, str]:
        return {
            "PLATFORMIO_CORE_DIR": str(self._workspace.state_dir / "platformio"),
            "PLATFORMIO_CACHE_DIR": str(self._workspace.state_dir / "platformio-cache"),
            "PLATFORMIO_BUILD_CACHE_DIR": str(self._workspace.state_dir / "platformio-build-cache"),
        }
