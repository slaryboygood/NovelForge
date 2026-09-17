"""字段级 Patch（V4-06 §8–§10、§59、§63）。

规则：

```text
1. 只接受**字段级** changes（不接收整节点覆盖）
2. 结构 identity / provenance 字段受保护 → EditorPreserveViolation
3. 未知字段 / 类型不合法 → EditorValidationError（pydantic 报错不外泄）
4. 应用后重新跑 schema 校验；引用 / 父层级 / ownership 由调用方用
   blueprint.require_valid 再校验（写入前门禁）
5. 新 revision 的 status = proposed，quality_status = unevaluated
   （手工编辑后不得沿用旧 revision 的 passed，§31）
```
"""

from __future__ import annotations

from typing import Any, Mapping

from novelforge.blueprint import (
    PAYLOAD_MODELS,
    STRUCTURAL_IDENTITY_FIELDS,
    BlueprintNode,
)

from .errors import EditorPreserveViolation, EditorValidationError

#: 手工 patch **永远**不能改的字段（§10）
PROTECTED_FIELDS: tuple[str, ...] = (
    "node_id", "novel_id", "node_type", "parent_id", "sequence",
    "revision", "parent_revision", "schema_version",
    "status", "quality_status",
    "source_ids", "context_digest",
    "generation_contract", "generation_contract_version", "provenance",
    "created_at", "updated_at",
)

#: 结构关系字段：只能通过 move_node 契约修改（§39）
STRUCTURAL_FIELDS: tuple[str, ...] = ("parent_id", "sequence")


def payload_dict(node: BlueprintNode) -> dict[str, Any]:
    payload = node.payload
    if hasattr(payload, "model_dump"):
        return payload.model_dump(mode="json")
    return dict(payload)


def editable_fields(node_type: str) -> tuple[str, ...]:
    """该节点类型真正可编辑的 payload 字段（= payload 模型字段）。"""

    model = PAYLOAD_MODELS.get(str(node_type))
    if model is None:
        return ()
    return tuple(sorted(str(name) for name in model.model_fields))


def structural_identity_fields(node_type: str) -> tuple[str, ...]:
    """该节点类型的结构 identity 字段（patch 一律拒绝，只能经 move_node 改）。"""

    return tuple(STRUCTURAL_IDENTITY_FIELDS.get(str(node_type), ()))


def validate_changes(node: BlueprintNode, changes: Mapping[str, Any]) -> dict[str, Any]:
    """校验 patch：返回规范化后的 changes（不改任何东西）。"""

    if not isinstance(changes, Mapping):
        raise EditorValidationError("changes 必须是字段字典",
                                    details={"node_id": node.node_id})
    protected = sorted({str(key) for key in changes} & set(PROTECTED_FIELDS))
    if protected:
        raise EditorPreserveViolation(
            f"这些字段受保护，不能通过 patch 修改：{protected}",
            details={"node_id": node.node_id, "protected_fields": protected,
                     "hint": ("结构关系请使用 move_node；状态请使用 accept / reject；"
                              "provenance / revision 由系统维护")})
    identity = sorted({str(key) for key in changes}
                      & set(STRUCTURAL_IDENTITY_FIELDS.get(node.node_type, ())))
    if identity:
        raise EditorPreserveViolation(
            f"这些字段属于结构 identity，不能通过 patch 修改：{identity}",
            details={"node_id": node.node_id, "structural_fields": identity,
                     "hint": "结构关系请使用 move_node（parent_id / sequence 与 identity 一起校验）"})
    allowed = set(editable_fields(node.node_type))
    unknown = sorted({str(key) for key in changes} - allowed)
    if unknown:
        raise EditorValidationError(
            f"这些字段不属于 {node.node_type}：{unknown}",
            details={"node_id": node.node_id, "unknown_fields": unknown,
                     "editable_fields": sorted(allowed)})
    return {str(key): value for key, value in changes.items()}


def merge_changes(node: BlueprintNode, changes: Mapping[str, Any]) -> dict[str, Any]:
    """把 changes 合并到当前 payload，并做 schema 校验（返回新 payload dict）。"""

    model = PAYLOAD_MODELS[str(node.node_type)]
    merged = {**payload_dict(node), **dict(changes)}
    try:
        validated = model.model_validate(merged)
    except Exception as exc:  # noqa: BLE001 - pydantic 原始报错不外泄（§75）
        raise EditorValidationError(
            f"patch 后的 payload 不符合 {node.node_type} 的 schema：{exc}",
            details={"node_id": node.node_id, "changed_fields": sorted(changes)}) from exc
    return validated.model_dump(mode="json")


def build_edited_node(node: BlueprintNode, *, payload: Any, provenance_extra: Mapping[str, Any],
                      status: str = "proposed",
                      quality_status: str = "unevaluated") -> BlueprintNode:
    """构造待写入的新 revision（revision 序号由 Repository 分配）。"""

    provenance = {**dict(node.provenance), **dict(provenance_extra)}
    return BlueprintNode(
        node_id=node.node_id, novel_id=node.novel_id, node_type=node.node_type,
        payload=payload, parent_id=node.parent_id, revision=node.revision,
        parent_revision=node.parent_revision, status=status,
        source_ids=tuple(node.source_ids), context_digest=node.context_digest,
        created_at=node.created_at, generation_contract=node.generation_contract,
        generation_contract_version=node.generation_contract_version,
        provenance=provenance, quality_status=quality_status,
        schema_version=node.schema_version, sequence=node.sequence)


__all__ = [
    "PROTECTED_FIELDS", "STRUCTURAL_FIELDS", "build_edited_node", "editable_fields",
    "merge_changes", "payload_dict", "structural_identity_fields", "validate_changes",
]
