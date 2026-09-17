"""Editor 测试 fixture（零网络、零真实模型）。

复用 V4-04 / V4-05 的 Golden fixture：

```text
tests/memory/support.py          最小作品（profile / content pack / Canon / StoryState）
tests/generation/gen_support.py  StubProvider + gateway + payload builders
tests/quality/quality_support.py broken / repairable Blueprint（V4-05 §62 植入缺陷）
```

本模块额外装配：`BlueprintEditorService`（editor）与 `EditorService`（application 组合）。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))


def _load(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


_memory_support = _load("memory_support_for_editor",
                        ROOT / "tests" / "memory" / "support.py")
_gen_support = _load("gen_support_for_editor",
                     ROOT / "tests" / "generation" / "gen_support.py")
_quality_support = _load("quality_support_for_editor",
                         ROOT / "tests" / "quality" / "quality_support.py")

build_novel = _memory_support.build_novel
service_for = _memory_support.service_for
stub_gateway = _gen_support.stub_gateway
chapter_payload = _gen_support.chapter_payload
scene_payload = _gen_support.scene_payload

REPAIRABLE_CHAPTER = _quality_support.repaired_chapter_payload
repaired_chapter_payload = _quality_support.repaired_chapter_payload
repaired_scene_payload = _quality_support.repaired_scene_payload
build_broken_blueprint = _quality_support.build_broken_blueprint
build_repairable_blueprint = _quality_support.build_repairable_blueprint
broken_nodes = _quality_support.broken_nodes
WEAPON_RULE_TEXT = _quality_support.WEAPON_RULE_TEXT
NOVEL_ID = _quality_support.NOVEL_ID


def editor_stack(tmp_path: Path, *, novel_id: str = NOVEL_ID,
                 repairable: bool = True, script: Sequence[Any] = (),
                 gateway: Any = None, memory: Any = None,
                 policy: Any = None) -> dict[str, Any]:
    """装配 repository / memory / generation / quality / editor / application 服务。"""

    from novelforge.application.services import EditorService, ReviewService
    from novelforge.editor import BlueprintEditorService, EditorStore
    from novelforge.generation import BlueprintGenerationService
    from novelforge.quality import QualityService

    build_novel(tmp_path, novel_id, title="阿尔法计划", fact_text=WEAPON_RULE_TEXT)
    repository = (build_repairable_blueprint(tmp_path, novel_id) if repairable
                  else build_broken_blueprint(tmp_path, novel_id))
    resolved_memory = memory or service_for(tmp_path, novel_id)
    provider = None
    if gateway is None:
        gateway, provider = stub_gateway(list(script))
    generation = BlueprintGenerationService(tmp_path, novel_id, gateway=gateway,
                                            memory=resolved_memory,
                                            repository=repository)
    quality = QualityService(tmp_path, novel_id, repository=repository,
                             memory=resolved_memory)
    review = ReviewService(tmp_path, novel_id, quality=quality, generation=generation,
                           repository=repository, policy=policy)
    store = EditorStore(tmp_path, novel_id)
    editor = BlueprintEditorService(tmp_path, novel_id, repository=repository,
                                    generation=generation, store=store)
    service = EditorService(tmp_path, novel_id, editor=editor, quality=quality,
                            review=review, generation=generation,
                            repository=repository, policy=policy)
    return {"novel_id": novel_id, "root": tmp_path, "repository": repository,
            "memory": resolved_memory, "generation": generation, "quality": quality,
            "review": review, "store": store, "editor": editor, "service": service,
            "gateway": gateway, "provider": provider}


# ------------------------------------------------------------------ 便捷函数
def current_payload(stack: dict[str, Any], node_id: str) -> dict[str, Any]:
    node = stack["repository"].get_current(node_id)
    assert node is not None, node_id
    return node.payload.model_dump(mode="json")


def scripted(stack: dict[str, Any], *payloads: Any) -> None:
    """覆盖 stub provider 的脚本（用于按当前 revision 精确构造模型输出）。"""

    provider = stack.get("provider")
    assert provider is not None, "该 stack 没有 stub provider"
    provider.script = [dict(payload) if isinstance(payload, dict) else payload
                       for payload in payloads]


def revision(stack: dict[str, Any], node_id: str) -> int:
    return stack["repository"].current_revision(node_id)


__all__ = [
    "NOVEL_ID", "REPAIRABLE_CHAPTER", "ROOT", "WEAPON_RULE_TEXT",
    "broken_nodes", "build_broken_blueprint", "build_novel",
    "build_repairable_blueprint", "chapter_payload", "current_payload",
    "editor_stack", "repaired_chapter_payload", "repaired_scene_payload",
    "revision", "scene_payload", "scripted", "service_for", "stub_gateway",
]
