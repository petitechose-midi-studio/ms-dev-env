from __future__ import annotations

import ast

from ._gate import require_arch_checks_enabled
from ._utils import iter_python_files, ms_root, read_tree


def _has_direct_subprocess_call(tree: ast.AST) -> list[int]:
    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute):
            continue
        if func.attr not in {"run", "check_output", "Popen"}:
            continue
        if not isinstance(func.value, ast.Name):
            continue
        if func.value.id != "subprocess":
            continue
        lines.append(node.lineno)
    return lines


def test_direct_subprocess_usage_is_constrained_to_allowlist() -> None:
    require_arch_checks_enabled()

    root = ms_root()
    allowlist = {
        "platform/process.py",
        "platform/clipboard.py",
        "services/bridge_headless.py",
        "services/checkers/common.py",
        "services/hardware.py",
        "oc_cli/common.py",
        "oc_cli/oc_build.py",
        "oc_cli/oc_upload.py",
        "oc_cli/oc_monitor.py",
    }

    offenders: list[str] = []
    for file_path in iter_python_files(root):
        rel = file_path.relative_to(root)
        if rel.parts and rel.parts[0] == "test":
            continue
        rel_str = str(rel)
        if rel_str in allowlist:
            continue

        tree = read_tree(file_path)
        direct_call_lines = _has_direct_subprocess_call(tree)
        for line in direct_call_lines:
            offenders.append(f"{rel}:{line}: direct subprocess call outside allowlist")

    assert not offenders, "Subprocess policy violations:\n" + "\n".join(offenders)
