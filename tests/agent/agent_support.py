"""Agent 测试 fixture（V4-11）。

复用 V4-04→V4-10 的 Golden fixture（stub 模型，零网络）：

```text
tests/generation/gen_support       payload builders + stub gateway
tests/memory/support               build_novel / service_for
tests/studio/studio_support        统一装载上面两个（唯一入口，避免重复加载）
```

每个 stack 用**两个独立 gateway**：seed 用第一个（产出基础 Blueprint），
agent 用第二个（只负责 agent 触发的生成），因此 agent 的模型调用可计数、可复现。
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


_studio = _load("studio_support_for_agent",
                ROOT / "tests" / "studio" / "studio_support.py")

build_novel = _studio.build_novel
service_for = _studio.service_for
stub_gateway = _studio.stub_gateway
premise_payload = _studio.premise_payload
world_payload = _studio.world_payload
character_payload = _studio.character_payload
story_arc_payload = _studio.story_arc_payload
unit_payload = _studio.unit_payload
chapter_payload = _studio.chapter_payload
scene_payload = _studio.scene_payload

DEFAULT_NOVEL = "agent_alpha"


def seed_services(root: Path, novel_id: str, *, script: Sequence[Any]) -> Any:
    from novelforge.application.services.facade import application_services

    gateway, _provider = stub_gateway(list(script))
    return application_services(root, novel_id, gateway=gateway,
                                memory=service_for(root, novel_id))


def base_script() -> list[Any]:
    """基础 Blueprint：premise / world / story_arc / structural_unit /
    chapter / 2 scenes / character（顺序 = 生成调用顺序）。"""

    return [premise_payload(), world_payload(), story_arc_payload(), unit_payload(),
            character_payload("林澈"), chapter_payload(),
            scene_payload("ch_001"), scene_payload("ch_001")]


def seed(root: Path, novel_id: str = DEFAULT_NOVEL,
         script: Sequence[Any] | None = None,
         accept: Sequence[str] = ()) -> dict[str, Any]:
    """构造一个已有基础 Blueprint 的作品（结构见 base_script）。"""

    build_novel(root, novel_id, title="Agent 测试作品",
                fact_text="测试规则：电气维护优先级高于个人装备。")
    services = seed_services(root, novel_id, script=list(script or base_script()))
    services.blueprint.generate_task("premise")
    services.blueprint.generate_task("world")
    story = services.blueprint.generate_task("story_arc")
    unit = services.blueprint.generate_task(
        "structural_unit", parent_id=story.node["node_id"])
    services.blueprint.generate_task("character")
    chapter = services.blueprint.generate_task(
        "chapter", parent_id=unit.node["node_id"], sequence=1,
        task_input={"index": 1})
    chapter_id = chapter.node["node_id"]
    services.blueprint.generate_task("scene", parent_id=chapter_id,
                                     task_input={"sequence": 1,
                                                 "chapter_index": 1})
    services.blueprint.generate_task("scene", parent_id=chapter_id,
                                     task_input={"sequence": 2,
                                                 "chapter_index": 1})
    for node_id in accept:
        services.editor.accept(node_id, revision=1)
    return {"root": root, "novel_id": novel_id, "services": services,
            "unit_id": unit.node["node_id"], "chapter_id": chapter_id,
            "story_arc_id": story.node["node_id"]}


def agent_for(stack: dict[str, Any], *, script: Sequence[Any] | None = None,
              planner: Any = None, planner_model: Any = None) -> Any:
    """为 stack 构造 AgentService（默认再生成 3 个 chapter 的脚本）。"""

    from novelforge.application.services.agent import agent_service

    gateway, provider = stub_gateway(list(script or [chapter_payload(),
                                                    chapter_payload(),
                                                    chapter_payload()]))
    service = agent_service(stack["root"], stack["novel_id"], gateway=gateway,
                            memory=service_for(stack["root"], stack["novel_id"]),
                            planner=planner, planner_model=planner_model)
    stack["agent_provider"] = provider
    stack["agent"] = service
    return service


def goal_for(stack: dict[str, Any], **overrides: Any) -> Any:
    from novelforge.agent import AgentGoal, AgentScope

    payload = {"novel_id": stack["novel_id"],
               "instruction": "把第一幕扩展到 3 个章节，每章至少有 2 个场景，"
                              "运行质量检查并修复可以自动安全修复的问题，不要自动接受",
               "scope": AgentScope(kind="structural_unit", unit_id=stack["unit_id"])}
    payload.update(overrides)
    return AgentGoal(**payload)


__all__ = [
    "DEFAULT_NOVEL", "ROOT", "agent_for", "base_script", "build_novel",
    "chapter_payload", "character_payload", "goal_for", "premise_payload",
    "scene_payload", "seed", "seed_services", "service_for", "story_arc_payload",
    "stub_gateway", "unit_payload", "world_payload",
]
