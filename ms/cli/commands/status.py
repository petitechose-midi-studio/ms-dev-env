"""Status command - check pending changes in all workspace repos."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from ms.cli.commands.status_collect import collect_repo_statuses, collect_repos
from ms.cli.commands.status_models import ChangeCounts, RepoStatus
from ms.cli.commands.status_plain import generate_plain_text
from ms.cli.context import build_context
from ms.git.repository import GitStatus, Repository
from ms.platform.clipboard import copy_to_clipboard

# Auto-detect TTY so piped output stays plain-text friendly.
_console = Console(legacy_windows=False)


def _render_counts(counts: ChangeCounts) -> Text:
    """Render change counts with colors."""
    text = Text()
    for i, (label, color) in enumerate(counts.as_parts()):
        if i > 0:
            text.append(" ")
        text.append(label, style=color)
    return text


def _render_divergence(st: GitStatus) -> Text:
    """Render ahead/behind."""
    text = Text()
    if st.ahead:
        text.append(f"{st.ahead}", style="green")
        text.append("^", style="green dim")
    if st.ahead and st.behind:
        text.append(" ")
    if st.behind:
        text.append(f"{st.behind}", style="red")
        text.append("v", style="red dim")
    return text


def _render_entry(xy: str, path: str) -> Text:
    """Render a file entry."""
    text = Text("    ")
    if xy == "??":
        text.append("? ", style="cyan")
    elif xy[0] == "M" or xy[1] == "M":
        text.append("M ", style="yellow")
    elif xy[0] == "A":
        text.append("A ", style="green")
    elif xy[0] == "D" or xy[1] == "D":
        text.append("D ", style="red")
    else:
        char = xy[0] if xy[0] != " " else xy[1]
        text.append(f"{char} ")
    text.append(path, style="dim")
    return text


def _render_changed_repo(r: RepoStatus, detailed: bool) -> Text:
    """Render a repo with changes."""
    st = r.status
    assert st is not None

    lines = Text()

    # Line 1: name
    lines.append(r.name, style="bold")
    lines.append("\n")

    # Line 2: path (dim)
    lines.append(str(r.path), style="dim")
    lines.append("\n")

    # Line 3: branch + counts + divergence
    lines.append(st.branch or "?", style="blue")
    lines.append("  ")
    lines.append_text(_render_counts(ChangeCounts.from_status(st)))
    div = _render_divergence(st)
    if div.plain:
        lines.append("  ")
        lines.append_text(div)

    # Files if detailed
    if detailed and st.entries:
        lines.append("\n")
        for i, entry in enumerate(st.entries):
            if i > 0:
                lines.append("\n")
            lines.append_text(_render_entry(entry.xy, entry.path))

    return lines


def status(
    detailed: bool = typer.Option(False, "--detailed", "-d", help="Show modified files"),
    fetch: bool = typer.Option(False, "--fetch", "-f", help="Fetch remotes first"),
    no_copy: bool = typer.Option(False, "--no-copy", help="Don't copy to clipboard"),
) -> None:
    """Check pending changes in all workspace repos."""
    ctx = build_context()

    repo_list = collect_repos(
        ctx.workspace.root,
        ctx.workspace.midi_studio_dir,
        ctx.workspace.open_control_dir,
    )

    # Fetch if requested
    if fetch:
        _console.print("[dim]Fetching remotes...[/dim]")
        for _name, path in repo_list:
            Repository(path).fetch()
        _console.print()

    # Collect statuses
    statuses = collect_repo_statuses(repo_list)

    changed = [r for r in statuses if r.has_changes or r.error]
    clean = [r for r in statuses if not r.has_changes and not r.error]

    # Render changed repos
    if changed:
        changed_items: list[Text] = []
        for r in changed:
            if r.error:
                err_text = Text()
                err_text.append(r.name, style="bold red")
                err_text.append(f"\n{r.error}", style="red dim")
                changed_items.append(err_text)
            else:
                changed_items.append(_render_changed_repo(r, detailed))

        # Join with blank lines
        combined = Text()
        for i, item in enumerate(changed_items):
            if i > 0:
                combined.append("\n\n")
            combined.append_text(item)

        panel = Panel(
            combined,
            title="[bold yellow]PENDING[/bold yellow]",
            title_align="left",
            border_style="yellow",
            padding=(0, 1),
        )
        _console.print(panel)
        _console.print()

    # Render clean repos
    if clean:
        clean_text = Text()
        for i, r in enumerate(clean):
            if i > 0:
                clean_text.append("\n")
            clean_text.append(r.name, style="dim")

        panel = Panel(
            clean_text,
            title=f"[bold green]OK[/bold green] [dim]({len(clean)})[/dim]",
            title_align="left",
            border_style="green dim",
            padding=(0, 1),
        )
        _console.print(panel)

    if not changed and not clean:
        _console.print("[dim]No repos found[/dim]")

    # Copy to clipboard by default
    if not no_copy:
        plain = generate_plain_text(changed, clean, detailed)
        if copy_to_clipboard(plain):
            _console.print("\n[dim]Copied to clipboard[/dim]")
