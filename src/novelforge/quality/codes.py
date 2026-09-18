"""Issue Code Registry（V4-05 §28）。

**LLM 不得自由生成 issue code**：critic 只能从本注册表里选。
每个 code 固定声明：属于哪个 Gate、最低 severity、是否可自动修、默认 preserve / allow_change。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IssueCodeSpec:
    code: str
    gate: str
    severity: str
    repairable: bool
    description: str = ""
    preserve: tuple[str, ...] = ()
    allow_change: tuple[str, ...] = ()


def _spec(code: str, gate: str, severity: str, repairable: bool,
          description: str = "", preserve: tuple[str, ...] = (),
          allow_change: tuple[str, ...] = ()) -> IssueCodeSpec:
    return IssueCodeSpec(code=code, gate=gate, severity=severity,
                         repairable=repairable, description=description,
                         preserve=preserve, allow_change=allow_change)


#: 统一 code registry（V4-05 §28 列表 + 各 Gate 实际产出）
ISSUE_CODES: tuple[IssueCodeSpec, ...] = (
    # Q0 Schema
    _spec("SCHEMA_INVALID", "Q0", "blocker", False, "节点 payload / 结构不符合 schema"),
    _spec("REFERENCE_BROKEN", "Q0", "blocker", False, "引用了不存在的节点或字段"),
    _spec("PARENT_TYPE_INVALID", "Q0", "blocker", False, "父节点类型不符合层级约束"),
    _spec("SEQUENCE_INVALID", "Q0", "major", False, "子节点 sequence 缺失 / 重复"),
    # Q1 Integrity
    _spec("OWNERSHIP_MISMATCH", "Q1", "blocker", False, "节点归属与请求作品不一致"),
    _spec("DUPLICATE_NODE_ID", "Q1", "blocker", False, "同一 node_id 出现多次"),
    _spec("REVISION_CHAIN_BROKEN", "Q1", "blocker", False, "revision / parent_revision 链不连续"),
    _spec("MISSING_REQUIRED_NODE", "Q1", "major", False, "缺少必需节点"),
    _spec("PROVENANCE_INVALID", "Q1", "minor", False, "provenance / source_ids 不完整"),
    _spec("UNEVALUATED_REQUIRED_GATE", "Q1", "minor", False, "必需 gate 尚未评估"),
    _spec("INDEX_INCONSISTENT", "Q1", "major", False, "index / manifest 与节点文件不一致"),
    _spec("IDEMPOTENCY_INCONSISTENT", "Q1", "minor", False, "idempotency 记录与节点不匹配"),
    # Q2 Canon
    _spec("CANON_CONTRADICTION", "Q2", "blocker", True,
          "蓝图与已确认 Canon 事实冲突",
          preserve=("node_id", "characters", "source_ids"),
          allow_change=("goal", "conflict", "turn", "outcome", "title")),
    _spec("CANON_CHARACTER_IDENTITY_CONFLICT", "Q2", "blocker", True,
          "与人物身份 / 角色状态冲突",
          preserve=("node_id", "source_ids"),
          allow_change=("goal", "conflict", "turn", "outcome")),
    # Q3 Continuity
    _spec("CONTINUITY_TIME_CONFLICT", "Q3", "major", True,
          "时间顺序在相邻场景之间不成立",
          preserve=("node_id", "chapter_id", "source_ids"),
          allow_change=("time", "pov", "scene_purpose", "conflict", "turn", "outcome")),
    _spec("CONTINUITY_LOCATION_CONFLICT", "Q3", "major", True,
          "地点跳转缺少过渡",
          preserve=("node_id", "chapter_id", "source_ids"),
          allow_change=("location", "scene_purpose", "escalation", "turn")),
    _spec("CONTINUITY_KNOWLEDGE_LEAK", "Q3", "major", True,
          "角色使用了尚未获得的信息",
          preserve=("node_id", "source_ids"),
          allow_change=("scene_purpose", "information_reveal", "conflict", "turn")),
    _spec("CONTINUITY_RELATIONSHIP_CONFLICT", "Q3", "minor", True,
          "关系变化缺少前置事件",
          preserve=("node_id", "source_ids"),
          allow_change=("relationship_change", "conflict", "turn")),
    # Q4 Character
    _spec("CHARACTER_MOTIVATION_GAP", "Q4", "major", True,
          "角色行为缺少动机或前置压力",
          preserve=("node_id", "characters", "source_ids"),
          allow_change=("character_goals", "conflict", "escalation", "turn", "outcome")),
    _spec("CHARACTER_ARC_STALL", "Q4", "major", True,
          "人物弧长时间没有推进",
          preserve=("node_id", "character_id", "source_ids"),
          allow_change=("key_turns", "midpoint_change", "crisis", "climax_choice")),
    _spec("CHARACTER_ARC_UNSUPPORTED_TURN", "Q4", "major", True,
          "人物弧的关键转折没有场景支撑",
          preserve=("node_id", "character_id", "source_ids"),
          allow_change=("key_turns", "linked_scenes", "midpoint_change")),
    # Q5 Causality
    _spec("CAUSAL_GAP", "Q5", "major", True,
          "关键结果缺少原因（事件突然发生）",
          preserve=("node_id", "chapter_id", "source_ids"),
          allow_change=("scene_purpose", "conflict", "escalation", "turn", "outcome")),
    _spec("UNMOTIVATED_DECISION", "Q5", "major", True,
          "关键决定缺少动机",
          preserve=("node_id", "characters", "source_ids"),
          allow_change=("character_goals", "conflict", "turn", "outcome")),
    _spec("ORPHAN_EVENT", "Q5", "minor", True,
          "场景既不由前因产生，也不产生后果",
          preserve=("node_id", "source_ids"),
          allow_change=("scene_purpose", "outcome", "next_hook")),
    _spec("CIRCULAR_DEPENDENCY", "Q5", "major", False,
          "因果链出现环（A 依赖 B，B 依赖 A）"),
    _spec("UNSUPPORTED_PAYOFF", "Q5", "major", True,
          "回收没有前置埋设支撑",
          preserve=("node_id", "source_ids"),
          allow_change=("payoff", "setup", "outcome")),
    _spec("DEAD_BRANCH", "Q5", "minor", True,
          "线索从此不再被使用",
          preserve=("node_id", "source_ids"),
          allow_change=("setup", "next_hook", "outcome")),
    # Q6 Semantic
    _spec("SCENE_SEMANTIC_REPETITION", "Q6", "major", True,
          "连续场景承担相同叙事动作",
          preserve=("node_id", "chapter_id", "source_ids"),
          allow_change=("scene_purpose", "conflict", "escalation", "turn", "outcome",
                        "story_function")),
    _spec("CHAPTER_GOAL_REPETITION", "Q6", "major", True,
          "章节目标重复",
          preserve=("node_id", "characters", "parent_id", "source_ids"),
          allow_change=("title", "goal", "conflict", "turn", "hook")),
    _spec("TITLE_SEMANTIC_REPETITION", "Q6", "major", True,
          "标题语义重复（字符串唯一但意思相同）",
          preserve=("node_id", "source_ids"), allow_change=("title",)),
    _spec("CONFLICT_PATTERN_REPETITION", "Q6", "minor", True,
          "冲突模式重复",
          preserve=("node_id", "source_ids"),
          allow_change=("conflict", "escalation", "turn")),
    _spec("HOLLOW_NODE", "Q6", "minor", True,
          "节点内容空洞（无具体信息）",
          preserve=("node_id", "source_ids"),
          allow_change=("goal", "conflict", "turn", "outcome", "scene_purpose")),
    # Q7 Narrative
    _spec("SCENE_NO_NARRATIVE_FUNCTION", "Q7", "major", True,
          "场景没有任何叙事功能（删掉也不损失）",
          preserve=("node_id", "chapter_id", "source_ids"),
          allow_change=("story_function", "scene_purpose", "conflict", "escalation",
                        "turn", "outcome", "next_hook")),
    _spec("PACING_STAGNATION", "Q7", "minor", True,
          "连续多场没有升级或转折",
          preserve=("node_id", "chapter_id", "source_ids"),
          allow_change=("conflict", "escalation", "turn", "story_function")),
    _spec("CLIMAX_UNPREPARED", "Q7", "major", True,
          "高潮缺少前置积累",
          preserve=("node_id", "source_ids"),
          allow_change=("climax", "crisis", "major_turns")),
    _spec("RESOLUTION_INCOMPLETE", "Q7", "major", True,
          "收束没有覆盖主要冲突",
          preserve=("node_id", "source_ids"),
          allow_change=("resolution", "climax")),
    _spec("SETUP_PAYOFF_DISTRIBUTION_SKEW", "Q7", "minor", True,
          "setup / payoff 分布严重不均",
          preserve=("node_id", "source_ids"),
          allow_change=("setup", "payoff", "next_hook")),
    # Q8 Blueprint Style
    _spec("BLUEPRINT_VAGUE_CONTENT", "Q8", "major", True,
          "内容过于泛化 / 模板化（无法执行）",
          preserve=("node_id", "source_ids"),
          allow_change=("goal", "conflict", "turn", "outcome", "title",
                        "scene_purpose")),
    _spec("BLUEPRINT_FIELD_LABEL_TEXT", "Q8", "major", True,
          "字段标签 / 内部枚举进入作者可见文本",
          preserve=("node_id", "source_ids"),
          allow_change=("title", "goal", "conflict", "turn", "outcome", "hook",
                        "scene_purpose")),
    _spec("BLUEPRINT_PLACEHOLDER_TEXT", "Q8", "major", True,
          "出现占位符（未命名 / TODO / 待定）",
          preserve=("node_id", "source_ids"),
          allow_change=("goal", "conflict", "turn", "outcome", "title")),
    _spec("BLUEPRINT_TITLE_TOO_SIMILAR", "Q8", "minor", True,
          "标题大量相似（措辞重复）",
          preserve=("node_id", "source_ids"), allow_change=("title",)),
    # Q9 Delivery readiness
    _spec("DELIVERY_MISSING_REQUIRED_NODE", "Q9", "blocker", False,
          "缺少交付必需的核心节点"),
    _spec("DELIVERY_UNRESOLVED_BLOCKER", "Q9", "blocker", False,
          "仍有 blocker issue 未处理"),
    _spec("DELIVERY_UNPAID_SETUP", "Q9", "major", True,
          "交付前仍有未回收的必需 setup",
          preserve=("node_id", "source_ids"),
          allow_change=("setup", "payoff", "outcome")),
    _spec("DELIVERY_MISSING_CHAPTER_OR_SCENE", "Q9", "blocker", False,
          "缺失章节 / 场景"),
    _spec("DELIVERY_ORPHAN_NODE", "Q9", "minor", True,
          "存在孤立节点",
          preserve=("node_id", "source_ids"), allow_change=("parent_id",)),
    _spec("DELIVERY_PLACEHOLDER", "Q9", "major", True,
          "交付物含占位内容",
          preserve=("node_id", "source_ids"),
          allow_change=("goal", "title", "outcome")),
    _spec("DELIVERY_CROSS_NOVEL_CONTAMINATION", "Q9", "blocker", False,
          "检测到其他作品的数据"),
)

CODE_REGISTRY: dict[str, IssueCodeSpec] = {spec.code: spec for spec in ISSUE_CODES}

#: V4-09 §36：第三方（plugin）issue code 动态注册表（必须 namespaced）
PLUGIN_CODE_REGISTRY: dict[str, IssueCodeSpec] = {}


def register_plugin_code(code: str, *, gate: str, severity: str, plugin_id: str,
                         description: str = "", repairable: bool = False
                         ) -> IssueCodeSpec:
    """注册插件 issue code：必须形如 `plugin.<plugin_id>.<CODE>`（§36）。"""

    from .errors import QualityPolicyError

    value = str(code or "").strip()
    expected_prefix = f"plugin.{plugin_id}."
    if not value.startswith(expected_prefix):
        raise QualityPolicyError(
            f"插件 issue code 必须使用 namespace {expected_prefix}*",
            details={"code": value, "plugin_id": plugin_id})
    if value in CODE_REGISTRY:
        raise QualityPolicyError(f"插件 code 不得覆盖 Core code：{value}",
                                 details={"code": value})
    spec = IssueCodeSpec(code=value, gate=str(gate), severity=str(severity),
                         repairable=bool(repairable), description=str(description))
    PLUGIN_CODE_REGISTRY[value] = spec
    return spec


def unregister_plugin_codes(plugin_id: str) -> int:
    before = len(PLUGIN_CODE_REGISTRY)
    for code in [key for key in PLUGIN_CODE_REGISTRY
                 if key.startswith(f"plugin.{plugin_id}.")]:
        PLUGIN_CODE_REGISTRY.pop(code, None)
    return before - len(PLUGIN_CODE_REGISTRY)


def code_spec(code: str) -> IssueCodeSpec:
    spec = CODE_REGISTRY.get(str(code)) or PLUGIN_CODE_REGISTRY.get(str(code))
    if spec is None:
        raise KeyError(f"未注册的 issue code：{code}")
    return spec


def codes_for_gate(gate: str) -> tuple[str, ...]:
    return tuple(spec.code for spec in ISSUE_CODES if spec.gate == gate)


def is_registered(code: str) -> bool:
    value = str(code)
    return value in CODE_REGISTRY or value in PLUGIN_CODE_REGISTRY


__all__ = ["CODE_REGISTRY", "ISSUE_CODES", "PLUGIN_CODE_REGISTRY", "IssueCodeSpec",
           "code_spec", "codes_for_gate", "is_registered", "register_plugin_code",
           "unregister_plugin_codes"]
