from __future__ import annotations

import re
from pathlib import Path

from rich.console import Console

_RE_FLASH = re.compile(r"teensy_size:.*FLASH:")
_RE_RAM1 = re.compile(r"teensy_size:.*RAM1:")
_RE_RAM2 = re.compile(r"teensy_size:.*RAM2:")
_RE_EXTRAM = re.compile(r"teensy_size:.*EXTRAM:")


def _draw_bar(pct: int, width: int = 16) -> str:
    filled = max(0, min(width, pct * width // 100))
    return "#" * filled + "-" * (width - filled)


def _parse_env_symlink_libs(
    platformio_ini: Path,
    env_name: str,
    project_root: Path,
) -> dict[str, Path]:
    try:
        lines = platformio_ini.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {}

    header = f"[env:{env_name}]".lower()
    in_section = False
    mapping: dict[str, Path] = {}
    for raw in lines:
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            in_section = stripped.lower() == header
            continue
        if not in_section:
            continue

        match = re.match(r"^([A-Za-z0-9_-]+)\s*=\s*symlink://(.+)$", stripped)
        if not match:
            continue
        name = match.group(1)
        rel = match.group(2).strip()
        mapping[name] = (project_root / rel).resolve()
    return mapping


def _show_dependencies(console: Console, output: str, project_root: Path, env_name: str) -> None:
    platformio_ini = project_root / "platformio.ini"
    symlinks = _parse_env_symlink_libs(platformio_ini, env_name, project_root)

    deps = [line for line in output.splitlines() if line.lstrip().startswith("|--")]
    if not deps:
        return

    console.print("Dependencies", style="dim")
    for shown, line in enumerate(deps):
        if shown >= 10:
            break

        rest = line.lstrip()[3:].strip()
        lib = rest.split()[0] if rest else ""
        ver_match = re.search(r"@\s*([0-9][0-9.]*)", rest)
        ver = ver_match.group(1) if ver_match else ""

        path = symlinks.get(lib)
        suffix = f" -> {path.name}" if path is not None and path.is_dir() else ""

        if ver:
            console.print(f"  {lib} @ {ver}{suffix}", style="dim")
        else:
            console.print(f"  {lib}{suffix}", style="dim")

    console.print()


def _show_memory(console: Console, output: str) -> None:
    lines = output.splitlines()

    flash_line = next((line for line in lines if _RE_FLASH.search(line)), "")
    ram1_line = next((line for line in lines if _RE_RAM1.search(line)), "")
    ram2_line = next((line for line in lines if _RE_RAM2.search(line)), "")
    extram_line = next((line for line in lines if _RE_EXTRAM.search(line)), "")

    if not flash_line:
        return

    console.print("Memory", style="dim")

    def _num(pattern: str, value: str) -> int | None:
        match = re.search(pattern, value)
        return int(match.group(1)) if match else None

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

    if ram1_line:
        ram1_vars = _num(r"variables:(\d+)", ram1_line)
        ram1_code = _num(r"code:(\d+)", ram1_line)
        ram1_pad = _num(r"padding:(\d+)", ram1_line)
        ram1_free = _num(r"free for local variables:(\d+)", ram1_line)
        if (
            ram1_vars is not None
            and ram1_code is not None
            and ram1_pad is not None
            and ram1_free is not None
        ):
            ram1_used = ram1_vars + ram1_code + ram1_pad
            ram1_total = ram1_used + ram1_free
            ram1_pct = int((ram1_used * 100 / ram1_total) if ram1_total else 0)
            console.print(
                "  RAM1  "
                f"{_draw_bar(ram1_pct)} {ram1_used // 1024}KB/{ram1_total // 1024}KB ({ram1_pct}%)",
                style="dim",
            )

    if ram2_line:
        ram2_vars = _num(r"variables:(\d+)", ram2_line)
        ram2_free = _num(r"free for malloc/new:(\d+)", ram2_line)
        if ram2_vars is not None and ram2_free is not None:
            ram2_used = ram2_vars
            ram2_total = ram2_used + ram2_free
            ram2_pct = int((ram2_used * 100 / ram2_total) if ram2_total else 0)
            console.print(
                "  RAM2  "
                f"{_draw_bar(ram2_pct)} {ram2_used // 1024}KB/{ram2_total // 1024}KB ({ram2_pct}%)",
                style="dim",
            )

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
    warnings = [line for line in output.splitlines() if "warning:" in line]
    if not warnings:
        return

    console.print(f"Warnings: {len(warnings)}", style="yellow")
    for line in warnings[:5]:
        match = re.match(r"(.+?):(\d+):\d*:?\s*warning:\s*(.*)", line)
        if match:
            file = Path(match.group(1)).name
            num = match.group(2)
            msg = match.group(3).strip()
            console.print(f"  {file}:{num} {msg}", style="yellow")
        else:
            console.print(f"  {line.strip()}", style="yellow")
    if len(warnings) > 5:
        console.print(f"  ... and {len(warnings) - 5} more", style="dim")
    console.print()


def _show_errors(console: Console, output: str) -> None:
    errors = [line for line in output.splitlines() if "error:" in line]
    if not errors:
        return

    console.print(f"Errors: {len(errors)}", style="red")
    for line in errors[:5]:
        match = re.match(r"(.+?):(\d+):\d*:?\s*error:\s*(.*)", line)
        if match:
            file = Path(match.group(1)).name
            num = match.group(2)
            msg = match.group(3).strip()
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
