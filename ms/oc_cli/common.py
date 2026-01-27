"""Shared utilities for oc-* Python commands.

Goals:
- Keep the UX close to the previous oc-* bash scripts (spinner + compact summary)
- Stay cross-platform (no bash)
- Avoid requiring PlatformIO to be installed globally (honor $PIO and ms workspace toolchain)
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path


from rich.console import Console


__all__ = [
    "OCContext",
    "OCPlatform",
    "build_pio_env",
    "detect_env",
    "find_project_root",
    "get_console",
    "kill_monitors",
    "list_serial_ports",
    "run_with_spinner",
    "show_results",
    "wait_for_serial_port",
]


_RE_FLASH = re.compile(r"teensy_size:.*FLASH:")
_RE_RAM1 = re.compile(r"teensy_size:.*RAM1:")
_RE_RAM2 = re.compile(r"teensy_size:.*RAM2:")
_RE_EXTRAM = re.compile(r"teensy_size:.*EXTRAM:")


class OCPlatform:
    """Minimal platform helper."""

    def __init__(self) -> None:
        self.is_windows = os.name == "nt"


@dataclass(frozen=True, slots=True)
class OCContext:
    project_root: Path
    env_name: str
    pio: str
    platform: OCPlatform


def get_console() -> Console:
    # highlight=False avoids accidental syntax highlighting in build logs
    return Console(highlight=False)


def find_project_root(start: Path | None = None) -> Path:
    """Walk upward from start (or cwd) to find platformio.ini."""
    base = (start or Path.cwd()).resolve()
    for parent in (base, *base.parents):
        if (parent / "platformio.ini").is_file():
            return parent
    raise FileNotFoundError("platformio.ini not found (run from project directory)")


def _find_workspace_root(start: Path) -> Path | None:
    """Walk upward to find a ms workspace root (.ms-workspace)."""
    base = start.resolve()
    for parent in (base, *base.parents):
        if (parent / ".ms-workspace").is_file():
            return parent
    return None


def _resolve_pio_cmd(start: Path, platform: OCPlatform) -> str:
    """Resolve the PlatformIO executable.

    Resolution order:
    1) $PIO
    2) workspace-local tools/platformio/venv
    3) fallback: "pio" (PATH)
    """
    explicit = os.environ.get("PIO")
    if explicit:
        return explicit

    ws = _find_workspace_root(start)
    if ws is None:
        return "pio"

    venv = ws / "tools" / "platformio" / "venv"
    pio = venv / ("Scripts/pio.exe" if platform.is_windows else "bin/pio")
    if pio.exists():
        return str(pio)

    return "pio"


def build_pio_env(start: Path, platform: OCPlatform) -> dict[str, str]:
    """Build an env dict that isolates PlatformIO to the workspace when possible."""
    env = dict(os.environ)
    ws = _find_workspace_root(start)
    if ws is None:
        return env

    ms_state = ws / ".ms"
    env.setdefault("PLATFORMIO_CORE_DIR", str(ms_state / "platformio"))
    env.setdefault("PLATFORMIO_CACHE_DIR", str(ms_state / "platformio-cache"))
    env.setdefault("PLATFORMIO_BUILD_CACHE_DIR", str(ms_state / "platformio-build-cache"))

    # If PIO wasn't set by the caller, try workspace toolchain.
    env.setdefault("PIO", _resolve_pio_cmd(start, platform))
    return env


def detect_env(project_root: Path, explicit: str | None) -> str:
    """Detect PlatformIO env (matches the previous oc-* behavior)."""
    if explicit:
        return explicit

    build_dir = project_root / ".pio" / "build"
    if build_dir.is_dir():
        dirs = [p for p in build_dir.iterdir() if p.is_dir() and p.name != "build"]
        if dirs:
            dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            return dirs[0].name

    # Fallback to default_envs or dev
    ini = project_root / "platformio.ini"
    try:
        for line in ini.read_text(encoding="utf-8", errors="replace").splitlines():
            raw = line.strip()
            if not raw or raw.startswith(";") or raw.startswith("#"):
                continue
            if raw.startswith("default_envs"):
                _, _, rhs = raw.partition("=")
                candidates = [c.strip() for c in rhs.split(",")]
                for c in candidates:
                    if c:
                        # default_envs can contain multiple entries
                        return c.split()[0]
    except OSError:
        pass

    return "dev"


def _draw_bar(pct: int, width: int = 16) -> str:
    filled = max(0, min(width, pct * width // 100))
    return "#" * filled + "-" * (width - filled)


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

    # Write output to a file to avoid pipe deadlocks on large logs.
    with open(log_path, "wb") as log:
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(cwd),
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        except OSError as e:
            try:
                Path(log_path).unlink(missing_ok=True)
            except OSError:
                pass
            return 127, f"{e}", 0

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

    # Clear spinner line
    sys.stderr.write("\r" + (" " * 64) + "\r")
    sys.stderr.flush()

    try:
        output = Path(log_path).read_text(encoding="utf-8", errors="replace")
    finally:
        try:
            Path(log_path).unlink(missing_ok=True)
        except OSError:
            pass

    seconds = int(time.time() - start)
    return code, output, seconds


def _parse_env_symlink_libs(
    platformio_ini: Path, env_name: str, project_root: Path
) -> dict[str, Path]:
    """Parse lines like `MyLib = symlink://path` from a PlatformIO env section."""
    try:
        lines = platformio_ini.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {}

    header = f"[env:{env_name}]".lower()
    in_section = False
    mapping: dict[str, Path] = {}
    for raw in lines:
        s = raw.strip()
        if not s:
            continue
        if s.startswith("[") and s.endswith("]"):
            in_section = s.lower() == header
            continue
        if not in_section:
            continue

        m = re.match(r"^([A-Za-z0-9_-]+)\s*=\s*symlink://(.+)$", s)
        if not m:
            continue
        name = m.group(1)
        rel = m.group(2).strip()
        mapping[name] = (project_root / rel).resolve()
    return mapping


def _show_dependencies(console: Console, output: str, project_root: Path, env_name: str) -> None:
    platformio_ini = project_root / "platformio.ini"
    symlinks = _parse_env_symlink_libs(platformio_ini, env_name, project_root)

    deps = [line for line in output.splitlines() if line.lstrip().startswith("|--")]
    if not deps:
        return

    console.print("Dependencies", style="dim")
    shown = 0
    for line in deps:
        if shown >= 10:
            break

        rest = line.lstrip()[3:].strip()
        lib = rest.split()[0] if rest else ""
        ver_match = re.search(r"@\s*([0-9][0-9.]*)", rest)
        ver = ver_match.group(1) if ver_match else ""

        path = symlinks.get(lib)
        if path is not None and path.is_dir():
            suffix = f" -> {path.name}"
        else:
            suffix = ""

        if ver:
            console.print(f"  {lib} @ {ver}{suffix}", style="dim")
        else:
            console.print(f"  {lib}{suffix}", style="dim")
        shown += 1

    console.print()


def _show_memory(console: Console, output: str) -> None:
    lines = output.splitlines()

    flash_line = next((l for l in lines if _RE_FLASH.search(l)), "")
    ram1_line = next((l for l in lines if _RE_RAM1.search(l)), "")
    ram2_line = next((l for l in lines if _RE_RAM2.search(l)), "")
    extram_line = next((l for l in lines if _RE_EXTRAM.search(l)), "")

    if not flash_line:
        return

    console.print("Memory", style="dim")

    def _num(pattern: str, s: str) -> int | None:
        m = re.search(pattern, s)
        return int(m.group(1)) if m else None

    # FLASH
    flash_code = _num(r"code:(\d+)", flash_line) or 0
    flash_data = _num(r"data:(\d+)", flash_line) or 0
    flash_hdr = _num(r"headers:(\d+)", flash_line) or 0
    flash_free = _num(r"free for files:(\d+)", flash_line) or 0
    flash_used = flash_code + flash_data + flash_hdr
    flash_total = flash_used + flash_free
    flash_pct = int((flash_used * 100 / flash_total) if flash_total else 0)
    flash_kb = flash_used // 1024
    flash_total_mb = flash_total / 1024 / 1024 if flash_total else 0.0
    console.print(
        f"  FLASH {_draw_bar(flash_pct)} {flash_kb}KB/{flash_total_mb:.1f}MB ({flash_pct}%)",
        style="dim",
    )

    # RAM1
    if ram1_line:
        ram1_vars = _num(r"variables:(\d+)", ram1_line)
        ram1_code = _num(r"code:(\d+)", ram1_line)
        ram1_pad = _num(r"padding:(\d+)", ram1_line)
        ram1_free = _num(r"free for local variables:(\d+)", ram1_line)
        if None not in (ram1_vars, ram1_code, ram1_pad, ram1_free):
            ram1_used = int(ram1_vars + ram1_code + ram1_pad)  # type: ignore[operator]
            ram1_total = int(ram1_used + ram1_free)  # type: ignore[operator]
            ram1_pct = int((ram1_used * 100 / ram1_total) if ram1_total else 0)
            console.print(
                f"  RAM1  {_draw_bar(ram1_pct)} {ram1_used // 1024}KB/{ram1_total // 1024}KB ({ram1_pct}%)",
                style="dim",
            )

    # RAM2
    if ram2_line:
        ram2_vars = _num(r"variables:(\d+)", ram2_line)
        ram2_free = _num(r"free for malloc/new:(\d+)", ram2_line)
        if None not in (ram2_vars, ram2_free):
            ram2_used = int(ram2_vars)  # type: ignore[arg-type]
            ram2_total = int(ram2_used + ram2_free)  # type: ignore[operator]
            ram2_pct = int((ram2_used * 100 / ram2_total) if ram2_total else 0)
            console.print(
                f"  RAM2  {_draw_bar(ram2_pct)} {ram2_used // 1024}KB/{ram2_total // 1024}KB ({ram2_pct}%)",
                style="dim",
            )

    # EXTRAM (PSRAM)
    if extram_line:
        extram_vars = _num(r"variables:(\d+)", extram_line)
        if extram_vars is not None:
            extram_total = 8 * 1024 * 1024
            extram_pct = int((extram_vars * 100 / extram_total) if extram_total else 0)
            console.print(
                f"  PSRAM {_draw_bar(extram_pct)} {extram_vars // 1024}KB/8MB ({extram_pct}%)",
                style="dim",
            )

    console.print()


def _show_warnings(console: Console, output: str) -> None:
    warnings = [l for l in output.splitlines() if "warning:" in l]
    if not warnings:
        return

    console.print(f"Warnings: {len(warnings)}", style="yellow")
    for line in warnings[:5]:
        m = re.match(r"(.+?):(\d+):\d*:?\s*warning:\s*(.*)", line)
        if m:
            file = Path(m.group(1)).name
            num = m.group(2)
            msg = m.group(3).strip()
            console.print(f"  {file}:{num} {msg}", style="yellow")
        else:
            console.print(f"  {line.strip()}", style="yellow")
    if len(warnings) > 5:
        console.print(f"  ... and {len(warnings) - 5} more", style="dim")
    console.print()


def _show_errors(console: Console, output: str) -> None:
    errors = [l for l in output.splitlines() if "error:" in l]
    if not errors:
        return

    console.print(f"Errors: {len(errors)}", style="red")
    for line in errors[:5]:
        m = re.match(r"(.+?):(\d+):\d*:?\s*error:\s*(.*)", line)
        if m:
            file = Path(m.group(1)).name
            num = m.group(2)
            msg = m.group(3).strip()
            console.print(f"  {file}:{num} {msg}", style="red")
        else:
            console.print(f"  {line.strip()}", style="red")
    if len(errors) > 5:
        console.print(f"  ... and {len(errors) - 5} more", style="dim")
    console.print()


def show_results(
    console: Console,
    *,
    output: str,
    project_root: Path,
    env_name: str,
    status: int,
    seconds: int,
) -> int:
    _show_dependencies(console, output, project_root, env_name)
    _show_memory(console, output)
    _show_warnings(console, output)

    if status != 0:
        _show_errors(console, output)
        console.print(f"BUILD FAILED {seconds}s", style="red bold")
        return 1

    if "Uploading" in output:
        console.print(f"BUILD OK Uploaded in {seconds}s", style="green bold")
    else:
        console.print(f"BUILD OK {seconds}s", style="green bold")
    console.print()
    return 0


def kill_monitors(platform: OCPlatform) -> None:
    """Best-effort: kill existing `pio device monitor` processes."""
    if platform.is_windows:
        cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            (
                "Get-CimInstance Win32_Process | "
                "Where-Object { $_.Name -match 'python' -and $_.CommandLine -match 'device.*monitor|platformio.*monitor' } | "
                "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
            ),
        ]
        subprocess.run(cmd, capture_output=True, text=True, check=False)
    else:
        subprocess.run(["pkill", "-f", "pio device monitor"], check=False)
        subprocess.run(["pkill", "-f", "minicom.*tty"], check=False)
        subprocess.run(["pkill", "-f", "screen.*/dev/tty"], check=False)

    time.sleep(0.3)


def list_serial_ports(pio: str, *, env: dict[str, str]) -> list[str]:
    cmd = [pio, "device", "list", "--json-output"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env, check=False)
    except OSError:
        return []

    if proc.returncode != 0:
        return []

    raw = proc.stdout.strip()
    if not raw:
        return []

    ports: list[str] = []
    try:
        from ms.core.structured import as_obj_list, as_str_dict, get_str

        data_obj: object = json.loads(raw)
        items = as_obj_list(data_obj)
        if items is not None:
            for item in items:
                d = as_str_dict(item)
                if d is None:
                    continue
                port = get_str(d, "port")
                if port:
                    ports.append(port)
    except json.JSONDecodeError:
        # Fallback: regex extract "port": "..."
        ports = re.findall(r"\"port\"\s*:\s*\"([^\"]+)\"", raw)

    filtered: list[str] = []
    for p in ports:
        if re.match(r"^COM1$", p):
            continue
        if re.match(r"^/dev/ttyS\d+$", p):
            continue
        filtered.append(p)
    return filtered


def wait_for_serial_port(
    pio: str,
    *,
    env: dict[str, str],
    timeout_s: int = 5,
) -> str | None:
    start = time.time()
    while int(time.time() - start) < timeout_s:
        ports = list_serial_ports(pio, env=env)
        if ports:
            sys.stderr.write("\r" + (" " * 48) + "\r")
            sys.stderr.flush()
            return ports[0]

        elapsed = int(time.time() - start)
        sys.stderr.write(f"\rWaiting for device... {elapsed}s   ")
        sys.stderr.flush()
        time.sleep(0.5)

    sys.stderr.write("\r" + (" " * 48) + "\r")
    sys.stderr.flush()
    return None
