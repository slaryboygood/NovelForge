"""Quality aggregation helper（V4-05 §41 / §56）：issue 去重与 usage 汇总。

两件事：

```text
1. issue 聚合：同一 issue_id 在多轮 / 多 gate 出现时只保留一条（severity 取最高）
2. usage 汇总：evaluation / repair / verification / total 的规范化与相加
```

**不是**质量分数：`decide_status` 只看 gate + severity + policy（§10）。
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from .contracts import (
    SEVERITY_ORDER,
    QualityGateResult,
    QualityIssue,
    QualityReport,
)

USAGE_KEYS: tuple[str, ...] = ("input_tokens", "output_tokens", "cost", "calls")


def empty_usage() -> dict[str, Any]:
    return {key: (0.0 if key == "cost" else 0) for key in USAGE_KEYS}


def normalize_usage(raw: Mapping[str, Any] | None, *, calls: int = 1
                    ) -> dict[str, Any]:
    """把一次模型调用 / 一次评估的 usage 归一化为统一形状。"""

    row = dict(raw or {})
    usage = empty_usage()
    input_tokens = row.get("input_tokens")
    if not isinstance(input_tokens, (int, float)):
        input_tokens = row.get("prompt_tokens")
    output_tokens = row.get("output_tokens")
    if not isinstance(output_tokens, (int, float)):
        output_tokens = row.get("completion_tokens")
    if isinstance(input_tokens, (int, float)):
        usage["input_tokens"] += int(input_tokens)
    if isinstance(output_tokens, (int, float)):
        usage["output_tokens"] += int(output_tokens)
    cost = row.get("estimated_cost", row.get("cost"))
    if isinstance(cost, (int, float)):
        usage["cost"] += float(cost)
    usage["calls"] += int(row.get("calls") or calls)
    usage["cost"] = round(float(usage["cost"]), 6)
    return usage


def merge_usage(*parts: Mapping[str, Any] | None) -> dict[str, Any]:
    """相加多个归一化 usage（缺键视为 0）。"""

    total = empty_usage()
    for part in parts:
        row = dict(part or {})
        for key in USAGE_KEYS:
            value = row.get(key)
            if isinstance(value, (int, float)):
                total[key] += float(value) if key == "cost" else int(value)
    total["cost"] = round(float(total["cost"]), 6)
    return total


def usage_totals(usage: Mapping[str, Any] | None) -> tuple[int, float]:
    """返回 (tokens, cost)：供 budget 判断（§41）。"""

    row = dict(usage or {})
    tokens = int(row.get("input_tokens") or 0) + int(row.get("output_tokens") or 0)
    return tokens, float(row.get("cost") or 0.0)


def build_usage(*, evaluation: Mapping[str, Any] | None = None,
                repair: Mapping[str, Any] | None = None,
                verification: Mapping[str, Any] | None = None
                ) -> dict[str, Any]:
    """QualityReport / Loop 的统一 usage 形状（§41）。"""

    evaluation_usage = merge_usage(evaluation)
    repair_usage = merge_usage(repair)
    verification_usage = merge_usage(verification)
    return {"evaluation": evaluation_usage, "repair": repair_usage,
            "verification": verification_usage,
            "total": merge_usage(evaluation_usage, repair_usage, verification_usage)}


def _severity_rank(issue: QualityIssue) -> int:
    return SEVERITY_ORDER.get(issue.severity, len(SEVERITY_ORDER))


def merge_issues(issues: Iterable[QualityIssue]) -> tuple[QualityIssue, ...]:
    """按 issue_id 去重；同一 id 取 severity 更高（更严重）的一条。

    规则（§5 / §28）：`ARTIFACT_IDENTITY_IS_NOT_SEMANTIC_IDENTITY` ——
    issue_id 已经是语义 identity，因此重复出现只表示同一条问题。
    """

    best: dict[str, QualityIssue] = {}
    for issue in issues:
        current = best.get(issue.issue_id)
        if current is None or _severity_rank(issue) < _severity_rank(current):
            best[issue.issue_id] = issue
    return tuple(best[key] for key in sorted(best))


def group_by_gate(issues: Iterable[QualityIssue]) -> dict[str, tuple[QualityIssue, ...]]:
    grouped: dict[str, list[QualityIssue]] = {}
    for issue in issues:
        grouped.setdefault(issue.gate, []).append(issue)
    return {gate: tuple(sorted(rows, key=lambda row: row.issue_id))
            for gate, rows in sorted(grouped.items())}


def summarize_gates(report: QualityReport) -> dict[str, Any]:
    """每个 gate 的计数摘要（不含分数）。"""

    summary: dict[str, Any] = {}
    for row in report.gate_results:
        summary[row.gate] = {"status": row.status, "issues": len(row.issues),
                             "blockers": row.blocker_count,
                             "skipped_reason": row.skipped_reason}
    return summary


def summarize_report(report: QualityReport) -> dict[str, Any]:
    """面向 Application / MCP / UI 的紧凑摘要。"""

    counts: dict[str, int] = {}
    for issue in report.issues:
        counts[issue.severity] = counts.get(issue.severity, 0) + 1
    return {"report_id": report.report_id, "novel_id": report.novel_id,
            "status": report.status, "scope": report.scope.as_dict(),
            "issue_count": len(report.issues),
            "severity_counts": dict(sorted(counts.items())),
            "gates": summarize_gates(report), "usage": dict(report.usage),
            "generated_at": report.generated_at}


def gate_status(issues: Sequence[QualityIssue], *, blocking: Sequence[str]) -> str:
    """单个 gate 的状态（blocker > blocking severity > passed）。"""

    if any(issue.severity == "blocker" for issue in issues):
        return "blocked"
    if any(issue.severity in set(blocking) for issue in issues):
        return "failed"
    return "passed"


def summarize_gate_results(rows: Iterable[QualityGateResult]) -> dict[str, str]:
    return {row.gate: row.status for row in rows}


__all__ = [
    "USAGE_KEYS", "build_usage", "empty_usage", "gate_status", "group_by_gate",
    "merge_issues", "merge_usage", "normalize_usage", "summarize_gate_results",
    "summarize_gates", "summarize_report", "usage_totals",
]
