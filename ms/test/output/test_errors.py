from __future__ import annotations

from ms.output.console import MockConsole
from ms.output.errors import print_build_error
from ms.services.build_errors import CompileFailed, ConfigureFailed


def test_configure_failure_prints_cmake_diagnostics() -> None:
    console = MockConsole()

    print_build_error(
        ConfigureFailed(returncode=1, details="CMake Error: missing compiler\n"),
        console,
    )

    assert "cmake configure failed (exit 1)" in console.text
    assert "CMake Error: missing compiler" in console.text


def test_compile_failure_prints_build_diagnostics() -> None:
    console = MockConsole()

    print_build_error(
        CompileFailed(returncode=1, details="ninja: build stopped\n"),
        console,
    )

    assert "build failed (exit 1)" in console.text
    assert "ninja: build stopped" in console.text
