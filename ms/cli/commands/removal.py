from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from ms.output.console import ConsoleProtocol, Style
from ms.platform.files import remove_tree


def remove_directories(
    directories: Iterable[Path],
    *,
    yes: bool,
    empty_message: str,
    console: ConsoleProtocol,
) -> None:
    existing = [path for path in directories if path.exists()]
    if not existing:
        console.print(empty_message, Style.DIM)
        return

    console.newline()
    console.print("EXECUTE" if yes else "DRY-RUN", Style.ERROR if yes else Style.WARNING)
    console.newline()
    for path in existing:
        console.print(f"  {path}", Style.DIM)

    if not yes:
        console.newline()
        console.print("Use -y to execute", Style.DIM)
        return

    for path in existing:
        remove_tree(path)
    console.newline()
    console.print(f"Removed {len(existing)} directories", Style.SUCCESS)
