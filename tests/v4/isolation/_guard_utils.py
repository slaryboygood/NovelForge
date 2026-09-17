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
    """在隔离数据根里造一本最小作品（profile + 内容包），返回 pack_id。

    只写 design 态数据（profile / content pack），不写 StoryState 事实，
    也不依赖任何历史资产。
    """

    from novelforge.story_engine.creative import CreativeBrief, save_creative_brief
    from novelforge.story_engine.profile import NovelProfileRepository
    from novelforge.story_engine.settings_gen import (
        content_pack_draft,
        default_pack_id,
        deterministic_seed,
        validate_pack_draft,
        write_content_pack,
    )

    repository = NovelProfileRepository(root)
    repository.create(novel_id, title=title)
    brief = CreativeBrief(original_idea=f"{title}：一个只属于 {novel_id} 的开局创意。",
                          tone="冷峻写实")
    save_creative_brief(root, novel_id, brief)
    seed = deterministic_seed(brief)
    pack_id = default_pack_id(novel_id)
    pack = validate_pack_draft(content_pack_draft(seed, pack_id=pack_id, brief=brief))
    write_content_pack(root, pack)
    return pack_id
