"""Generation 测试 fixture（零网络、零真实模型）。

复用 tests/memory 的作品 fixture（同一套最小作品 A/B），
外加一个声明 `creative + structured_output` capability 的 Stub provider。
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))


def _load_memory_support():
    """显式加载 tests/memory/support.py（避免两个 support 模块同名冲突）。"""

    path = ROOT / "tests" / "memory" / "support.py"
    spec = importlib.util.spec_from_file_location("memory_support_for_generation", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["memory_support_for_generation"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


_memory_support = _load_memory_support()
build_novel = _memory_support.build_novel
build_two_novels = _memory_support.build_two_novels
service_for = _memory_support.service_for


class StubCreativeProvider:
    """按脚本返回 JSON（结构化生成主线用）。"""

    def __init__(self, provider_id: str, script: Sequence[Any]) -> None:
        self.provider_id = provider_id
        self.script = list(script)
        self.requests: list[Any] = []

    @property
    def calls(self) -> int:
        return len(self.requests)

    def complete(self, request: Any) -> Any:
        from novelforge.ai import ProviderResponse

        self.requests.append(request)
        item = self.script.pop(0) if self.script else {}
        text = item if isinstance(item, str) else json.dumps(item, ensure_ascii=False)
        return ProviderResponse(text=text, model=request.model,
                                usage_raw={"prompt_tokens": 12, "completion_tokens": 8},
                                finish_reason="stop")


def stub_gateway(script: Sequence[Any], *,
                 capabilities: Sequence[str] = ("creative", "structured_output",
                                                "large_context"),
                 model_id: str = "stub-creative") -> tuple[Any, StubCreativeProvider]:
    """构造只连 StubCreativeProvider 的 LLMGateway（零网络）。"""

    from novelforge.ai import (
        InMemoryCache,
        LLMGateway,
        ModelRouter,
        ModelSpec,
        ProviderConfig,
        ProviderRegistry,
    )

    config = ProviderConfig(provider_id="stub", kind="openai_compatible",
                            base_url="http://stub.local/v1",
                            api_key_env="STUB_KEY", enabled=True,
                            default_model=model_id,
                            models=(ModelSpec(model_id=model_id,
                                              capabilities=tuple(capabilities),
                                              cost_tier=4, speed_tier=2,
                                              context_tokens=128000),))
    provider = StubCreativeProvider("stub", script)
    gateway = LLMGateway({"stub": provider},
                         router=ModelRouter(ProviderRegistry([config])),
                         cache=InMemoryCache(), sleep=lambda _s: None,
                         clock=lambda: 0.0)
    return gateway, provider


def blueprint_service(root: Path, novel_id: str, script: Sequence[Any],
                      **kwargs: Any):
    """装配 BlueprintService（memory + context builder + generation）。"""

    from novelforge.application.services import BlueprintService
    from novelforge.generation import BlueprintGenerationService

    memory = service_for(root, novel_id)
    gateway, provider = stub_gateway(script, **kwargs)
    generation = BlueprintGenerationService(root, novel_id, gateway=gateway,
                                            memory=memory)
    return BlueprintService(root, novel_id, generation=generation), provider


# --------------------------------------------------------------- minimal payloads
def premise_payload(**overrides: Any) -> dict[str, Any]:
    payload = {"premise": "一个关于修复与代价的故事",
               "central_conflict": "主角必须修好中转站的供电，否则据点失守",
               "protagonist_goal": "在断电前恢复备用电源",
               "stakes": "据点里所有人",
               "dramatic_question": "他愿意为此付出什么？",
               "story_promise": "技术性解决问题 + 关系代价",
               "genre": "科幻", "tone": "冷峻", "constraints": ["不使用枪械"]}
    payload.update(overrides)
    return payload


def theme_payload(**overrides: Any) -> dict[str, Any]:
    payload = {"theme": "修复意味着承担", "statement": "修补他人留下的裂缝要付出自己的代价",
               "counter_theme": "先保住自己才有余力帮人", "motifs": ["损坏的电路", "备用电源"]}
    payload.update(overrides)
    return payload


def world_payload(**overrides: Any) -> dict[str, Any]:
    payload = {"rules": ["断电后 12 小时内必须恢复，否则气象屏障失效"],
               "locations": [{"id": "station", "name": "中转站", "kind": "site"}],
               "factions": [{"id": "authority", "name": "管理局", "stance": "秩序维护方"}],
               "resources": ["备用电源", "维修件"],
               "technology_or_magic": ["旧式工业电网"],
               "social_constraints": ["进入核心区需要许可"],
               "conflict_sources": ["许可审批被拖延"],
               "story_relevant_history": ["十年前的大断电"]}
    payload.update(overrides)
    return payload


def character_payload(name: str, **overrides: Any) -> dict[str, Any]:
    payload = {"name": name, "role": "维修工", "kind": "npc",
               "goal": "让中转站重新通电", "motivation": "证明自己修得好",
               "need": "被信任", "fear": "再次失去据点", "misbelief": "只要技术够好就不需要别人",
               "strength": "对旧电网了如指掌", "flaw": "不肯求助",
               "conflict_source": "许可与零件都被别人控制",
               "relationships": [{"target": "rival", "kind": "旧识", "tension": "立场不同"}],
               "story_function": "承担主线行动", "constraints": ["不使用枪械"]}
    payload.update(overrides)
    return payload


def character_arc_payload(character_id: str, **overrides: Any) -> dict[str, Any]:
    payload = {"character_id": character_id, "start_state": "独自扛下所有维修工作",
               "internal_conflict": "想被信任却不肯求助",
               "external_pressure": "断电倒计时与审批拖延",
               "key_turns": ["第一次开口求助", "发现破坏来自内部"],
               "midpoint_change": "承认自己修不好全部",
               "crisis": "必须在保人或保电之间选择",
               "climax_choice": "把最后一次机会交给对手",
               "end_state": "学会与人共同承担", "linked_chapters": [],
               "linked_scenes": []}
    payload.update(overrides)
    return payload


def story_arc_payload(**overrides: Any) -> dict[str, Any]:
    payload = {"initial_state": "据点按例行节奏运转",
               "inciting_incident": "备用电源被发现破坏",
               "progressive_complications": ["许可被拖延", "零件被截留"],
               "major_turns": ["发现内部破坏者", "敌方掌握关键零件"],
               "midpoint": "主角意识到技术不是唯一问题",
               "crisis": "供电与救人只能选一个",
               "climax": "主角把修复权交给对手共同完成",
               "resolution": "据点通电，主角获得新的位置"}
    payload.update(overrides)
    return payload


def unit_payload(unit_type: str = "act", **overrides: Any) -> dict[str, Any]:
    payload = {"unit_type": unit_type, "title": "第一幕：断电倒计时",
               "goal": "让读者看到压力", "conflict": "许可与时间",
               "turn": "内部破坏暴露", "outcome": "主角决定绕过常规流程",
               "child_units": []}
    payload.update(overrides)
    return payload


def chapter_payload(title: str = "维修记录里的异常编号", **overrides: Any) -> dict[str, Any]:
    payload = {"title": title, "goal": "确认被删除的维修日志是否真实存在",
               "pov": "", "characters": [], "location": "station",
               "conflict": "主管拒绝开放旧记录", "turn": "日志编号仍存在于设备缓存",
               "outcome": "获得一条指向殖民区的线索", "hook": "缓存显示最后访问者已死亡",
               "setup": ["备用电源曾被破坏"],
               "payoff": [], "state_change_intent": [
                   {"kind": "knowledge", "actor": "hero", "target": "core_record",
                    "value": "known", "scope": "novel"}]}
    payload.update(overrides)
    return payload


def scene_payload(chapter_id: str, **overrides: Any) -> dict[str, Any]:
    payload = {"chapter_id": chapter_id, "pov": "", "location": "station",
               "time": "第三天清晨", "scene_purpose": "让主角拿到被删除日志的第一条证据",
               "character_goals": ["拿到日志", "阻止他继续查"],
               "conflict": "主管拒绝开放记录", "escalation": "对手把许可撤回",
               "turn": "缓存在设备里仍保留日志编号", "outcome": "主角获得线索但失去许可",
               "information_reveal": ["日志最后由一个已死亡的人访问"],
               "character_change": "主角决定绕过流程",
               "relationship_change": "与对手的信任进一步下降",
               "setup": ["备用电源曾被破坏"], "payoff": [],
               "state_transition_intent": [
                   {"kind": "knowledge", "actor": "hero", "target": "core_record",
                    "value": "known"}],
               "next_hook": "死亡者为什么能访问缓存",
               "story_function": ["advance_plot", "reveal_information", "setup"]}
    payload.update(overrides)
    return payload


__all__ = [
    "StubCreativeProvider", "blueprint_service", "build_novel", "build_two_novels",
    "chapter_payload", "character_arc_payload", "character_payload",
    "premise_payload", "scene_payload", "service_for", "story_arc_payload",
    "stub_gateway", "theme_payload", "unit_payload", "world_payload",
]
