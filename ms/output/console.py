"""Console output abstraction.

This module provides a protocol for console output that can be implemented
by different backends (Rich, plain text, mock for testing). This allows
services to output styled text without depending on a specific library.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Protocol

__all__ = [
    "Style",
    "ConsoleProtocol",
    "RichConsole",
    "MockConsole",
]


class Style(Enum):
    """Text styles for console output."""

    DEFAULT = auto()
    SUCCESS = auto()  # Green checkmark, positive message
    ERROR = auto()  # Red X, error message
    WARNING = auto()  # Yellow, warning message
    INFO = auto()  # Blue/cyan, informational
    DIM = auto()  # Dimmed/muted text
    BOLD = auto()  # Bold text
    HEADER = auto()  # Section header

    def __str__(self) -> str:
        return self.name.lower()


class ConsoleProtocol(Protocol):
    """Protocol for console output.

    This protocol defines the interface for outputting styled text to the
    console. Implementations can use Rich, plain ANSI, or capture output
    for testing.
    """

    def print(self, message: str, style: Style = Style.DEFAULT) -> None:
        """Print a message with optional styling.

        Args:
            message: The text to print
            style: The style to apply
        """
        ...

    def success(self, message: str) -> None:
        """Print a success message (shorthand for print with SUCCESS style)."""
        ...

    def error(self, message: str) -> None:
        """Print an error message (shorthand for print with ERROR style)."""
        ...

    def warning(self, message: str) -> None:
        """Print a warning message (shorthand for print with WARNING style)."""
        ...

    def info(self, message: str) -> None:
        """Print an info message (shorthand for print with INFO style)."""
        ...

    def header(self, message: str) -> None:
        """Print a section header."""
        ...

    def newline(self) -> None:
        """Print an empty line."""
        ...


class RichConsole:
    """Console implementation using Rich library.

    This is the production implementation that uses Rich for styled output.
    """

    def __init__(self) -> None:
        # Import Rich lazily to avoid import-time dependency
        from rich.console import Console

        self._console = Console()
        self._style_map = {
            Style.DEFAULT: "",
            Style.SUCCESS: "green",
            Style.ERROR: "red bold",
            Style.WARNING: "yellow",
            Style.INFO: "cyan",
            Style.DIM: "dim",
            Style.BOLD: "bold",
            Style.HEADER: "blue bold",
        }

    def print(self, message: str, style: Style = Style.DEFAULT) -> None:
        rich_style = self._style_map.get(style, "")
        if rich_style:
            self._console.print(message, style=rich_style)
        else:
            self._console.print(message)

    def success(self, message: str) -> None:
        self._console.print(f"[green]OK[/green] {message}")

    def error(self, message: str) -> None:
        self._console.print(f"[red bold]error:[/red bold] {message}")

    def warning(self, message: str) -> None:
        self._console.print(f"[yellow]warning:[/yellow] {message}")

    def info(self, message: str) -> None:
        self._console.print(f"[cyan]info:[/cyan] {message}")

    def header(self, message: str) -> None:
        self._console.print(f"\n[blue bold]{message}[/blue bold]")

    def newline(self) -> None:
        self._console.print()


@dataclass
class OutputRecord:
    """A single output record for MockConsole."""

    message: str
    style: Style


def _empty_outputs() -> list[OutputRecord]:
    """Factory for empty outputs list (helps type inference)."""
    return []


@dataclass
class MockConsole:
    """Console implementation that captures output for testing.

    Use this in tests to verify what would have been printed without
    actually printing anything.
    """

    outputs: list[OutputRecord] = field(default_factory=_empty_outputs)

    def print(self, message: str, style: Style = Style.DEFAULT) -> None:
        self.outputs.append(OutputRecord(message, style))

    def success(self, message: str) -> None:
        self.outputs.append(OutputRecord(f"OK {message}", Style.SUCCESS))

    def error(self, message: str) -> None:
        self.outputs.append(OutputRecord(f"error: {message}", Style.ERROR))

    def warning(self, message: str) -> None:
        self.outputs.append(OutputRecord(f"warning: {message}", Style.WARNING))

    def info(self, message: str) -> None:
        self.outputs.append(OutputRecord(f"info: {message}", Style.INFO))

    def header(self, message: str) -> None:
        self.outputs.append(OutputRecord(message, Style.HEADER))

    def newline(self) -> None:
        self.outputs.append(OutputRecord("", Style.DEFAULT))

    # Test helper methods

    def clear(self) -> None:
        """Clear all captured output."""
        self.outputs.clear()

    @property
    def messages(self) -> list[str]:
        """Get all output messages as a list of strings."""
        return [o.message for o in self.outputs]

    @property
    def text(self) -> str:
        """Get all output as a single newline-separated string."""
        return "\n".join(self.messages)

    def has_error(self) -> bool:
        """Check if any error was printed."""
        return any(o.style == Style.ERROR for o in self.outputs)

    def has_warning(self) -> bool:
        """Check if any warning was printed."""
        return any(o.style == Style.WARNING for o in self.outputs)

    def has_success(self) -> bool:
        """Check if any success message was printed."""
        return any(o.style == Style.SUCCESS for o in self.outputs)

    def find(self, substring: str) -> list[OutputRecord]:
        """Find all outputs containing a substring."""
        return [o for o in self.outputs if substring in o.message]

    def count(self, style: Style) -> int:
        """Count outputs with a specific style."""
        return sum(1 for o in self.outputs if o.style == style)
