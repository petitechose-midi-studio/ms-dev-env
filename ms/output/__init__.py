"""Output abstraction layer."""

from .console import (
    ConsoleProtocol,
    MockConsole,
    RichConsole,
    Style,
)

__all__ = [
    "ConsoleProtocol",
    "MockConsole",
    "RichConsole",
    "Style",
]
