"""Wrapper script generator for tools.

This module generates wrapper scripts (bash/cmd) that invoke tool binaries.
Used for:
- Creating unified bin/ directory with all tool wrappers
- Setting up environment variables before invoking tools (e.g., emscripten)

Wrappers ensure:
- Bash scripts use LF line endings
- Cmd scripts use CRLF line endings
- Scripts are executable on Unix
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ms.platform.detection import Platform

__all__ = ["WrapperGenerator", "WrapperSpec", "create_emscripten_wrappers", "create_zig_wrappers"]


@dataclass(frozen=True, slots=True)
class WrapperSpec:
    """Specification for a wrapper script.

    Attributes:
        name: Wrapper name (e.g., "emcc")
        target: Path to the actual binary
        args: Additional arguments to pass
        env: Environment variables to set before running
    """

    name: str
    target: Path
    args: tuple[str, ...] = ()
    env: dict[str, str] | None = None


class WrapperGenerator:
    """Generates wrapper scripts for tools.

    Creates bash scripts (for Unix) and cmd scripts (for Windows)
    that invoke tool binaries with proper arguments and environment.
    """

    def __init__(self, bin_dir: Path) -> None:
        """Initialize the generator.

        Args:
            bin_dir: Directory to write wrapper scripts to
        """
        self._bin_dir = bin_dir

    @property
    def bin_dir(self) -> Path:
        """Get the bin directory."""
        return self._bin_dir

    def generate(self, spec: WrapperSpec, platform: Platform) -> Path:
        """Generate a wrapper script.

        Args:
            spec: Wrapper specification
            platform: Target platform

        Returns:
            Path to generated script
        """
        self._bin_dir.mkdir(parents=True, exist_ok=True)

        if str(platform).lower() == "windows":
            return self._generate_cmd(spec)
        else:
            return self._generate_bash(spec)

    def generate_all(
        self,
        specs: list[WrapperSpec],
        platform: Platform,
    ) -> list[Path]:
        """Generate multiple wrapper scripts.

        Args:
            specs: List of wrapper specifications
            platform: Target platform

        Returns:
            List of paths to generated scripts
        """
        return [self.generate(spec, platform) for spec in specs]

    def _generate_bash(self, spec: WrapperSpec) -> Path:
        """Generate a bash wrapper script.

        Uses LF line endings.
        """
        script_path = self._bin_dir / spec.name

        lines = ["#!/usr/bin/env bash", "# Auto-generated wrapper script", ""]

        # Add environment variables
        if spec.env:
            for key, value in spec.env.items():
                lines.append(f'export {key}="{value}"')
            lines.append("")

        # Build command
        args_str = " ".join(f'"{arg}"' for arg in spec.args) if spec.args else ""
        if args_str:
            lines.append(f'exec "{spec.target}" {args_str} "$@"')
        else:
            lines.append(f'exec "{spec.target}" "$@"')

        # Write with LF line endings
        content = "\n".join(lines) + "\n"
        script_path.write_text(content, encoding="utf-8", newline="\n")

        # Make executable
        script_path.chmod(0o755)

        return script_path

    def _generate_cmd(self, spec: WrapperSpec) -> Path:
        """Generate a cmd wrapper script.

        Uses CRLF line endings.
        """
        script_path = self._bin_dir / f"{spec.name}.cmd"

        lines = ["@echo off", "REM Auto-generated wrapper script", ""]

        # Add environment variables
        if spec.env:
            for key, value in spec.env.items():
                lines.append(f'set "{key}={value}"')
            lines.append("")

        # Build command
        args_str = " ".join(f'"{arg}"' for arg in spec.args) if spec.args else ""
        if args_str:
            lines.append(f'"{spec.target}" {args_str} %*')
        else:
            lines.append(f'"{spec.target}" %*')

        # Write with CRLF line endings
        content = "\r\n".join(lines) + "\r\n"
        script_path.write_bytes(content.encode("utf-8"))

        return script_path


def create_emscripten_wrappers(
    emsdk_dir: Path,
    bin_dir: Path,
    platform: Platform,
) -> list[Path]:
    """Create emcc and emcmake wrappers with EMSDK environment.

    Args:
        emsdk_dir: Path to emsdk directory
        bin_dir: Directory to write wrappers to
        platform: Target platform

    Returns:
        List of paths to generated wrappers
    """
    generator = WrapperGenerator(bin_dir)

    emscripten_dir = emsdk_dir / "upstream" / "emscripten"
    env = {"EMSDK": str(emsdk_dir)}

    if str(platform).lower() == "windows":
        emcc = emscripten_dir / "emcc.bat"
        emcmake = emscripten_dir / "emcmake.bat"
    else:
        emcc = emscripten_dir / "emcc"
        emcmake = emscripten_dir / "emcmake"

    specs = [
        WrapperSpec(name="emcc", target=emcc, env=env),
        WrapperSpec(name="emcmake", target=emcmake, env=env),
    ]

    return generator.generate_all(specs, platform)


def create_zig_wrappers(
    zig_dir: Path,
    bin_dir: Path,
    platform: Platform,
) -> list[Path]:
    """Create zig compiler wrapper scripts (zig-cc, zig-cxx, zig-ar).

    These wrappers invoke zig with -target x86_64-windows-gnu to produce
    GNU-compatible binaries that link with SDL2 MinGW libraries.

    Args:
        zig_dir: Path to zig directory (tools/zig)
        bin_dir: Directory to write wrappers to
        platform: Target platform

    Returns:
        List of paths to generated wrappers
    """
    generator = WrapperGenerator(bin_dir)
    zig_exe = zig_dir / ("zig.exe" if str(platform).lower() == "windows" else "zig")

    specs = [
        WrapperSpec(
            name="zig-cc",
            target=zig_exe,
            args=("cc", "-target", "x86_64-windows-gnu"),
        ),
        WrapperSpec(
            name="zig-cxx",
            target=zig_exe,
            args=("c++", "-target", "x86_64-windows-gnu"),
        ),
        WrapperSpec(
            name="zig-ar",
            target=zig_exe,
            args=("ar",),
        ),
    ]

    return generator.generate_all(specs, platform)
