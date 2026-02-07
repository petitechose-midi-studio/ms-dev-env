from __future__ import annotations

from ._gate import require_arch_checks_enabled
from ._utils import iter_python_files, matches_prefix, ms_root, parse_imports


def test_services_do_not_import_cli_modules() -> None:
    require_arch_checks_enabled()

    root = ms_root()
    services_root = root / "services"
    offenders: list[str] = []

    for file_path in iter_python_files(services_root):
        rel = file_path.relative_to(root)
        for item in parse_imports(file_path):
            if matches_prefix(item.module, "ms.cli"):
                offenders.append(f"{rel}:{item.line}: forbidden import '{item.module}'")

    assert not offenders, "services -> cli dependency violations:\n" + "\n".join(offenders)


def test_release_package_does_not_depend_on_legacy_services_release() -> None:
    require_arch_checks_enabled()

    root = ms_root()
    release_root = root / "release"
    if not release_root.exists():
        return

    offenders: list[str] = []
    for file_path in iter_python_files(release_root):
        rel = file_path.relative_to(root)
        for item in parse_imports(file_path):
            if matches_prefix(item.module, "ms.services.release"):
                offenders.append(f"{rel}:{item.line}: forbidden import '{item.module}'")

    assert not offenders, "release -> legacy services.release dependency violations:\n" + "\n".join(
        offenders
    )
