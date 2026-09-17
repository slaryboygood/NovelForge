"""结构化 Blueprint Diff（V4-06 §14–§16、§33、§61）。

**零模型**：哪些字段变了必须由确定性算法决定，不能交给模型（§15）。

```text
BlueprintDiff
  node_id / novel_id / revision_before / revision_after
  added_fields / removed_fields / changed_fields / unchanged_fields
  list_changes（added / removed / reordered）
  before / after（只含发生变化的字段）
  digest（稳定内容摘要，可比较、可缓存）
```

支持嵌套结构（dict / list 递归比较），但作者可见的摘要仍以**顶层字段**为准
（Blueprint payload 是扁平字段 + list，顶层字段才是作者语言）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from novelforge.core.ids import digest_payload

from .errors import EditorValidationError


@dataclass(frozen=True)
class FieldChange:
    """一个顶层字段的变化（kind ∈ added / removed / changed）。"""

    field: str
    kind: str
    before: Any = None
    after: Any = None
    nested: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {"field": self.field, "kind": self.kind, "before": self.before,
                "after": self.after, "nested": list(self.nested)}


@dataclass(frozen=True)
class ListChange:
    """list 字段的条目级变化（added / removed / reordered）。"""

    field: str
    added: tuple[Any, ...] = ()
    removed: tuple[Any, ...] = ()
    reordered: bool = False
    before: tuple[Any, ...] = ()
    after: tuple[Any, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {"field": self.field, "added": list(self.added),
                "removed": list(self.removed), "reordered": self.reordered,
                "before": list(self.before), "after": list(self.after)}


def _stable(value: Any) -> Any:
    """把值转成可比较 / 可序列化的稳定形式（dict / list 递归）。"""

    if isinstance(value, Mapping):
        return {str(key): _stable(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_stable(item) for item in value]
    return value


def _fingerprint(value: Any) -> str:
    return digest_payload(_stable(value))


def _multiset_diff(before: Sequence[Any], after: Sequence[Any]
                   ) -> tuple[tuple[Any, ...], tuple[Any, ...]]:
    """按稳定 fingerprint 做多重集差（保留出现次数，避免"重复项"被当成没变）。"""

    remaining = list(after)
    removed: list[Any] = []
    for item in before:
        match = next((index for index, other in enumerate(remaining)
                      if _fingerprint(other) == _fingerprint(item)), None)
        if match is None:
            removed.append(item)
        else:
            remaining.pop(match)
    return tuple(remaining), tuple(removed)


def _nested_paths(before: Any, after: Any, prefix: str) -> tuple[str, ...]:
    """嵌套 dict 的差异路径（用于说明"哪个子字段变了"）。"""

    if not isinstance(before, Mapping) or not isinstance(after, Mapping):
        return ()
    paths: list[str] = []
    for key in sorted(set(before) | set(after)):
        if before.get(key) == after.get(key):
            continue
        paths.append(f"{prefix}.{key}")
    return tuple(paths)


@dataclass(frozen=True)
class BlueprintDiff:
    """两个 revision 之间的结构化差异（同节点、同作品）。"""

    node_id: str
    novel_id: str
    revision_before: int
    revision_after: int
    field_changes: tuple[FieldChange, ...] = ()
    list_changes: tuple[ListChange, ...] = ()
    unchanged_fields: tuple[str, ...] = ()
    before: Mapping[str, Any] = field(default_factory=dict)
    after: Mapping[str, Any] = field(default_factory=dict)
    status_before: str = ""
    status_after: str = ""
    quality_status_before: str = ""
    quality_status_after: str = ""
    digest: str = ""

    def __post_init__(self) -> None:
        if not self.digest:
            object.__setattr__(self, "digest", digest_payload(
                {"node": self.node_id, "before": self.revision_before,
                 "after": self.revision_after,
                 "changes": [row.as_dict() for row in self.field_changes],
                 "lists": [row.as_dict() for row in self.list_changes]}))

    @property
    def added_fields(self) -> tuple[str, ...]:
        return tuple(row.field for row in self.field_changes if row.kind == "added")

    @property
    def removed_fields(self) -> tuple[str, ...]:
        return tuple(row.field for row in self.field_changes if row.kind == "removed")

    @property
    def changed_fields(self) -> tuple[str, ...]:
        return tuple(row.field for row in self.field_changes if row.kind == "changed")

    @property
    def all_changed_fields(self) -> tuple[str, ...]:
        return tuple(sorted({row.field for row in self.field_changes}))

    @property
    def changed(self) -> bool:
        return bool(self.field_changes) or bool(self.list_changes)

    @property
    def status_changed(self) -> bool:
        return bool(self.status_before) and self.status_before != self.status_after

    def as_dict(self) -> dict[str, Any]:
        return {"node_id": self.node_id, "novel_id": self.novel_id,
                "revision_before": self.revision_before,
                "revision_after": self.revision_after,
                "changed": self.changed,
                "added_fields": list(self.added_fields),
                "removed_fields": list(self.removed_fields),
                "changed_fields": list(self.changed_fields),
                "all_changed_fields": list(self.all_changed_fields),
                "unchanged_fields": list(self.unchanged_fields),
                "field_changes": [row.as_dict() for row in self.field_changes],
                "list_changes": [row.as_dict() for row in self.list_changes],
                "before": dict(self.before), "after": dict(self.after),
                "status": {"before": self.status_before, "after": self.status_after},
                "quality_status": {"before": self.quality_status_before,
                                   "after": self.quality_status_after},
                "digest": self.digest}


def diff_payloads(*, node_id: str, novel_id: str, before: Mapping[str, Any],
                  after: Mapping[str, Any], revision_before: int,
                  revision_after: int, status_before: str = "",
                  status_after: str = "", quality_status_before: str = "",
                  quality_status_after: str = "") -> BlueprintDiff:
    """确定性字段级 diff（零模型、可重复）。"""

    left, right = dict(before or {}), dict(after or {})
    changes: list[FieldChange] = []
    lists: list[ListChange] = []
    unchanged: list[str] = []
    for name in sorted(set(left) | set(right)):
        if name not in left:
            changes.append(FieldChange(field=name, kind="added",
                                       after=_stable(right[name])))
            continue
        if name not in right:
            changes.append(FieldChange(field=name, kind="removed",
                                       before=_stable(left[name])))
            continue
        old, new = _stable(left[name]), _stable(right[name])
        if old == new:
            unchanged.append(name)
            continue
        nested = _nested_paths(old, new, name)
        changes.append(FieldChange(field=name, kind="changed", before=old, after=new,
                                   nested=nested))
        if isinstance(old, list) and isinstance(new, list):
            added_items, removed_items = _multiset_diff(old, new)
            reordered = (not added_items and not removed_items and old != new)
            lists.append(ListChange(field=name, added=added_items,
                                    removed=removed_items, reordered=reordered,
                                    before=tuple(old), after=tuple(new)))
    payload_before = {row.field: row.before for row in changes if row.kind != "added"}
    payload_after = {row.field: row.after for row in changes if row.kind != "removed"}
    return BlueprintDiff(node_id=node_id, novel_id=novel_id,
                         revision_before=int(revision_before),
                         revision_after=int(revision_after),
                         field_changes=tuple(changes), list_changes=tuple(lists),
                         unchanged_fields=tuple(unchanged), before=payload_before,
                         after=payload_after, status_before=status_before,
                         status_after=status_after,
                         quality_status_before=quality_status_before,
                         quality_status_after=quality_status_after)


def assert_same_target(*, novel_id: str, left_novel_id: str, right_novel_id: str,
                       left_node_id: str, right_node_id: str) -> None:
    """§61 / §64：跨作品或跨节点的比较必须被拒绝。"""

    if str(left_novel_id) != str(novel_id) or str(right_novel_id) != str(novel_id):
        raise EditorValidationError(
            "不允许跨作品比较 revision",
            details={"novel_id": novel_id, "left": left_novel_id,
                     "right": right_novel_id})
    if str(left_node_id) != str(right_node_id):
        raise EditorValidationError(
            "不允许跨节点比较 revision",
            details={"left_node_id": left_node_id, "right_node_id": right_node_id})


__all__ = ["BlueprintDiff", "FieldChange", "ListChange", "assert_same_target",
           "diff_payloads"]
