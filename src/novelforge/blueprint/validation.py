"""Blueprint 校验（V4-04 §33–§34）。

本阶段只做：

```text
schema（payload 严格模型）
structural（parent 类型 / 必填 / sequence）
ownership（同一 novel_id）
reference integrity（父节点、被引用节点、setup/payoff、causal link 端点）
```

**不做**（属于 V4-05）：人物一致性评分、节奏评估、语义重复检测、因果评估、repair planner。
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from .contracts import (
    ALLOWED_PARENT_TYPES,
    PAYLOAD_MODELS,
    BlueprintNode,
    validate_node_id,
)
from .errors import BlueprintValidationError


def validate_node(node: BlueprintNode, *, parent: BlueprintNode | None = None,
                  known: Mapping[str, BlueprintNode] | None = None) -> list[dict[str, Any]]:
    """校验单个节点；返回 issue 列表（空表示通过）。"""

    issues: list[dict[str, Any]] = []

    def issue(code: str, message: str, **extra: Any) -> None:
        issues.append({"code": code, "message": message, **extra})

    try:
        validate_node_id(node.node_id)
    except ValueError as exc:
        issue("NODE_ID_INVALID", str(exc))

    if node.node_type not in PAYLOAD_MODELS:
        issue("NODE_TYPE_UNKNOWN", f"未知节点类型：{node.node_type}")
        return issues

    model = PAYLOAD_MODELS[node.node_type]
    if not isinstance(node.payload, model):  # pragma: no cover - 由构造保证
        issue("PAYLOAD_MODEL_MISMATCH",
              f"payload 与节点类型不符：{type(node.payload).__name__} != {model.__name__}")

    allowed_parents = ALLOWED_PARENT_TYPES.get(node.node_type, ())
    if allowed_parents and node.parent_id:
        if parent is None:
            issue("PARENT_NOT_FOUND", f"父节点不存在：{node.parent_id}")
        elif parent.node_type not in allowed_parents:
            issue("PARENT_TYPE_INVALID",
                  f"{node.node_type} 的父节点类型不能是 {parent.node_type}",
                  parent_id=node.parent_id)
        elif parent.novel_id != node.novel_id:
            issue("PARENT_OWNERSHIP_MISMATCH", "父节点属于其他作品")
    elif allowed_parents and not node.parent_id and None not in allowed_parents:
        issue("PARENT_REQUIRED", f"{node.node_type} 必须指定父节点")

    known = dict(known or {})
    payload = node.payload.model_dump(mode="json")

    def require_exists(values: Iterable[str], *, code: str, field: str) -> None:
        for value in values:
            if value and value not in known:
                issue(code, f"{field} 引用了不存在的节点：{value}", reference=value)

    if node.node_type == "character_arc":
        require_exists([str(payload.get("character_id") or "")],
                       code="CHARACTER_NOT_FOUND", field="character_id")
    if node.node_type == "chapter":
        require_exists([str(value) for value in payload.get("characters") or []],
                       code="CHARACTER_NOT_FOUND", field="characters")
    if node.node_type == "scene":
        chapter_id = str(payload.get("chapter_id") or "")
        if not chapter_id:
            issue("SCENE_CHAPTER_REQUIRED", "Scene Card 必须声明 chapter_id")
        elif chapter_id not in known:
            issue("CHAPTER_NOT_FOUND", f"章节不存在：{chapter_id}")
    if node.node_type == "causal_link":
        for field in ("source_node", "target_node"):
            value = str(payload.get(field) or "")
            if value and value not in known:
                issue("CAUSAL_ENDPOINT_NOT_FOUND",
                      f"causal link 端点不存在：{value}", reference=value)
    if node.node_type == "payoff":
        require_exists([str(value) for value in payload.get("resolves_setup_ids") or []],
                       code="SETUP_NOT_FOUND", field="resolves_setup_ids")

    transitions = payload.get("state_change_intent") or payload.get(
        "state_transition_intent") or []
    for row in transitions:
        if not isinstance(row, Mapping) or not row.get("kind"):
            issue("TRANSITION_INTENT_INVALID",
                  "state transition intent 必须至少包含 kind")
        elif str(row.get("scope", "")).startswith("novel:") and \
                not str(row.get("scope")).endswith(node.novel_id):
            issue("TRANSITION_SCOPE_MISMATCH", "transition intent 属于其他作品")

    if node.status == "accepted" and node.quality_status == "failed":
        issue("ACCEPTED_WITH_FAILED_QUALITY", "质量失败的节点不应标记为 accepted")

    return issues


def validate_graph(nodes: Sequence[BlueprintNode], *, novel_id: str = ""
                    ) -> dict[str, Any]:
    """校验整个 Blueprint：ownership / 父子 / 引用 / sequence 完整性。"""

    issues: list[dict[str, Any]] = []
    by_id: dict[str, BlueprintNode] = {}
    for node in nodes:
        if novel_id and node.novel_id != novel_id:
            issues.append({"code": "OWNERSHIP_MISMATCH", "node_id": node.node_id,
                           "message": f"节点属于 {node.novel_id}，期望 {novel_id}"})
        if node.node_id in by_id:
            issues.append({"code": "DUPLICATE_NODE_ID", "node_id": node.node_id,
                           "message": "同一 node_id 出现多次"})
        by_id[node.node_id] = node

    for node in nodes:
        parent = by_id.get(node.parent_id) if node.parent_id else None
        for row in validate_node(node, parent=parent, known=by_id):
            issues.append({**row, "node_id": node.node_id})

    ordered_children: dict[str, list[BlueprintNode]] = {}
    for node in nodes:
        if node.parent_id:
            ordered_children.setdefault(node.parent_id, []).append(node)
    for parent_id, rows in ordered_children.items():
        sequences = [row.sequence for row in rows]
        if len(sequences) != len(set(sequences)):
            issues.append({"code": "SEQUENCE_DUPLICATE", "node_id": parent_id,
                           "message": "同一父节点下 sequence 重复"})
        if any(value <= 0 for value in sequences):
            issues.append({"code": "SEQUENCE_INVALID", "node_id": parent_id,
                           "message": "子节点必须声明正的 sequence"})

    setup_ids = {node.node_id for node in nodes if node.node_type == "setup"}
    paid = set()
    for node in nodes:
        if node.node_type != "payoff":
            continue
        payload = node.payload.model_dump(mode="json")
        paid.update(str(value) for value in payload.get("resolves_setup_ids") or [])
    orphans = sorted(setup_ids - paid)

    return {"ok": not issues, "issue_count": len(issues), "issues": issues,
            "node_count": len(nodes),
            "unpaid_setups": orphans,
            "read_only": True}


def require_valid(node: BlueprintNode, *, parent: BlueprintNode | None = None,
                  known: Mapping[str, BlueprintNode] | None = None) -> None:
    """校验失败时抛出 BlueprintValidationError（写入前的门禁）。"""

    issues = validate_node(node, parent=parent, known=known)
    if issues:
        raise BlueprintValidationError(
            f"Blueprint 节点未通过校验（{len(issues)} 项）", issues=issues)


__all__ = ["require_valid", "validate_graph", "validate_node"]

