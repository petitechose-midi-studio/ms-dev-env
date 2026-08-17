"""Tests for ms.core.result module."""

import pytest

from ms.core.result import Err, Ok, Result


class TestOk:
    """Tests for Ok type."""

    def test_create_ok(self) -> None:
        """Ok can be created with a value."""
        result = Ok(42)
        assert result.value == 42

    def test_ok_unwrap(self) -> None:
        """Ok.unwrap() returns the value."""
        result = Ok(42)
        assert result.unwrap() == 42

    def test_ok_unwrap_err_raises(self) -> None:
        """Ok.unwrap_err() raises ValueError."""
        result = Ok(42)
        with pytest.raises(ValueError, match="called unwrap_err on Ok"):
            result.unwrap_err()

    def test_ok_repr(self) -> None:
        """Ok has readable repr."""
        result = Ok(42)
        assert repr(result) == "Ok(42)"

    def test_ok_frozen(self) -> None:
        """Ok is immutable."""
        result = Ok(42)
        with pytest.raises(AttributeError):
            result.value = 0  # type: ignore[misc]

    def test_ok_equality(self) -> None:
        """Ok instances with same value are equal."""
        assert Ok(42) == Ok(42)
        assert Ok(42) != Ok(0)
        assert Ok(42) != Err(42)


class TestErr:
    """Tests for Err type."""

    def test_create_err(self) -> None:
        """Err can be created with an error."""
        result = Err("something went wrong")
        assert result.error == "something went wrong"

    def test_err_unwrap_raises(self) -> None:
        """Err.unwrap() raises ValueError."""
        result = Err("something went wrong")
        with pytest.raises(ValueError, match="called unwrap on Err"):
            result.unwrap()

    def test_err_unwrap_err(self) -> None:
        """Err.unwrap_err() returns the error."""
        result = Err("something went wrong")
        assert result.unwrap_err() == "something went wrong"

    def test_err_repr(self) -> None:
        """Err has readable repr."""
        result = Err("oops")
        assert repr(result) == "Err('oops')"

    def test_err_frozen(self) -> None:
        """Err is immutable."""
        result = Err("error")
        with pytest.raises(AttributeError):
            result.error = "other"  # type: ignore[misc]

    def test_err_equality(self) -> None:
        """Err instances with same error are equal."""
        assert Err("a") == Err("a")
        assert Err("a") != Err("b")
        assert Err(42) != Ok(42)


def _make_ok_result() -> Result[int, str]:
    """Helper to create Ok result (hides concrete type from pyright)."""
    return Ok(42)


def _make_err_result() -> Result[int, str]:
    """Helper to create Err result (hides concrete type from pyright)."""
    return Err("oops")


class TestPatternMatching:
    """Tests for pattern matching with match statement."""

    def test_match_ok(self) -> None:
        """Pattern matching works with Ok."""
        result = _make_ok_result()
        match result:
            case Ok(value):
                assert value == 42
            case Err(_):
                pytest.fail("Should not match Err")

    def test_match_err(self) -> None:
        """Pattern matching works with Err."""
        result = _make_err_result()
        match result:
            case Ok(_):
                pytest.fail("Should not match Ok")
            case Err(error):
                assert error == "oops"


class TestRealWorldUsage:
    """Tests demonstrating real-world usage patterns."""

    def test_parsing_function(self) -> None:
        """Result can be used for parsing with explicit errors."""

        def parse_int(s: str) -> Result[int, str]:
            try:
                return Ok(int(s))
            except ValueError:
                return Err(f"cannot parse '{s}' as integer")

        assert parse_int("42") == Ok(42)
        assert parse_int("abc") == Err("cannot parse 'abc' as integer")

    def test_file_operation(self) -> None:
        """Result can wrap file operations."""
        from pathlib import Path

        def read_file(path: Path) -> Result[str, str]:
            try:
                return Ok(path.read_text())
            except FileNotFoundError:
                return Err(f"file not found: {path}")
            except PermissionError:
                return Err(f"permission denied: {path}")

        # Test with non-existent file
        result = read_file(Path("/nonexistent/file.txt"))
        assert isinstance(result, Err)
        assert "file not found" in result.error

    def test_with_dataclass_error(self) -> None:
        """Result can use structured error types."""
        from dataclasses import dataclass

        @dataclass
        class ValidationError:
            field: str
            message: str

        def validate_age(age: int) -> Result[int, ValidationError]:
            if age < 0:
                return Err(ValidationError("age", "must be non-negative"))
            if age > 150:
                return Err(ValidationError("age", "unrealistic age"))
            return Ok(age)

        assert validate_age(25) == Ok(25)

        result = validate_age(-5)
        assert isinstance(result, Err)
        assert result.error.field == "age"
        assert result.error.message == "must be non-negative"
