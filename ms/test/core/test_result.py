"""Tests for ms.core.result module."""

import pytest

from ms.core.result import Ok, Err, Result, is_ok, is_err


class TestOk:
    """Tests for Ok type."""

    def test_create_ok(self) -> None:
        """Ok can be created with a value."""
        result = Ok(42)
        assert result.value == 42

    def test_ok_is_ok(self) -> None:
        """Ok.is_ok() returns True."""
        result = Ok(42)
        assert result.is_ok() is True

    def test_ok_is_not_err(self) -> None:
        """Ok.is_err() returns False."""
        result = Ok(42)
        assert result.is_err() is False

    def test_ok_unwrap(self) -> None:
        """Ok.unwrap() returns the value."""
        result = Ok(42)
        assert result.unwrap() == 42

    def test_ok_unwrap_or(self) -> None:
        """Ok.unwrap_or() returns the value, ignoring default."""
        result = Ok(42)
        assert result.unwrap_or(0) == 42

    def test_ok_unwrap_err_raises(self) -> None:
        """Ok.unwrap_err() raises ValueError."""
        result = Ok(42)
        with pytest.raises(ValueError, match="called unwrap_err on Ok"):
            result.unwrap_err()

    def test_ok_map(self) -> None:
        """Ok.map() transforms the value."""
        result = Ok(21)
        mapped = result.map(lambda x: x * 2)
        assert mapped == Ok(42)

    def test_ok_map_err(self) -> None:
        """Ok.map_err() returns self unchanged."""
        result = Ok(42)
        mapped = result.map_err(lambda e: f"error: {e}")
        assert mapped == Ok(42)

    def test_ok_flat_map_to_ok(self) -> None:
        """Ok.flat_map() with function returning Ok."""
        result: Result[int, str] = Ok(21)
        flat = result.flat_map(lambda x: Ok(x * 2))
        assert flat == Ok(42)

    def test_ok_flat_map_to_err(self) -> None:
        """Ok.flat_map() with function returning Err."""
        result: Result[int, str] = Ok(0)
        flat = result.flat_map(lambda x: Err("zero") if x == 0 else Ok(100 // x))
        assert flat == Err("zero")

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

    def test_err_is_not_ok(self) -> None:
        """Err.is_ok() returns False."""
        result = Err("error")
        assert result.is_ok() is False

    def test_err_is_err(self) -> None:
        """Err.is_err() returns True."""
        result = Err("error")
        assert result.is_err() is True

    def test_err_unwrap_raises(self) -> None:
        """Err.unwrap() raises ValueError."""
        result = Err("something went wrong")
        with pytest.raises(ValueError, match="called unwrap on Err"):
            result.unwrap()

    def test_err_unwrap_or(self) -> None:
        """Err.unwrap_or() returns the default."""
        result: Result[int, str] = Err("error")
        assert result.unwrap_or(42) == 42

    def test_err_unwrap_err(self) -> None:
        """Err.unwrap_err() returns the error."""
        result = Err("something went wrong")
        assert result.unwrap_err() == "something went wrong"

    def test_err_map(self) -> None:
        """Err.map() returns self unchanged."""
        result: Result[int, str] = Err("error")
        mapped = result.map(lambda x: x * 2)
        assert mapped == Err("error")

    def test_err_map_err(self) -> None:
        """Err.map_err() transforms the error."""
        result = Err("oops")
        mapped = result.map_err(lambda e: f"error: {e}")
        assert mapped == Err("error: oops")

    def test_err_flat_map(self) -> None:
        """Err.flat_map() returns self unchanged."""
        result: Result[int, str] = Err("error")
        flat = result.flat_map(lambda x: Ok(x * 2))
        assert flat == Err("error")

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


class TestTypeGuards:
    """Tests for is_ok() and is_err() type guards."""

    def test_is_ok_on_ok(self) -> None:
        """is_ok() returns True for Ok."""
        result: Result[int, str] = Ok(42)
        assert is_ok(result) is True

    def test_is_ok_on_err(self) -> None:
        """is_ok() returns False for Err."""
        result: Result[int, str] = Err("error")
        assert is_ok(result) is False

    def test_is_err_on_err(self) -> None:
        """is_err() returns True for Err."""
        result: Result[int, str] = Err("error")
        assert is_err(result) is True

    def test_is_err_on_ok(self) -> None:
        """is_err() returns False for Ok."""
        result: Result[int, str] = Ok(42)
        assert is_err(result) is False


class TestPatternMatching:
    """Tests for pattern matching with match statement."""

    def test_match_ok(self) -> None:
        """Pattern matching works with Ok."""
        result: Result[int, str] = Ok(42)
        match result:
            case Ok(value):
                assert value == 42
            case Err(_):
                pytest.fail("Should not match Err")

    def test_match_err(self) -> None:
        """Pattern matching works with Err."""
        result: Result[int, str] = Err("oops")
        match result:
            case Ok(_):
                pytest.fail("Should not match Ok")
            case Err(error):
                assert error == "oops"


class TestResultChaining:
    """Tests for chaining multiple operations."""

    def test_chain_maps(self) -> None:
        """Multiple map operations can be chained."""
        result: Result[int, str] = Ok(10)
        final = result.map(lambda x: x * 2).map(lambda x: x + 1).map(str)
        assert final == Ok("21")

    def test_chain_flat_maps(self) -> None:
        """Multiple flat_map operations can be chained."""

        def safe_div(a: int, b: int) -> Result[int, str]:
            if b == 0:
                return Err("division by zero")
            return Ok(a // b)

        result: Result[int, str] = Ok(100)
        final = result.flat_map(lambda x: safe_div(x, 2)).flat_map(
            lambda x: safe_div(x, 5)
        )
        assert final == Ok(10)

    def test_chain_stops_on_err(self) -> None:
        """Chain stops propagating on first Err."""

        def safe_div(a: int, b: int) -> Result[int, str]:
            if b == 0:
                return Err("division by zero")
            return Ok(a // b)

        result: Result[int, str] = Ok(100)
        final = result.flat_map(lambda x: safe_div(x, 0)).flat_map(
            lambda x: safe_div(x, 5)
        )
        assert final == Err("division by zero")


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
        assert is_err(result)
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
        assert is_err(result)
        assert result.error.field == "age"
        assert result.error.message == "must be non-negative"
