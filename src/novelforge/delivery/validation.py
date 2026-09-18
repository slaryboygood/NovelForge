"""DeliveryValidator（V4-07 §16–§18、§50–§51、§80–§81）。

```text
Q9（V4-05）        → story-level delivery readiness（已经有结论，存在 Quality Store）
DeliveryValidator → 真实 export 请求 + 选中的 revision + package 完整性
```

因此本模块**不重新实现** Q9：它消费 Quality Store 里针对被选 revision 的
Q0–Q9 issue（§18「优先复用 Q9 Quality issues」），再补上交付特有的检查
（accepted 要求 / review 拒绝 / stale quality / 引用完整性 / 跨作品 / schema）。

稳定 issue code 见 `ISSUE_CODES`。
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from novelforge.blueprint import BLUEPRINT_SCHEMA_VERSION, BlueprintNode

from .compiler import BlueprintCompiler
from .contracts import (
    DeliveryIssue,
    DeliverySelection,
    DeliverySnapshot,
    DeliveryValidationResult,
)
from .selection import NodeQualityState, SelectionOutcome

#: 交付 issue code（稳定，§51）
ISSUE_CODES: tuple[str, ...] = (
    "DELIVERY_NO_ACCEPTED_REVISION",
    "DELIVERY_REVISION_MISSING",
    "DELIVERY_SCHEMA_UNSUPPORTED",
    "DELIVERY_REJECTED_REVISION",
    "DELIVERY_QUALITY_UNEVALUATED",
    "DELIVERY_QUALITY_FAILED",
    "DELIVERY_QUALITY_STALE",
    "DELIVERY_Q9_BLOCKER",
    "DELIVERY_INVALIDATION_PENDING",
    "DELIVERY_MISSING_REQUIRED_NODE",
    "DELIVERY_ORPHAN_NODE",
    "DELIVERY_REFERENCE_BROKEN",
    "DELIVERY_CROSS_NOVEL_REFERENCE",
    "DELIVERY_PLACEHOLDER_CONTENT",
    "DELIVERY_UNPAID_REQUIRED_SETUP",
    "DELIVERY_OWNERSHIP_MISMATCH",
    "DELIVERY_ARTIFACT_MISSING",
    "DELIVERY_ARTIFACT_EMPTY",
    "DELIVERY_CHECKSUM_MISMATCH",
    "DELIVERY_MANIFEST_MISMATCH",
    "DELIVERY_PATH_UNSAFE",
)

#: 占位 / 无效交付内容（来自 Q8 / Q9 的 issue code → 交付 code）
PLACEHOLDER_SOURCES: tuple[str, ...] = (
    "BLUEPRINT_PLACEHOLDER_TEXT", "DELIVERY_PLACEHOLDER", "HOLLOW_NODE",
)


class DeliveryValidator:
    """preflight（写文件之前）+ post-build（发布之前）两道校验。"""

    def __init__(self, repository: Any, *, quality_store: Any = None) -> None:
        self.repository = repository
        self.novel_id = repository.novel_id
        self.quality_store = quality_store
        self.compiler = BlueprintCompiler(repository)

    # -------------------------------------------------------------- preflight
    def preflight(self, *, selection: DeliverySelection,
                  outcome: SelectionOutcome,
                  snapshot: DeliverySnapshot) -> DeliveryValidationResult:
        policy = selection.policy
        issues: list[DeliveryIssue] = []
        warnings: list[DeliveryIssue] = []
        # §9：被排除的节点必须显式说明原因（"没有 accepted revision" 是交付 blocker）
        for row in outcome.excluded:
            reason = str(row.get("reason") or "")
            if reason == "NO_ACCEPTED_REVISION" and policy.require_accepted:
                issues.append(DeliveryIssue(
                    code="DELIVERY_NO_ACCEPTED_REVISION", severity="blocker",
                    message=f"{row.get('node_id')} 没有 accepted revision",
                    node_ids=(str(row.get("node_id")),),
                    evidence=dict(row)))
        nodes: dict[str, BlueprintNode] = {}
        for node_id, revision in sorted(outcome.selected.items()):
            stored = self.repository.get_revision(node_id, int(revision))
            if stored is None:
                issues.append(DeliveryIssue(
                    code="DELIVERY_REVISION_MISSING", severity="blocker",
                    message=f"选中的 revision 不存在：{node_id}@{revision}",
                    node_ids=(node_id,), revision=int(revision)))
                continue
            if str(stored.novel_id) != self.novel_id:
                issues.append(DeliveryIssue(
                    code="DELIVERY_CROSS_NOVEL_REFERENCE", severity="blocker",
                    message=f"{node_id} 属于其他作品（{stored.novel_id}）",
                    node_ids=(node_id,), revision=int(revision)))
                continue
            if int(stored.schema_version) != int(BLUEPRINT_SCHEMA_VERSION):
                issues.append(DeliveryIssue(
                    code="DELIVERY_SCHEMA_UNSUPPORTED", severity="blocker",
                    message=(f"{node_id} 的 schema_version={stored.schema_version} "
                             f"不受当前交付契约支持"),
                    node_ids=(node_id,), revision=int(revision)))
            nodes[node_id] = stored
            # accepted 要求（§11：与质量要求互相独立）
            if policy.require_accepted and str(stored.status) != "accepted":
                issues.append(DeliveryIssue(
                    code="DELIVERY_NO_ACCEPTED_REVISION", severity="blocker",
                    message=f"{node_id}@{revision} 不是 accepted（status={stored.status}）",
                    node_ids=(node_id,), revision=int(revision),
                    evidence={"status": str(stored.status)}))
            review = str(outcome.review_refs.get(node_id) or "")
            if review.startswith("rejected"):
                issues.append(DeliveryIssue(
                    code="DELIVERY_REJECTED_REVISION", severity="blocker",
                    message=f"{node_id}@{revision} 已被 review 拒绝",
                    node_ids=(node_id,), revision=int(revision),
                    evidence={"review": review}))
            issues.extend(self._quality_issues(
                node_id, int(revision), outcome.quality.get(node_id), policy))
            issues.extend(self._q9_issues(node_id, int(revision), policy))
        # 结构完整性
        issues.extend(self._structure_issues(nodes, selection))
        issues.extend(self._placeholder_issues(nodes))
        # §14：编辑发生在质量评估之后 → 必须先重新评估
        for row in outcome.pending_invalidations:
            node_id = str(row.get("node_id"))
            issue = DeliveryIssue(
                code="DELIVERY_INVALIDATION_PENDING",
                severity="blocker" if policy.require_no_pending_invalidation
                else "warning",
                message=f"{node_id} 在质量评估之后又被编辑过，需要重新评估",
                node_ids=(node_id,), revision=int(row.get("revision") or 0),
                evidence=dict(row))
            (issues if issue.blocking else warnings).append(issue)
        # issues = 阻断项；其余（severity=warning）归入 warnings（§51）
        blocking = [row for row in issues if row.blocking]
        warnings = [*warnings, *(row for row in issues if not row.blocking)]
        reason = blocking[0].message if blocking else ""
        return DeliveryValidationResult(
            novel_id=self.novel_id, phase="preflight", ok=not blocking,
            issues=tuple(issues), warnings=tuple(warnings),
            selected_revisions=dict(outcome.selected),
            quality_summary=self._quality_summary(outcome), blocking_reason=reason)

    # ------------------------------------------------------------- post-build
    def post_build(self, *, snapshot: DeliverySnapshot,
                   artifacts: Sequence[Any],
                   manifest: Any) -> DeliveryValidationResult:
        issues: list[DeliveryIssue] = []
        manifest_paths = {str(row["path"]) for row in manifest.artifacts}
        for artifact in artifacts:
            if artifact.size <= 0 or not artifact.content:
                issues.append(DeliveryIssue(
                    code="DELIVERY_ARTIFACT_EMPTY", severity="blocker",
                    message=f"{artifact.filename} 为空", node_ids=()))
            if artifact.relative_path not in manifest_paths:
                issues.append(DeliveryIssue(
                    code="DELIVERY_MANIFEST_MISMATCH", severity="blocker",
                    message=f"{artifact.filename} 未出现在 manifest 中", node_ids=()))
            if not _safe_relative(artifact.relative_path):
                issues.append(DeliveryIssue(
                    code="DELIVERY_PATH_UNSAFE", severity="blocker",
                    message=f"artifact 路径不安全：{artifact.relative_path}",
                    node_ids=()))
            if str(artifact.format) == "json" or str(artifact.format) == "markdown":
                if not artifact.text:
                    issues.append(DeliveryIssue(
                        code="DELIVERY_ARTIFACT_MISSING", severity="blocker",
                        message=f"{artifact.filename} 不是可读文本格式", node_ids=()))
        return DeliveryValidationResult(
            novel_id=self.novel_id, phase="post_build", ok=not issues,
            issues=tuple(issues), selected_revisions=dict(snapshot.node_revisions),
            quality_summary=dict(manifest.quality_summary),
            blocking_reason=issues[0].message if issues else "")

    # ------------------------------------------------------------------ 内部
    @staticmethod
    def _quality_issues(node_id: str, revision: int,
                        state: NodeQualityState | None,
                        policy: Any) -> list[DeliveryIssue]:
        """§11–§13：质量要求与 accepted 要求互相独立，且 stale 必须被识别。"""

        if not policy.require_quality_pass or state is None:
            return []
        if state.state == "failed":
            return [DeliveryIssue(
                code="DELIVERY_QUALITY_FAILED", severity="blocker",
                message=(f"{node_id}@{revision} 存在阻断质量结论："
                         f"{list(state.blocking_codes)}"),
                node_ids=(node_id,), revision=int(revision),
                evidence={"blocking_codes": list(state.blocking_codes),
                          "report_id": state.report_id})]
        if state.state == "stale":
            return [DeliveryIssue(
                code="DELIVERY_QUALITY_STALE",
                severity="warning" if policy.allow_stale_quality else "blocker",
                message=(f"{node_id} 的质量结论针对 r{state.evaluated_revision}，"
                         f"但交付选中 r{revision}"),
                node_ids=(node_id,), revision=int(revision),
                evidence={"evaluated_revision": int(state.evaluated_revision),
                          "report_id": state.report_id})]
        if state.state == "unevaluated" and not policy.allow_unevaluated:
            return [DeliveryIssue(
                code="DELIVERY_QUALITY_UNEVALUATED", severity="blocker",
                message=f"{node_id}@{revision} 没有质量结论",
                node_ids=(node_id,), revision=int(revision))]
        return []

    def _q9_issues(self, node_id: str, revision: int,
                   policy: Any) -> list[DeliveryIssue]:
        if self.quality_store is None:
            return []
        rows: list[DeliveryIssue] = []
        for issue in self.quality_store.list_issues():
            scope = dict(issue.get("scope") or {})
            if node_id not in scope.get("node_ids", []):
                continue
            if str(issue.get("gate")) != "Q9":
                continue
            if str(issue.get("severity")) not in set(policy.blocking_severities):
                continue
            rows.append(DeliveryIssue(
                code="DELIVERY_Q9_BLOCKER", severity="blocker",
                message=f"Q9 交付就绪度问题：{issue.get('code')}",
                node_ids=(node_id,), revision=int(revision),
                evidence={"quality_issue_id": issue.get("issue_id"),
                          "quality_code": issue.get("code")}))
        return rows

    def _structure_issues(self, nodes: Mapping[str, BlueprintNode],
                          selection: DeliverySelection) -> list[DeliveryIssue]:
        issues: list[DeliveryIssue] = []
        policy = selection.policy
        present_types = {node.node_type for node in nodes.values()}
        missing = [kind for kind in ("premise", "story_arc", "chapter", "scene")
                   if kind not in present_types]
        if missing:
            issues.append(DeliveryIssue(
                code="DELIVERY_MISSING_REQUIRED_NODE", severity="blocker",
                message=f"缺少交付必需节点类型：{missing}",
                evidence={"missing": missing}))
        if policy.require_no_orphans:
            for node in nodes.values():
                if node.node_type not in ("chapter", "scene"):
                    continue
                if node.parent_id and node.parent_id in nodes:
                    continue
                issues.append(DeliveryIssue(
                    code="DELIVERY_ORPHAN_NODE", severity="blocker",
                    message=f"{node.node_id} 在交付集中没有父节点",
                    node_ids=(node.node_id,), revision=node.revision))
        # 引用完整性（父节点 / causal 端点 / setup 绑定必须都在交付集内）
        for node in nodes.values():
            payload = _payload(node)
            if node.parent_id and node.parent_id not in nodes:
                issues.append(DeliveryIssue(
                    code="DELIVERY_REFERENCE_BROKEN", severity="blocker",
                    message=f"{node.node_id} 的父节点 {node.parent_id} 不在交付集中",
                    node_ids=(node.node_id,), revision=node.revision))
            if node.node_type == "causal_link":
                for field in ("source_node", "target_node"):
                    target = str(payload.get(field) or "")
                    if target and target not in nodes:
                        issues.append(DeliveryIssue(
                            code="DELIVERY_REFERENCE_BROKEN", severity="blocker",
                            message=f"{node.node_id} 引用了不在交付集中的 {target}",
                            node_ids=(node.node_id,), revision=node.revision,
                            evidence={"field": field, "reference": target}))
            if node.node_type == "payoff":
                for setup_id in payload.get("resolves_setup_ids") or []:
                    if str(setup_id) and str(setup_id) not in nodes:
                        issues.append(DeliveryIssue(
                            code="DELIVERY_REFERENCE_BROKEN", severity="blocker",
                            message=(f"{node.node_id} 回收了不在交付集中的 "
                                     f"{setup_id}"),
                            node_ids=(node.node_id,), revision=node.revision))
        # 未回收 required setup（§17）
        if policy.require_no_unpaid_required_setup:
            bound = {str(value) for node in nodes.values()
                     if node.node_type == "payoff"
                     for value in (_payload(node).get("resolves_setup_ids") or [])}
            for node in nodes.values():
                if node.node_type != "setup":
                    continue
                payload = _payload(node)
                if node.node_id in bound or str(payload.get("status")) in ("paid",
                                                                          "abandoned"):
                    continue
                issues.append(DeliveryIssue(
                    code="DELIVERY_UNPAID_REQUIRED_SETUP", severity="blocker",
                    message=f"{node.node_id} 尚未回收",
                    node_ids=(node.node_id,), revision=node.revision))
        return issues

    def _placeholder_issues(self, nodes: Mapping[str, BlueprintNode]
                            ) -> list[DeliveryIssue]:
        """复用 Quality Store 的 Q8/Q9 占位符结论（不重新实现规则，§18）。"""

        if self.quality_store is None:
            return []
        issues: list[DeliveryIssue] = []
        for issue in self.quality_store.list_issues():
            code = str(issue.get("code"))
            if code not in PLACEHOLDER_SOURCES:
                continue
            for node_id in (issue.get("scope") or {}).get("node_ids", []):
                if node_id not in nodes:
                    continue
                issues.append(DeliveryIssue(
                    code="DELIVERY_PLACEHOLDER_CONTENT", severity="blocker",
                    message=f"{node_id} 含占位 / 空洞内容（{code}）",
                    node_ids=(node_id,), revision=nodes[node_id].revision,
                    evidence={"quality_issue_id": issue.get("issue_id"),
                              "quality_code": code}))
        return issues

    @staticmethod
    def _quality_summary(outcome: SelectionOutcome) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for state in outcome.quality.values():
            counts[state.state] = counts.get(state.state, 0) + 1
        return {"nodes": len(outcome.selected),
                "by_state": dict(sorted(counts.items())),
                "excluded": len(outcome.excluded)}


def _payload(node: BlueprintNode) -> dict[str, Any]:
    payload = getattr(node, "payload", None)
    if hasattr(payload, "model_dump"):
        return payload.model_dump(mode="json")
    return dict(payload or {})


def _safe_relative(path: str) -> bool:
    text = str(path or "").replace("\\", "/")
    if not text or text.startswith("/") or ":" in text:
        return False
    parts = [part for part in text.split("/") if part]
    return bool(parts) and all(part not in ("..", ".") for part in parts)


__all__ = ["ISSUE_CODES", "PLACEHOLDER_SOURCES", "DeliveryValidator"]
