"""Shell activation script generation.

This module generates activation scripts that:
- Set environment variables (JAVA_HOME, M2_HOME, EMSDK, etc.)
- Add tool directories to PATH
- Support multiple shells: bash/zsh, PowerShell, cmd

Usage:
    source tools/activate.sh      # bash/zsh
    . tools/activate.ps1          # PowerShell
    tools\\activate.bat           # cmd

The scripts are designed to be sourced (not executed) so they can
modify the current shell's environment.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ms.platform.detection import Platform

__all__ = [
    "generate_bash_activate",
    "generate_powershell_activate",
    "generate_cmd_activate",
    "generate_activation_scripts",
]


def generate_bash_activate(
    tools_dir: Path,
    env_vars: dict[str, str],
    path_additions: list[Path],
) -> str:
    """Generate bash/zsh activation script.

    Args:
        tools_dir: Base tools directory
        env_vars: Environment variables to set
        path_additions: Directories to add to PATH

    Returns:
        Script content with LF line endings
    """
    sentinel = "__MS_UNSET__"

    lines = [
        "#!/usr/bin/env bash",
        "# Auto-generated activation script for ms tools",
        f"# Source this file: source {tools_dir}/activate.sh",
        "",
        "# Guard: avoid double-activation (and handle execution vs sourcing)",
        'if [ -n "${_MS_ACTIVE-}" ]; then',
        '    echo "ms tools already activated. Run ms_deactivate to restore."',
        "    return 0 2>/dev/null || exit 0",
        "fi",
        "",
        "# Save original values for deactivation",
        'export _MS_ACTIVE="1"',
        'export _MS_OLD_PATH="$PATH"',
    ]

    # Save original env vars (distinguish unset vs empty via sentinel)
    for key in sorted(env_vars.keys()):
        lines.append(f'export _MS_OLD_{key}="${{{key}-{sentinel}}}"')

    lines.append("")

    # Set environment variables
    if env_vars:
        lines.append("# Environment variables")
        for key, value in sorted(env_vars.items()):
            lines.append(f'export {key}="{value}"')
        lines.append("")

    # Add to PATH
    if path_additions:
        lines.append("# Add tools to PATH")
        for path in path_additions:
            lines.append(f'export PATH="{path}:$PATH"')
        lines.append("")

    # Deactivation function
    lines.extend(
        [
            "# Deactivation function",
            "ms_deactivate() {",
            '    export PATH="$_MS_OLD_PATH"',
            "    unset _MS_OLD_PATH",
        ]
    )

    for key in sorted(env_vars.keys()):
        lines.extend(
            [
                f'    if [ "${{_MS_OLD_{key}-}}" = "{sentinel}" ]; then',
                f"        unset {key}",
                "    else",
                f'        export {key}="${{_MS_OLD_{key}}}"',
                "    fi",
                f"    unset _MS_OLD_{key}",
            ]
        )

    lines.extend(
        [
            "    unset _MS_ACTIVE",
            "    unset -f ms_deactivate",
            "}",
            "",
            'echo "ms tools activated. Run ms_deactivate to restore."',
        ]
    )

    return "\n".join(lines) + "\n"


def generate_powershell_activate(
    tools_dir: Path,
    env_vars: dict[str, str],
    path_additions: list[Path],
) -> str:
    """Generate PowerShell activation script.

    Args:
        tools_dir: Base tools directory
        env_vars: Environment variables to set
        path_additions: Directories to add to PATH

    Returns:
        Script content with CRLF line endings
    """
    lines = [
        "# Auto-generated activation script for ms tools",
        f"# Dot-source this file: . {tools_dir}\\activate.ps1",
        "",
        "# Guard against double-activation",
        "if ($env:_MS_ACTIVE -eq '1') {",
        "    Write-Host 'ms tools already activated. Run ms_deactivate to restore.'",
        "    return",
        "}",
        "$env:_MS_ACTIVE = '1'",
        "",
    ]

    # Save original values for deactivation
    lines.append("# Save original values")
    lines.append("$env:_MS_OLD_PATH = $env:PATH")
    for key in sorted(env_vars.keys()):
        lines.append(f"$env:_MS_OLD_{key} = $env:{key}")
    lines.append("")

    # Set environment variables
    if env_vars:
        lines.append("# Environment variables")
        for key, value in sorted(env_vars.items()):
            lines.append(f'$env:{key} = "{value}"')
        lines.append("")

    # Add to PATH
    if path_additions:
        lines.append("# Add tools to PATH")
        for path in path_additions:
            lines.append(f'$env:PATH = "{path};$env:PATH"')
        lines.append("")

    # Deactivation function
    lines.extend(
        [
            "# Deactivation function",
            "function global:ms_deactivate {",
            "    $env:PATH = $env:_MS_OLD_PATH",
            "    Remove-Item Env:_MS_OLD_PATH -ErrorAction SilentlyContinue",
        ]
    )

    for key in sorted(env_vars.keys()):
        lines.append(f"    $env:{key} = $env:_MS_OLD_{key}")
        lines.append(f"    Remove-Item Env:_MS_OLD_{key} -ErrorAction SilentlyContinue")

    lines.extend(
        [
            "    Remove-Item Env:_MS_ACTIVE -ErrorAction SilentlyContinue",
            "    Remove-Item Function:ms_deactivate -ErrorAction SilentlyContinue",
            "}",
            "",
            'Write-Host "ms tools activated. Run ms_deactivate to restore."',
        ]
    )

    return "\r\n".join(lines) + "\r\n"


def generate_cmd_activate(
    tools_dir: Path,
    env_vars: dict[str, str],
    path_additions: list[Path],
) -> str:
    """Generate cmd.exe activation script.

    Args:
        tools_dir: Base tools directory
        env_vars: Environment variables to set
        path_additions: Directories to add to PATH

    Returns:
        Script content with CRLF line endings

    Note: cmd.exe doesn't support functions, so no deactivation is provided.
    """
    lines = [
        "@echo off",
        "REM Auto-generated activation script for ms tools",
        f"REM Run this file: {tools_dir}\\activate.bat",
        "",
    ]

    # Set environment variables
    if env_vars:
        lines.append("REM Environment variables")
        for key, value in sorted(env_vars.items()):
            lines.append(f'set "{key}={value}"')
        lines.append("")

    # Add to PATH
    if path_additions:
        lines.append("REM Add tools to PATH")
        for path in path_additions:
            lines.append(f'set "PATH={path};%PATH%"')
        lines.append("")

    lines.append("echo ms tools activated.")

    return "\r\n".join(lines) + "\r\n"


def generate_activation_scripts(
    tools_dir: Path,
    env_vars: dict[str, str],
    path_additions: list[Path],
    platform: Platform,
) -> dict[str, Path]:
    """Generate all activation scripts for a platform.

    Args:
        tools_dir: Base tools directory (scripts written here)
        env_vars: Environment variables to set
        path_additions: Directories to add to PATH
        platform: Target platform

    Returns:
        Dict mapping script type to path
    """
    tools_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, Path] = {}

    # Always generate bash script (useful on Windows via Git Bash)
    bash_path = tools_dir / "activate.sh"
    bash_content = generate_bash_activate(tools_dir, env_vars, path_additions)
    bash_path.write_text(bash_content, encoding="utf-8", newline="\n")
    result["bash"] = bash_path

    # Make bash script executable on Unix
    if str(platform).lower() != "windows":
        bash_path.chmod(0o755)

    # Generate Windows scripts
    if str(platform).lower() == "windows":
        # PowerShell
        ps_path = tools_dir / "activate.ps1"
        ps_content = generate_powershell_activate(tools_dir, env_vars, path_additions)
        ps_path.write_bytes(ps_content.encode("utf-8"))
        result["powershell"] = ps_path

        # Cmd
        cmd_path = tools_dir / "activate.bat"
        cmd_content = generate_cmd_activate(tools_dir, env_vars, path_additions)
        cmd_path.write_bytes(cmd_content.encode("utf-8"))
        result["cmd"] = cmd_path

    return result
