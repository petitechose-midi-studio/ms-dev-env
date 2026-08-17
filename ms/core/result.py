"""Result type for explicit error handling.

This module provides a Result type similar to Rust's Result<T, E>.
It forces explicit handling of success and failure cases, eliminating
the need for try/except blocks scattered throughout the app.

Usage:
    def divide(a: int, b: int) -> Result[float, str]:
        if b == 0:
            return Err("division by zero")
        return Ok(a / b)

    result = divide(10, 2)
    if isinstance(result, Ok):
        print(f"Result: {result.value}")
    else:
        print(f"Error: {result.error}")

    # Or with pattern matching (Python 3.10+)
    match divide(10, 2):
        case Ok(value):
            print(f"Result: {value}")
        case Err(error):
            print(f"Error: {error}")
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeVar

T = TypeVar("T")
E = TypeVar("E")


@dataclass(frozen=True, slots=True)
class Ok[T]:
    """Represents a successful result containing a value.

    Attributes:
        value: The success value.
    """

    value: T

    def unwrap(self) -> T:
        """Returns the contained value.

        Returns:
            The success value.
        """
        return self.value

    def unwrap_err(self) -> None:
        """Raises ValueError since this is Ok.

        Raises:
            ValueError: Always, since Ok has no error.
        """
        raise ValueError(f"called unwrap_err on Ok: {self.value}")

    def __repr__(self) -> str:
        return f"Ok({self.value!r})"


@dataclass(frozen=True, slots=True)
class Err[E]:
    """Represents a failed result containing an error.

    Attributes:
        error: The error value.
    """

    error: E

    def unwrap(self) -> None:
        """Raises ValueError with the error.

        Raises:
            ValueError: Always, containing the error.
        """
        raise ValueError(f"called unwrap on Err: {self.error}")

    def unwrap_err(self) -> E:
        """Returns the contained error.

        Returns:
            The error value.
        """
        return self.error

    def __repr__(self) -> str:
        return f"Err({self.error!r})"


type Result[T, E] = Ok[T] | Err[E]
