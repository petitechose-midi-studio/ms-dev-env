# SPDX-License-Identifier: MIT
"""Tests for CheckResult and CheckStatus."""

import pytest

from ms.services.checkers.base import CheckResult, CheckStatus


class TestCheckStatus:
    """Tests for CheckStatus enum."""

    def test_ok_status(self) -> None:
        assert CheckStatus.OK.name == "OK"

    def test_warning_status(self) -> None:
        assert CheckStatus.WARNING.name == "WARNING"

    def test_error_status(self) -> None:
        assert CheckStatus.ERROR.name == "ERROR"


class TestCheckResult:
    """Tests for CheckResult dataclass."""

    def test_success_factory(self) -> None:
        result = CheckResult.success("test", "passed")
        assert result.name == "test"
        assert result.status == CheckStatus.OK
        assert result.message == "passed"
        assert result.hint is None

    def test_warning_factory(self) -> None:
        result = CheckResult.warning("test", "optional missing", hint="install foo")
        assert result.name == "test"
        assert result.status == CheckStatus.WARNING
        assert result.message == "optional missing"
        assert result.hint == "install foo"

    def test_error_factory(self) -> None:
        result = CheckResult.error("test", "not found", hint="run setup")
        assert result.name == "test"
        assert result.status == CheckStatus.ERROR
        assert result.message == "not found"
        assert result.hint == "run setup"

    def test_ok_property_for_success(self) -> None:
        result = CheckResult.success("test", "ok")
        assert result.ok is True
        assert result.is_error is False
        assert result.is_warning is False

    def test_ok_property_for_warning(self) -> None:
        result = CheckResult.warning("test", "warn")
        assert result.ok is True  # Warnings still count as "ok"
        assert result.is_error is False
        assert result.is_warning is True

    def test_ok_property_for_error(self) -> None:
        result = CheckResult.error("test", "fail")
        assert result.ok is False
        assert result.is_error is True
        assert result.is_warning is False

    def test_frozen_dataclass(self) -> None:
        result = CheckResult.success("test", "ok")
        with pytest.raises(AttributeError):
            result.name = "changed"  # type: ignore[misc]

    def test_hint_default_none(self) -> None:
        result = CheckResult(
            name="test",
            status=CheckStatus.OK,
            message="ok",
        )
        assert result.hint is None
