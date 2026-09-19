"""Revision selection 与质量 / review 证据解析（V4-07 §7–§14、§69）。

选择规则（§9）：**不是"目录里 revision 最大的就是最终版"**。

```text
accepted            → 该节点 status == accepted 的最新 revision
                      （且该 revision 未被 review 拒绝）
explicit_revisions  → 调用方显式钉住 node_id → revision
current             → 当前 revision（可能 proposed / unevaluated → 交由 policy 判定）
```

质量真相来源（§12）：Quality Store（issue + report），**不是**节点上的
`quality_status` 投影；stale 判定（§13）：报告记录的评估 revision != 选中 revision。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from novelforge.blueprint import BlueprintNode, BlueprintRepository
from novelforge.core.ids import digest_payload

from .contracts import DeliveryIssue, DeliverySelection
from .errors import DeliveryOwnershipError, DeliverySelectionError

REQUIRED_NODE_TYPES: tuple[str, ...] = ("premise", "story_arc", "chapter", "scene")


@dataclass(frozen=True)
class NodeQualityState:
    """一个被选中节点在**被选 revision** 上的质量证据状态（§12–§13）。"""

    node_id: str
    revision: int
    state: str = "unevaluated"       # passed | failed | unevaluated | stale
    evaluated_revision: int = 0
    report_id: str = ""
    evaluated_at: str = ""
    blocking_codes: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {"node_id": self.node_id, "revision": self.revision,
                "state": self.state, "evaluated_revision": self.evaluated_revision,
                "report_id": self.report_id, "evaluated_at": self.evaluated_at,
                "blocking_codes": list(self.blocking_codes)}


@dataclass(frozen=True)
class SelectionOutcome:
    selection: DeliverySelection
    selected: Mapping[str, int] = field(default_factory=dict)
    node_types: Mapping[str, str] = field(default_factory=dict)
    excluded: tuple[Mapping[str, Any], ...] = ()
    quality: Mapping[str, NodeQualityState] = field(default_factory=dict)
    review_refs: Mapping[str, str] = field(default_factory=dict)
    quality_refs: Mapping[str, str] = field(default_factory=dict)
    pending_invalidations: tuple[Mapping[str, Any], ...] = ()
    issues: tuple[DeliveryIssue, ...] = ()

    @property
    def digest(self) -> str:
        return digest_payload({"selection": self.selection.digest,
                               "selected": {str(key): int(value) for key, value in
                                            sorted(self.selected.items())},
                               "quality": {key: value.state for key, value
                                           in sorted(self.quality.items())}})

    def by_type(self, node_type: str) -> tuple[str, ...]:
        return tuple(sorted(node_id for node_id, kind in self.node_types.items()
                            if kind == node_type))

    def as_dict(self) -> dict[str, Any]:
        return {"novel_id": self.selection.novel_id,
                "selection_mode": self.selection.selection_mode,
                "profile": self.selection.profile,
                "selected": {str(key): int(value) for key, value
                             in sorted(self.selected.items())},
                "node_types": dict(sorted(self.node_types.items())),
                "excluded": [dict(row) for row in self.excluded],
                "quality": {key: value.as_dict()
                            for key, value in sorted(self.quality.items())},
                "review_refs": dict(sorted(self.review_refs.items())),
                "quality_refs": dict(sorted(self.quality_refs.items())),
                "pending_invalidations": [dict(row) for row in
                                          self.pending_invalidations],
                "digest": self.digest}


class RevisionSelector:
    """把 DeliverySelection 解析成 (node_id → revision) + 质量 / review 证据。"""

    def __init__(self, repository: BlueprintRepository, *,
                 quality_store: Any = None, editor_store: Any = None) -> None:
        self.repository = repository
        self.novel_id = repository.novel_id
        self.quality_store = quality_store
        self.editor_store = editor_store

    # ------------------------------------------------------------------ 入口
    def select(self, selection: DeliverySelection) -> SelectionOutcome:
        if str(selection.novel_id) != self.novel_id:
            raise DeliveryOwnershipError(
                f"拒绝跨作品交付：{selection.novel_id} != {self.novel_id}",
                details={"novel_id": self.novel_id,
                         "requested": str(selection.novel_id)})
        nodes = {node.node_id: node for node in self.repository.all_nodes()}
        wanted_types = {str(value) for value in selection.include_node_types if value}
        selected: dict[str, int] = {}
        node_types: dict[str, str] = {}
        excluded: list[dict[str, Any]] = []
        issues: list[DeliveryIssue] = []
        for node_id in sorted(nodes):
            node = nodes[node_id]
            if wanted_types and node.node_type not in wanted_types:
                excluded.append({"node_id": node_id, "revision": 0,
                                 "reason": "NODE_TYPE_FILTERED",
                                 "node_type": node.node_type})
                continue
            revision = self._resolve_revision(selection, node)
            if not revision:
                excluded.append({"node_id": node_id, "revision": 0,
                                 "reason": "NO_ACCEPTED_REVISION"
                                 if selection.selection_mode == "accepted"
                                 else "NO_REVISION",
                                 "node_type": node.node_type})
                continue
            selected[node_id] = int(revision)
            node_types[node_id] = node.node_type
        quality = {node_id: self._quality_state(node_id, revision, selection)
                   for node_id, revision in sorted(selected.items())}
        review_refs = {node_id: self._review_ref(node_id, revision)
                       for node_id, revision in sorted(selected.items())}
        quality_refs = {node_id: state.report_id for node_id, state in quality.items()
                        if state.report_id}
        return SelectionOutcome(
            selection=selection, selected=selected, node_types=node_types,
            excluded=tuple(excluded), quality=quality, review_refs=review_refs,
            quality_refs=quality_refs,
            pending_invalidations=self._pending_invalidations(selected, quality),
            issues=tuple(issues))

    # -------------------------------------------------------- revision 解析
    def _resolve_revision(self, selection: DeliverySelection,
                          node: BlueprintNode) -> int:
        mode = selection.selection_mode
        if mode == "explicit_revisions":
            revision = int(selection.explicit_revisions.get(node.node_id) or 0)
            if not revision:
                return 0
            stored = self.repository.get_revision(node.node_id, revision)
            if stored is None or stored.novel_id != self.novel_id:
                raise DeliverySelectionError(
                    f"显式 revision 不存在或归属不符：{node.node_id}@{revision}",
                    details={"node_id": node.node_id, "revision": revision})
            return revision
        if mode == "current":
            return int(self.repository.current_revision(node.node_id) or 0)
        return self._accepted_revision(node.node_id)

    def _accepted_revision(self, node_id: str) -> int:
        """status == accepted 的**最新** revision，且未被 review 拒绝（§9–§10）。"""

        accepted: list[int] = []
        for revision in self.repository.list_revisions(node_id):
            stored = self.repository.get_revision(node_id, revision)
            if stored is None or str(stored.status) != "accepted":
                continue
            if self._review_decision(node_id, revision) == "rejected":
                continue
            accepted.append(int(revision))
        return max(accepted) if accepted else 0

    # ------------------------------------------------------ review / quality
    def _review_decision(self, node_id: str, revision: int) -> str:
        if self.editor_store is None:
            return ""
        row = self.editor_store.review_for(node_id, int(revision))
        return str(row.get("decision") or "")

    def _review_ref(self, node_id: str, revision: int) -> str:
        decision = self._review_decision(node_id, revision)
        return f"{decision}@{revision}" if decision else ""

    def _quality_state(self, node_id: str, revision: int,
                       selection: DeliverySelection) -> NodeQualityState:
        blocking = set(selection.policy.blocking_severities)
        if self.quality_store is None:
            return NodeQualityState(node_id=node_id, revision=int(revision))
        # V4.0.2 PB-1：只统计**仍是当前真相**的 issue（open/repairing + 最新报告仍包含它），
        # 历史（已 resolved 或已被新报告取代）的 issue 不得继续把节点判成 failed。
        issues = self.quality_store.live_issues(node_id=node_id,
                                                revision=int(revision))
        blocking_codes = tuple(sorted(str(row.get("code")) for row in issues
                                      if str(row.get("severity")) in blocking))
        evaluated_revision, report_id, evaluated_at = self._evaluated_revision(node_id)
        if blocking_codes:
            state = "failed"
        elif evaluated_revision == int(revision):
            state = "passed"
        elif evaluated_revision:
            state = "stale"
        else:
            state = "unevaluated"
        return NodeQualityState(node_id=node_id, revision=int(revision), state=state,
                                evaluated_revision=evaluated_revision,
                                report_id=report_id, evaluated_at=evaluated_at,
                                blocking_codes=blocking_codes)

    def _evaluated_revision(self, node_id: str) -> tuple[int, str, str]:
        """该节点最后一次质量评估覆盖的 revision（取最新报告）。"""

        best: tuple[int, str, str] = (0, "", "")
        for report in self.quality_store.reports():
            mapping = dict(report.get("node_revisions") or {})
            if node_id not in mapping:
                continue
            revision = int(mapping.get(node_id) or 0)
            generated = str(report.get("generated_at") or "")
            if revision > best[0] or (revision == best[0] and generated > best[2]):
                best = (revision, str(report.get("report_id") or ""), generated)
        return best

    def _pending_invalidations(self, selected: Mapping[str, int],
                               quality: Mapping[str, NodeQualityState]
                               ) -> tuple[Mapping[str, Any], ...]:
        """§14：质量评估之后如果该节点又被编辑过 → 交付前必须重新评估。"""

        if self.editor_store is None:
            return ()
        rows: list[dict[str, Any]] = []
        for node_id, revision in sorted(selected.items()):
            state = quality.get(node_id)
            if state is None or not state.evaluated_at:
                continue
            operations = self.editor_store.operations(node_id=node_id)
            later = [row for row in operations
                     if str(row.get("created_at") or "") > state.evaluated_at
                     and int(row.get("result_revision") or 0) != int(revision)]
            if later:
                rows.append({"node_id": node_id, "revision": int(revision),
                             "reason": "EDIT_AFTER_EVALUATION",
                             "operation_ids": [str(row.get("operation_id"))
                                               for row in later]})
        return tuple(rows)


__all__ = ["NodeQualityState", "REQUIRED_NODE_TYPES", "RevisionSelector",
           "SelectionOutcome"]
