"""Tests for ms.platform.process module."""

from __future__ import annotations

from pathlib import Path

import pytest

from ms.core.result import Err, Ok
from ms.platform.process import ProcessError, run, run_silent


class TestProcessError:
    """Test ProcessError dataclass."""

    def test_str_short_command(self) -> None:
        error = ProcessError(
            command=("git", "status"),
            returncode=1,
            stdout="",
            stderr="fatal: not a git repository",
        )
        assert str(error) == "git status failed (exit 1)"

    def test_str_long_command_truncated(self) -> None:
        error = ProcessError(
            command=("cmake", "-G", "Ninja", "-S", "src", "-B", "build"),
            returncode=1,
            stdout="",
            stderr="error",
        )
        assert str(error) == "cmake -G Ninja ... failed (exit 1)"

    def test_frozen(self) -> None:
        error = ProcessError(("cmd",), 1, "", "")
        with pytest.raises(AttributeError):
            error.returncode = 2  # type: ignore[misc]


class TestRun:
    """Test run function."""

    def test_success_returns_stdout(self, tmp_path: Path) -> None:
        # Use a command that works on all platforms
        result = run(["python", "-c", "print('hello')"], cwd=tmp_path)

        assert isinstance(result, Ok)
        assert "hello" in result.value

    def test_failure_returns_error(self, tmp_path: Path) -> None:
        result = run(["python", "-c", "import sys; sys.exit(42)"], cwd=tmp_path)

        assert isinstance(result, Err)
        assert result.error.returncode == 42

    def test_command_not_found(self, tmp_path: Path) -> None:
        result = run(["nonexistent_command_12345"], cwd=tmp_path)

        assert isinstance(result, Err)
        assert result.error.returncode == -1
        # Error message varies by OS and locale
        assert len(result.error.stderr) > 0

    def test_captures_stderr(self, tmp_path: Path) -> None:
        # Test stderr capture on failure (exit 1)
        result = run(
            ["python", "-c", "import sys; sys.stderr.write('error msg'); sys.exit(1)"],
            cwd=tmp_path,
        )

        assert isinstance(result, Err)
        assert "error msg" in result.error.stderr

    def test_uses_cwd(self, tmp_path: Path) -> None:
        # Create a file in tmp_path
        (tmp_path / "test.txt").write_text("content")

        result = run(["python", "-c", "import os; print(os.listdir('.'))"], cwd=tmp_path)

        assert isinstance(result, Ok)
        assert "test.txt" in result.value

    def test_uses_env(self, tmp_path: Path) -> None:
        import os

        env = os.environ.copy()
        env["TEST_VAR_12345"] = "test_value"

        result = run(
            ["python", "-c", "import os; print(os.environ.get('TEST_VAR_12345', ''))"],
            cwd=tmp_path,
            env=env,
        )

        assert isinstance(result, Ok)
        assert "test_value" in result.value

    def test_timeout(self, tmp_path: Path) -> None:
        result = run(
            ["python", "-c", "import time; time.sleep(10)"],
            cwd=tmp_path,
            timeout=0.1,
        )

        assert isinstance(result, Err)
        assert "timed out" in result.error.stderr.lower()


class TestRunSilent:
    """Test run_silent function."""

    def test_success_returns_none(self, tmp_path: Path) -> None:
        result = run_silent(["python", "-c", "pass"], cwd=tmp_path, timeout=1.0)

        assert isinstance(result, Ok)
        assert result.value is None

    def test_failure_returns_error(self, tmp_path: Path) -> None:
        result = run_silent(
            ["python", "-c", "import sys; sys.exit(1)"],
            cwd=tmp_path,
            timeout=1.0,
        )

        assert isinstance(result, Err)
        assert result.error.returncode == 1

    def test_failure_captures_stderr(self, tmp_path: Path) -> None:
        result = run_silent(
            ["python", "-c", "import sys; sys.stderr.write('boom'); sys.exit(2)"],
            cwd=tmp_path,
            timeout=1.0,
        )

        assert isinstance(result, Err)
        assert result.error.returncode == 2
        assert "boom" in result.error.stderr

    def test_timeout_returns_error(self, tmp_path: Path) -> None:
        result = run_silent(
            ["python", "-c", "import time; time.sleep(10)"],
            cwd=tmp_path,
            timeout=0.1,
        )

        assert isinstance(result, Err)
        assert "timed out" in result.error.stderr.lower()

    def test_command_not_found(self, tmp_path: Path) -> None:
        result = run_silent(["nonexistent_command_12345"], cwd=tmp_path, timeout=1.0)

        assert isinstance(result, Err)
        assert result.error.returncode == -1
