"""Tests for ms.core.errors module."""

import pytest

from ms.core.errors import ErrorCode


class TestErrorCodeValues:
    """Test that error codes have expected numeric values."""

    def test_ok_is_zero(self) -> None:
        assert ErrorCode.OK == 0

    def test_user_error_is_one(self) -> None:
        assert ErrorCode.USER_ERROR == 1

    def test_env_error_is_two(self) -> None:
        assert ErrorCode.ENV_ERROR == 2

    def test_build_error_is_three(self) -> None:
        assert ErrorCode.BUILD_ERROR == 3

    def test_network_error_is_four(self) -> None:
        assert ErrorCode.NETWORK_ERROR == 4

    def test_io_error_is_five(self) -> None:
        assert ErrorCode.IO_ERROR == 5


class TestErrorCodeUsage:
    """Test that ErrorCode works well as exit codes."""

    def test_can_use_as_int(self) -> None:
        """ErrorCode can be used directly where int is expected."""
        code: int = ErrorCode.BUILD_ERROR
        assert code == 3

    def test_can_compare_with_int(self) -> None:
        """ErrorCode can be compared with plain integers."""
        assert ErrorCode.OK == 0
        assert ErrorCode.USER_ERROR != 0

    def test_is_success_on_ok(self) -> None:
        assert ErrorCode.OK.is_success is True

    def test_is_success_on_errors(self) -> None:
        assert ErrorCode.USER_ERROR.is_success is False
        assert ErrorCode.ENV_ERROR.is_success is False
        assert ErrorCode.BUILD_ERROR.is_success is False
        assert ErrorCode.NETWORK_ERROR.is_success is False
        assert ErrorCode.IO_ERROR.is_success is False

    def test_is_error_on_ok(self) -> None:
        assert ErrorCode.OK.is_error is False

    def test_is_error_on_errors(self) -> None:
        assert ErrorCode.USER_ERROR.is_error is True
        assert ErrorCode.ENV_ERROR.is_error is True
        assert ErrorCode.BUILD_ERROR.is_error is True
        assert ErrorCode.NETWORK_ERROR.is_error is True
        assert ErrorCode.IO_ERROR.is_error is True


class TestErrorCodeStr:
    """Test string representation of error codes."""

    def test_ok_str(self) -> None:
        assert str(ErrorCode.OK) == "ok"

    def test_user_error_str(self) -> None:
        assert str(ErrorCode.USER_ERROR) == "user error"

    def test_env_error_str(self) -> None:
        assert str(ErrorCode.ENV_ERROR) == "env error"

    def test_build_error_str(self) -> None:
        assert str(ErrorCode.BUILD_ERROR) == "build error"

    def test_network_error_str(self) -> None:
        assert str(ErrorCode.NETWORK_ERROR) == "network error"

    def test_io_error_str(self) -> None:
        assert str(ErrorCode.IO_ERROR) == "io error"


class TestErrorCodeEnum:
    """Test enum behavior."""

    def test_all_codes_exist(self) -> None:
        """Ensure all expected codes are defined."""
        codes = list(ErrorCode)
        assert len(codes) == 6

    def test_codes_are_unique(self) -> None:
        """Ensure no duplicate values."""
        values = [code.value for code in ErrorCode]
        assert len(values) == len(set(values))

    def test_codes_are_sequential(self) -> None:
        """Ensure codes are 0-5."""
        values = sorted(code.value for code in ErrorCode)
        assert values == [0, 1, 2, 3, 4, 5]

    def test_lookup_by_name(self) -> None:
        """Can look up code by name."""
        assert ErrorCode["OK"] == ErrorCode.OK
        assert ErrorCode["USER_ERROR"] == ErrorCode.USER_ERROR

    def test_lookup_by_value(self) -> None:
        """Can look up code by value."""
        assert ErrorCode(0) == ErrorCode.OK
        assert ErrorCode(1) == ErrorCode.USER_ERROR
        assert ErrorCode(3) == ErrorCode.BUILD_ERROR

    def test_invalid_lookup_raises(self) -> None:
        """Looking up invalid value raises ValueError."""
        with pytest.raises(ValueError):
            ErrorCode(99)
