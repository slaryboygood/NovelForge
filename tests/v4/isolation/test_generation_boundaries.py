"""永久守卫：generation / blueprint 模块边界与跨作品隔离（V4-04 §51）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from _guard_utils import (
    ROOT,
    identifier_names,
    imports_matching,
    iter_imports,
    module_level_imports,
    python_files,
    string_literals,
)

GENERATION_FORBIDDEN_PREFIXES = (
    "novelforge.api", "novelforge.ai.providers",
    "fastapi", "starlette", "mcp", "httpx", "requests", "urllib", "openai",
    "anthropic",
)

#: generation 允许依赖的层（白名单式表述，便于守卫报错时说明）
GENERATION_ALLOWED_PREFIXES = (
    "novelforge.ai", "novelforge.memory", "novelforge.blueprint",
    "novelforge.core", "novelforge.persistence", "novelforge.story_engine",
    "novelforge.models",
)

FORBIDDEN_IDENTIFIERS = ("CanonRepository", "StoryStateRepository",
                         "resolve_creator_context", "MemoryIndex",
                         "SemanticIndex", "EpisodicStore")


def test_generation_does_not_depend_on_interface_or_provider() -> None:
    offenders: list[str] = []
    for path in python_files("generation"):
        for name, line in iter_imports(path):
            if name.startswith(GENERATION_FORBIDDEN_PREFIXES):
                offenders.append(f"{path.relative_to(ROOT)}:{line} → {name}")
    assert offenders == [], (
        "generation 不得依赖 interface / provider 实现：\n" + "\n".join(offenders))


def test_generation_only_depends_on_allowed_layers() -> None:
    offenders: list[str] = []
    for path in python_files("generation"):
        for name, line in iter_imports(path):
            if not name.startswith("novelforge"):
                continue
            if name.startswith(GENERATION_ALLOWED_PREFIXES):
                continue
            offenders.append(f"{path.relative_to(ROOT)}:{line} → {name}")
    assert offenders == [], (
        "generation 只能依赖 ai / memory / blueprint / core / persistence / domain：\n"
        + "\n".join(offenders))


def test_generation_does_not_do_its_own_memory_retrieval() -> None:
    """generation 只声明需要什么上下文，不得直接查 Canon / StoryState / 索引。"""

    offenders: list[str] = []
    for path in python_files("generation"):
        for name, line in identifier_names(path):
            if name in FORBIDDEN_IDENTIFIERS:
                offenders.append(f"{path.relative_to(ROOT)}:{line} → {name}")
    assert offenders == [], (
        "generation 不得自行做 memory retrieval（必须经 ContextBuilder）：\n"
        + "\n".join(offenders))


def test_generation_and_blueprint_do_not_build_paths() -> None:
    offenders: list[str] = []
    for package in ("generation", "blueprint"):
        for path in python_files(package):
            for value, line in string_literals(path):
                cleaned = value.strip().strip("`").replace("\\", "/")
                if cleaned.startswith(("novel/", "workspace/")):
                    offenders.append(f"{path.relative_to(ROOT)}:{line} → {value!r}")
    assert offenders == [], (
        "generation / blueprint 不得自行拼 artifact 路径（必须经 persistence.paths）：\n"
        + "\n".join(offenders))


def test_domain_ai_memory_do_not_import_generation() -> None:
    offenders: list[str] = []
    for package in ("story_engine", "story_builder", "ai", "memory", "core",
                    "persistence"):
        for path in python_files(package):
            for name, line in module_level_imports(path):
                if name.startswith("novelforge.generation"):
                    offenders.append(f"{path.relative_to(ROOT)}:{line} → {name}")
    assert offenders == [], (
        "依赖方向必须是 generation → 其他层（不得反向）：\n" + "\n".join(offenders))


def test_blueprint_module_does_not_import_ai_or_generation() -> None:
    offenders: list[str] = []
    for path in python_files("blueprint"):
        for name, line in iter_imports(path):
            if name.startswith(("novelforge.ai", "novelforge.generation",
                                "novelforge.memory")):
                offenders.append(f"{path.relative_to(ROOT)}:{line} → {name}")
    assert offenders == [], (
        "blueprint 是 canonical store，不得依赖 ai / generation / memory：\n"
        + "\n".join(offenders))


def test_application_service_is_the_generation_entry_point() -> None:
    """接口层不得直接 import generation 内部实现（§52）。"""

    offenders: list[str] = []
    for path in python_files("api"):
        for name, line in iter_imports(path):
            if name.startswith("novelforge.generation"):
                offenders.append(f"{path.relative_to(ROOT)}:{line} → {name}")
    assert offenders == [], (
        "api 层必须经 application.services 使用生成能力：\n" + "\n".join(offenders))


def test_blueprint_store_is_isolated_per_novel(tmp_path: Path) -> None:
    """两本作品的 Blueprint 存储互不可见。"""

    import sys

    sys.path.insert(0, str(ROOT / "tests" / "generation"))
    from gen_support import blueprint_service, build_two_novels, premise_payload  # type: ignore

    build_two_novels(tmp_path)
    alpha, _provider = blueprint_service(tmp_path, "novel_alpha", [premise_payload()])
    alpha.generate_task("premise")
    beta, _provider2 = blueprint_service(tmp_path, "novel_beta", [premise_payload()])

    assert beta.read("premise") is None, "B 看不到 A 的 Blueprint 节点"
    assert beta.tree()["node_count"] == 0

    beta.generate_task("premise")
    assert alpha.read("premise")["novel_id"] == "novel_alpha"
    assert beta.read("premise")["novel_id"] == "novel_beta"
    assert alpha.tree()["by_type"] == {"premise": 1}
    assert beta.tree()["by_type"] == {"premise": 1}
    assert alpha.generation.repository.root != beta.generation.repository.root

    # B 不得读取 A 的节点文件（repository 按 novel_id 解析路径）
    with pytest.raises(Exception):
        alpha.generation.repository.save_revision(
            beta.generation.repository.get_current("premise"), expected_revision=None)
