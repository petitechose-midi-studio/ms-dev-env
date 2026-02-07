from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ImportRef:
    module: str
    line: int


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def ms_root() -> Path:
    return Path(__file__).resolve().parents[2]


def iter_python_files(base: Path) -> list[Path]:
    root = ms_root()
    files: list[Path] = []
    for path in sorted(base.rglob("*.py")):
        rel = path.relative_to(root)
        if any(part.startswith(".") for part in rel.parts):
            continue
        if any(part == "__pycache__" for part in rel.parts):
            continue
        files.append(path)
    return files


def read_tree(path: Path) -> ast.AST:
    source = path.read_text(encoding="utf-8")
    return ast.parse(source, filename=str(path))


def parse_imports(path: Path) -> list[ImportRef]:
    tree = read_tree(path)
    imports: list[ImportRef] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(ImportRef(module=alias.name, line=node.lineno))
            continue

        if isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                continue
            if node.module is None:
                continue
            imports.append(ImportRef(module=node.module, line=node.lineno))

    return imports


def count_lines(path: Path) -> int:
    return sum(1 for _ in path.open("r", encoding="utf-8"))


def matches_prefix(module: str, prefix: str) -> bool:
    return module == prefix or module.startswith(prefix + ".")
