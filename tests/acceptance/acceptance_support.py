"""V4-12 Final Acceptance fixture（§12–§13）：**完全隔离**的 Golden Project。

复用既有确定性 fixture（stub 模型，零网络）：

```text
tests/delivery/delivery_support   已接受 + 质量通过的基础 Blueprint（16 节点）
tests/generation/gen_support      payload builders + stub gateway
tests/memory/support              Canon / StoryState / memory
tests/studio/studio_support       统一装载
tests/plugins/plugins_support     插件 fixture（可选）
```

所有数据写在 `tmp_path`；绝不读取或写入作者数据。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))


def _load(module_name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


_memory = _load("memory_support_for_acceptance",
                ROOT / "tests" / "memory" / "support.py")
_gen = _load("gen_support_for_acceptance",
             ROOT / "tests" / "generation" / "gen_support.py")
_delivery = _load("delivery_support_for_acceptance",
                  ROOT / "tests" / "delivery" / "delivery_support.py")
_plugins = _load("plugins_support_for_acceptance",
                 ROOT / "tests" / "plugins" / "plugins_support.py")

build_novel = _memory.build_novel
build_two_novels = _memory.build_two_novels
service_for = _memory.service_for
stub_gateway = _gen.stub_gateway
character_payload = _gen.character_payload
unit_payload = _gen.unit_payload
chapter_payload = _gen.chapter_payload
scene_payload = _gen.scene_payload
delivery_stack = _delivery.delivery_stack
repaired_scene_payload = _delivery.repaired_scene_payload
repair_script = _delivery.repair_script
NOVEL_ID = _delivery.NOVEL_ID

plugin_host = _plugins.plugin_host
exporter_manifest = _plugins.exporter_manifest
active_plugin = _plugins.active_plugin
EXPORTER_PLUGIN = _plugins.EXPORTER_PLUGIN

#: Golden Project 目标规模（§12）
GOLDEN_SHAPE = {"characters": 3, "structural_units": 2, "chapters": 4, "scenes": 8}


def _extend_script() -> list[Any]:
    """扩展 Golden Project 所需的生成脚本（顺序 = 调用顺序）。"""

    return [
        character_payload("秦默"), character_payload("周砚"),          # 3 名人物
        unit_payload("volume"),                                       # 第 2 个结构单元
        chapter_payload(title="第二章：备用电量"),                        # chapter index 2
        chapter_payload(title="第三章：水务塔"),                        # chapter index 3
        chapter_payload(title="第四章：分配方案"),                        # chapter index 4
        scene_payload("ch_002"), scene_payload("ch_002"),              # 场景补充到 8+
        scene_payload("ch_003"), scene_payload("ch_003"),
    ]


def golden_project(tmp_path: Path, *, novel_id: str = NOVEL_ID) -> dict[str, Any]:
    """V4 Golden Project：覆盖核心产品概念，完全隔离在 tmp_path。"""

    stack = delivery_stack(tmp_path, novel_id=novel_id)
    gateway, provider = stub_gateway(_extend_script())
    from novelforge.application.services.facade import application_services

    memory = service_for(tmp_path, novel_id)
    services = application_services(tmp_path, novel_id, gateway=gateway,
                                    memory=memory)
    for _ in range(2):
        services.blueprint.generate_task("character")
    second_unit = services.blueprint.generate_task("structural_unit",
                                                   task_input={"unit_type": "volume"})
    first_unit = "unit_01"
    for index in (2, 3, 4):
        services.blueprint.generate_task("chapter", parent_id=first_unit,
                                         task_input={"index": index})
    for chapter_id in ("ch_002", "ch_003"):
        for seq in (1, 2):
            services.blueprint.generate_task("scene", parent_id=chapter_id,
                                             task_input={"sequence": seq,
                                                         "chapter_index":
                                                         int(chapter_id[-1])})
    view = services.export.blueprint_view(selection_mode="current")
    nodes = [dict(row) for row in view["blueprint"]["nodes"]]
    stack.update({"services": services, "extension_gateway": gateway,
                  "extension_provider": provider, "memory": memory,
                  "nodes": nodes, "second_unit": second_unit.node["node_id"],
                  "view": view})
    return stack


def node_counts(nodes: Sequence[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in nodes:
        kind = str(row.get("node_type") or "")
        counts[kind] = counts.get(kind, 0) + 1
    return counts


def services_with_script(stack: dict[str, Any], script: Sequence[Any]) -> Any:
    """用**新的** stub 脚本构造同一作品的 ApplicationServices（用于额外生成）。"""

    from novelforge.application.services.facade import application_services

    gateway, provider = stub_gateway(list(script))
    stack["extension_gateway"] = gateway
    stack["extension_provider"] = provider
    return application_services(stack["root"], stack["novel_id"], gateway=gateway,
                                memory=stack["memory"])


def tree_hashes(root: Path, *relative: str) -> dict[str, str]:
    """对给定相对路径下的文件做内容哈希（用于"未变化"证明）。"""

    import hashlib

    rows: dict[str, str] = {}
    for item in relative:
        path = root / item
        if path.is_file():
            rows[item] = hashlib.sha256(path.read_bytes()).hexdigest()
        elif path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file() and "__pycache__" not in child.parts:
                    key = str(child.relative_to(root)).replace("\\", "/")
                    rows[key] = hashlib.sha256(child.read_bytes()).hexdigest()
    return rows


def truth_hashes(root: Path, novel_id: str) -> dict[str, str]:
    """story truth（Canon / StoryState / Blueprint）内容哈希。"""

    return tree_hashes(root, f"novel/authoring/story_engine/canon/{novel_id}",
                       f"novel/authoring/story_engine/canon",
                       f"novel/authoring/story_engine/state/{novel_id}",
                       f"novel/authoring/story_engine/blueprint/{novel_id}")


__all__ = [
    "EXPORTER_PLUGIN", "GOLDEN_SHAPE", "NOVEL_ID", "ROOT", "active_plugin",
    "build_novel", "build_two_novels", "chapter_payload", "delivery_stack",
    "exporter_manifest", "golden_project", "node_counts", "plugin_host",
    "repair_script", "repaired_scene_payload", "scene_payload", "service_for",
    "services_with_script", "stub_gateway", "tree_hashes", "truth_hashes",
    "unit_payload",
]
