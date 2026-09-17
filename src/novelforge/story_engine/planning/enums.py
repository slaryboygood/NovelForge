"""M2A：Story Planning IR 的枚举 / Literal / 常量。

只放题材无关的通用取值。任何具体题材都用 kind / category / template_id 表达，
核心代码里不写题材分支，也不放默认题材内容。
"""

from __future__ import annotations

from typing import Literal

# ---------------------------------------------------------------- 层级与来源
TruthLayer = Literal["planning", "canon", "story_state", "chapter_ir"]

Provenance = Literal["supplied", "inferred", "generated", "confirmed"]
"""supplied = 作者显式给出；inferred = 从既有资料推导；generated = 生成；confirmed = 经 service 确认。

规则：generated / inferred 不得覆盖 supplied（validator.PROVENANCE_SUPPLIED_OVERWRITTEN）。
"""

RevisionStatus = Literal["draft", "proposed", "confirmed", "superseded", "rolled_back"]
RevisionSource = Literal["author", "planner", "imported", "template", "route"]

# ---------------------------------------------------------------- 规划深度
PlanningDetailLevel = Literal["concept", "spine", "volume", "arc", "chapter_ready"]
"""Progressive Elaboration：同一份 Planning truth 里不同对象可以处于不同深度。

concept（意图 / 主题 / 世界 / 人物）＜ spine（关键节点与脊柱）＜ volume ＜ arc
＜ chapter_ready（当前 Arc 已能直接喂给 Chapter IR 上游）。

不是所有对象都必须达到最深一级：远期 Volume 允许只到 volume / spine 深度。
"""

DETAIL_LEVEL_ORDER: dict[str, int] = {"concept": 0, "spine": 1, "volume": 2, "arc": 3,
                                      "chapter_ready": 4}

# ---------------------------------------------------------------- 时间线
TimelineTimeKind = Literal["absolute_time", "relative_time", "era", "sequence_order"]
TimelineStatus = Literal["planned", "hypothesis", "legend", "confirmed"]
CONFIRMED_TIMELINE_STATUS: str = "confirmed"
NON_FACT_TIMELINE_STATUSES: tuple[str, ...] = ("hypothesis", "legend")

# ---------------------------------------------------------------- 分支来源
BranchSourceKind = Literal["planning_revision", "route_candidate"]
PLANNING_BRANCH_SOURCE_KINDS: tuple[str, ...] = ("planning_revision",)

# ---------------------------------------------------------------- 世界规则
WorldRuleType = Literal["hard_rule", "soft_rule", "belief", "rumor", "unknown"]
NON_FACT_RULE_TYPES: tuple[str, ...] = ("belief", "rumor", "unknown")

# ---------------------------------------------------------------- 剧情 / 节点
PlotNodeImportance = Literal["core", "major", "minor"]
NodeEdgeRelation = Literal["requires", "causes", "enables", "blocks", "reveals", "pays_off",
                           "escalates", "resolves"]
SPINE_CAUSAL_RELATIONS: tuple[str, ...] = ("requires", "causes", "enables")

# ---------------------------------------------------------------- M6：压力 / 冲突升级
PlotPressureKind = Literal[
    "character_arc_pressure", "relationship_pressure", "faction_pressure", "resource_deficit",
    "information_due", "foreshadow_due", "progression_due", "map_unlock",
    "autonomous_action", "reward_drought", "requirement_unlock", "prior_node_consequence",
    "theme_pressure", "equipment_need", "base_need", "custom",
]
PressureState = Literal["open", "blocked", "scheduled", "resolved", "deferred",
                        "intentionally_unresolved", "ignored"]
ConflictScope = Literal["local", "arc", "volume", "macro", "custom"]
ESCALATION_SIGNALS: tuple[str, ...] = (
    "stakes", "constraint_change", "resource_pressure", "information_asymmetry",
    "relationship_cost", "faction_involvement", "location_scope", "irreversibility",
    "time_pressure", "authority", "expected_consequence",
)

# ---------------------------------------------------------------- 信息 / 伏笔
InformationMoveType = Literal["plant", "hint", "false_belief", "reveal", "reinterpretation",
                              "payoff"]
ForeshadowMoveType = Literal["plant", "reinforce", "misdirect", "reveal", "payoff"]

# ---------------------------------------------------------------- 成长
ProgressionCategory = Literal["ability", "equipment", "resource", "base", "territory",
                              "faction", "reputation", "relationship", "knowledge", "map",
                              "authority"]

# ---------------------------------------------------------------- 节奏
PacingChannel = Literal["tension", "release", "mystery", "exploration", "combat",
                        "relationship", "reveal", "progression", "reward", "climax"]

# ---------------------------------------------------------------- 稳定 ID
PLANNING_ID_PREFIXES: dict[str, str] = {
    "plan": "PLAN",
    "intent": "INTENT",
    "theme": "THEME",
    "world": "WORLD",
    "rule": "RULE",
    "character": "CHAR",
    "char_arc": "CARCH",
    "relationship_arc": "RELARC",
    "faction": "FACTION",
    "faction_arc": "FARC",
    "location": "LOC",
    "location_graph": "LOCGRAPH",
    "timeline": "TL",
    "timeline_entry": "TLE",
    "truth": "TRUTH",
    "information_arc": "INFO",
    "information_move": "IMOVE",
    "foreshadow": "FSP",
    "foreshadow_move": "FSMOVE",
    "track": "TRACK",
    "milestone": "TRACKMILE",
    "node": "NODE",
    "spine": "SPINE",
    "volume": "VOL",
    "arc": "ARC",
    "pacing": "PACE",
    "revision": "PREV",
    # M5 long-form planning
    "requirement": "REQ",
    "unit": "UNIT",
    "resource_plan": "RPLAN",
    "resource_flow": "RFLOW",
    "equipment": "EQ",
    "base": "BASE",
    "base_stage": "BASESTAGE",
    "map_expansion": "MAPEXP",
    "map_milestone": "MAPMILE",
    "reward": "REWARD",
    "reward_plan": "REWARD",
    "autonomous_action": "ACT",
    "faction_relation": "FREL",
    # M6 plot synthesis / conflict escalation
    "pressure": "PRESS",
    "conflict_chain": "CONFLICT",
    "conflict_stage": "CSTAGE",
    "candidate": "CAND",
    "plot_proposal": "PPROP",
}
PLANNING_ID_KINDS: tuple[str, ...] = tuple(sorted(PLANNING_ID_PREFIXES))

# 题材词只允许出现在 content pack / genre template / 小说数据里，不允许出现在 Core。
FORBIDDEN_GENRE_TERMS_IN_CORE: tuple[str, ...] = (
    "wasteland", "废土", "xianxia", "修仙", "爽文", "起点",
)

PLANNING_SCHEMA_VERSION = 1

# ---------------------------------------------------------------- M5：条件 / 资源 / 生命周期
RequirementKind = Literal[
    "world_rule", "fact", "knowledge", "ability", "progression", "resource", "equipment",
    "relationship", "faction", "location", "plot_node", "custom",
]
RequirementOperator = Literal["all", "any"]

UnitKind = Literal["count", "mass", "volume", "energy", "currency", "custom"]
ResourceScarcity = Literal["abundant", "common", "scarce", "unique", "unknown"]
ResourceFlowType = Literal["produce", "acquire", "consume", "store", "transfer", "lose",
                           "destroy", "recover"]
ResourceFlowRepeatability = Literal["once", "repeatable", "per_volume", "unbounded"]

EquipmentPlannedState = Literal["planned", "acquired", "equipped", "damaged", "repaired",
                                "upgraded", "transferred", "lost", "consumed"]

MapExpansionStage = Literal["unknown", "known", "reachable", "surveyed", "controlled",
                           "secured"]
MAP_EXPANSION_ORDER: dict[str, int] = {
    "unknown": 0, "known": 1, "reachable": 2, "surveyed": 3, "controlled": 4, "secured": 5,
}

RewardType = Literal["progression", "resource", "status", "knowledge", "relationship",
                     "territory", "revenge", "recognition", "survival", "mystery_resolution",
                     "custom"]
RewardMagnitude = Literal["minor", "medium", "major", "climax"]
REWARD_MAGNITUDE_ORDER: dict[str, int] = {"minor": 0, "medium": 1, "major": 2, "climax": 3}
RewardScope = Literal["scene", "arc", "volume", "book"]

FactionRelationType = Literal["alliance", "hostility", "dependency", "trade", "influence",
                              "vassalage", "competition", "non_aggression", "custom"]
AutonomousVisibility = Literal["public", "faction_internal", "secret", "reader_only"]

HealthState = Literal["healthy", "needs_attention", "blocked"]

# 每个 planning 模型都继承的公共字段名（validator / versioning 复用）
PLANNED_FIELD_NAMES: tuple[str, ...] = ("provenance", "source", "confirmation_ref", "note")

__all__ = [
    "BranchSourceKind",
    "CONFIRMED_TIMELINE_STATUS",
    "DETAIL_LEVEL_ORDER",
    "FORBIDDEN_GENRE_TERMS_IN_CORE",
    "ForeshadowMoveType",
    "InformationMoveType",
    "NON_FACT_RULE_TYPES",
    "NON_FACT_TIMELINE_STATUSES",
    "NodeEdgeRelation",
    "PLANNED_FIELD_NAMES",
    "PLANNING_ID_KINDS",
    "PLANNING_ID_PREFIXES",
    "PLANNING_SCHEMA_VERSION",
    "PLANNING_BRANCH_SOURCE_KINDS",
    "PacingChannel",
    "PlanningDetailLevel",
    "PlotNodeImportance",
    "ProgressionCategory",
    "Provenance",
    "RevisionSource",
    "RevisionStatus",
    "SPINE_CAUSAL_RELATIONS",
    "TimelineStatus",
    "TimelineTimeKind",
    "TruthLayer",
    "WorldRuleType",
    # M5 long-form planning
    "AutonomousVisibility",
    "EquipmentPlannedState",
    "FactionRelationType",
    "HealthState",
    "MAP_EXPANSION_ORDER",
    "MapExpansionStage",
    "REWARD_MAGNITUDE_ORDER",
    "RequirementKind",
    "RequirementOperator",
    "ResourceFlowRepeatability",
    "ResourceFlowType",
    "ResourceScarcity",
    "RewardMagnitude",
    "RewardScope",
    "RewardType",
    "UnitKind",
    # M6 plot synthesis / conflict escalation
    "ConflictScope",
    "ESCALATION_SIGNALS",
    "PlotPressureKind",
    "PressureState",
]
