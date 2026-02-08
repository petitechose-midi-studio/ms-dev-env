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
    non_strict_overrides: dict[str, int] = {
        # Guided flows were extracted in A7 and are intentionally larger for now.
        # Keep a bounded cap until the next split wave.
        "release/flow/guided/app_steps.py": 560,
        "release/flow/guided/content_steps.py": 700,
        "release/flow/guided/sessions.py": 540,
    }

    offenders: list[str] = []
    for file_path in iter_python_files(release_root):
        rel = file_path.relative_to(root)
        if rel.name == "__init__.py":
            continue
        line_count = count_lines(file_path)
        limit = non_strict_overrides.get(str(rel), release_limit) if not strict else release_limit
        if line_count > limit:
            offenders.append(f"{rel}: {line_count} lines (limit {limit})")

    assert not offenders, "New release module size violations:\n" + "\n".join(offenders)
