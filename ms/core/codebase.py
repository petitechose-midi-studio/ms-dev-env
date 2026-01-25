"""Codebase resolution and management.

A codebase represents a buildable project within the workspace, typically
located in midi-studio/. Each codebase can have:
- Teensy firmware (platformio.ini)
- Native SDL desktop simulator (sdl/)
- WASM web simulator (sdl/ with emscripten)

Usage:
    from ms.core.codebase import resolve, list_all, Codebase

    # Resolve a codebase by name
    match resolve("core", workspace):
        case Ok(codebase):
            print(f"Path: {codebase.path}")
            if codebase.has_teensy:
                print("Has Teensy firmware")
        case Err(error):
            print(f"Not found: {error.message}")

    # List all available codebases
    codebases = list_all(workspace)
    print(f"Available: {', '.join(codebases)}")
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from ms.core.result import Err, Ok, Result

if TYPE_CHECKING:
    pass

__all__ = [
    "Codebase",
    "CodebaseError",
    "list_all",
    "resolve",
]


@dataclass(frozen=True, slots=True)
class CodebaseError:
    """Error resolving a codebase.

    Attributes:
        name: Attempted codebase name
        message: Error description
        available: List of available codebases
    """

    name: str
    message: str
    available: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Codebase:
    """Resolved codebase information.

    Represents a buildable project with its capabilities.

    Attributes:
        name: Codebase identifier (e.g., "core", "bitwig")
        path: Absolute path to codebase root
        sdl_path: Path to SDL sources if available
        has_teensy: True if platformio.ini exists
        has_sdl: True if SDL sources exist
    """

    name: str
    path: Path
    sdl_path: Path | None = None
    has_teensy: bool = False
    has_sdl: bool = False


def resolve(name: str, workspace: Path) -> Result[Codebase, CodebaseError]:
    """Resolve a codebase by name.

    Mapping:
    - "core" -> midi-studio/core
    - Other names -> midi-studio/plugin-{name}

    Args:
        name: Codebase identifier
        workspace: Workspace root directory

    Returns:
        Ok(Codebase) if found
        Err(CodebaseError) if not found
    """
    midi_studio = workspace / "midi-studio"

    # Determine path based on name
    if name == "core":
        path = midi_studio / "core"
    else:
        path = midi_studio / f"plugin-{name}"

    # Check if path exists
    if not path.is_dir():
        available = list_all(workspace)
        return Err(
            CodebaseError(
                name=name,
                message=f"Unknown codebase: {name}",
                available=tuple(available),
            )
        )

    # Find SDL sources
    sdl_path = _find_sdl_path(path, midi_studio)

    return Ok(
        Codebase(
            name=name,
            path=path,
            sdl_path=sdl_path,
            has_teensy=(path / "platformio.ini").exists(),
            has_sdl=sdl_path is not None,
        )
    )


def list_all(workspace: Path) -> list[str]:
    """List all available codebases.

    Scans midi-studio/ for:
    - core/
    - plugin-*/

    Args:
        workspace: Workspace root directory

    Returns:
        Sorted list of codebase names
    """
    midi_studio = workspace / "midi-studio"
    codebases: list[str] = []

    # Check for core
    if (midi_studio / "core").is_dir():
        codebases.append("core")

    # Check for plugins
    if midi_studio.is_dir():
        for child in sorted(midi_studio.iterdir()):
            if child.is_dir() and child.name.startswith("plugin-"):
                codebases.append(child.name.removeprefix("plugin-"))

    return codebases


def _find_sdl_path(codebase_path: Path, midi_studio: Path) -> Path | None:
    """Find SDL sources for a codebase.

    Checks:
    1. codebase/sdl/app.cmake (codebase-specific SDL)
    2. midi-studio/core/sdl/app.cmake (shared SDL from core)

    Args:
        codebase_path: Path to codebase
        midi_studio: Path to midi-studio/

    Returns:
        Path to SDL directory, or None if not found
    """
    # Check codebase-specific SDL
    sdl_path = codebase_path / "sdl"
    if (sdl_path / "app.cmake").exists():
        return sdl_path

    # Fall back to core SDL
    core_sdl = midi_studio / "core" / "sdl"
    if (core_sdl / "app.cmake").exists():
        return core_sdl

    return None
