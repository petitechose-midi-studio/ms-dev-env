from __future__ import annotations

import sys

from ms.core.config import CONTROLLER_CORE_NATIVE_PORT, Config
from ms.core.errors import ErrorCode
from ms.core.result import Err, Ok
from ms.output.console import Style
from ms.platform.process import run_silent
from ms.services.bridge_headless import spec_for, start_headless_bridge

from .targets import BuildTargetsMixin


class BuildRuntimeMixin(BuildTargetsMixin):
    def run_native(self, *, app_name: str) -> int:
        result = self.build_native(app_name=app_name)

        match result:
            case Ok(exe_path):
                cfg = self._config or Config()
                bridge = start_headless_bridge(
                    workspace=self._workspace,
                    platform=self._platform,
                    config=cfg,
                    console=self._console,
                    app_name=app_name,
                    mode="native",
                )
                if isinstance(bridge, Err):
                    self._console.error(bridge.error.message)
                    if bridge.error.hint:
                        self._console.print(f"hint: {bridge.error.hint}", Style.DIM)
                    return int(ErrorCode.ENV_ERROR)

                with bridge.value:
                    self._console.print(f"run: {exe_path}", Style.DIM)
                    args = [
                        str(exe_path),
                        "1053",
                        "--bridge-udp-port",
                        str(bridge.value.spec.controller_port),
                    ]
                    try:
                        run_result = run_silent(args, cwd=self._workspace.root, timeout=None)
                    except KeyboardInterrupt:
                        return 0

                    match run_result:
                        case Ok(_):
                            return 0
                        case Err(e):
                            return e.returncode
            case Err(error):
                self._print_build_error(error)
                return self._error_to_exit_code(error)

        return 1

    def serve_wasm(self, *, app_name: str, port: int = CONTROLLER_CORE_NATIVE_PORT) -> int:
        result = self.build_wasm(app_name=app_name)

        match result:
            case Ok(html_path):
                cfg = self._config or Config()
                expected_ws_port = spec_for(cfg, app_name=app_name, mode="wasm").controller_port
                if int(port) == int(expected_ws_port):
                    self._console.error(
                        f"HTTP port {port} conflicts with bridge WS port {expected_ws_port}"
                    )
                    return int(ErrorCode.USER_ERROR)

                bridge = start_headless_bridge(
                    workspace=self._workspace,
                    platform=self._platform,
                    config=cfg,
                    console=self._console,
                    app_name=app_name,
                    mode="wasm",
                )
                if isinstance(bridge, Err):
                    self._console.error(bridge.error.message)
                    if bridge.error.hint:
                        self._console.print(f"hint: {bridge.error.hint}", Style.DIM)
                    return int(ErrorCode.ENV_ERROR)

                out_dir = html_path.parent
                url_path = html_path.name
                ws_port = bridge.value.spec.controller_port
                self._console.print(
                    f"serve: http://localhost:{port}/{url_path}?bridgeWsPort={ws_port}",
                    Style.INFO,
                )

                with bridge.value:
                    cmd = [sys.executable, "-m", "http.server", str(port), "-d", str(out_dir)]
                    try:
                        run_result = run_silent(cmd, cwd=self._workspace.root, timeout=None)
                    except KeyboardInterrupt:
                        return 0
                    match run_result:
                        case Ok(_):
                            return 0
                        case Err(e):
                            return e.returncode
            case Err(error):
                self._print_build_error(error)
                return self._error_to_exit_code(error)

        return 1
