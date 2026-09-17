"""Quality / Repair 测试 fixture（零网络、零真实模型）。

`build_broken_blueprint()` 在 V4-04 Golden Blueprint 的基础上**刻意植入**（§62）：

```text
1 Canon contradiction           sc_001_03 outcome 使用被 Canon 禁止的"枪械"
1 knowledge continuity leak     sc_001_03 使用尚未揭示的 hidden_truth
1 character motivation gap      sc_001_04 做出决定但没有动机 / 压力
1 causal gap                    sc_001_04 没有因果入边且没有 escalation+conflict
2 semantic duplicate scenes     sc_001_02 与 sc_001_01 在 5 个结构字段上重复
1 no-function scene             sc_001_02 story_function 只有 transition
1 unpaid setup                  setup_001 没有任何 payoff 绑定
1 vague chapter goal            ch_001 goal = "关系进一步发展"
```

全部节点都是**结构合法**的（Q0/Q1 无 issue），因此断言只针对 Q2–Q9。
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


_memory_support = _load("memory_support_for_quality",
                        ROOT / "tests" / "memory" / "support.py")
_gen_support = _load("gen_support_for_quality",
                     ROOT / "tests" / "generation" / "gen_support.py")

build_novel = _memory_support.build_novel
service_for = _memory_support.service_for
stub_gateway = _gen_support.stub_gateway
chapter_payload = _gen_support.chapter_payload

WEAPON_RULE_TEXT = "主角不会使用枪械"
NOVEL_ID = "novel_alpha"


def save_node(repository: Any, node: Any) -> Any:
    return repository.save_revision(node, expected_revision=None)


def _node(novel_id: str, node_id: str, node_type: str, payload: Any, *,
          parent_id: str = "", sequence: int = 0,
          source_ids: Sequence[str] = ("FACT_WEAPON_RULE",),
          contract: str = "blueprint.fixture.v1") -> Any:
    from novelforge.blueprint import BlueprintNode

    return BlueprintNode(node_id=node_id, novel_id=novel_id, node_type=node_type,
                         payload=payload, parent_id=parent_id, sequence=sequence,
                         source_ids=tuple(source_ids), status="proposed",
                         generation_contract=contract, context_digest="fixture")


def broken_nodes(novel_id: str = NOVEL_ID) -> list[Any]:
    from novelforge.blueprint import (
        CausalLinkPayload,
        ChapterCardPayload,
        CharacterArcPayload,
        CharacterPayload,
        PayoffPayload,
        PremisePayload,
        SceneCardPayload,
        SetupPayload,
        StoryArcPayload,
        StructuralUnitPayload,
        ThemePayload,
        WorldPayload,
    )

    nodes: list[Any] = [
        _node(novel_id, "premise", "premise", PremisePayload(
            premise="一名维修工必须在断电倒计时内修好中转站的备用电源",
            central_conflict="主管拒绝开放旧记录，而破坏者来自内部",
            protagonist_goal="恢复备用电源", stakes="据点里所有人",
            dramatic_question="他愿意为修复付出什么代价？",
            story_promise="技术性解题 + 关系代价", genre="科幻", tone="冷峻",
            constraints=["不使用枪械"])),
        _node(novel_id, "theme", "theme", ThemePayload(
            theme="修复意味着承担", statement="修补他人留下的裂缝要付出自己的代价",
            counter_theme="先保住自己才有余力帮人",
            motifs=["损坏的电路", "备用电源"])),
        _node(novel_id, "world", "world", WorldPayload(
            rules=["断电后 12 小时内必须恢复，否则气象屏障失效"],
            locations=[{"id": "station", "name": "中转站", "kind": "site"}],
            factions=[{"id": "authority", "name": "管理局", "stance": "秩序维护方"}],
            resources=["备用电源", "维修件"],
            technology_or_magic=["旧式工业电网"],
            social_constraints=["进入核心区需要许可"],
            conflict_sources=["许可审批被拖延"],
            story_relevant_history=["十年前的大断电"])),
        _node(novel_id, "char_001", "character", CharacterPayload(
            name="主角", role="维修工", kind="player",
            goal="在断电倒计时结束前让中转站重新通电",
            motivation="证明自己修得好", need="被信任", fear="再次失去据点",
            misbelief="只要技术够好就不需要别人", strength="对旧电网了如指掌",
            flaw="不肯求助", conflict_source="许可与零件都被别人控制",
            relationships=[], story_function="承担主线行动", constraints=[])),
        _node(novel_id, "arc_001", "character_arc",
              CharacterArcPayload(
                  character_id="char_001", start_state="独自扛下所有维修工作",
                  internal_conflict="想被信任却不肯求助",
                  external_pressure="断电倒计时与审批拖延",
                  key_turns=["第一次开口求助"],
                  midpoint_change="承认自己修不好全部",
                  crisis="必须在保人或保电之间选择",
                  climax_choice="把最后一次机会交给对手",
                  end_state="学会与人共同承担"),
              parent_id="char_001", sequence=1),
        _node(novel_id, "story_arc", "story_arc", StoryArcPayload(
            initial_state="据点按例行节奏运转",
            inciting_incident="备用电源被发现破坏",
            progressive_complications=["许可被拖延", "零件被截留"],
            major_turns=["发现内部破坏者", "敌方掌握关键零件"],
            midpoint="主角意识到技术不是唯一问题",
            crisis="供电与救人只能选一个",
            climax="主角把修复权交给对手共同完成",
            resolution="据点通电，主角获得新的位置")),
        _node(novel_id, "unit_01", "structural_unit", StructuralUnitPayload(
            unit_type="act", title="第一幕：断电倒计时", goal="让读者看到压力",
            conflict="许可与时间", turn="内部破坏暴露",
            outcome="主角决定绕过常规流程"),
            parent_id="story_arc", sequence=1),
        # ① vague chapter goal（Q8）
        _node(novel_id, "ch_001", "chapter", ChapterCardPayload(
            title="被删除的维修日志", goal="关系进一步发展", pov="char_001",
            characters=["char_001"], location="station",
            conflict="主管拒绝开放旧记录", turn="日志编号仍存在于设备缓存",
            outcome="获得一条指向殖民区的线索", hook="缓存显示最后访问者已死亡",
            setup=[], payoff=[],
            state_change_intent=[{"kind": "knowledge", "actor": "char_001",
                                  "target": "core_record", "value": "known",
                                  "scope": "novel"}]),
            parent_id="unit_01", sequence=1),
        # 正常场：提供 reveal，供后续 knowledge 使用合法
        _node(novel_id, "sc_001_01", "scene", SceneCardPayload(
            chapter_id="ch_001", pov="char_001", location="station",
            time="第三天清晨",
            scene_purpose="让主角拿到被删除日志的第一条证据",
            character_goals=[], conflict="主管拒绝开放记录",
            escalation="对手把许可撤回", turn="缓存在设备里仍保留日志编号",
            outcome="主角获得线索但失去许可",
            information_reveal=["core_record 的最后访问者已死亡"],
            character_change="主角完成第一次开口求助，决定绕过流程",
            relationship_change="", setup=[], payoff=[],
            state_transition_intent=[],
            next_hook="死亡者为什么能访问缓存",
            story_function=["advance_plot", "reveal_information"]),
            parent_id="ch_001", sequence=1),
        # ② 语义重复（与 01 的 5 个字段完全相同）+ ③ 无叙事功能（只有 transition）
        _node(novel_id, "sc_001_02", "scene", SceneCardPayload(
            chapter_id="ch_001", pov="char_001", location="station",
            time="第三天正午",
            scene_purpose="让主角拿到被删除日志的第一条证据",
            character_goals=[], conflict="主管拒绝开放记录",
            escalation="对手把许可撤回", turn="缓存在设备里仍保留日志编号",
            outcome="主角获得线索但失去许可",
            information_reveal=[], character_change="", relationship_change="",
            setup=[], payoff=[],
            state_transition_intent=[{"kind": "knowledge", "actor": "char_001",
                                      "target": "core_record", "value": "known"}],
            next_hook="", story_function=["transition"]),
            parent_id="ch_001", sequence=2),
        # ④ Canon contradiction（"使用枪械"）+ ⑤ knowledge leak（hidden_truth）
        _node(novel_id, "sc_001_03", "scene", SceneCardPayload(
            chapter_id="ch_001", pov="char_001", location="station",
            time="第三天傍晚",
            scene_purpose="让主角确认破坏来自内部维修队列",
            character_goals=[], conflict="", escalation="",
            turn="残留编号指向内部维修队列",
            outcome="主角拿到内部维修记录：只有使用枪械才能压住现场的混乱",
            information_reveal=["内部维修队列存在异常编号"],
            character_change="", relationship_change="", setup=[], payoff=[],
            state_transition_intent=[{"kind": "knowledge", "actor": "char_001",
                                      "target": "hidden_truth", "value": "known"}],
            next_hook="谁在内部维修队列里留下了编号",
            story_function=["advance_plot"]),
            parent_id="ch_001", sequence=3),
        # ⑥ motivation gap + ⑦ causal gap（无入边、无 escalation/conflict）
        _node(novel_id, "sc_001_04", "scene", SceneCardPayload(
            chapter_id="ch_001", pov="char_001", location="station",
            time="第三天夜",
            scene_purpose="让主角在许可失效前做出取舍",
            character_goals=[], conflict="", escalation="",
            turn="许可即将在午夜失效",
            outcome="主角决定继续留在维修区查下去",
            information_reveal=[], character_change="", relationship_change="",
            setup=[], payoff=[], state_transition_intent=[],
            next_hook="午夜之后谁还留在维修区",
            story_function=["decision"]),
            parent_id="ch_001", sequence=4),
        # ⑧ unpaid setup（无 payoff 绑定）
        _node(novel_id, "setup_001", "setup", SetupPayload(
            content="备用电源曾被内部人员破坏", expected_payoff="", status="open"),
            parent_id="sc_001_03", sequence=1001,
            source_ids=("sc_001_03",), contract="deterministic.links.v1"),
    ]
    # 因果链：01 → 02、01 → 03（04 故意没有入边 → causal gap）
    nodes.extend([
        _node(novel_id, "cl_001", "causal_link", CausalLinkPayload(
            source_node="sc_001_01", target_node="sc_001_02", relation="causes",
            reason="上一场的结果改变了下一场的起点"), sequence=1,
            contract="deterministic.links.v1"),
        _node(novel_id, "cl_002", "causal_link", CausalLinkPayload(
            source_node="sc_001_01", target_node="sc_001_03", relation="causes",
            reason="上一场的结果改变了下一场的起点"), sequence=2,
            contract="deterministic.links.v1"),
    ])
    return nodes


def build_broken_blueprint(root: Path, novel_id: str = NOVEL_ID) -> Any:
    """写入 broken blueprint，返回 BlueprintRepository。"""

    from novelforge.blueprint import BlueprintRepository

    repository = BlueprintRepository(root, novel_id)
    for node in broken_nodes(novel_id):
        save_node(repository, node)
    return repository


def build_repairable_blueprint(root: Path, novel_id: str = NOVEL_ID) -> Any:
    """broken blueprint 的"全部可自动修"变体：setup_001 已被 payoff_001 回收。"""

    from novelforge.blueprint import BlueprintRepository, PayoffPayload, SetupPayload

    repository = BlueprintRepository(root, novel_id)
    for node in broken_nodes(novel_id):
        if node.node_id == "setup_001":  # 改成已回收状态
            continue
        save_node(repository, node)
    save_node(repository, _node(
        novel_id, "setup_001", "setup",
        SetupPayload(content="备用电源曾被内部人员破坏", expected_payoff="",
                     status="paid"),
        parent_id="sc_001_03", sequence=1001, source_ids=("sc_001_03",),
        contract="deterministic.links.v1"))
    save_node(repository, _node(
        novel_id, "payoff_001", "payoff",
        PayoffPayload(resolves_setup_ids=["setup_001"],
                      result="备用电源曾被内部人员破坏", status="paid"),
        parent_id="sc_001_04", sequence=1002, source_ids=("sc_001_04",),
        contract="deterministic.links.v1"))
    return repository


def build_quality_novel(tmp_path: Path, novel_id: str = NOVEL_ID) -> Any:
    """构造最小作品（profile / pack / Canon / StoryState）+ broken blueprint。"""

    build_novel(tmp_path, novel_id, title="阿尔法计划", fact_text=WEAPON_RULE_TEXT)
    return build_broken_blueprint(tmp_path, novel_id)


def quality_stack(tmp_path: Path, *, script: Sequence[Any] | None = (),
                  novel_id: str = NOVEL_ID, policy: Any = None,
                  repairable: bool = False,
                  extra_nodes: Sequence[Any] = ()) -> dict[str, Any]:
    """装配 memory / quality / generation / review（零网络）。"""

    from novelforge.application.services import ReviewService
    from novelforge.blueprint import BlueprintRepository
    from novelforge.generation import BlueprintGenerationService
    from novelforge.quality import QualityService

    build_novel(tmp_path, novel_id, title="阿尔法计划", fact_text=WEAPON_RULE_TEXT)
    repository = (build_repairable_blueprint(tmp_path, novel_id) if repairable
                  else build_broken_blueprint(tmp_path, novel_id))
    for extra in extra_nodes:
        save_node(repository, extra)
    memory = service_for(tmp_path, novel_id)
    quality = QualityService(tmp_path, novel_id, memory=memory,
                             repository=repository)
    generation = None
    provider = None
    if script is not None:
        gateway, provider = stub_gateway(list(script))
        generation = BlueprintGenerationService(tmp_path, novel_id, gateway=gateway,
                                                memory=memory)
    review = ReviewService(tmp_path, novel_id, quality=quality,
                           generation=generation, repository=repository,
                           policy=policy)
    return {"repository": repository, "memory": memory, "quality": quality,
            "generation": generation, "review": review, "provider": provider,
            "novel_id": novel_id}


# ------------------------------------------------------------ repair responses
def repaired_scene_payload(chapter_id: str = "ch_001", *,
                           sequence: int = 1) -> dict[str, Any]:
    """修复后的 Scene Card（三个变体互不重复，且不含任何 fixture 缺陷）。"""

    variants: dict[int, dict[str, Any]] = {
        1: {  # 替换 sc_001_02：语义不重复 + 有明确叙事功能
            "time": "第四天清晨",
            "scene_purpose": "让主角核对被撤回的许可记录",
            "conflict": "管理局要求他先交出设备再谈许可",
            "escalation": "管理局把设备列入了封存清单",
            "turn": "封存清单上出现了主管的签名",
            "outcome": "主角拿到主管签字的封存清单副本",
            "information_reveal": ["封存清单上有主管的签字"],
            "next_hook": "主管为什么要在断电前封存设备",
            "story_function": ["reveal_information", "advance_plot"]},
        2: {  # 替换 sc_001_03：不再使用被 Canon 禁止的物品；knowledge 已在前一场揭示
            "time": "第四天正午",
            "scene_purpose": "让主角追踪内部维修队列的改写痕迹",
            "conflict": "维修队列的记录被有权限的人移除",
            "escalation": "对手抢先一步封存了队列备份",
            "turn": "备份里保留了一次被移除的维修命令",
            "outcome": "主角拿到内部人员改写维修记录的证据",
            "information_reveal": ["维修命令的提交时间早于断电"],
            "next_hook": "谁有权提交并移除维修命令",
            "story_function": ["advance_plot", "reveal_information"]},
        3: {  # 替换 sc_001_04：有动机、有原因、有升级
            "time": "第四天傍晚",
            "scene_purpose": "让主角在封存压力下决定独自承担维修",
            "conflict": "主管要求他停止调查并交出全部记录",
            "escalation": "主管部门下达了强制撤离令",
            "turn": "撤离令会让备用电源彻底无人维护",
            "outcome": "主角决定留下并私下完成维修",
            "information_reveal": ["撤离令由主管本人申请"],
            "character_change": "主角第一次主动承担不属于自己的责任",
            "next_hook": "撤离令生效后还有谁留在中转站",
            "story_function": ["decision", "escalate_conflict"]},
    }
    base = variants.get(sequence, variants[1])
    payload: dict[str, Any] = {
        "chapter_id": chapter_id, "pov": "char_001", "location": "station",
        "character_goals": ["在许可失效前拿到内部维修记录"],
        "character_change": "", "relationship_change": "", "setup": [],
        "payoff": ["回收：被移除的维修命令"],
        "state_transition_intent": [{"kind": "knowledge", "actor": "char_001",
                                     "target": "core_record", "value": "known"}],
        **base}
    return payload


def repaired_chapter_payload() -> dict[str, Any]:
    return chapter_payload(
        title="维修队列里的异常编号",
        goal="确认内部维修队列是否被人为改写",
        characters=["char_001"],  # preserve：章节人物不得被质量修复改写
        conflict="维修队列的记录被有权限的人移除",
        turn="备份保留了被移除的命令",
        outcome="主角拿到内部人员改写记录的证据",
        hook="改写者在断电前就进入了核心区")


# ------------------------------------------------------------- 单 gate 测试助手
def node(novel_id: str, node_id: str, node_type: str, payload: Any, **kwargs: Any):
    return _node(novel_id, node_id, node_type, payload, **kwargs)


def scene(node_id: str, *, novel_id: str = NOVEL_ID, parent: str = "ch_001",
          sequence: int = 1, **fields: Any) -> Any:
    from novelforge.blueprint import SceneCardPayload

    payload: dict[str, Any] = {
        "chapter_id": parent, "pov": "char_001", "location": "station",
        "time": "第三天清晨", "scene_purpose": "让主角核对维修记录",
        "character_goals": ["拿到内部维修记录"], "conflict": "主管拒绝开放记录",
        "escalation": "许可被撤回", "turn": "缓存里仍保留维修编号",
        "outcome": "主角拿到线索但失去许可", "information_reveal": [],
        "character_change": "", "relationship_change": "", "setup": [], "payoff": [],
        "state_transition_intent": [], "next_hook": "谁删除了编号",
        "story_function": ["advance_plot"]}
    payload.update(fields)
    return _node(novel_id, node_id, "scene", SceneCardPayload(**payload),
                 parent_id=parent, sequence=sequence)


def chapter(node_id: str = "ch_001", *, novel_id: str = NOVEL_ID,
            parent: str = "unit_01", sequence: int = 1, **fields: Any) -> Any:
    from novelforge.blueprint import ChapterCardPayload

    payload: dict[str, Any] = {"title": "被删除的维修日志",
                               "goal": "确认内部维修队列是否被人为改写",
                               "conflict": "记录被有权限的人移除",
                               "turn": "备份保留了被移除的命令",
                               "outcome": "拿到内部人员改写的证据",
                               "hook": "改写者在断电前就进入了核心区",
                               "characters": ["char_001"], "pov": "char_001",
                               "location": "station", "setup": [], "payoff": [],
                               "state_change_intent": []}
    payload.update(fields)
    return _node(novel_id, node_id, "chapter", ChapterCardPayload(**payload),
                 parent_id=parent, sequence=sequence)


def setup_node(node_id: str = "setup_001", *, novel_id: str = NOVEL_ID,
               parent: str = "sc_001_01", sequence: int = 1001,
               content: str = "备用电源曾被内部人员破坏",
               status: str = "open") -> Any:
    from novelforge.blueprint import SetupPayload

    return _node(novel_id, node_id, "setup",
                 SetupPayload(content=content, status=status),
                 parent_id=parent, sequence=sequence,
                 source_ids=(parent,), contract="deterministic.links.v1")


def payoff_node(node_id: str = "payoff_001", *, novel_id: str = NOVEL_ID,
                parent: str = "sc_001_02", sequence: int = 1002,
                resolves: Sequence[str] = ("setup_001",),
                result: str = "备用电源曾被内部人员破坏") -> Any:
    from novelforge.blueprint import PayoffPayload

    return _node(novel_id, node_id, "payoff",
                 PayoffPayload(resolves_setup_ids=list(resolves), result=result,
                               status="paid"),
                 parent_id=parent, sequence=sequence,
                 source_ids=(parent,), contract="deterministic.links.v1")


def causal_node(source: str, target: str, *, node_id: str = "", index: int = 1,
                relation: str = "causes", novel_id: str = NOVEL_ID) -> Any:
    from novelforge.blueprint import CausalLinkPayload

    return _node(novel_id, node_id or f"cl_{index:03d}", "causal_link",
                 CausalLinkPayload(source_node=source, target_node=target,
                                   relation=relation),
                 sequence=index, contract="deterministic.links.v1")


def isolated_gate(tmp_path: Path, nodes: Sequence[Any], gate: str, *,
                  novel_id: str = NOVEL_ID, with_novel: bool = True,
                  fact_text: str = WEAPON_RULE_TEXT,
                  policy: Any = None) -> tuple[Any, ...]:
    """写入 nodes 后只评估一个 gate；返回 (issues, quality_service)。"""

    from novelforge.quality import QualityPolicy, QualityService

    from novelforge.blueprint import BlueprintRepository

    repository = BlueprintRepository(tmp_path, novel_id)
    for item in nodes:
        save_node(repository, item)
    memory = None
    if with_novel:
        build_novel(tmp_path, novel_id, title="阿尔法计划", fact_text=fact_text)
        memory = service_for(tmp_path, novel_id)
    quality = QualityService(tmp_path, novel_id, memory=memory,
                             repository=repository)
    report = quality.evaluate(
        gates=(gate,), policy=policy or QualityPolicy(required_gates=(gate,)))
    return report.issues, quality


def codes(issues: Sequence[Any]) -> list[str]:
    return sorted(issue.code for issue in issues)


def direct_context(nodes: Sequence[Any], *, novel_id: str = NOVEL_ID,
                   repository: Any = None, memory: Any = None,
                   scope: Any = None, policy: Any = None) -> Any:
    """直接构造 EvaluationContext（用于模拟磁盘上不可能出现的损坏）。"""

    from novelforge.quality import QualityPolicy, QualityScope
    from novelforge.quality.evaluators.base import EvaluationContext

    by_id = {item.node_id: item for item in nodes}
    resolved_scope = scope or QualityScope(
        novel_id=novel_id, node_ids=tuple(sorted(by_id)), kind="blueprint")
    return EvaluationContext(novel_id=novel_id, scope=resolved_scope,
                             nodes=by_id, policy=policy or QualityPolicy(),
                             repository=repository, memory=memory)


__all__ = [
    "NOVEL_ID", "WEAPON_RULE_TEXT", "build_broken_blueprint",
    "build_quality_novel", "build_repairable_blueprint", "build_novel",
    "broken_nodes", "causal_node", "chapter", "chapter_payload", "codes",
    "direct_context",
    "isolated_gate", "node", "payoff_node", "quality_stack",
    "repaired_chapter_payload", "repaired_scene_payload", "save_node", "scene",
    "service_for", "setup_node", "stub_gateway",
]
