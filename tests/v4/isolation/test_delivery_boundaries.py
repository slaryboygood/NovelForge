"""永久守卫：V4-07 delivery 模块边界（`docs/v4/V4_MODULE_BOUNDARIES.md` §3.14）。

```text
delivery      → blueprint / quality Public Contract / editor metadata / core / persistence.paths
禁止          → LLM / memory retrieval / HTTP / 修改任何 truth / 自行拼路径
禁止          → delivery import api / application
禁止          → 下层（core…editor）反向 import delivery
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

DELIVERY_FORBIDDEN_PREFIXES = (
    "novelforge.api", "novelforge.application", "novelforge.ai",
    "novelforge.ai.providers", "novelforge.memory", "novelforge.story_engine",
    "novelforge.story_builder",
    "fastapi", "starlette", "mcp", "httpx", "requests", "urllib", "aiohttp",
    "openai", "anthropic",
)

DELIVERY_CONSUMERS_FORBIDDEN = (
    "core", "story_engine", "story_builder", "ai", "memory", "blueprint",
    "generation", "quality", "editor", "persistence", "legacy", "observability",
)

#: 允许 delivery 读取的只读来源（§82）
DELIVERY_ALLOWED_PREFIXES = (
    "novelforge.blueprint", "novelforge.quality", "novelforge.editor",
    "novelforge.core", "novelforge.persistence",
)


def _relative(path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def test_delivery_does_not_depend_on_interfaces_or_llm() -> None:
    offenders: list[str] = []
    for path in python_files("delivery"):
        for name, line in iter_imports(path):
            if name.startswith(DELIVERY_FORBIDDEN_PREFIXES):
                offenders.append(f"{_relative(path)}:{line} → {name}")
    assert offenders == [], (
        "delivery 不得依赖 interface / application / ai / memory / domain / HTTP：\n"
        + "\n".join(offenders))


def test_delivery_only_imports_readonly_contracts() -> None:
    offenders: list[str] = []
    for path in python_files("delivery"):
        for name, line in iter_imports(path):
            if not name.startswith("novelforge."):
                continue
            if not name.startswith(DELIVERY_ALLOWED_PREFIXES) and \
                    not name.startswith("novelforge.delivery"):
                offenders.append(f"{_relative(path)}:{line} → {name}")
    assert offenders == [], (
        "delivery 只允许依赖 blueprint / quality / editor metadata / core / persistence：\n"
        + "\n".join(offenders))


def test_delivery_does_not_build_artifact_paths() -> None:
    offenders: list[str] = []
    for path in python_files("delivery"):
        for value, line in string_literals(path):
            lowered = value.lower()
            if lowered.startswith(("novel/", "novel\\", "workspace/",
                                   "workspace\\")) or "authoring/" in lowered:
                offenders.append(f"{_relative(path)}:{line} → {value!r}")
    assert offenders == [], (
        "delivery 不得自行拼 artifact 路径（必须经 persistence.paths）：\n"
        + "\n".join(offenders))


def test_delivery_uses_persistence_paths_only() -> None:
    offenders: list[str] = []
    for path in python_files("delivery"):
        for name, line in iter_imports(path):
            if name.startswith("novelforge.persistence") and \
                    not name.startswith("novelforge.persistence.paths"):
                offenders.append(f"{_relative(path)}:{line} → {name}")
    assert offenders == [], (
        "delivery 只能依赖 persistence.paths：\n" + "\n".join(offenders))


def test_delivery_never_modifies_truth() -> None:
    forbidden = ("CanonRepository", "StoryStateRepository", "StoryState(",
                 "save_revision", "set_status", "canon_db_path", "RepairExecutor",
                 "editor.patch", "EditorService")
    offenders: list[str] = []
    for path in python_files("delivery"):
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            if token in text:
                offenders.append(f"{_relative(path)} → {token}")
    assert offenders == [], (
        "delivery 只读：不得写 Blueprint / Canon / StoryState，也不得调用 repair：\n"
        + "\n".join(offenders))


def test_delivery_makes_no_llm_calls() -> None:
    """§49：交付不得出现任何模型调用面（gateway / contract / model_policy）。"""

    tokens = ("LLMContract", "ModelPolicy", "model_policy", "gateway",
              "completion(", "chat_completion", "structured_output")
    offenders: list[str] = []
    for path in python_files("delivery"):
        text = path.read_text(encoding="utf-8")
        for token in tokens:
            if token in text:
                offenders.append(f"{_relative(path)} → {token}")
    assert offenders == [], (
        "delivery 不得调用模型（§49）：\n" + "\n".join(offenders))


def test_layers_do_not_import_delivery() -> None:
    offenders: list[str] = []
    for package in DELIVERY_CONSUMERS_FORBIDDEN:
        for path in python_files(package):
            for name, line in iter_imports(path):
                if name.startswith("novelforge.delivery"):
                    offenders.append(f"{_relative(path)}:{line} → {name}")
    assert offenders == [], (
        "依赖方向必须是 delivery → 下层（不得反向）：\n" + "\n".join(offenders))


def test_delivery_module_level_imports_avoid_heavy_layers() -> None:
    offenders: list[str] = []
    for path in python_files("delivery"):
        for name, line in module_level_imports(path):
            if name.startswith(("novelforge.application", "novelforge.api",
                                "novelforge.ai", "novelforge.memory",
                                "novelforge.story_engine")):
                offenders.append(f"{_relative(path)}:{line} 模块级 → {name}")
    assert offenders == [], (
        "delivery 顶层不得 import application / api / ai / memory / domain：\n"
        + "\n".join(offenders))


def test_delivery_public_contract_is_small() -> None:
    import novelforge.delivery as delivery

    exported = set(delivery.__all__)
    assert {"DeliveryService", "DeliveryRequest", "DeliveryResult",
            "DeliveryPolicy", "DeliverySelection", "DeliverySnapshot",
            "DeliveryManifest", "DeliveryValidationResult", "DeliveryIssue",
            "ExportArtifact", "NovelForgePackage", "ExporterRegistry",
            "ExporterSpec", "DeliveryStore"} <= exported
    assert not [name for name in exported if name.startswith("_")]
    # 具体 exporter 模块不导出
    assert not [name for name in exported if name.endswith("_exporter")]


def test_delivery_api_layer_is_thin() -> None:
    path = ROOT / "src" / "novelforge" / "api" / "delivery_routes.py"
    imports = {name for name, _line in iter_imports(path)}
    assert "novelforge.application.services.export" in imports
    forbidden = [name for name in imports
                 if name.startswith(("novelforge.blueprint", "novelforge.quality",
                                     "novelforge.generation", "novelforge.editor"))]
    assert forbidden == [], f"delivery 路由不得直接依赖业务实现：{forbidden}"
    text = path.read_text(encoding="utf-8")
    # V4-10：构造点从“每个路由各写一次”收敛为**唯一 helper**（_export_service），
    # 因此这里断言的不变式是「路由只通过 ExportService facade 访问交付能力」，
    # 且构造点唯一（比计数更严格，不是放宽）。
    assert "ExportService(" in text, "delivery 路由必须经 ExportService facade"
    assert text.count("ExportService(") == 1, (
        "delivery 路由只允许一个 ExportService 构造点（_export_service helper）")
    assert text.count("_export_service(") >= 5, "每个路由都必须经 facade helper"


def test_application_facade_routes_delivery_through_service() -> None:
    """§21：Application ExportService 是唯一 facade。"""

    path = ROOT / "src" / "novelforge" / "application" / "services" / "export.py"
    text = path.read_text(encoding="utf-8")
    assert "DeliveryService" in text and "DeliveryRequest" in text
    assert "def deliver(" in text and "def delivery_selection(" in text
