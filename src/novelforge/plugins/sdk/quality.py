"""SDK：构造插件 quality issue（V4-09 §35–§37、§96）。

插件通过本函数返回结构化 finding；Host adapter 负责校验 namespace 与注册 code。
"""

from __future__ import annotations

from typing import Any, Sequence


def quality_issue(context: Any, *, code: str, reason: str,
                  node_ids: Sequence[str] = (), severity: str = "minor",
                  explanation: str = "", excerpt: str = "",
                  evidence_kind: str = "node_field",
                  metric: dict[str, Any] | None = None) -> Any:
    """构造一条插件 QualityIssue（只读；不修改 Blueprint / Canon / StoryState）。

    ```text
    1. code 必须 namespaced（plugin.<plugin_id>.<CODE>）；Host 会再次校验
    2. evidence 由本函数补齐（不允许无证据判定）
    3. 插件 evaluator 默认 non-blocking；是否参与由 QualityPolicy 决定
    ```
    """

    from novelforge.quality import QualityEvidence, QualityScope, make_issue

    novel_id = str(getattr(context, "novel_id", "") or "")
    nodes = getattr(context, "nodes", {}) or {}
    resolved = [nodes[str(value)] for value in node_ids if str(value) in nodes]
    resolved_ids = tuple(sorted(str(value) for value in node_ids))
    node_types = tuple(sorted({str(getattr(node, "node_type", ""))
                               for node in resolved} - {""}))
    revisions = [int(getattr(node, "revision", 0) or 0) for node in resolved]
    revision = max(revisions) if revisions else None
    scope = QualityScope(novel_id=novel_id, node_ids=resolved_ids,
                         node_types=node_types, revision=revision, kind="nodes")
    evidence = QualityEvidence(
        evidence_id=f"plugin:{code}:{'-'.join(resolved_ids)}",
        kind=str(evidence_kind), explanation=str(explanation or reason),
        node_ids=resolved_ids, revision=revision,
        excerpt=str(excerpt)[:300], metric=dict(metric or {}))
    return make_issue(code=str(code), novel_id=novel_id, scope=scope,
                      reason=str(reason), evidence=[evidence],
                      evaluator_id=str(code), severity=str(severity))


__all__ = ["quality_issue"]
