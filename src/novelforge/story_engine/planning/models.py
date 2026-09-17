"""M2A：Story Planning IR V1 数据模型（Design / Models / Schema）。

四层边界（本文件只负责第一层）：

- **Story Planning IR = future planning truth**：还没有发生的计划、意图、节点与弧；
- Canon = confirmed stable truth（已确认的稳定事实与身份）；
- StoryState = happened runtime truth（真正发生过的运行时事实）；
- Chapter Semantic IR = 章节执行计划（一章怎么执行）。

硬规则：

1. Planning 只**引用** Canon / StoryState / Chapter IR 的稳定 ID，不复制它们的实体、
   事实、事件、知识、关系、状态模型（不建立第二套 truth source）；
2. Planning 不能把未来写成 happened：本模块没有 `status="happened"` 之类的字段，
   伏笔计划只能停在 `planned`，事实性判定必须由正式 service 在 Canon 侧完成；
3. 稳定 ID 在创建时确定，禁止从 display name / chapter number / 可变描述派生
   （复用 `canon.ids` 的禁止模式与 key 形态）；
4. 每个 planning 模型都带 provenance：generated / inferred 不得覆盖 supplied。

M2A 只建立模型能力，不实现 Builder / Compiler / LLM Planner（M2B / M3）。
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from novelforge.models import StrictModel
from novelforge.story_engine.canon.ids import (
    FORBIDDEN_ID_PATTERN,
    KEY_PATTERN,
    new_random_key,
)

from .enums import (
    AutonomousVisibility,
    ConflictScope,
    EquipmentPlannedState,
    FactionRelationType,
    ForeshadowMoveType,
    InformationMoveType,
    MapExpansionStage,
    NodeEdgeRelation,
    PacingChannel,
    PlanningDetailLevel,
    PLANNING_ID_PREFIXES,
    PLANNING_SCHEMA_VERSION,
    PlotNodeImportance,
    ProgressionCategory,
    Provenance,
    RequirementKind,
    RequirementOperator,
    PlotPressureKind,
    PressureState,
    ResourceFlowRepeatability,
    ResourceFlowType,
    ResourceScarcity,
    RewardMagnitude,
    RewardScope,
    RewardType,
    TimelineStatus,
    TimelineTimeKind,
    UnitKind,
    WorldRuleType,
)


def planning_id(value: str, kind: str) -> str:
    """校验 planning 稳定 ID 形态；拒绝章节号 / 序号型 identity。"""

    prefix = PLANNING_ID_PREFIXES[kind]
    if FORBIDDEN_ID_PATTERN.match(value or ""):
        raise ValueError(f"chapter/order 型编号不能作为 planning identity：{value}")
    if not (value or "").startswith(prefix + "_"):
        raise ValueError(f"planning id 前缀必须是 {prefix}_：{value}")
    key = value[len(prefix) + 1:]
    if not KEY_PATTERN.match(key):
        raise ValueError(f"planning key 形态非法（A-Z0-9_）：{key}")
    return value


def new_planning_id(kind: str, key: str = "") -> str:
    """生成稳定 ID。无语义 key 时使用随机 key，并必须被持久化复用（同 Canon 规则）。"""

    return f"{PLANNING_ID_PREFIXES[kind]}_{(key or new_random_key()).upper()}"


# 拉丁词用词边界；中文短语直接匹配（\b 对 CJK 不生效）
_ACTIVE_TEXT = re.compile(r"\b(happened|occurred)\b|已完成|已发生|已经发生|已落实")


class PlannedModel(StrictModel):
    """所有 planning 条目的公共外壳：provenance + source + 确认引用 + 规划深度。"""

    provenance: Provenance = "generated"
    source: str = Field(default="", max_length=96)
    confirmation_ref: str = Field(default="", max_length=160)
    note: str = Field(default="", max_length=300)
    # Progressive Elaboration：同一个作者计划里，不同对象可以停在不同的规划深度
    detail_level: PlanningDetailLevel = "concept"


class NovelIntent(PlannedModel):
    """一句话创意 → 创作意图。只描述目标，不描述任何已发生事实。"""

    intent_id: str = Field(min_length=8, max_length=64)
    novel_id: str = Field(min_length=1, max_length=96)
    genre: str = Field(default="", max_length=64)
    subgenres: list[str] = Field(default_factory=list)
    target_words: int = Field(default=0, ge=0, le=20_000_000)
    target_reader: str = Field(default="", max_length=200)
    commercial_promise: str = Field(default="", max_length=300)
    reader_experience: list[str] = Field(default_factory=list)
    tone: str = Field(default="", max_length=200)
    pace_strategy: str = Field(default="", max_length=200)
    template_id: str = Field(default="", max_length=64)

    @field_validator("intent_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return planning_id(value, "intent")


class ThemePlan(PlannedModel):
    """主题：只约束策划方向，不自动成为 happened fact。"""

    theme_id: str = Field(min_length=7, max_length=64)
    central_theme: str = Field(default="", max_length=300)
    dramatic_question: str = Field(default="", max_length=300)
    value_conflicts: list[str] = Field(default_factory=list)
    protagonist_internal_question: str = Field(default="", max_length=300)
    final_answer_direction: str = Field(default="", max_length=300)

    @field_validator("theme_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return planning_id(value, "theme")


class WorldRule(PlannedModel):
    """世界规则。belief / rumor 不能直接成为 Canon fact。"""

    rule_id: str = Field(min_length=6, max_length=64)
    rule_type: WorldRuleType = "hard_rule"
    statement: str = Field(default="", max_length=400)
    scope: str = Field(default="", max_length=120)
    enforcement: str = Field(default="", max_length=200)
    consequences: list[str] = Field(default_factory=list)
    canon_fact_ref: str = Field(default="", max_length=160)
    canon_constraint_ref: str = Field(default="", max_length=160)

    @field_validator("rule_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return planning_id(value, "rule")


class WorldPlan(PlannedModel):
    """世界设定：规则 + 历史 / 社会 / 经济 / 技术 / 环境的规划文本。"""

    world_id: str = Field(min_length=7, max_length=64)
    world_rules: list[WorldRule] = Field(default_factory=list)
    history: str = Field(default="", max_length=1200)
    society: str = Field(default="", max_length=800)
    politics: str = Field(default="", max_length=800)
    economy: str = Field(default="", max_length=800)
    resource_system: str = Field(default="", max_length=800)
    technology: str = Field(default="", max_length=800)
    power_system: str = Field(default="", max_length=800)
    environment: str = Field(default="", max_length=800)
    hazards: list[str] = Field(default_factory=list)
    transport: str = Field(default="", max_length=400)
    communication: str = Field(default="", max_length=400)
    taboos: list[str] = Field(default_factory=list)

    @field_validator("world_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return planning_id(value, "world")


class CharacterPlan(PlannedModel):
    """人物规划：只写目标 / 需求 / 恐惧 / 弧线，不复制 CanonEntity 的身份字段。"""

    character_id: str = Field(min_length=6, max_length=64)
    entity_ref: str = Field(default="", max_length=160)
    display_name: str = Field(default="", max_length=80)
    external_goal: str = Field(default="", max_length=300)
    internal_need: str = Field(default="", max_length=300)
    desire: str = Field(default="", max_length=300)
    fear: str = Field(default="", max_length=300)
    wound: str = Field(default="", max_length=300)
    false_belief: str = Field(default="", max_length=300)
    strength: str = Field(default="", max_length=300)
    weakness: str = Field(default="", max_length=300)
    secret: str = Field(default="", max_length=300)
    knowledge_boundary: list[str] = Field(default_factory=list)
    story_function: str = Field(default="", max_length=200)
    character_arc_id: str = Field(default="", max_length=64)

    @field_validator("character_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return planning_id(value, "character")


class ArcChoice(PlannedModel):
    """弧线上的重大选择：必须能下沉到 ChapterSemanticIR.decision。"""

    node_id: str = Field(default="", max_length=64)
    decision_owner_ref: str = Field(default="", max_length=160)
    choice: str = Field(default="", max_length=300)
    expected_change: str = Field(default="", max_length=300)
    has_alternative: bool = True


class CharacterArc(PlannedModel):
    arc_id: str = Field(min_length=7, max_length=64)
    character_id: str = Field(min_length=6, max_length=64)
    start_state: str = Field(default="", max_length=300)
    pressure: str = Field(default="", max_length=300)
    choice: str = Field(default="", max_length=300)
    change: str = Field(default="", max_length=300)
    regression: str = Field(default="", max_length=300)
    breakthrough: str = Field(default="", max_length=300)
    end_state: str = Field(default="", max_length=300)
    major_choices: list[ArcChoice] = Field(default_factory=list)

    @field_validator("arc_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return planning_id(value, "char_arc")

    @field_validator("character_id")
    @classmethod
    def _character(cls, value: str) -> str:
        return planning_id(value, "character")


class RelationshipStage(PlannedModel):
    """关系不是单个 current value，而是带触发条件与不可逆点的阶段链。"""

    stage_id: str = Field(default="", max_length=64)
    label: str = Field(default="", max_length=120)
    trigger: str = Field(default="", max_length=300)
    # M5：显式节点绑定优先于 trigger 文本解析（文本仍是作者展示用）
    trigger_node_id: str = Field(default="", max_length=64)
    state: str = Field(default="", max_length=300)
    irreversible: bool = False


class RelationshipArc(PlannedModel):
    arc_id: str = Field(min_length=8, max_length=64)
    participants: list[str] = Field(default_factory=list)
    start_state: str = Field(default="", max_length=300)
    stages: list[RelationshipStage] = Field(default_factory=list)
    triggers: list[str] = Field(default_factory=list)
    relationship_change: str = Field(default="", max_length=300)
    irreversible_node: str = Field(default="", max_length=64)
    future_payoff: str = Field(default="", max_length=300)

    @field_validator("arc_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return planning_id(value, "relationship_arc")

    @model_validator(mode="after")
    def _participants(self) -> "RelationshipArc":
        if len(self.participants) < 2:
            raise ValueError("关系弧至少要有两个参与者")
        if len(set(self.participants)) != len(self.participants):
            raise ValueError("关系弧的参与者不能重复")
        return self


class FactionPlan(PlannedModel):
    faction_id: str = Field(min_length=9, max_length=64)
    entity_ref: str = Field(default="", max_length=160)
    display_name: str = Field(default="", max_length=80)
    goal: str = Field(default="", max_length=300)
    resources: list[str] = Field(default_factory=list)
    territory: list[str] = Field(default_factory=list)
    public_goal: str = Field(default="", max_length=300)
    hidden_goal: str = Field(default="", max_length=300)
    strategy: str = Field(default="", max_length=300)
    red_line: str = Field(default="", max_length=300)
    allies: list[str] = Field(default_factory=list)
    enemies: list[str] = Field(default_factory=list)
    relationship_to_protagonist: str = Field(default="", max_length=300)
    faction_arc_id: str = Field(default="", max_length=64)

    @field_validator("faction_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return planning_id(value, "faction")


class FactionStage(PlannedModel):
    stage_id: str = Field(default="", max_length=64)
    label: str = Field(default="", max_length=120)
    strategy: str = Field(default="", max_length=300)
    trigger: str = Field(default="", max_length=300)
    trigger_node_id: str = Field(default="", max_length=64)
    expected_state: str = Field(default="", max_length=300)


class FactionArc(PlannedModel):
    arc_id: str = Field(min_length=6, max_length=64)
    faction_id: str = Field(min_length=9, max_length=64)
    stages: list[FactionStage] = Field(default_factory=list)
    start_state: str = Field(default="", max_length=300)
    end_state: str = Field(default="", max_length=300)

    @field_validator("arc_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return planning_id(value, "faction_arc")

    @field_validator("faction_id")
    @classmethod
    def _faction(cls, value: str) -> str:
        return planning_id(value, "faction")


class LocationPlan(PlannedModel):
    location_id: str = Field(min_length=5, max_length=64)
    entity_ref: str = Field(default="", max_length=160)
    display_name: str = Field(default="", max_length=80)
    parent_region: str = Field(default="", max_length=64)
    environment: str = Field(default="", max_length=300)
    resources: list[str] = Field(default_factory=list)
    hazards: list[str] = Field(default_factory=list)
    entry_requirement: str = Field(default="", max_length=300)
    entry_requirement_group: RequirementGroup | None = None
    exit_routes: list[str] = Field(default_factory=list)
    travel_cost: str = Field(default="", max_length=200)
    story_function: str = Field(default="", max_length=200)
    discoverability: str = Field(default="", max_length=200)
    current_planned_state: str = Field(default="", max_length=300)

    @field_validator("location_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return planning_id(value, "location")


class LocationEdge(PlannedModel):
    """地图边：用于地图扩张、旅行合理性与路线解锁。"""

    from_location_id: str = Field(min_length=5, max_length=64)
    to_location_id: str = Field(min_length=5, max_length=64)
    route: str = Field(default="", max_length=120)
    distance: float = Field(default=0, ge=0)
    travel_time: str = Field(default="", max_length=80)
    risk: str = Field(default="", max_length=200)
    requirement: str = Field(default="", max_length=200)
    requirement_group: RequirementGroup | None = None
    availability: str = Field(default="", max_length=200)

    @field_validator("from_location_id", "to_location_id")
    @classmethod
    def _locations(cls, value: str) -> str:
        return planning_id(value, "location")


class LocationGraph(PlannedModel):
    graph_id: str = Field(min_length=10, max_length=64)
    location_ids: list[str] = Field(default_factory=list)
    edges: list[LocationEdge] = Field(default_factory=list)

    @field_validator("graph_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return planning_id(value, "location_graph")


class TimelineEntry(PlannedModel):
    """时间线条目：sequence_order / anchor_node_id 才是排序依据，estimated_chapter 只是估算。

    不复制 CanonEvent：已确认的历史通过 `canon_event_ref` / `canon_fact_ref` 引用；
    规划中的未来、假说与传说继续留在 Planning，并带 status / provenance。
    """

    entry_id: str = Field(min_length=5, max_length=64)
    label: str = Field(default="", max_length=200)
    status: TimelineStatus = "planned"
    time_kind: TimelineTimeKind = "sequence_order"
    sequence_order: int = Field(default=0, ge=0)
    absolute_time: str = Field(default="", max_length=120)
    relative_time: str = Field(default="", max_length=200)
    era: str = Field(default="", max_length=120)
    anchor_node_id: str = Field(default="", max_length=64)
    estimated_chapter: int | None = Field(default=None, ge=0)
    relative_to: list[str] = Field(default_factory=list)
    span: str = Field(default="", max_length=120)
    participants: list[str] = Field(default_factory=list)
    canon_event_ref: str = Field(default="", max_length=160)
    canon_fact_ref: str = Field(default="", max_length=160)

    @field_validator("entry_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return planning_id(value, "timeline_entry")


class TimelinePlan(PlannedModel):
    timeline_id: str = Field(min_length=4, max_length=64)
    world_history: list[TimelineEntry] = Field(default_factory=list)
    story_timeline: list[TimelineEntry] = Field(default_factory=list)
    character_timeline: dict[str, list[TimelineEntry]] = Field(default_factory=dict)

    @field_validator("timeline_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return planning_id(value, "timeline")


class InformationTruth(PlannedModel):
    """一条待揭示的真相；谁（读者 / 主角 / 角色 / 势力）知道由计划给定。

    与 CanonKnowledge 的边界：这里只是计划，实际“谁知道”以 Canon / StoryState 为准。
    """

    truth_id: str = Field(min_length=7, max_length=64)
    statement: str = Field(default="", max_length=400)
    reader_knows: bool = False
    protagonist_knows: bool = False
    character_knows: list[str] = Field(default_factory=list)
    faction_knows: list[str] = Field(default_factory=list)
    canon_fact_ref: str = Field(default="", max_length=160)
    access_requirement: str = Field(default="", max_length=200)

    @field_validator("truth_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return planning_id(value, "truth")


class InformationMove(PlannedModel):
    move_id: str = Field(min_length=7, max_length=64)
    truth_id: str = Field(min_length=7, max_length=64)
    move_type: InformationMoveType = "hint"
    node_id: str = Field(default="", max_length=64)
    holder_ids: list[str] = Field(default_factory=list)
    description: str = Field(default="", max_length=300)

    @field_validator("move_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return planning_id(value, "information_move")

    @field_validator("truth_id")
    @classmethod
    def _truth(cls, value: str) -> str:
        return planning_id(value, "truth")


class InformationArc(PlannedModel):
    arc_id: str = Field(min_length=6, max_length=64)
    truths: list[InformationTruth] = Field(default_factory=list)
    truth_ids: list[str] = Field(default_factory=list)
    moves: list[InformationMove] = Field(default_factory=list)
    start_state: str = Field(default="", max_length=300)
    end_state: str = Field(default="", max_length=300)

    @field_validator("arc_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return planning_id(value, "information_arc")

    @model_validator(mode="after")
    def _truth_index(self) -> "InformationArc":
        ids = [truth.truth_id for truth in self.truths]
        if self.truth_ids and list(self.truth_ids) != ids:
            raise ValueError("truth_ids 必须与 truths 中定义的 truth_id 完全一致")
        object.__setattr__(self, "truth_ids", ids)
        return self


class ForeshadowMove(PlannedModel):
    move_id: str = Field(min_length=8, max_length=64)
    move_type: ForeshadowMoveType = "plant"
    node_id: str = Field(default="", max_length=64)
    description: str = Field(default="", max_length=300)

    @field_validator("move_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return planning_id(value, "foreshadow_move")


class ForeshadowPlan(PlannedModel):
    """伏笔计划：plan_status 只能是 planned —— 已经埋设 / 回收由 Canon 记录。"""

    foreshadow_id: str = Field(min_length=5, max_length=64)
    subject: str = Field(default="", max_length=200)
    intended_payoff: str = Field(default="", max_length=300)
    moves: list[ForeshadowMove] = Field(default_factory=list)
    canon_foreshadow_ref: str = Field(default="", max_length=160)
    plant_node_id: str = Field(default="", max_length=64)
    payoff_node_id: str = Field(default="", max_length=64)
    misdirection: str = Field(default="", max_length=300)
    plan_status: Literal["planned"] = "planned"

    @field_validator("foreshadow_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return planning_id(value, "foreshadow")


class ProgressionMilestone(PlannedModel):
    milestone_id: str = Field(min_length=11, max_length=64)
    label: str = Field(default="", max_length=120)
    requirement: str = Field(default="", max_length=300)
    node_id: str = Field(default="", max_length=64)
    order_index: int = Field(default=0, ge=0)
    cost: str = Field(default="", max_length=200)
    unlock: str = Field(default="", max_length=200)
    cap: str = Field(default="", max_length=120)

    @field_validator("milestone_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return planning_id(value, "milestone")


class ProgressionTrack(PlannedModel):
    track_id: str = Field(min_length=7, max_length=64)
    category: ProgressionCategory = "ability"
    label: str = Field(default="", max_length=120)
    start_state: str = Field(default="", max_length=300)
    milestones: list[ProgressionMilestone] = Field(default_factory=list)
    requirements: list[str] = Field(default_factory=list)
    cost: str = Field(default="", max_length=200)
    unlock: str = Field(default="", max_length=200)
    cap: str = Field(default="", max_length=200)

    @field_validator("track_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return planning_id(value, "track")


class PlotNode(PlannedModel):
    """全书真正关键剧情节点（不是章节 beat 模板）。

    Progressive Elaboration：早期节点可以只存在于 StorySpine（unscheduled）；
    一旦进入 Volume Compiler 被正式排期，`scheduled_volume_id` 唯一
    （其他卷只能通过 foreshadow / consequence / refs 关联，不能重复执行）。
    """

    node_id: str = Field(min_length=6, max_length=64)
    detail_level: PlanningDetailLevel = "spine"
    purpose: str = Field(default="", max_length=300)
    participants: list[str] = Field(default_factory=list)
    location_id: str = Field(default="", max_length=64)
    prerequisites: list[str] = Field(default_factory=list)
    trigger: str = Field(default="", max_length=300)
    conflict: str = Field(default="", max_length=300)
    major_choice: str = Field(default="", max_length=300)
    decision_owner_ref: str = Field(default="", max_length=160)
    state_change: str = Field(default="", max_length=300)
    character_change: str = Field(default="", max_length=300)
    relationship_change: str = Field(default="", max_length=300)
    information_change: str = Field(default="", max_length=300)
    progression_change: str = Field(default="", max_length=300)
    cost: str = Field(default="", max_length=300)
    payoff: str = Field(default="", max_length=300)
    foreshadow_ids: list[str] = Field(default_factory=list)
    truth_ids: list[str] = Field(default_factory=list)
    track_ids: list[str] = Field(default_factory=list)
    # M6：结构化引用（全部 optional，旧 fixture 兼容）
    requirements: RequirementGroup | None = None
    character_arc_refs: list[str] = Field(default_factory=list)
    relationship_arc_refs: list[str] = Field(default_factory=list)
    faction_arc_refs: list[str] = Field(default_factory=list)
    information_move_refs: list[str] = Field(default_factory=list)
    foreshadow_move_refs: list[str] = Field(default_factory=list)
    progression_milestone_refs: list[str] = Field(default_factory=list)
    resource_flow_refs: list[str] = Field(default_factory=list)
    equipment_refs: list[str] = Field(default_factory=list)
    base_progression_refs: list[str] = Field(default_factory=list)
    map_expansion_refs: list[str] = Field(default_factory=list)
    reward_refs: list[str] = Field(default_factory=list)
    autonomous_action_refs: list[str] = Field(default_factory=list)
    faction_relation_refs: list[str] = Field(default_factory=list)
    stage_trigger_refs: list[str] = Field(default_factory=list)
    conflict_chain_ref: str = Field(default="", max_length=64)
    pressure_refs: list[str] = Field(default_factory=list)
    pressure_kinds: list[PlotPressureKind] = Field(default_factory=list)
    theme_refs: list[str] = Field(default_factory=list)
    importance: PlotNodeImportance = "major"
    must_happen: bool = False
    optional: bool = False
    alternatives: list[str] = Field(default_factory=list)
    # 排期（可以长期为空 = unscheduled；一旦写入即为唯一 execution volume）
    scheduled_volume_id: str = Field(default="", max_length=64)
    scheduled_position: int | None = Field(default=None, ge=0)

    @field_validator("node_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return planning_id(value, "node")

    @model_validator(mode="after")
    def _not_both_mandatory_and_optional(self) -> "PlotNode":
        if self.must_happen and self.optional:
            raise ValueError("must_happen 与 optional 不能同时为真")
        return self

    def is_empty_beat(self) -> bool:
        """没有任何语义内容、只剩排序位置的节点 = beat 模板残留。"""

        return not any((self.conflict, self.major_choice, self.state_change,
                        self.payoff, self.character_change, self.relationship_change,
                        self.information_change, self.progression_change))


class SpineEdge(StrictModel):
    from_node_id: str = Field(min_length=6, max_length=64)
    to_node_id: str = Field(min_length=6, max_length=64)
    relation: NodeEdgeRelation = "requires"

    @field_validator("from_node_id", "to_node_id")
    @classmethod
    def _nodes(cls, value: str) -> str:
        return planning_id(value, "node")


class StorySpine(PlannedModel):
    """PlotNode 的因果 DAG：不是固定 beat ladder，也不是 future plan 的循环取模。"""

    spine_id: str = Field(min_length=7, max_length=64)
    detail_level: PlanningDetailLevel = "spine"
    novel_id: str = Field(min_length=1, max_length=96)
    nodes: list[str] = Field(default_factory=list)
    edges: list[SpineEdge] = Field(default_factory=list)
    entry_node_ids: list[str] = Field(default_factory=list)
    terminal_node_ids: list[str] = Field(default_factory=list)

    @field_validator("spine_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return planning_id(value, "spine")

    def incoming(self, node_id: str) -> list[SpineEdge]:
        return [edge for edge in self.edges if edge.to_node_id == node_id]


class DecisionStep(PlannedModel):
    """ArcPlan 的决策链：每一步都能下沉成章节里的 decision。"""

    node_id: str = Field(min_length=6, max_length=64)
    decision_owner_ref: str = Field(default="", max_length=160)
    choice: str = Field(default="", max_length=300)
    consequence: str = Field(default="", max_length=300)
    has_alternative: bool = True

    @field_validator("node_id")
    @classmethod
    def _node(cls, value: str) -> str:
        return planning_id(value, "node")


class ArcPlan(PlannedModel):
    """Arc 是 Chapter Semantic IR 的直接上游。"""

    arc_id: str = Field(min_length=5, max_length=64)
    detail_level: PlanningDetailLevel = "arc"
    volume_id: str = Field(min_length=5, max_length=64)
    index: int = Field(default=1, ge=1)
    title: str = Field(default="", max_length=120)
    arc_goal: str = Field(default="", max_length=300)
    opening_state: str = Field(default="", max_length=300)
    participants: list[str] = Field(default_factory=list)
    location_scope: list[str] = Field(default_factory=list)
    conflict: str = Field(default="", max_length=300)
    decision_chain: list[DecisionStep] = Field(default_factory=list)
    turns: list[str] = Field(default_factory=list)
    payoff: str = Field(default="", max_length=300)
    cost: str = Field(default="", max_length=300)
    ending_state: str = Field(default="", max_length=300)
    plot_nodes: list[str] = Field(default_factory=list)
    chapter_budget: int = Field(default=0, ge=0, le=500)
    # M9：chapter_ready Arc 的 chapter index / refs（由 ChapterIRStore 绑定 digest）
    chapter_refs: list[str] = Field(default_factory=list)
    chapter_ir_digest: str = Field(default="", max_length=64)

    @field_validator("arc_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return planning_id(value, "arc")

    @field_validator("volume_id")
    @classmethod
    def _volume(cls, value: str) -> str:
        return planning_id(value, "volume")


class VolumePlan(PlannedModel):
    volume_id: str = Field(min_length=5, max_length=64)
    detail_level: PlanningDetailLevel = "volume"
    index: int = Field(default=1, ge=1)
    title: str = Field(default="", max_length=120)
    volume_goal: str = Field(default="", max_length=300)
    opening_state: str = Field(default="", max_length=300)
    major_conflict: str = Field(default="", max_length=300)
    character_arc_stage: str = Field(default="", max_length=300)
    faction_state: str = Field(default="", max_length=300)
    location_expansion: list[str] = Field(default_factory=list)
    progression_goal: str = Field(default="", max_length=300)
    information_goal: str = Field(default="", max_length=300)
    major_nodes: list[str] = Field(default_factory=list)
    climax: str = Field(default="", max_length=300)
    climax_node_id: str = Field(default="", max_length=64)
    cost: str = Field(default="", max_length=300)
    ending_state: str = Field(default="", max_length=300)
    next_volume_pressure: str = Field(default="", max_length=300)
    arc_ids: list[str] = Field(default_factory=list)
    chapter_budget: int = Field(default=0, ge=0, le=2000)

    @field_validator("volume_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return planning_id(value, "volume")


class PacingBand(StrictModel):
    volume_id: str = Field(min_length=5, max_length=64)
    intensity: dict[str, float] = Field(default_factory=dict)
    note: str = Field(default="", max_length=200)

    @field_validator("volume_id")
    @classmethod
    def _volume(cls, value: str) -> str:
        return planning_id(value, "volume")


class PacingPlan(PlannedModel):
    """节奏相对强度：默认建议由 Genre Template 提供，Core 不硬编码题材。

    `intensity` 是**相对强弱**（不要求和为 1，也不作为章节配额）；
    `target_distribution` 只允许作为 analysis / recommendation，永远不是 story truth。
    """

    pacing_id: str = Field(min_length=6, max_length=64)
    template_id: str = Field(default="", max_length=64)
    intensity: dict[str, float] = Field(default_factory=dict)
    bands: list[PacingBand] = Field(default_factory=list)
    strategy: str = Field(default="", max_length=300)
    target_distribution: dict[str, float] = Field(default_factory=dict)
    target_distribution_is_authoritative: Literal[False] = False

    @field_validator("pacing_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return planning_id(value, "pacing")

    @field_validator("intensity", "target_distribution")
    @classmethod
    def _intensity(cls, value: dict[str, float]) -> dict[str, float]:
        for channel, weight in value.items():
            if channel not in PacingChannel.__args__:  # type: ignore[attr-defined]
                raise ValueError(f"未知节奏通道：{channel}")
            if weight < 0:
                raise ValueError(f"节奏强度不能为负：{channel}")
        return value


# ---------------------------------------------------------------- M5：结构化条件
class RequirementRef(PlannedModel):
    """未来设计要求的稳定引用；description / condition 只是说明，不是机器真值。"""

    requirement_id: str = Field(min_length=5, max_length=64)
    kind: RequirementKind = "custom"
    ref_id: str = Field(default="", max_length=160)
    condition: str = Field(default="", max_length=200)
    satisfied_by: list[str] = Field(default_factory=list)
    description: str = Field(default="", max_length=300)

    @field_validator("requirement_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return planning_id(value, "requirement")


class RequirementGroup(StrictModel):
    """最小条件表达式：all / any + 一组 RequirementRef（不做通用规则引擎）。"""

    operator: RequirementOperator = "all"
    requirements: list[RequirementRef] = Field(default_factory=list)
    description: str = Field(default="", max_length=300)

    def requirement_ids(self) -> list[str]:
        return [item.requirement_id for item in self.requirements]


class UnitConversion(StrictModel):
    to_unit_id: str = Field(min_length=6, max_length=64)
    factor: float = Field(default=1.0, gt=0)
    note: str = Field(default="", max_length=200)

    @field_validator("to_unit_id")
    @classmethod
    def _unit(cls, value: str) -> str:
        return planning_id(value, "unit")


class UnitDef(PlannedModel):
    """单位定义：只有显式配置才允许换算，不同 unit 不能直接相加。"""

    unit_id: str = Field(min_length=6, max_length=64)
    unit_kind: UnitKind = "custom"
    label: str = Field(default="", max_length=80)
    conversions: list[UnitConversion] = Field(default_factory=list)

    @field_validator("unit_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return planning_id(value, "unit")


# ---------------------------------------------------------------- M5：资源
class ResourcePlan(PlannedModel):
    """资源规划：只写"这种资源怎么运作"，不写库存（库存属于 StoryState）。"""

    resource_plan_id: str = Field(min_length=7, max_length=64)
    resource_id: str = Field(default="", max_length=160)
    planned_resource_id: str = Field(default="", max_length=160)
    unit_id: str = Field(default="", max_length=64)
    category: str = Field(default="", max_length=64)
    scarcity: ResourceScarcity = "unknown"
    storage_limit: float | None = Field(default=None, ge=0)
    renewable: bool = False
    notes: str = Field(default="", max_length=300)

    @field_validator("resource_plan_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return planning_id(value, "resource_plan")

    @model_validator(mode="after")
    def _identity(self) -> "ResourcePlan":
        if not (self.resource_id or self.planned_resource_id):
            raise ValueError("ResourcePlan 必须有 resource_id（已确认）或 planned_resource_id（planning-only）")
        return self

    def is_planning_only(self) -> bool:
        return not self.resource_id

    def identity(self) -> str:
        return self.resource_id or self.planned_resource_id


class ResourceFlow(PlannedModel):
    """资源流动：produce / acquire / consume / store / transfer / lose / destroy / recover。"""

    flow_id: str = Field(min_length=7, max_length=64)
    resource_id: str = Field(default="", max_length=160)
    planned_resource_id: str = Field(default="", max_length=160)
    flow_type: ResourceFlowType = "acquire"
    amount: float = Field(default=0, ge=0)
    unit_id: str = Field(default="", max_length=64)
    source_ref: str = Field(default="", max_length=160)
    target_ref: str = Field(default="", max_length=160)
    trigger_node_id: str = Field(default="", max_length=64)
    planned_time_ref: str = Field(default="", max_length=64)
    repeatability: ResourceFlowRepeatability = "once"
    irreversible: bool = False
    note: str = Field(default="", max_length=200)

    @field_validator("flow_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return planning_id(value, "resource_flow")

    @model_validator(mode="after")
    def _identity(self) -> "ResourceFlow":
        if not (self.resource_id or self.planned_resource_id):
            raise ValueError("ResourceFlow 必须有 resource_id 或 planned_resource_id")
        return self

    def identity(self) -> str:
        return self.resource_id or self.planned_resource_id


# ---------------------------------------------------------------- M5：装备 / 物品
class EquipmentLifecycleStep(StrictModel):
    step_id: str = Field(default="", max_length=64)
    state: EquipmentPlannedState = "planned"
    node_id: str = Field(default="", max_length=64)
    detail: str = Field(default="", max_length=200)


class EquipmentPlan(PlannedModel):
    """装备 / 物品生命周期（planned lifecycle，不是 happened state）。"""

    equipment_id: str = Field(min_length=4, max_length=64)
    equipment_ref: str = Field(default="", max_length=160)
    display_name: str = Field(default="", max_length=80)
    owner_ref: str = Field(default="", max_length=160)
    acquisition_node: str = Field(default="", max_length=64)
    upgrade_nodes: list[str] = Field(default_factory=list)
    damage_nodes: list[str] = Field(default_factory=list)
    repair_nodes: list[str] = Field(default_factory=list)
    transfer_nodes: list[str] = Field(default_factory=list)
    loss_node: str = Field(default="", max_length=64)
    consume_node: str = Field(default="", max_length=64)
    consumable: bool = False
    unique: bool = True
    durability_policy: str = Field(default="", max_length=200)
    story_function: str = Field(default="", max_length=200)
    lifecycle: list[EquipmentLifecycleStep] = Field(default_factory=list)

    @field_validator("equipment_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return planning_id(value, "equipment")

    def nodes(self) -> list[str]:
        rows = [self.acquisition_node, self.loss_node, self.consume_node]
        rows += self.upgrade_nodes + self.damage_nodes + self.repair_nodes + self.transfer_nodes
        rows += [step.node_id for step in self.lifecycle]
        return sorted({item for item in rows if item})


# ---------------------------------------------------------------- M5：据点 / 地图扩张
class BaseStage(PlannedModel):
    stage_id: str = Field(min_length=11, max_length=64)
    label: str = Field(default="", max_length=120)
    capacity: str = Field(default="", max_length=200)
    defense: str = Field(default="", max_length=200)
    production: str = Field(default="", max_length=200)
    population: str = Field(default="", max_length=200)
    services: list[str] = Field(default_factory=list)
    territory: list[str] = Field(default_factory=list)
    requirements: RequirementGroup | None = None
    unlock_node: str = Field(default="", max_length=64)
    cost_refs: list[str] = Field(default_factory=list)

    @field_validator("stage_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return planning_id(value, "base_stage")


class BaseProgressionPlan(PlannedModel):
    """基地 / 据点 / 城市 / 领地 / 组织根据地的阶段升级（题材无关）。"""

    base_id: str = Field(min_length=6, max_length=64)
    base_ref: str = Field(default="", max_length=160)
    display_name: str = Field(default="", max_length=80)
    stages: list[BaseStage] = Field(default_factory=list)
    start_stage_id: str = Field(default="", max_length=64)
    end_stage_id: str = Field(default="", max_length=64)
    story_function: str = Field(default="", max_length=200)

    @field_validator("base_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return planning_id(value, "base")


class MapExpansionMilestone(PlannedModel):
    milestone_id: str = Field(min_length=10, max_length=64)
    location_ref: str = Field(min_length=1, max_length=64)
    from_stage: MapExpansionStage = "unknown"
    to_stage: MapExpansionStage = "known"
    requirements: RequirementGroup | None = None
    trigger_node_id: str = Field(default="", max_length=64)
    cost_refs: list[str] = Field(default_factory=list)
    benefits: list[str] = Field(default_factory=list)

    @field_validator("milestone_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return planning_id(value, "map_milestone")


class MapExpansionPlan(PlannedModel):
    """地图扩张计划：基于 LocationGraph，阶段见 MapExpansionStage。"""

    expansion_id: str = Field(min_length=8, max_length=64)
    milestones: list[MapExpansionMilestone] = Field(default_factory=list)
    scope_note: str = Field(default="", max_length=300)

    @field_validator("expansion_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return planning_id(value, "map_expansion")


# ---------------------------------------------------------------- M5：回报节奏
class RewardEvent(PlannedModel):
    """回报事件：magnitude 用 ordinal level，不用"爽点=87"这种数值真相。"""

    reward_id: str = Field(min_length=8, max_length=64)
    reward_type: RewardType = "custom"
    payoff_ref: str = Field(default="", max_length=160)
    trigger_node_id: str = Field(default="", max_length=64)
    recipient_ref: str = Field(default="", max_length=160)
    magnitude: RewardMagnitude = "medium"
    scope: RewardScope = "arc"
    delayed: bool = False
    cost_ref: str = Field(default="", max_length=160)
    description: str = Field(default="", max_length=300)

    @field_validator("reward_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return planning_id(value, "reward")


class RewardPlan(PlannedModel):
    reward_plan_id: str = Field(min_length=8, max_length=64)
    events: list[RewardEvent] = Field(default_factory=list)
    policy_note: str = Field(default="", max_length=300)

    @field_validator("reward_plan_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return planning_id(value, "reward")


# ---------------------------------------------------------------- M5：自主行动 / 势力关系
class AutonomousActionPlan(PlannedModel):
    """NPC / 势力自主行动：默认不要求主角在场（世界不围着主角转）。"""

    action_id: str = Field(min_length=5, max_length=64)
    actor_ref: str = Field(min_length=1, max_length=160)
    goal: str = Field(default="", max_length=300)
    trigger_ref: str = Field(default="", max_length=160)
    location_ref: str = Field(default="", max_length=64)
    target_refs: list[str] = Field(default_factory=list)
    planned_action: str = Field(default="", max_length=300)
    expected_consequence: str = Field(default="", max_length=300)
    visibility: AutonomousVisibility = "faction_internal"
    information_dependency: list[str] = Field(default_factory=list)
    requires_protagonist_presence: bool = False
    planned_time_ref: str = Field(default="", max_length=64)

    @field_validator("action_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return planning_id(value, "autonomous_action")


class FactionRelation(PlannedModel):
    """势力级策略网络关系；与 RelationshipArc 的边界见 M5 报告。"""

    relation_id: str = Field(min_length=6, max_length=64)
    relation_type: FactionRelationType = "custom"
    from_faction_id: str = Field(min_length=1, max_length=160)
    to_faction_id: str = Field(min_length=1, max_length=160)
    state: str = Field(default="", max_length=300)
    symmetric: bool = True
    public: bool = True
    requirements: RequirementGroup | None = None
    trigger_node_id: str = Field(default="", max_length=64)
    detail: str = Field(default="", max_length=200)

    @field_validator("relation_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return planning_id(value, "faction_relation")

    @model_validator(mode="after")
    def _distinct(self) -> "FactionRelation":
        if self.from_faction_id == self.to_faction_id:
            raise ValueError("FactionRelation 两端不能是同一个势力")
        return self


# ---------------------------------------------------------------- M6：压力 / 冲突升级 / 候选
class PlotPressure(StrictModel):
    """派生分析对象：从 M4 / M5 分析得到的压力或机会，**不是新的 Planning truth**。"""

    pressure_id: str = Field(min_length=6, max_length=64)
    kind: PlotPressureKind = "custom"
    state: PressureState = "open"
    source_ref: str = Field(default="", max_length=160)
    affected_refs: list[str] = Field(default_factory=list)
    urgency: str = Field(default="medium", max_length=16)
    available_after: str = Field(default="", max_length=64)
    expires_after: str = Field(default="", max_length=64)
    suggested_resolution_types: list[str] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)
    non_authoritative: Literal[True] = True

    @field_validator("pressure_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return planning_id(value, "pressure")


class ConflictEscalationStage(PlannedModel):
    """冲突升级的单个阶段：必须改变至少一个结构化维度（stakes / constraints / …）。"""

    stage_id: str = Field(min_length=8, max_length=64)
    conflict_id: str = Field(min_length=9, max_length=64)
    scope: ConflictScope = "local"
    trigger_node_id: str = Field(default="", max_length=64)
    actor_refs: list[str] = Field(default_factory=list)
    target_refs: list[str] = Field(default_factory=list)
    location_refs: list[str] = Field(default_factory=list)
    pressure_refs: list[str] = Field(default_factory=list)
    requirement_refs: list[str] = Field(default_factory=list)
    resource_refs: list[str] = Field(default_factory=list)
    faction_relation_refs: list[str] = Field(default_factory=list)
    autonomous_action_refs: list[str] = Field(default_factory=list)
    stakes: str = Field(default="", max_length=300)
    constraint_change: str = Field(default="", max_length=300)
    cost_change: str = Field(default="", max_length=300)
    expected_consequence: str = Field(default="", max_length=300)
    resolution_requirement: RequirementGroup | None = None
    previous_stage_id: str = Field(default="", max_length=64)

    @field_validator("stage_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return planning_id(value, "conflict_stage")

    @field_validator("conflict_id")
    @classmethod
    def _conflict(cls, value: str) -> str:
        return planning_id(value, "conflict_chain")

    def escalation_signals(self) -> list[str]:
        """本阶段相对上一阶段实际改变的维度（结构化判断，不看文字形容强弱）。"""

        rows: list[str] = []
        if self.stakes:
            rows.append("stakes")
        if self.constraint_change:
            rows.append("constraint_change")
        if self.cost_change:
            rows.append("resource_pressure")
        if self.scope in ("volume", "macro"):
            rows.append("location_scope")
        if self.faction_relation_refs:
            rows.append("faction_involvement")
        if self.autonomous_action_refs:
            rows.append("faction_involvement")
        if self.requirement_refs:
            rows.append("authority")
        if self.expected_consequence:
            rows.append("expected_consequence")
        if self.resource_refs:
            rows.append("resource_pressure")
        if self.pressure_refs:
            rows.append("information_asymmetry")
        return sorted(set(rows))


class ConflictEscalationChain(PlannedModel):
    conflict_id: str = Field(min_length=9, max_length=64)
    title: str = Field(default="", max_length=160)
    central_question: str = Field(default="", max_length=300)
    stages: list[ConflictEscalationStage] = Field(default_factory=list)
    related_node_ids: list[str] = Field(default_factory=list)
    ending_direction: str = Field(default="", max_length=300)

    @field_validator("conflict_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return planning_id(value, "conflict_chain")

    def stage(self, stage_id: str) -> ConflictEscalationStage | None:
        return next((item for item in self.stages if item.stage_id == stage_id), None)


class PlotNodeCandidate(PlannedModel):
    """PlotNode 提案（proposal DTO）：只有经过 explicit promote 才会成为 Planning truth。"""

    candidate_id: str = Field(min_length=6, max_length=64)
    source_revision: str = Field(default="", max_length=64)
    pressure_refs: list[str] = Field(default_factory=list)
    proposed_node: PlotNode
    proposed_edges: list[SpineEdge] = Field(default_factory=list)
    reasoning_summary: str = Field(default="", max_length=400)
    validation_findings: list[dict[str, Any]] = Field(default_factory=list)
    provider: str = Field(default="static", max_length=64)
    model: str = Field(default="", max_length=64)
    approved: bool = False

    @field_validator("candidate_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return planning_id(value, "candidate")

    def blocking(self) -> bool:
        return any(str(item.get("severity", "ERROR")) == "ERROR"
                   for item in self.validation_findings)


class PlotProposal(StrictModel):
    proposal_id: str = Field(min_length=6, max_length=64)
    novel_id: str = Field(default="", max_length=96)
    source_revision: str = Field(default="", max_length=64)
    provider: str = Field(default="static", max_length=64)
    model: str = Field(default="", max_length=64)
    candidates: list[PlotNodeCandidate] = Field(default_factory=list)

    @field_validator("proposal_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return planning_id(value, "plot_proposal")


class StoryPlanningIR(StrictModel):
    """Story Planning IR 顶层文档：future planning truth 的唯一入口。"""

    planning_id: str = Field(default="", max_length=64)
    novel_id: str = Field(min_length=1, max_length=96)
    schema_version: int = PLANNING_SCHEMA_VERSION
    revision: int = Field(default=1, ge=1)
    parent_revision: str = Field(default="", max_length=64)
    branch: str = Field(default="main", max_length=64)
    title: str = Field(default="", max_length=160)
    logline: str = Field(default="", max_length=400)
    canon_snapshot_digest: str = Field(default="", max_length=64)
    intent: NovelIntent | None = None
    theme: ThemePlan | None = None
    world: WorldPlan | None = None
    characters: list[CharacterPlan] = Field(default_factory=list)
    character_arcs: list[CharacterArc] = Field(default_factory=list)
    relationship_arcs: list[RelationshipArc] = Field(default_factory=list)
    factions: list[FactionPlan] = Field(default_factory=list)
    faction_arcs: list[FactionArc] = Field(default_factory=list)
    locations: list[LocationPlan] = Field(default_factory=list)
    location_graph: LocationGraph | None = None
    timeline: TimelinePlan | None = None
    information_arcs: list[InformationArc] = Field(default_factory=list)
    foreshadow_plans: list[ForeshadowPlan] = Field(default_factory=list)
    progression_tracks: list[ProgressionTrack] = Field(default_factory=list)
    plot_nodes: list[PlotNode] = Field(default_factory=list)
    spine: StorySpine | None = None
    volumes: list[VolumePlan] = Field(default_factory=list)
    arcs: list[ArcPlan] = Field(default_factory=list)
    pacing: PacingPlan | None = None
    # M5 long-form planning（全部 optional，旧 fixture 不受影响）
    unit_defs: list[UnitDef] = Field(default_factory=list)
    resource_plans: list[ResourcePlan] = Field(default_factory=list)
    resource_flows: list[ResourceFlow] = Field(default_factory=list)
    equipment_plans: list[EquipmentPlan] = Field(default_factory=list)
    base_progressions: list[BaseProgressionPlan] = Field(default_factory=list)
    map_expansions: list[MapExpansionPlan] = Field(default_factory=list)
    reward_plans: list[RewardPlan] = Field(default_factory=list)
    autonomous_actions: list[AutonomousActionPlan] = Field(default_factory=list)
    faction_relations: list[FactionRelation] = Field(default_factory=list)
    # M6
    conflict_chains: list[ConflictEscalationChain] = Field(default_factory=list)
    provenance: Provenance = "generated"
    source: str = Field(default="", max_length=96)
    confirmation_ref: str = Field(default="", max_length=160)
    note: str = Field(default="", max_length=400)

    @field_validator("planning_id")
    @classmethod
    def _planning_id(cls, value: str) -> str:
        return planning_id(value, "plan") if value else value

    def node(self, node_id: str) -> PlotNode | None:
        return next((item for item in self.plot_nodes if item.node_id == node_id), None)

    def arc(self, arc_id: str) -> ArcPlan | None:
        return next((item for item in self.arcs if item.arc_id == arc_id), None)

    def volume(self, volume_id: str) -> VolumePlan | None:
        return next((item for item in self.volumes if item.volume_id == volume_id), None)

    def planning_ids(self) -> list[tuple[str, str]]:
        """所有 planning 稳定 ID（含重复项，顺序稳定）：(id, kind)。"""

        rows: list[tuple[str, str]] = []
        if self.planning_id:
            rows.append((self.planning_id, "plan"))
        singles = (("intent", self.intent), ("theme", self.theme), ("world", self.world),
                   ("spine", self.spine), ("pacing", self.pacing),
                   ("location_graph", self.location_graph), ("timeline", self.timeline))
        for kind, item in singles:
            if item is not None:
                rows.append((str(getattr(item, _ID_FIELD[kind])), kind))
        collections = (
            ("rule", [rule for rule in (self.world.world_rules if self.world else [])]),
            ("character", self.characters), ("char_arc", self.character_arcs),
            ("relationship_arc", self.relationship_arcs), ("faction", self.factions),
            ("faction_arc", self.faction_arcs), ("location", self.locations),
            ("truth", [truth for arc in self.information_arcs for truth in _truths_of(arc)]),
            ("information_arc", self.information_arcs),
            ("information_move", [move for arc in self.information_arcs for move in arc.moves]),
            ("foreshadow", self.foreshadow_plans),
            ("foreshadow_move", [move for plan in self.foreshadow_plans for move in plan.moves]),
            ("track", self.progression_tracks),
            ("milestone", [item for track in self.progression_tracks
                           for item in track.milestones]),
            ("node", self.plot_nodes), ("volume", self.volumes), ("arc", self.arcs),
            ("requirement", [ref for group in self.requirement_groups()
                             for ref in group.requirements]),
            ("unit", self.unit_defs), ("resource_plan", self.resource_plans),
            ("resource_flow", self.resource_flows), ("equipment", self.equipment_plans),
            ("base", self.base_progressions),
            ("base_stage", [stage for item in self.base_progressions
                            for stage in item.stages]),
            ("map_expansion", self.map_expansions),
            ("map_milestone", [item for expansion in self.map_expansions
                               for item in expansion.milestones]),
            ("reward_plan", self.reward_plans),
            ("reward", [item for plan in self.reward_plans for item in plan.events]),
            ("autonomous_action", self.autonomous_actions),
            ("faction_relation", self.faction_relations),
            ("conflict_chain", self.conflict_chains),
            ("conflict_stage", [stage for chain in self.conflict_chains
                                for stage in chain.stages]),
        )
        for kind, items in collections:
            for item in items:
                rows.append((str(getattr(item, _ID_FIELD[kind])), kind))
        if self.timeline is not None:
            for entry in _timeline_entries(self.timeline):
                rows.append((entry.entry_id, "timeline_entry"))
        return rows

    def requirement_groups(self) -> list[RequirementGroup]:
        """所有内联 RequirementGroup（地点 / 路线 / 据点 / 地图 / 势力关系）。"""

        groups: list[RequirementGroup] = []
        for location in self.locations:
            if location.entry_requirement_group is not None:
                groups.append(location.entry_requirement_group)
        if self.location_graph is not None:
            for edge in self.location_graph.edges:
                if edge.requirement_group is not None:
                    groups.append(edge.requirement_group)
        for plan in self.base_progressions:
            for stage in plan.stages:
                if stage.requirements is not None:
                    groups.append(stage.requirements)
        for expansion in self.map_expansions:
            for milestone in expansion.milestones:
                if milestone.requirements is not None:
                    groups.append(milestone.requirements)
        for relation in self.faction_relations:
            if relation.requirements is not None:
                groups.append(relation.requirements)
        return groups

    def all_ids(self) -> dict[str, str]:
        """所有 planning 稳定 ID → 所属集合（重复 ID 保留第一次出现的 kind）。"""

        rows: dict[str, str] = {}
        for identifier, kind in self.planning_ids():
            rows.setdefault(identifier, kind)
        return rows


_ID_FIELD: dict[str, str] = {
    "plan": "planning_id", "intent": "intent_id", "theme": "theme_id", "world": "world_id",
    "rule": "rule_id",
    "character": "character_id", "char_arc": "arc_id", "relationship_arc": "arc_id",
    "faction": "faction_id", "faction_arc": "arc_id", "location": "location_id",
    "location_graph": "graph_id", "timeline": "timeline_id", "truth": "truth_id",
    "timeline_entry": "entry_id",
    "information_arc": "arc_id", "information_move": "move_id", "foreshadow": "foreshadow_id",
    "foreshadow_move": "move_id", "track": "track_id", "milestone": "milestone_id",
    "node": "node_id", "spine": "spine_id", "volume": "volume_id", "arc": "arc_id",
    "pacing": "pacing_id",
    # M5
    "requirement": "requirement_id", "unit": "unit_id",
    "resource_plan": "resource_plan_id", "resource_flow": "flow_id",
    "equipment": "equipment_id", "base": "base_id", "base_stage": "stage_id",
    "map_expansion": "expansion_id", "map_milestone": "milestone_id",
    "reward": "reward_id", "reward_plan": "reward_plan_id",
    "autonomous_action": "action_id", "faction_relation": "relation_id",
    # M6
    "conflict_chain": "conflict_id", "conflict_stage": "stage_id",
    "pressure": "pressure_id", "candidate": "candidate_id",
    "plot_proposal": "proposal_id",
}


def _truths_of(arc: InformationArc) -> list[InformationTruth]:
    """InformationArc 通过 truth_ids 引用 Truth 时必须内联定义（M2A 无跨文档引用表）。"""

    return list(arc.truths)


def _timeline_entries(plan: TimelinePlan) -> list[TimelineEntry]:
    rows = list(plan.world_history) + list(plan.story_timeline)
    for items in plan.character_timeline.values():
        rows.extend(items)
    return rows


def claims_happened(text: str) -> bool:
    """规划文本是否在声称“已经发生”（future/happened 边界检查）。"""

    return bool(_ACTIVE_TEXT.search(text or ""))


def iter_planning_entries(plan: "StoryPlanningIR") -> list[tuple[str, "PlannedModel"]]:
    """按 kind 顺序遍历所有 planning 条目（validator 查重 / versioning merge 共用）。"""

    rows: list[tuple[str, PlannedModel]] = []
    singles = (("intent", plan.intent), ("theme", plan.theme), ("world", plan.world),
               ("spine", plan.spine), ("pacing", plan.pacing),
               ("location_graph", plan.location_graph), ("timeline", plan.timeline))
    for kind, item in singles:
        if item is not None:
            rows.append((kind, item))
    for rule in (plan.world.world_rules if plan.world else []):
        rows.append(("rule", rule))
    rows.extend(("character", item) for item in plan.characters)
    for arc in plan.character_arcs:
        rows.append(("char_arc", arc))
        rows.extend(("char_arc", choice) for choice in arc.major_choices)
    for arc in plan.relationship_arcs:
        rows.append(("relationship_arc", arc))
        rows.extend(("relationship_arc", stage) for stage in arc.stages)
    rows.extend(("faction", item) for item in plan.factions)
    for arc in plan.faction_arcs:
        rows.append(("faction_arc", arc))
        rows.extend(("faction_arc", stage) for stage in arc.stages)
    rows.extend(("location", item) for item in plan.locations)
    if plan.location_graph is not None:
        rows.extend(("location", edge) for edge in plan.location_graph.edges)
    if plan.timeline is not None:
        entries = list(plan.timeline.world_history) + list(plan.timeline.story_timeline)
        for items in plan.timeline.character_timeline.values():
            entries.extend(items)
        rows.extend(("timeline_entry", entry) for entry in entries)
    for arc in plan.information_arcs:
        rows.append(("information_arc", arc))
        rows.extend(("truth", truth) for truth in arc.truths)
        rows.extend(("information_move", move) for move in arc.moves)
    for foreshadow in plan.foreshadow_plans:
        rows.append(("foreshadow", foreshadow))
        rows.extend(("foreshadow_move", move) for move in foreshadow.moves)
    for track in plan.progression_tracks:
        rows.append(("track", track))
        rows.extend(("milestone", milestone) for milestone in track.milestones)
    for group in plan.requirement_groups():
        rows.extend(("requirement", ref) for ref in group.requirements)
    rows.extend(("unit", item) for item in plan.unit_defs)
    rows.extend(("resource_plan", item) for item in plan.resource_plans)
    rows.extend(("resource_flow", item) for item in plan.resource_flows)
    rows.extend(("equipment", item) for item in plan.equipment_plans)
    for base in plan.base_progressions:
        rows.append(("base", base))
        rows.extend(("base_stage", stage) for stage in base.stages)
    for expansion in plan.map_expansions:
        rows.append(("map_expansion", expansion))
        rows.extend(("map_milestone", item) for item in expansion.milestones)
    for reward_plan in plan.reward_plans:
        rows.append(("reward_plan", reward_plan))
        rows.extend(("reward", item) for item in reward_plan.events)
    rows.extend(("autonomous_action", item) for item in plan.autonomous_actions)
    rows.extend(("faction_relation", item) for item in plan.faction_relations)
    for chain in plan.conflict_chains:
        rows.append(("conflict_chain", chain))
        rows.extend(("conflict_stage", stage) for stage in chain.stages)
    rows.extend(("node", node) for node in plan.plot_nodes)
    rows.extend(("volume", volume) for volume in plan.volumes)
    for arc in plan.arcs:
        rows.append(("arc", arc))
    if plan.pacing is not None:
        rows.extend(("pacing", band) for band in plan.pacing.bands)
    return rows


def entry_id(kind: str, model: "PlannedModel") -> str:
    return str(getattr(model, _ID_FIELD[kind], ""))
