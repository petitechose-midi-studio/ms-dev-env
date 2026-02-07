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
    if is_ok(result):
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

from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeGuard, TypeVar

T = TypeVar("T")
U = TypeVar("U")
E = TypeVar("E")
F = TypeVar("F")


@dataclass(frozen=True, slots=True)
class Ok[T]:
    """Represents a successful result containing a value.

    Attributes:
        value: The success value.
    """

    value: T

    def is_ok(self) -> bool:
        """Returns True."""
        return True

    def is_err(self) -> bool:
        """Returns False."""
        return False

    def unwrap(self) -> T:
        """Returns the contained value.

        Returns:
            The success value.
        """
        return self.value

    def unwrap_or(self, default: T) -> T:
        """Returns the contained value.

        Args:
            default: Ignored for Ok.

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

    def map(self, f: Callable[[T], U]) -> Ok[U]:
        """Applies a function to the contained value.

        Args:
            f: Function to apply to the value.

        Returns:
            Ok with the transformed value.
        """
        return Ok(f(self.value))

    def map_err(self, f: Callable[[E], F]) -> Ok[T]:
        """Returns self unchanged (no error to map).

        Args:
            f: Ignored for Ok.

        Returns:
            Self unchanged.
        """
        return self

    def flat_map(self, f: Callable[[T], Result[U, E]]) -> Result[U, E]:
        """Applies a function that returns a Result.

        Args:
            f: Function that takes the value and returns a Result.

        Returns:
            The Result returned by f.
        """
        return f(self.value)

    def __repr__(self) -> str:
        return f"Ok({self.value!r})"


@dataclass(frozen=True, slots=True)
class Err[E]:
    """Represents a failed result containing an error.

    Attributes:
        error: The error value.
    """

    error: E

    def is_ok(self) -> bool:
        """Returns False."""
        return False

    def is_err(self) -> bool:
        """Returns True."""
        return True

    def unwrap(self) -> None:
        """Raises ValueError with the error.

        Raises:
            ValueError: Always, containing the error.
        """
        raise ValueError(f"called unwrap on Err: {self.error}")

    def unwrap_or(self, default: T) -> T:
        """Returns the default value.

        Args:
            default: Value to return.

        Returns:
            The default value.
        """
        return default

    def unwrap_err(self) -> E:
        """Returns the contained error.

        Returns:
            The error value.
        """
        return self.error

    def map(self, f: Callable[[T], U]) -> Err[E]:
        """Returns self unchanged (no value to map).

        Args:
            f: Ignored for Err.

        Returns:
            Self unchanged.
        """
        return self

    def map_err(self, f: Callable[[E], F]) -> Err[F]:
        """Applies a function to the contained error.

        Args:
            f: Function to apply to the error.

        Returns:
            Err with the transformed error.
        """
        return Err(f(self.error))

    def flat_map(self, f: Callable[[T], Result[U, E]]) -> Err[E]:
        """Returns self unchanged (no value to flat_map).

        Args:
            f: Ignored for Err.

        Returns:
            Self unchanged.
        """
        return self

    def __repr__(self) -> str:
        return f"Err({self.error!r})"


# Type alias for Result
type Result[T, E] = Ok[T] | Err[E]


def is_ok[T, E](result: Result[T, E]) -> TypeGuard[Ok[T]]:
    """Type guard that checks if a Result is Ok.

    This function narrows the type for static type checkers.

    Args:
        result: The Result to check.

    Returns:
        True if the result is Ok, False otherwise.

    Example:
        result: Result[int, str] = Ok(42)
        if is_ok(result):
            # Type checker knows result is Ok[int] here
            print(result.value)
    """
    return isinstance(result, Ok)


def is_err[T, E](result: Result[T, E]) -> TypeGuard[Err[E]]:
    """Type guard that checks if a Result is Err.

    This function narrows the type for static type checkers.

    Args:
        result: The Result to check.

    Returns:
        True if the result is Err, False otherwise.

    Example:
        result: Result[int, str] = Err("error")
        if is_err(result):
            # Type checker knows result is Err[str] here
            print(result.error)
    """
    return isinstance(result, Err)
