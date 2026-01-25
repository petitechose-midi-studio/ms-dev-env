# SPDX-License-Identifier: MIT
"""Base types for checkers."""

from dataclasses import dataclass
from enum import Enum, auto


class CheckStatus(Enum):
    """Status of a check result."""

    OK = auto()
    """Check passed successfully."""

    WARNING = auto()
    """Check passed but with warnings (optional dependency missing)."""

    ERROR = auto()
    """Check failed (required dependency missing or broken)."""


@dataclass(frozen=True, slots=True)
class CheckResult:
    """Result of a single check.

    Attributes:
        name: Short identifier for what was checked (e.g., "git", "SDL2")
        status: Whether the check passed, warned, or failed
        message: Human-readable result message
        hint: Optional installation/fix command or URL
    """

    name: str
    status: CheckStatus
    message: str
    hint: str | None = None

    @property
    def ok(self) -> bool:
        """Return True if check passed (OK or WARNING)."""
        return self.status != CheckStatus.ERROR

    @property
    def is_error(self) -> bool:
        """Return True if check failed."""
        return self.status == CheckStatus.ERROR

    @property
    def is_warning(self) -> bool:
        """Return True if check has warnings."""
        return self.status == CheckStatus.WARNING

    @classmethod
    def success(cls, name: str, message: str) -> "CheckResult":
        """Create a successful check result."""
        return cls(name=name, status=CheckStatus.OK, message=message)

    @classmethod
    def warning(cls, name: str, message: str, hint: str | None = None) -> "CheckResult":
        """Create a warning check result."""
        return cls(name=name, status=CheckStatus.WARNING, message=message, hint=hint)

    @classmethod
    def error(cls, name: str, message: str, hint: str | None = None) -> "CheckResult":
        """Create a failed check result."""
        return cls(name=name, status=CheckStatus.ERROR, message=message, hint=hint)
