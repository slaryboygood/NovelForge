"""隔离测试共用工具：源码扫描与临时作品构造。"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src" / "novelforge"


def python_files(*relative_dirs: str) -> list[Path]:
    """枚举 src/novelforge 下给定子目录的 .py 文件（排除 __pycache__）。"""

    files: list[Path] = []
    for rel in relative_dirs:
        base = SRC / rel
        if base.is_file():
            files.append(base)
        elif base.is_dir():
            files.extend(sorted(base.rglob("*.py")))
    return [path for path in files if "__pycache__" not in path.parts]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def module_name(path: Path) -> str:
    """src/novelforge/a/b.py -> novelforge.a.b"""

    relative = path.relative_to(ROOT / "src").with_suffix("")
    parts = list(relative.parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def iter_imports(path: Path) -> list[tuple[str, int]]:
    """返回 (被导入模块名, 行号) 列表；覆盖 import / from-import 与函数内 import。"""

    tree = ast.parse(read_text(path))
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append((alias.name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                module = f"{'.' * node.level}{module}"
            found.append((module, node.lineno))
    return found


def module_level_imports(path: Path) -> list[tuple[str, int]]:
    """只返回**模块顶层**的 import（函数/方法内 import 属于惰性依赖，单独判断）。"""

    tree = ast.parse(read_text(path))
    found: list[tuple[str, int]] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append((alias.name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                module = f"{'.' * node.level}{module}"
            found.append((module, node.lineno))
    return found


def imports_matching(path: Path, prefixes: tuple[str, ...]) -> list[tuple[str, int]]:
    return [(name, line) for name, line in iter_imports(path)
            if name.startswith(prefixes)]


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """收集 docstring 常量节点的 id（文档里提到历史资产不算违规）。"""

    ids: set[int] = set()
    holders = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    for node in ast.walk(tree):
        if isinstance(node, holders) and node.body:
            first = node.body[0]
            if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                ids.add(id(first.value))
    return ids


def string_literals(path: Path) -> list[tuple[str, int]]:
    """返回非 docstring 的字符串字面量 (值, 行号)。"""

    tree = ast.parse(read_text(path))
    skip = _docstring_nodes(tree)
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) in skip:
                continue
            found.append((node.value, node.lineno))
    return found


def identifier_names(path: Path) -> list[tuple[str, int]]:
    """返回全部标识符引用（Name.id 与 Attribute.attr）。"""

    tree = ast.parse(read_text(path))
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            found.append((node.id, node.lineno))
        elif isinstance(node, ast.Attribute):
            found.append((node.attr, node.lineno))
    return found


def write_minimal_novel(root: Path, novel_id: str, *, title: str) -> str:
    """在隔离数据根里造一本最小作品（只建 NovelProfile），返回 pack_id。

    post-release cleanup：content pack / creative brief 已随 V2 Story Builder 后端退休，
    最小作品只需要 profile；不写 StoryState 事实，也不依赖任何历史资产。
    """

    from novelforge.story_engine.profile import NovelProfileRepository

    NovelProfileRepository(root).create(novel_id, title=title)
    return ""
