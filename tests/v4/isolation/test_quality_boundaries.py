"""永久守卫：V4-05 quality / repair 模块边界（`docs/v4/V4_MODULE_BOUNDARIES.md` §3.11–§3.12）。

```text
quality          → blueprint / memory / ai / core / persistence.paths / domain public contract
quality.repair   → generation Public Contract（唯一允许的方向）
禁止             → ai / memory / blueprint / generation / domain 反向 import quality
禁止             → quality import interfaces(api) / ai.providers / HTTP client / 自行拼路径
```
"""

from __future__ import annotations

from _guard_utils import (
    ROOT,
    imports_matching,
    iter_imports,
    module_level_imports,
    python_files,
    string_literals,
)

QUALITY_FORBIDDEN_PREFIXES = (
    "novelforge.api", "novelforge.application", "novelforge.ai.providers",
    "fastapi", "starlette", "mcp", "httpx", "requests", "urllib", "aiohttp",
    "openai", "anthropic",
)

#: 依赖方向禁令：这些模块不得反向依赖 quality
QUALITY_CONSUMERS_FORBIDDEN = (
    "story_engine", "story_builder", "ai", "memory", "blueprint", "generation",
    "core", "persistence", "legacy", "observability",
)

#: 只有 repair 子模块允许依赖 generation（Public Contract）
GENERATION_IMPORT_ALLOWLIST = {
    "src/novelforge/quality/repair/executor.py",
}


def _relative(path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def test_quality_does_not_depend_on_interfaces_or_providers() -> None:
    offenders: list[str] = []
    for path in python_files("quality"):
        for name, line in iter_imports(path):
            if name.startswith(QUALITY_FORBIDDEN_PREFIXES):
                offenders.append(f"{_relative(path)}:{line} → {name}")
    assert offenders == [], (
        "quality 不得依赖 interface / provider 实现 / HTTP client：\n"
        + "\n".join(offenders))


def test_quality_does_not_build_artifact_paths() -> None:
    """路径常量只能来自 persistence.paths（不得自行拼 novel/ workspace/）。"""

    offenders: list[str] = []
    for path in python_files("quality"):
        for value, line in string_literals(path):
            lowered = value.lower()
            if lowered.startswith(("novel/", "novel\\", "workspace/", "workspace\\")) \
                    or "authoring/" in lowered:
                offenders.append(f"{_relative(path)}:{line} → {value!r}")
    assert offenders == [], (
        "quality 不得自行拼 artifact 路径：\n" + "\n".join(offenders))


def test_quality_uses_persistence_paths_only_through_contract() -> None:
    """路径解析只能来自 `persistence.paths`（不得 import 其他 persistence 内部模块）。"""

    offenders: list[str] = []
    for path in python_files("quality"):
        for name, line in iter_imports(path):
            if name.startswith("novelforge.persistence") and \
                    not name.startswith("novelforge.persistence.paths"):
                offenders.append(f"{_relative(path)}:{line} → {name}")
    assert offenders == [], (
        "quality 只能依赖 persistence.paths：\n" + "\n".join(offenders))


def test_evaluators_do_not_depend_on_generation() -> None:
    """§34：quality evaluator 不依赖 generation（repair 才允许）。"""

    offenders: list[str] = []
    for path in python_files("quality"):
        relative = _relative(path)
        if relative in GENERATION_IMPORT_ALLOWLIST or "/repair/" in relative:
            continue
        for name, line in iter_imports(path):
            if name.startswith("novelforge.generation"):
                offenders.append(f"{relative}:{line} → {name}")
    assert offenders == [], (
        "quality evaluator / service 不得依赖 generation：\n" + "\n".join(offenders))


def test_layers_do_not_import_quality() -> None:
    offenders: list[str] = []
    for package in QUALITY_CONSUMERS_FORBIDDEN:
        for path in python_files(package):
            for name, line in iter_imports(path):
                if name.startswith("novelforge.quality"):
                    offenders.append(f"{_relative(path)}:{line} → {name}")
    assert offenders == [], (
        "依赖方向必须是 quality → 下层（不得反向）：\n" + "\n".join(offenders))


def test_generation_never_imports_quality_or_repair() -> None:
    offenders: list[str] = []
    for path in python_files("generation"):
        for name, line in iter_imports(path):
            if name.startswith("novelforge.quality"):
                offenders.append(f"{_relative(path)}:{line} → {name}")
    assert offenders == [], (
        "generation 绝不能反向依赖 quality / repair（否则形成环）：\n"
        + "\n".join(offenders))


def test_quality_does_not_write_canon_or_story_state() -> None:
    """§47：repair 只改 Blueprint proposal，绝不修改 Canon / StoryState。"""

    forbidden = ("CanonRepository", "StoryStateRepository", "save_fact",
                 "state.save", "StoryState(", "canon_db_path")
    offenders: list[str] = []
    for path in python_files("quality"):
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            if token in text:
                offenders.append(f"{_relative(path)} → {token}")
    assert offenders == [], (
        "quality / repair 不得写 Canon / StoryState：\n" + "\n".join(offenders))


def test_quality_public_contract_is_small() -> None:
    """§6 / §79：Public Contract 保持精简（不导出 evaluator 内部实现）。"""

    import novelforge.quality as quality

    exported = set(quality.__all__)
    assert {"QualityService", "QualityIssue", "QualityEvidence", "QualityReport",
            "QualityPolicy", "EvaluatorRegistry", "EvaluatorSpec",
            "RepairPlanner", "RepairExecutor", "RepairVerifier",
            "RepairPlan", "RepairResult", "VerificationResult",
            "RepairBlastRadius"} <= exported
    # 不得导出 evaluator 模块本身（例如 schema_gate / canon_gate）
    assert not [name for name in exported
                if name.endswith("_gate") and not name.startswith("codes_")
                and not name.startswith("group_")]
    assert not [name for name in exported if name.startswith("_")]


def test_quality_module_level_imports_avoid_heavy_layers() -> None:
    """quality 顶层不 import generation / api（repair 也不在顶层 import generation）。"""

    offenders: list[str] = []
    for path in python_files("quality"):
        for name, line in module_level_imports(path):
            if name.startswith(("novelforge.generation", "novelforge.api",
                                "novelforge.application")):
                offenders.append(f"{_relative(path)}:{line} 模块级 → {name}")
    assert offenders == [], (
        "quality 顶层不得 import generation / api / application：\n"
        + "\n".join(offenders))
