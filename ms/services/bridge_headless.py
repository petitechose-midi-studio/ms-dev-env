from __future__ import annotations

import contextlib
import errno
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from ms.core.config import Config
from ms.core.result import Err, Ok, Result
from ms.output.console import Style
from ms.services.bridge import BridgeService

if TYPE_CHECKING:
    from ms.core.workspace import Workspace
    from ms.output.console import ConsoleProtocol
    from ms.platform.detection import PlatformInfo


Mode = Literal["native", "wasm"]


@dataclass(frozen=True, slots=True)
class BridgeHeadlessSpec:
    mode: Mode
    controller: Literal["udp", "ws"]
    controller_port: int
    host_udp_port: int


@dataclass(frozen=True, slots=True)
class BridgeHeadlessError:
    kind: Literal[
        "bridge_missing",
        "ports_in_use",
        "spawn_failed",
        "not_ready",
    ]
    message: str
    hint: str | None = None


def _controller_port_for_app(config: Config, *, app_name: str, mode: Mode) -> int:
    c = config.ports.controller

    if app_name == "core":
        return c.core_native if mode == "native" else c.core_wasm
    if app_name == "bitwig":
        return c.bitwig_native if mode == "native" else c.bitwig_wasm

    # Unknown apps fall back to core ports to keep the CLI usable.
    # This may collide; callers should warn.
    return c.core_native if mode == "native" else c.core_wasm


def spec_for(config: Config, *, app_name: str, mode: Mode) -> BridgeHeadlessSpec:
    controller_port = _controller_port_for_app(config, app_name=app_name, mode=mode)
    host_udp_port = config.ports.native if mode == "native" else config.ports.wasm
    controller: Literal["udp", "ws"] = "udp" if mode == "native" else "ws"
    return BridgeHeadlessSpec(
        mode=mode,
        controller=controller,
        controller_port=controller_port,
        host_udp_port=host_udp_port,
    )


def _udp_port_in_use(port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.bind(("127.0.0.1", port))
        return False
    except OSError as e:
        if e.errno == errno.EADDRINUSE:
            return True
        raise
    finally:
        with contextlib.suppress(OSError):
            s.close()


def _tcp_port_open(port: int, *, timeout_s: float = 0.2) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout_s):
            return True
    except OSError:
        return False


class HeadlessBridge:
    """Lifecycle wrapper for an oc-bridge headless subprocess.

    - If `proc` is None, the bridge is assumed to already exist (reuse).
    """

    def __init__(
        self,
        *,
        proc: subprocess.Popen[bytes] | None,
        spec: BridgeHeadlessSpec,
        console: ConsoleProtocol,
    ) -> None:
        self._proc = proc
        self._spec = spec
        self._console = console

    @property
    def proc(self) -> subprocess.Popen[bytes] | None:
        return self._proc

    @property
    def spec(self) -> BridgeHeadlessSpec:
        return self._spec

    def stop(self) -> None:
        p = self._proc
        if p is None:
            return
        if p.poll() is not None:
            return

        try:
            p.terminate()
        except OSError:
            return

        try:
            p.wait(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                p.kill()
            except OSError:
                return
            try:
                p.wait(timeout=2)
            except subprocess.TimeoutExpired:
                return

    def __enter__(self) -> HeadlessBridge:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object | None,
    ) -> None:
        self.stop()


def start_headless_bridge(
    *,
    workspace: Workspace,
    platform: PlatformInfo,
    config: Config,
    console: ConsoleProtocol,
    app_name: str,
    mode: Mode,
) -> Result[HeadlessBridge, BridgeHeadlessError]:
    spec = spec_for(config, app_name=app_name, mode=mode)

    if app_name not in ("core", "bitwig"):
        console.print(
            f"warning: unknown app '{app_name}', using core controller ports",
            Style.WARNING,
        )

    # Collision detection / reuse
    # - For WS: if controller port is already open, assume an existing bridge and reuse.
    # - For UDP: we can't probe liveness, so we check host/controller ports.
    host_in_use = _udp_port_in_use(spec.host_udp_port)
    if spec.controller == "ws":
        if _tcp_port_open(spec.controller_port):
            console.print(
                f"warning: bridge already listening on ws:{spec.controller_port} (reusing)",
                Style.WARNING,
            )
            return Ok(HeadlessBridge(proc=None, spec=spec, console=console))

        if host_in_use:
            return Err(
                BridgeHeadlessError(
                    kind="ports_in_use",
                    message=(f"host UDP port already in use: {spec.host_udp_port} (wasm mode)"),
                    hint="Stop the existing bridge using that port, or change config.toml ports.",
                )
            )
    else:
        ctrl_in_use = _udp_port_in_use(spec.controller_port)
        if host_in_use and ctrl_in_use:
            console.print(
                "warning: native bridge ports already in use "
                f"(udp:{spec.controller_port} -> host:{spec.host_udp_port}); "
                "assuming existing bridge (reusing)",
                Style.WARNING,
            )
            return Ok(HeadlessBridge(proc=None, spec=spec, console=console))
        if host_in_use:
            return Err(
                BridgeHeadlessError(
                    kind="ports_in_use",
                    message=f"host UDP port already in use: {spec.host_udp_port} (native mode)",
                    hint="Stop the existing bridge using that port, or change config.toml ports.",
                )
            )
        if ctrl_in_use:
            return Err(
                BridgeHeadlessError(
                    kind="ports_in_use",
                    message=(
                        f"controller UDP port already in use: {spec.controller_port} (native mode)"
                    ),
                    hint="Stop the existing bridge using that port, or change config.toml ports.",
                )
            )

    # Ensure oc-bridge exists.
    bridge_svc = BridgeService(
        workspace=workspace,
        platform=platform,
        config=config,
        console=console,
    )

    install = bridge_svc.install_prebuilt()
    if isinstance(install, Err):
        return Err(
            BridgeHeadlessError(
                kind="bridge_missing",
                message=install.error.message,
                hint=install.error.hint,
            )
        )

    exe: Path = install.value
    cmd = [
        str(exe),
        "--headless",
        "--controller",
        spec.controller,
        "--controller-port",
        str(spec.controller_port),
        "--udp-port",
        str(spec.host_udp_port),
    ]

    console.print(" ".join(cmd), Style.DIM)

    try:
        proc = subprocess.Popen(cmd, cwd=str(workspace.root))
    except OSError as e:
        return Err(
            BridgeHeadlessError(
                kind="spawn_failed",
                message=f"failed to start oc-bridge: {e}",
            )
        )

    # Readiness: ensure the bridge is alive and, for WS, that the port is open.
    deadline = time.time() + 2.0
    if spec.controller == "ws":
        while time.time() < deadline:
            if proc.poll() is not None:
                return Err(
                    BridgeHeadlessError(
                        kind="spawn_failed",
                        message=f"oc-bridge exited early (code {proc.returncode})",
                    )
                )
            if _tcp_port_open(spec.controller_port, timeout_s=0.1):
                return Ok(HeadlessBridge(proc=proc, spec=spec, console=console))
            time.sleep(0.05)
        return Err(
            BridgeHeadlessError(
                kind="not_ready",
                message=f"oc-bridge WS port did not open in time: {spec.controller_port}",
            )
        )

    # UDP controller: just ensure it didn't exit immediately.
    time.sleep(0.1)
    if proc.poll() is not None:
        return Err(
            BridgeHeadlessError(
                kind="spawn_failed",
                message=f"oc-bridge exited early (code {proc.returncode})",
            )
        )

    return Ok(HeadlessBridge(proc=proc, spec=spec, console=console))
