"""成长面板视图（V2-I-04）。

统一投影七类 Progression：progression / ability / identity / relationship /
faction / information / equipment / skill。

- 成长树定义来自内容包或 Novel Profile（数据），不是代码。
- owned / available / locked、前置、成本、推荐理由与剧情影响全部由既有
  `options` / `owned_nodes` 判定，前端只展示。
"""

from __future__ import annotations

from typing import Any

from .content import ContentPack
from .progression import (
    ProgressionCategory,
    ProgressionNode,
    ProgressionTree,
    options,
    owned_nodes,
)
from .state import StoryState

CATEGORY_ORDER: tuple[ProgressionCategory, ...] = (
    "progression", "ability", "identity", "relationship", "faction",
    "information", "equipment", "skill",
)
CATEGORY_LABELS: dict[str, str] = {
    "progression": "成长阶段",
    "ability": "能力",
    "identity": "身份",
    "relationship": "关系",
    "faction": "势力",
    "information": "信息",
    "equipment": "装备",
    "skill": "非战斗技能",
}


def node_row(tree: ProgressionTree, state: StoryState, node: ProgressionNode, *,
             owned: set[str], available: dict[str, Any], actor: str = "") -> dict[str, Any]:
    is_owned = node.id in owned
    option = available.get(node.id)
    status = "owned" if is_owned else (option.state if option is not None else "locked")
    return {
        "id": node.id,
        "tree_id": tree.tree_id,
        "name": node.name or node.id,
        "summary": node.summary,
        "category": node.category,
        "kind": node.kind,
        "level": node.level,
        "tags": list(node.tags),
        "source": node.source,
        "status": status,
        "requires": list(node.requires),
        "missing_requires": [item for item in node.requires if item not in owned],
        "exclusive_group": node.exclusive_group,
        "blocked_by": option.exclusive_blocked_by if option is not None else "",
        "reason": option.reason if option is not None else "",
        "unlock_condition": node.unlock.model_dump(mode="json") if node.unlock is not None else None,
        "costs": [item.model_dump(mode="json") for item in node.costs],
        "effects": [item.model_dump(mode="json") for item in node.effects],
        "recommendation": node.recommendation or (option.recommendation if option is not None else ""),
        "story_impact": node.story_impact,
        "data": dict(node.data),
    }


def tree_snapshot(tree: ProgressionTree, state: StoryState, *, actor: str = "") -> dict[str, Any]:
    owned = owned_nodes(state)
    option_rows = {item.node_id: item for item in options(tree, state, actor=actor)}
    nodes = [node_row(tree, state, node, owned=owned, available=option_rows, actor=actor)
             for node in tree.nodes]
    counts = {"owned": 0, "available": 0, "locked": 0}
    for node in nodes:
        counts[node["status"]] = counts.get(node["status"], 0) + 1
    return {"tree_id": tree.tree_id, "name": tree.name, "nodes": nodes, "counts": counts}


def progression_snapshot(context, *, actor: str = "") -> dict[str, Any]:
    """七类成长的统一视图；没有成长数据时给出空状态而不是编造节点。"""

    state = context.state
    trees = progression_trees(context)
    rows = [tree_snapshot(tree, state, actor=actor) for tree in trees]
    by_category: dict[str, list[dict[str, Any]]] = {name: [] for name in CATEGORY_ORDER}
    for tree in rows:
        for node in tree["nodes"]:
            by_category.setdefault(node["category"], []).append(node)
    counts = {"owned": 0, "available": 0, "locked": 0}
    for tree in rows:
        for key, value in tree["counts"].items():
            counts[key] = counts.get(key, 0) + value
    return {
        "meta": context.meta(),
        "actor": actor,
        "trees": rows,
        "categories": [
            {"category": name, "label": CATEGORY_LABELS.get(name, name), "nodes": by_category.get(name, [])}
            for name in CATEGORY_ORDER
        ],
        "counts": counts,
        "owned": sorted(owned_nodes(state)),
        "note": "" if rows else "当前小说还没有成长树数据；请先补内容包与成长树。",
    }


def progression_trees(context) -> list[ProgressionTree]:
    """成长树来源：内容包或 Novel Profile 的声明，不做题材判断。"""

    if context.pack is not None and context.pack.progressions:
        return list(context.pack.progressions)
    payload = context.profile.world_profile.get("progressions")
    if isinstance(payload, list):
        trees = []
        for item in payload:
            try:
                trees.append(ProgressionTree.model_validate(item))
            except Exception:  # noqa: BLE001 - 单棵树格式错误不影响其他树
                continue
        return trees
    return []

