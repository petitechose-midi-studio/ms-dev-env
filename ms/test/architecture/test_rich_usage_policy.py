from __future__ import annotations

from ._gate import require_arch_checks_enabled
from ._utils import iter_python_files, matches_prefix, ms_root, parse_imports


def test_direct_rich_imports_are_limited_to_approved_modules() -> None:
    require_arch_checks_enabled()

    root = ms_root()
    allowlist = {
        "output/console.py",
        "cli/commands/status.py",
        "cli/commands/clean.py",
        "cli/commands/wipe.py",
        "oc_cli/common.py",
    }

    offenders: list[str] = []
    for file_path in iter_python_files(root):
        rel = file_path.relative_to(root)
        if rel.parts and rel.parts[0] == "test":
            continue
        rel_str = str(rel)

        for item in parse_imports(file_path):
            if not (matches_prefix(item.module, "rich") or item.module == "rich"):
                continue
            if rel_str in allowlist:
                continue
            offenders.append(f"{rel}:{item.line}: direct rich import '{item.module}'")

    assert not offenders, "Direct rich usage policy violations:\n" + "\n".join(offenders)
