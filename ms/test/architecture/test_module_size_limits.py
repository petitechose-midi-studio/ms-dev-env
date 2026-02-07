from __future__ import annotations

import os

from ._gate import require_arch_checks_enabled
from ._utils import count_lines, iter_python_files, ms_root


def test_legacy_release_hotspots_do_not_grow_unbounded() -> None:
    require_arch_checks_enabled()

    root = ms_root()
    strict = os.getenv("MS_ARCH_STRICT") == "1"
    legacy_limit = 400 if strict else 900

    hotspots = [
        "cli/commands/release_content_commands.py",
        "cli/commands/release_app_commands.py",
        "cli/release_guided_content.py",
        "cli/release_guided_app.py",
        "services/release/service.py",
        "services/release/auto.py",
    ]

    offenders: list[str] = []
    for rel in hotspots:
        file_path = root / rel
        if not file_path.exists():
            continue
        line_count = count_lines(file_path)
        if line_count > legacy_limit:
            offenders.append(f"{rel}: {line_count} lines (limit {legacy_limit})")

    assert not offenders, "Legacy hotspot size violations:\n" + "\n".join(offenders)


def test_new_release_modules_keep_small_size_budget() -> None:
    require_arch_checks_enabled()

    root = ms_root()
    release_root = root / "release"
    if not release_root.exists():
        return

    strict = os.getenv("MS_ARCH_STRICT") == "1"
    release_limit = 300 if strict else 450

    offenders: list[str] = []
    for file_path in iter_python_files(release_root):
        rel = file_path.relative_to(root)
        if rel.name == "__init__.py":
            continue
        line_count = count_lines(file_path)
        if line_count > release_limit:
            offenders.append(f"{rel}: {line_count} lines (limit {release_limit})")

    assert not offenders, "New release module size violations:\n" + "\n".join(offenders)
