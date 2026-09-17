"""永久守卫：V4-06 editor 模块边界（`docs/v4/V4_MODULE_BOUNDARIES.md` §3.13）。

```text
editor        → blueprint / generation / core / persistence.paths
禁止          → editor import interfaces(api) / application / ai(provider) / memory /
                story_engine；editor 不自行拼 artifact 路径；不写 Canon / StoryState
禁止          → 任何下层（core / persistence / domain / ai / memory / blueprint /
                generation / quality）反向 import editor
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

EDITOR_FORBIDDEN_PREFIXES = (
    "novelforge.api", "novelforge.application", "novelforge.ai",
    "novelforge.ai.providers", "novelforge.story_engine", "novelforge.story_builder",
    "novelforge.quality", "novelforge.memory",
    "fastapi", "starlette", "mcp", "httpx", "requests", "urllib", "aiohttp",
    "openai", "anthropic",
)

EDITOR_CONSUMERS_FORBIDDEN = (
    "story_engine", "story_builder", "ai", "memory", "blueprint", "generation",
    "quality", "core", "persistence", "legacy", "observability",
)


def _relative(path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def test_editor_does_not_depend_on_interfaces_or_providers() -> None:
    offenders: list[str] = []
    for path in python_files("editor"):
        for name, line in iter_imports(path):
            if name.startswith(EDITOR_FORBIDDEN_PREFIXES):
                offenders.append(f"{_relative(path)}:{line} → {name}")
    assert offenders == [], (
        "editor 不得依赖 interface / application / provider / domain / quality：\n"
        + "\n".join(offenders))


def test_editor_does_not_build_artifact_paths() -> None:
    offenders: list[str] = []
    for path in python_files("editor"):
        for value, line in string_literals(path):
            lowered = value.lower()
            if lowered.startswith(("novel/", "novel\\", "workspace/",
                                   "workspace\\")) or "authoring/" in lowered:
                offenders.append(f"{_relative(path)}:{line} → {value!r}")
    assert offenders == [], (
        "editor 不得自行拼 artifact 路径（必须经 persistence.paths）：\n"
        + "\n".join(offenders))


def test_editor_uses_persistence_paths_only() -> None:
    offenders: list[str] = []
    for path in python_files("editor"):
        for name, line in iter_imports(path):
            if name.startswith("novelforge.persistence") and \
                    not name.startswith("novelforge.persistence.paths"):
                offenders.append(f"{_relative(path)}:{line} → {name}")
    assert offenders == [], (
        "editor 只能依赖 persistence.paths：\n" + "\n".join(offenders))


def test_editor_does_not_write_canon_or_story_state() -> None:
    forbidden = ("CanonRepository", "StoryStateRepository", "StoryState(",
                 "canon_db_path", "save_fact")
    offenders: list[str] = []
    for path in python_files("editor"):
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            if token in text:
                offenders.append(f"{_relative(path)} → {token}")
    assert offenders == [], (
        "editor 不得写 Canon / StoryState（只改 Blueprint proposal）：\n"
        + "\n".join(offenders))


def test_layers_do_not_import_editor() -> None:
    offenders: list[str] = []
    for package in EDITOR_CONSUMERS_FORBIDDEN:
        for path in python_files(package):
            for name, line in iter_imports(path):
                if name.startswith("novelforge.editor"):
                    offenders.append(f"{_relative(path)}:{line} → {name}")
    assert offenders == [], (
        "依赖方向必须是 editor → 下层（不得反向）：\n" + "\n".join(offenders))


def test_generation_never_imports_editor_or_quality() -> None:
    offenders: list[str] = []
    for path in python_files("generation"):
        for name, line in iter_imports(path):
            if name.startswith(("novelforge.editor", "novelforge.quality")):
                offenders.append(f"{_relative(path)}:{line} → {name}")
    assert offenders == [], (
        "generation 不得反向依赖 editor / quality：\n" + "\n".join(offenders))


def test_editor_module_level_imports_avoid_heavy_layers() -> None:
    offenders: list[str] = []
    for path in python_files("editor"):
        for name, line in module_level_imports(path):
            if name.startswith(("novelforge.application", "novelforge.api",
                                "novelforge.ai", "novelforge.memory",
                                "novelforge.quality")):
                offenders.append(f"{_relative(path)}:{line} 模块级 → {name}")
    assert offenders == [], (
        "editor 顶层不得 import application / api / ai / memory / quality：\n"
        + "\n".join(offenders))


def test_editor_public_contract_is_small() -> None:
    import novelforge.editor as editor

    exported = set(editor.__all__)
    assert {"BlueprintEditorService", "EditorStore", "EditRequest", "EditResult",
            "BatchEditRequest", "BatchEditResult", "BlueprintDiff", "DiffRequest",
            "RevisionView", "RevisionHistory", "RewriteRequest", "RewriteResult",
            "ApprovalResult", "RestoreResult", "ChangeImpact",
            "EditorOperationRecord", "ReviewDecision"} <= exported
    assert not [name for name in exported if name.startswith("_")]
    assert not [name for name in exported if name.endswith("_patch")
                and name not in ("diff_payloads", "merge_changes")]


def test_editor_api_layer_is_thin() -> None:
    """§52：REST route 只调用 application.services.editor。"""

    path = ROOT / "src" / "novelforge" / "api" / "editor_routes.py"
    imports = {name for name, _line in iter_imports(path)}
    assert "novelforge.application.services.editor" in imports
    # 例外（显式登记）：路由只能额外 import **错误模型**（稳定契约，用于 HTTP 错误码映射），
    # 不得 import editor 的实现模块 / repository / generation / quality evaluator。
    allowed = {"novelforge.editor.errors"}
    forbidden = [name for name in imports
                 if name.startswith(("novelforge.editor", "novelforge.blueprint",
                                     "novelforge.generation", "novelforge.quality"))]
    assert [name for name in forbidden if name not in allowed] == [], \
        f"editor 路由不得直接依赖业务实现：{forbidden}"
    text = path.read_text(encoding="utf-8")
    assert text.count("service_for(") >= 8       # route 都是薄封装


def test_editor_store_is_not_a_second_blueprint_store() -> None:
    """§5 / §49：editor 不复制 BlueprintRepository。"""

    text = (ROOT / "src" / "novelforge" / "editor" / "service.py").read_text(
        encoding="utf-8")
    assert "BlueprintRepository(" not in text or "repository or BlueprintRepository" in text
    store_text = (ROOT / "src" / "novelforge" / "editor" / "operations.py").read_text(
        encoding="utf-8")
    assert "BlueprintNode" not in store_text
