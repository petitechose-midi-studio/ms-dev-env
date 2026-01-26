"""Subprocess execution with Result-based error handling.

Provides a clean wrapper around subprocess.run that captures output
and returns structured errors instead of requiring try/except blocks.

Usage:
    result = run(["cmake", "--version"], cwd=Path("."))
    match result:
        case Ok(stdout):
            print(stdout)
        case Err(error):
            print(f"Failed: {error.stderr}")
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from ms.core.result import Err, Ok, Result

__all__ = ["ProcessError", "run", "run_silent"]


@dataclass(frozen=True, slots=True)
class ProcessError:
    """Error from a failed subprocess execution.

    Attributes:
        command: The command that was executed.
        returncode: The exit code of the process.
        stdout: Standard output (may be empty).
        stderr: Standard error (contains error details).
    """

    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str

    def __str__(self) -> str:
        """Format error for display."""
        cmd_str = " ".join(self.command[:3])
        if len(self.command) > 3:
            cmd_str += " ..."
        return f"{cmd_str} failed (exit {self.returncode})"


def run(
    cmd: list[str],
    cwd: Path,
    env: dict[str, str] | None = None,
    *,
    timeout: float | None = None,
) -> Result[str, ProcessError]:
    """Execute a command and return stdout or error.

    Args:
        cmd: Command and arguments to execute.
        cwd: Working directory for the command.
        env: Environment variables (uses current env if None).
        timeout: Maximum seconds to wait (None for no limit).

    Returns:
        Ok(stdout) on success, Err(ProcessError) on failure.

    Example:
        result = run(["git", "status"], cwd=repo_path)
        match result:
            case Ok(output):
                print(output)
            case Err(e):
                print(f"Git failed: {e.stderr}")
    """
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        return Err(
            ProcessError(
                command=tuple(cmd),
                returncode=-1,
                stdout=e.stdout or "" if isinstance(e.stdout, str) else "",
                stderr=f"Command timed out after {timeout}s",
            )
        )
    except OSError as e:
        return Err(
            ProcessError(
                command=tuple(cmd),
                returncode=-1,
                stdout="",
                stderr=str(e),
            )
        )

    if proc.returncode != 0:
        return Err(
            ProcessError(
                command=tuple(cmd),
                returncode=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
            )
        )

    return Ok(proc.stdout)


def run_silent(
    cmd: list[str],
    cwd: Path,
    env: dict[str, str] | None = None,
) -> Result[None, ProcessError]:
    """Execute a command without capturing output.

    Use this for commands where output should stream to terminal.
    Only captures stderr on failure.

    Args:
        cmd: Command and arguments to execute.
        cwd: Working directory for the command.
        env: Environment variables (uses current env if None).

    Returns:
        Ok(None) on success, Err(ProcessError) on failure.
    """
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            env=env,
            check=False,
        )
    except OSError as e:
        return Err(
            ProcessError(
                command=tuple(cmd),
                returncode=-1,
                stdout="",
                stderr=str(e),
            )
        )

    if proc.returncode != 0:
        return Err(
            ProcessError(
                command=tuple(cmd),
                returncode=proc.returncode,
                stdout="",
                stderr="",
            )
        )

    return Ok(None)
