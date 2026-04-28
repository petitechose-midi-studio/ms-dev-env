from __future__ import annotations

from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.output.console import Style
from ms.platform.resources import recommended_parallel_jobs
from ms.platform.shell import generate_activation_scripts
from ms.tools.download import Downloader
from ms.tools.http import RealHttpClient
from ms.tools.installer import Installer
from ms.tools.pins import ToolPins
from ms.tools.state import get_installed_version, set_installed_version
from ms.tools.wrapper import WrapperGenerator

from .helpers import ToolchainHelpersMixin
from .models import ToolchainError, git_install_commands, is_system_tool, uses_git_install


class ToolchainSyncMixin(ToolchainHelpersMixin):
    def sync_dev(
        self, *, dry_run: bool = False, force: bool = False
    ) -> Result[None, ToolchainError]:
        tool_ids = tuple(
            tool.spec.id
            for tool in self._registry.tools_for_mode("dev")
            if not is_system_tool(tool)
        )
        return self._sync_tools(tool_ids=tool_ids, dry_run=dry_run, force=force)

    def sync_unit_tests(
        self, *, dry_run: bool = False, force: bool = False
    ) -> Result[None, ToolchainError]:
        tool_ids = ["cmake", "ninja"]
        if self._platform.platform.is_windows:
            tool_ids.append("zig")
        return self._sync_tools(tool_ids=tuple(tool_ids), dry_run=dry_run, force=force)

    def _sync_tools(
        self,
        *,
        tool_ids: tuple[str, ...],
        dry_run: bool,
        force: bool,
    ) -> Result[None, ToolchainError]:
        pins_path = Path(__file__).resolve().parents[2] / "data" / "toolchains.toml"
        pins = ToolPins.load(pins_path)

        self._paths.tools_dir.mkdir(parents=True, exist_ok=True)
        self._paths.bin_dir.mkdir(parents=True, exist_ok=True)

        has_errors = False

        http = RealHttpClient()
        downloader = Downloader(http, self._paths.cache_downloads)
        installer = Installer()
        wrapper_gen = WrapperGenerator(self._paths.bin_dir)

        for tool_id in tool_ids:
            tool = self._registry.get_tool(tool_id)
            if tool is None:
                self._console.print(f"{tool_id}: unknown tool", Style.ERROR)
                has_errors = True
                continue

            if tool.spec.id == "platformio":
                if not self._ensure_platformio(pins.platformio_version, dry_run=dry_run):
                    has_errors = True
                continue

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

                if not self._install_jdk(
                    http=http,
                    downloader=downloader,
                    installer=installer,
                    pins=pins,
                ):
                    has_errors = True
                continue

            version = pins.versions.get(tool.spec.id, "latest")
            if version == "latest":
                if dry_run:
                    version = "latest"
                else:
                    vres = tool.latest_version(http)
                    if isinstance(vres, Err):
                        self._console.print(
                            f"{tool.spec.id}: failed to resolve version", Style.ERROR
                        )
                        self._console.print(str(vres.error), Style.DIM)
                        has_errors = True
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
            except (NotImplementedError, ValueError) as error:
                self._console.print(f"{tool.spec.id}: download URL error: {error}", Style.ERROR)
                has_errors = True
                continue

            if uses_git_install(tool):
                if not self._install_git_tool(tool, dry_run=dry_run):
                    has_errors = True
                else:
                    set_installed_version(self._paths.tools_dir, tool.spec.id, version)
                continue

            dres = downloader.download(url)
            if isinstance(dres, Err):
                self._console.print(f"{tool.spec.id}: download failed", Style.ERROR)
                self._console.print(str(dres.error), Style.DIM)
                has_errors = True
                continue

            if not self.verify_download_checksum(
                tool_id=tool.spec.id,
                version=version,
                archive_path=dres.value.path,
                pins=pins,
            ):
                has_errors = True
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
                has_errors = True
                continue

            tool.post_install(install_dir, self._platform.platform)
            set_installed_version(self._paths.tools_dir, tool.spec.id, version)

        self._generate_wrappers(wrapper_gen, dry_run=dry_run)

        if not dry_run:
            env_vars = self._registry.get_env_vars()
            env_vars.update(self._workspace.platformio_env_vars())

            # Ensure PlatformIO's SCons uses a safe default on Windows when
            # native builds rely on Zig-backed gcc/g++ wrappers.
            if self._platform.platform.is_windows:
                env_vars.setdefault("SCONSFLAGS", f"-j{recommended_parallel_jobs()}")

            path_additions = [self._paths.bin_dir, *self._registry.get_path_additions()]
            generate_activation_scripts(
                self._paths.tools_dir,
                env_vars,
                path_additions,
                self._platform.platform,
            )

        if has_errors:
            return Err(
                ToolchainError(
                    kind="sync_failed",
                    message="some tools failed to install",
                )
            )
        return Ok(None)

    def needs_git_for_sync_dev(self) -> bool:
        for tool in self._registry.tools_for_mode("dev"):
            if is_system_tool(tool):
                continue

            if uses_git_install(tool):
                cmds = git_install_commands(
                    tool,
                    tools_dir=self._paths.tools_dir,
                    platform=self._platform.platform,
                )
                if any(cmd and cmd[0] == "git" for cmd in cmds):
                    return True

        return False
