"""Clean command - remove build artifacts and caches."""

from __future__ import annotations

from pathlib import Path

import typer

from ms.cli.commands.removal import remove_directories
from ms.cli.context import build_context


def _find_pio_dirs(parent: Path) -> list[Path]:
    """Find all .pio directories in immediate subdirectories of parent."""
    if not parent.exists():
        return []
    return [d / ".pio" for d in parent.iterdir() if d.is_dir() and (d / ".pio").exists()]


def clean(
    all_: bool = typer.Option(False, "--all", help="Include tools and caches"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Execute (default is dry-run)"),
) -> None:
    """Clean build artifacts. Dry-run by default, use -y to execute."""
    ctx = build_context()
    ws = ctx.workspace

    # Collect directories - build artifacts
    dirs: list[Path] = [
        ws.build_dir,
        ws.platformio_dir,
        ws.state_dir / "platformio-cache",
        ws.state_dir / "platformio-build-cache",
    ]

    # Add all .pio directories from midi-studio apps (dynamic discovery)
    dirs.extend(_find_pio_dirs(ws.midi_studio_dir))

    if all_:
        dirs.extend([ws.tools_dir, ws.cache_dir])

    remove_directories(dirs, yes=yes, empty_message="Nothing to clean", console=ctx.console)
