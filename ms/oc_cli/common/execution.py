from __future__ import annotations

import contextlib
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def run_with_spinner(
    label: str,
    cmd: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
) -> tuple[int, str, int]:
    """Run command, capture output, show spinner; returns (code, output, seconds)."""
    start = time.time()

    fd, log_path = tempfile.mkstemp(prefix="oc_", suffix=".log")
    os.close(fd)

    with open(log_path, "wb") as log:
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(cwd),
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        except OSError as error:
            with contextlib.suppress(OSError):
                Path(log_path).unlink(missing_ok=True)
            return 127, f"{error}", 0

        frames = "|/-\\"
        idx = 0
        while proc.poll() is None:
            elapsed = int(time.time() - start)
            frame = frames[idx % len(frames)]
            idx += 1
            sys.stderr.write(f"\r{label} {frame} {elapsed}s   ")
            sys.stderr.flush()
            time.sleep(0.1)

        code = proc.wait()

    sys.stderr.write("\r" + (" " * 64) + "\r")
    sys.stderr.flush()

    try:
        output = Path(log_path).read_text(encoding="utf-8", errors="replace")
    finally:
        with contextlib.suppress(OSError):
            Path(log_path).unlink(missing_ok=True)

    seconds = int(time.time() - start)
    return code, output, seconds
