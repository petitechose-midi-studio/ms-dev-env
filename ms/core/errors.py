"""Error codes for CLI exit status.

This module provides a simple enum of error codes that map to shell exit codes.
These are used consistently throughout the application to indicate the type of
failure that occurred.
"""

from enum import IntEnum

__all__ = ["ErrorCode"]


class ErrorCode(IntEnum):
    """Exit codes for CLI commands.

    These values are used as process exit codes and should remain stable.
    The numeric values follow common conventions:
    - 0: Success
    - 1: User error (bad input, invalid arguments)
    - 2: Environment error (missing tools, wrong versions)
    - 3: Build error (compilation failed, tests failed)
    - 4: Network error (download failed, API unreachable)
    - 5: I/O error (file not found, permission denied)
    """

    OK = 0
    USER_ERROR = 1
    ENV_ERROR = 2
    BUILD_ERROR = 3
    NETWORK_ERROR = 4
    IO_ERROR = 5

    def __str__(self) -> str:
        """Return human-readable name."""
        return self.name.lower().replace("_", " ")

    @property
    def is_success(self) -> bool:
        """Check if this code indicates success."""
        return self == ErrorCode.OK

    @property
    def is_error(self) -> bool:
        """Check if this code indicates an error."""
        return self != ErrorCode.OK
