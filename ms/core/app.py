"""App resolution and management.

A app represents a buildable project within the workspace, typically
located in midi-studio/. Each app can have:
- Teensy firmware (platformio.ini)
- Native SDL desktop simulator (sdl/)
- WASM web simulator (sdl/ with emscripten)

Usage:
    from ms.core.app import resolve, list_all, App

    # Resolve a app by name
    match resolve("core", workspace):
        case Ok(app):
            print(f"Path: {app.path}")
            if app.has_teensy:
                print("Has Teensy firmware")
        case Err(error):
            print(f"Not found: {error.message}")

    # List all available apps
    apps = list_all(workspace)
    print(f"Available: {', '.join(apps)}")
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from ms.core.result import Err, Ok, Result

if TYPE_CHECKING:
    from ms.output.console import ConsoleProtocol

__all__ = [
    "App",
    "AppError",
    "list_all",
    "resolve",
    "resolve_or_none",
]


@dataclass(frozen=True, slots=True)
class AppError:
    """Error resolving a app.

    Attributes:
        name: Attempted app name
        message: Error description
        available: List of available apps
    """

    name: str
    message: str
    available: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class App:
    """Resolved app information.

    Represents a buildable project with its capabilities.

    Attributes:
        name: App identifier (e.g., "core", "bitwig")
        path: Absolute path to app root
        sdl_path: Path to SDL sources if available
        has_teensy: True if platformio.ini exists
        has_sdl: True if SDL sources exist
    """

    name: str
    path: Path
    sdl_path: Path | None = None
    has_teensy: bool = False
    has_sdl: bool = False


def resolve(name: str, workspace: Path) -> Result[App, AppError]:
    """Resolve a app by name.

    Mapping:
    - "core" -> midi-studio/core
    - Other names -> midi-studio/plugin-{name}

    Args:
        name: App identifier
        workspace: Workspace root directory

    Returns:
        Ok(App) if found
        Err(AppError) if not found
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
            AppError(
                name=name,
                message=f"Unknown app: {name}",
                available=tuple(available),
            )
        )

    # Find SDL sources
    sdl_path = _find_sdl_path(path, midi_studio)

    return Ok(
        App(
            name=name,
            path=path,
            sdl_path=sdl_path,
            has_teensy=(path / "platformio.ini").exists(),
            has_sdl=sdl_path is not None,
        )
    )


def list_all(workspace: Path) -> list[str]:
    """List all available apps.

    Scans midi-studio/ for:
    - core/
    - plugin-*/

    Args:
        workspace: Workspace root directory

    Returns:
        Sorted list of app names
    """
    midi_studio = workspace / "midi-studio"
    apps: list[str] = []

    # Check for core
    if (midi_studio / "core").is_dir():
        apps.append("core")

    # Check for plugins
    if midi_studio.is_dir():
        for child in sorted(midi_studio.iterdir()):
            if child.is_dir() and child.name.startswith("plugin-"):
                apps.append(child.name.removeprefix("plugin-"))

    return apps


def _find_sdl_path(app_path: Path, midi_studio: Path) -> Path | None:
    """Find SDL sources for a app.

    Checks:
    1. app/sdl/app.cmake (app-specific SDL)
    2. midi-studio/core/sdl/app.cmake (shared SDL from core)

    Args:
        app_path: Path to app
        midi_studio: Path to midi-studio/

    Returns:
        Path to SDL directory, or None if not found
    """
    # Check app-specific SDL
    sdl_path = app_path / "sdl"
    if (sdl_path / "app.cmake").exists():
        return sdl_path

    # Fall back to core SDL
    core_sdl = midi_studio / "core" / "sdl"
    if (core_sdl / "app.cmake").exists():
        return core_sdl

    return None


def resolve_or_none(
    name: str,
    workspace: Path,
    console: ConsoleProtocol,
) -> App | None:
    """Resolve a app, printing error if not found.

    Convenience function for CLI commands that combines resolve()
    with error printing.

    Args:
        name: App identifier
        workspace: Workspace root directory
        console: Console for error output

    Returns:
        App if found, None if not found (error already printed)

    Example:
        app = resolve_or_none("core", workspace, console)
        if app is None:
            return False  # Error already printed
    """
    from ms.output.console import Style

    result = resolve(name, workspace)

    match result:
        case Ok(app):
            return app
        case Err(error):
            console.error(error.message)
            if error.available:
                console.print(f"Available: {', '.join(error.available)}", Style.DIM)
            return None
