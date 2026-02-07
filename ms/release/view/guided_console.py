from __future__ import annotations

from ms.output.console import ConsoleProtocol, Style


def print_notes_status(
    *,
    console: ConsoleProtocol,
    notes_markdown: str | None,
    notes_path: str | None,
    notes_sha256: str | None,
    auto_label: str,
) -> None:
    if notes_markdown is None:
        console.print(auto_label, Style.DIM)
        return

    digest = notes_sha256[:12] if notes_sha256 is not None else "n/a"
    source = notes_path or "(unknown source)"
    console.print(
        f"notes: attached from {source} ({len(notes_markdown)} bytes, sha256={digest})",
        Style.DIM,
    )
