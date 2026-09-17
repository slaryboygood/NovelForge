"""永久守卫：Memory 跨作品隔离（V4-03 §31）。

即使两本作品有**相同的角色名、相同的规则文本、相同的关键词**，
也不允许跨作品检索。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from _guard_utils import ROOT, iter_imports, module_level_imports, python_files

from novelforge.memory import (
    AuthorPreferenceService,
    ContextBuilder,
    ContextRequest,
    MemoryIsolationError,
    MemoryQuery,
)


def _two_novels(tmp_path: Path) -> tuple[str, str]:
    import sys

    sys.path.insert(0, str(ROOT / "tests" / "memory"))
    from support import build_novel, service_for  # type: ignore

    build_novel(tmp_path, "novel_alpha", title="阿尔法计划", fact_text="主角不会使用枪械")
    build_novel(tmp_path, "novel_beta", title="贝塔计划", fact_text="主角不会使用枪械")
    # 只给 B 加一条独有事实，用于验证不会串进 A
    from novelforge.persistence.paths import canon_db_path
    from novelforge.story_engine.canon.models import CanonFact
    from novelforge.story_engine.canon.repository import CanonRepository

    repository = CanonRepository(canon_db_path(tmp_path, "novel_beta"))
    try:
        repository.save_fact(CanonFact(fact_id="FACT_BETA_ONLY", canonical_key="BETA_ONLY",
                                       novel_id="novel_beta", status="happened",
                                       canonical_description="贝塔专属事实"))
    finally:
        repository.close()
    service_for(tmp_path, "novel_alpha")  # 预热（无副作用）
    service_for(tmp_path, "novel_beta")
    return "novel_alpha", "novel_beta"


def _services(tmp_path: Path):
    import sys

    sys.path.insert(0, str(ROOT / "tests" / "memory"))
    from support import service_for  # type: ignore

    return service_for(tmp_path, "novel_alpha"), service_for(tmp_path, "novel_beta")


def test_service_rejects_query_for_other_novel(tmp_path: Path) -> None:
    _two_novels(tmp_path)
    alpha, beta = _services(tmp_path)
    with pytest.raises(MemoryIsolationError):
        alpha.search(MemoryQuery(novel_id=beta))
    with pytest.raises(MemoryIsolationError):
        beta.search(MemoryQuery(novel_id="novel_alpha"))


def test_retrieval_never_returns_other_novel(tmp_path: Path) -> None:
    _two_novels(tmp_path)
    alpha, beta = _services(tmp_path)
    alpha_result = alpha.search(MemoryQuery(novel_id="novel_alpha", task="专属 事实",
                                            policy=__import__(
                                                "novelforge.memory",
                                                fromlist=["RetrievalPolicy"]
                                            ).RetrievalPolicy(top_k=50)))
    beta_result = beta.search(MemoryQuery(novel_id="novel_beta", task="专属 事实",
                                          policy=__import__(
                                              "novelforge.memory",
                                              fromlist=["RetrievalPolicy"]
                                          ).RetrievalPolicy(top_k=50)))
    assert "贝塔专属事实" not in str(alpha_result.as_dict())
    assert "贝塔专属事实" in str(beta_result.as_dict())


def test_context_bundle_is_novel_scoped(tmp_path: Path) -> None:
    _two_novels(tmp_path)
    alpha, beta = _services(tmp_path)
    bundle_alpha = ContextBuilder(alpha).build(ContextRequest(
        novel_id="novel_alpha", task="下一场戏", characters=("hero", "rival")))
    bundle_beta = ContextBuilder(beta).build(ContextRequest(
        novel_id="novel_beta", task="下一场戏", characters=("hero", "rival")))
    assert "贝塔专属事实" not in str(bundle_alpha.as_dict())
    assert "贝塔专属事实" in str(bundle_beta.as_dict())
    assert "novel_beta" not in str(bundle_alpha.as_dict())


def test_preferences_do_not_leak_between_novels(tmp_path: Path) -> None:
    _two_novels(tmp_path)
    alpha_prefs = AuthorPreferenceService("novel_alpha", project_root=tmp_path,
                                          project_id="novel_alpha")
    alpha_prefs.set("novel", "forbidden_tropes", ["阿尔法专属禁用"])
    beta_prefs = AuthorPreferenceService("novel_beta", project_root=tmp_path,
                                         project_id="novel_beta")
    assert beta_prefs.resolve() == {}
    alpha, beta = _services(tmp_path)
    bundle_alpha = ContextBuilder(alpha, preferences=alpha_prefs).build(
        ContextRequest(novel_id="novel_alpha", task="x"))
    bundle_beta = ContextBuilder(beta, preferences=beta_prefs).build(
        ContextRequest(novel_id="novel_beta", task="x"))
    assert "阿尔法专属禁用" in str(bundle_alpha.as_dict())
    assert "阿尔法专属禁用" not in str(bundle_beta.as_dict())


def test_memory_module_boundaries() -> None:
    """memory 不 import interface / application / provider；不自行拼路径。"""

    forbidden_prefixes = ("novelforge.api", "novelforge.application",
                          "novelforge.ai.providers", "fastapi", "starlette", "mcp",
                          "httpx", "requests", "urllib", "openai", "anthropic")
    offenders: list[str] = []
    for path in python_files("memory"):
        relative = path.relative_to(ROOT)
        for name, line in iter_imports(path):
            if name.startswith(forbidden_prefixes):
                offenders.append(f"{relative}:{line} → {name}")
    assert offenders == [], (
        "memory 不得依赖 interface / application / provider 实现：\n"
        + "\n".join(offenders))


def test_domain_and_ai_do_not_import_memory() -> None:
    offenders: list[str] = []
    for package in ("story_engine", "story_builder", "ai", "core"):
        for path in python_files(package):
            for name, line in module_level_imports(path):
                if name.startswith("novelforge.memory"):
                    offenders.append(f"{path.relative_to(ROOT)}:{line} → {name}")
    assert offenders == [], (
        "domain / ai 不得依赖 memory（依赖方向是 memory → domain / ai）：\n"
        + "\n".join(offenders))


def test_memory_does_not_build_artifact_paths() -> None:
    """memory 必须经 persistence.paths 获取位置，不得自行拼路径。"""

    from _guard_utils import string_literals

    offenders: list[str] = []
    for path in python_files("memory"):
        for value, line in string_literals(path):
            cleaned = value.strip().strip("`").replace("\\", "/")
            if cleaned.startswith(("novel/", "workspace/")):
                offenders.append(f"{path.relative_to(ROOT)}:{line} → {value!r}")
    assert offenders == [], (
        "memory 不得自行拼 artifact 路径（必须经 persistence.paths）：\n"
        + "\n".join(offenders))

