"""成长树系统（主计划 T12）。

同一套 ProgressionNode 表达修仙境界、科幻等级、身份与非战斗叙事技能：

- 前置节点、解锁条件、成本、排他选择、等级、推荐理由、剧情影响全部是数据；
- 引擎只做“前置是否满足 → 条件是否通过 → 成本是否可付 → 写入状态”的通用流程；
- 具体节点来自内容包或题材模板，不在代码里写“金丹”“义体”等名词。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from novelforge.models import StrictModel

from .conditions import Condition, evaluate
from .effects import EffectSpec, apply_effects
from .state import StoryState

ProgressionKind = Literal["progression", "ability", "identity", "skill"]
ProgressionCategory = Literal["progression", "ability", "identity", "relationship", "faction",
                              "information", "equipment", "skill"]


class ProgressionNode(StrictModel):
    id: str = Field(min_length=1, max_length=128)
    tree_id: str = Field(default="", max_length=64)
    kind: ProgressionKind = "progression"
    category: ProgressionCategory = "progression"
    source: str = Field(default="", max_length=128)
    tags: list[str] = Field(default_factory=list)
    level: int = Field(default=1, ge=0, le=99)
    name: str = Field(default="", max_length=80)
    summary: str = Field(default="", max_length=300)
    requires: list[str] = Field(default_factory=list)
    exclusive_group: str = Field(default="", max_length=64)
    unlock: Condition | None = None
    costs: list[EffectSpec] = Field(default_factory=list)
    effects: list[EffectSpec] = Field(default_factory=list)
    recommendation: str = Field(default="", max_length=200)
    story_impact: str = Field(default="", max_length=300)
    data: dict[str, Any] = Field(default_factory=dict)


class ProgressionTree(StrictModel):
    tree_id: str = Field(min_length=1, max_length=64)
    name: str = Field(default="", max_length=80)
    nodes: list[ProgressionNode] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_graph(self) -> "ProgressionTree":
        ids = [item.id for item in self.nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("progression node ids must be unique")
        known = set(ids)
        for node in self.nodes:
            missing = [item for item in node.requires if item not in known]
            if missing:
                raise ValueError(f"node {node.id} requires unknown nodes: {missing}")
        return self

    def node(self, node_id: str) -> ProgressionNode:
        for item in self.nodes:
            if item.id == node_id:
                return item
        raise KeyError(node_id)


def owned_nodes(state: StoryState) -> set[str]:
    owned = set(state.abilities)
    for identities in state.identities.values():
        owned.update(identities)
    owned.update(str(item) for item in state.flags.get("progression", []) or [])
    return owned


class ProgressionOption(StrictModel):
    node_id: str
    available: bool
    reason: str = ""
    exclusive_blocked_by: str = ""
    recommendation: str = ""
    state: Literal["owned", "available", "locked"] = "locked"


def options(tree: ProgressionTree, state: StoryState, *, actor: str = "") -> list[ProgressionOption]:
    owned = owned_nodes(state)
    rows: list[ProgressionOption] = []
    for node in tree.nodes:
        if node.id in owned:
            continue
        missing = [item for item in node.requires if item not in owned]
        if missing:
            rows.append(ProgressionOption(node_id=node.id, available=False,
                                          state="locked", reason="需要先解锁：" + "、".join(missing)))
            continue
        if node.unlock is not None:
            result = evaluate(node.unlock, state, actor=actor)
            if not result.ok:
                rows.append(ProgressionOption(node_id=node.id, available=False, state="locked",
                                              reason=result.message))
                continue
        blocked = ""
        if node.exclusive_group:
            for other in tree.nodes:
                if other.exclusive_group == node.exclusive_group and other.id in owned:
                    blocked = other.id
                    break
        rows.append(ProgressionOption(node_id=node.id, available=not blocked,
                                      state="available" if not blocked else "locked",
                                      reason="与已选节点互斥" if blocked else "",
                                      exclusive_blocked_by=blocked,
                                      recommendation=node.recommendation))
    return rows


def unlock_state(tree: ProgressionTree, state: StoryState, node_id: str, *, actor: str = "") -> str:
    """统一解锁状态：owned / available / locked（由 Condition 与 StoryState 决定）。"""

    if node_id in owned_nodes(state):
        return "owned"
    row = next((item for item in options(tree, state, actor=actor) if item.node_id == node_id), None)
    if row is None:
        return "owned"
    return row.state


def acquire(tree: ProgressionTree, state: StoryState, node_id: str, *, actor: str = "") -> Any:
    """通用获取流程：前置 → 条件 → 排他 → 成本 → 效果；失败不改状态。"""

    node = tree.node(node_id)
    row = next((item for item in options(tree, state, actor=actor) if item.node_id == node_id), None)
    if row is None:
        return apply_effects(state, [], actor=actor, source=f"progression:{node_id}")
    if not row.available:
        from .effects import EffectOutcome
        return EffectOutcome(ok=False, code="PROGRESSION_LOCKED", message=row.reason or "还不能选择",
                             state=state, records=[])
    paid = apply_effects(state, node.costs, actor=actor, source=f"cost:{node_id}")
    if not paid.ok:
        return paid
    applied = apply_effects(paid.state, node.effects, actor=actor, source=f"progression:{node_id}")
    if not applied.ok:
        return applied
    working = applied.state
    current = list(working.flags.get("progression", []) or [])
    if node.id not in current:
        current.append(node.id)
    working.flags["progression"] = current
    return applied.model_copy(update={"state": working, "records": paid.records + applied.records})


XIANXIA_TREE = ProgressionTree(
    tree_id="xianxia", name="修仙成长",
    nodes=[
        ProgressionNode(id="qi_gathering", tree_id="xianxia", kind="progression", level=1, name="炼气",
                        summary="开始感应灵气", effects=[{"op": "add_identity", "value": "炼气弟子"}],
                        recommendation="最基础的入门阶段", story_impact="获得进入外门的资格"),
        ProgressionNode(id="foundation", tree_id="xianxia", kind="progression", level=2, name="筑基",
                        requires=["qi_gathering"],
                        costs=[{"op": "remove_resource", "target": "spirit_stone", "value": 3}],
                        effects=[{"op": "grant_ability", "target": "flying_sword",
                                  "data": {"kind": "功法", "name": "御剑"}}],
                        recommendation="资源充足且已有炼气基础", story_impact="可以参与更危险的秘境"),
    ])

SCI_FI_TREE = ProgressionTree(
    tree_id="sci_fi", name="科技成长",
    nodes=[
        ProgressionNode(id="civil_grade", tree_id="sci_fi", kind="progression", level=1, name="民用级",
                        summary="获得基础接口权限", effects=[{"op": "add_identity", "value": "民用权限"}],
                        recommendation="所有载体的起点", story_impact="可以接入公共网络"),
        ProgressionNode(id="neural_boost", tree_id="sci_fi", kind="ability", level=2, name="神经加速",
                        requires=["civil_grade"],
                        costs=[{"op": "remove_resource", "target": "energy", "value": 30}],
                        effects=[{"op": "grant_ability", "target": "neural_boost",
                                  "data": {"kind": "义体功能", "name": "神经加速"}}],
                        recommendation="能源充足且已有民用权限", story_impact="可以在高压环境快速反应"),
    ])

TREES = {XIANXIA_TREE.tree_id: XIANXIA_TREE, SCI_FI_TREE.tree_id: SCI_FI_TREE}
