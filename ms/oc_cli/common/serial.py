from __future__ import annotations

import json
import re
import subprocess
import sys
import time

from ms.core.structured import as_obj_list, as_str_dict, get_str

from .models import OCPlatform


def kill_monitors(platform: OCPlatform) -> None:
    """Best-effort: kill existing `pio device monitor` processes."""
    if platform.is_windows:
        cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            (
                "Get-CimInstance Win32_Process | "
                "Where-Object { $_.Name -match 'python' "
                "-and $_.CommandLine -match 'device.*monitor|platformio.*monitor' } | "
                "ForEach-Object { Stop-Process -Id $_.ProcessId -Force "
                "-ErrorAction SilentlyContinue }"
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
        ports = re.findall(r'"port"\s*:\s*"([^"]+)"', raw)

    filtered: list[str] = []
    for port in ports:
        if re.match(r"^COM1$", port):
            continue
        if re.match(r"^/dev/ttyS\d+$", port):
            continue
        filtered.append(port)
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
