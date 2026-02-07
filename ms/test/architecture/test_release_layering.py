from __future__ import annotations

from pathlib import Path

from ._gate import require_arch_checks_enabled
from ._utils import iter_python_files, matches_prefix, ms_root, parse_imports


def _release_layer(rel_path: Path) -> str | None:
    parts = rel_path.parts
    if len(parts) < 2 or parts[0] != "release":
        return None
    candidate = parts[1]
    if candidate in {"domain", "resolve", "flow", "view", "infra"}:
        return candidate
    return None


def test_release_layers_only_depend_on_allowed_directions() -> None:
    require_arch_checks_enabled()

    root = ms_root()
    release_root = root / "release"
    if not release_root.exists():
        return

    rules: dict[str, tuple[str, ...]] = {
        "domain": (
            "ms.release.resolve",
            "ms.release.flow",
            "ms.release.view",
            "ms.release.infra",
            "ms.cli",
            "typer",
            "rich",
        ),
        "resolve": (
            "ms.release.flow",
            "ms.release.view",
            "ms.cli",
            "typer",
            "rich",
        ),
        "flow": (
            "ms.release.view",
            "ms.cli",
            "typer",
            "rich",
        ),
        "view": (
            "ms.release.flow",
            "ms.release.resolve",
            "ms.release.infra",
            "ms.cli",
            "typer",
        ),
        "infra": (
            "ms.release.view",
            "ms.cli",
            "typer",
            "rich",
        ),
    }

    offenders: list[str] = []
    for file_path in iter_python_files(release_root):
        rel = file_path.relative_to(root)
        layer = _release_layer(rel)
        if layer is None:
            continue

        forbidden_prefixes = rules[layer]
        for item in parse_imports(file_path):
            if any(matches_prefix(item.module, prefix) for prefix in forbidden_prefixes):
                offenders.append(
                    f"{rel}:{item.line}: forbidden import '{item.module}' in layer {layer}"
                )

    assert not offenders, "Release layering violations:\n" + "\n".join(offenders)
