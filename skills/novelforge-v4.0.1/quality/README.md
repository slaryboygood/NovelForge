# Module: `quality` — Q0–Q9 质量门禁

```text
Module purpose     gate-based 质量评估：发现 issue + 提供 evidence，不做总分、不改节点
Authoritative owner src/novelforge/quality/{service,registry,store,contracts,codes}.py
Owned skills       evaluate-blueprint / inspect-quality-report / list-quality-issues /
                   understand-quality-gates
Truth ownership    Quality Store（report / issue / evidence）—— 与故事真相分离（ADR-020）
Public interfaces  UI「检查」；REST /studio/quality*、/editor/nodes/{id}/quality；
                   Application ReviewService / EditorService.get_quality；
                   MCP tool evaluate_blueprint + quality resources
Dependencies       blueprint（只读）、story_engine canon（只读）、memory（上下文）
Forbidden          修改 Blueprint / Canon / StoryState；写权威总分；让 evaluator 变成 repair
Related modules    repair（修 issue）、editor（作者改）、delivery（读质量结论做 preflight）
```

## Gate 表（唯一 SSOT：`quality/contracts.py::GATES`）

| Gate | 名称 | evaluator（deterministic / hybrid） |
| --- | --- | --- |
| Q0 | Schema | `quality.schema.v1` |
| Q1 | Integrity | `quality.integrity.v1` |
| Q2 | Canon | `quality.canon.v1` + `quality.canon.critic.v1`（llm_assisted，默认关闭） |
| Q3 | Continuity | `quality.continuity.v1` |
| Q4 | Character | `quality.character.v1` |
| Q5 | Causality | `quality.causality.v1` |
| Q6 | Semantic | `quality.semantic.v1` |
| Q7 | Narrative | `quality.narrative.v1` |
| Q8 | Blueprint Style | `quality.style.v1` |
| Q9 | Delivery Readiness | `quality.delivery.v1` |

## 严重级别与放行

```text
severity        info / minor / major / blocker
默认 blocking   blocker + major（QualityPolicy.blocking_severities）
issue status    open / repairing / resolved / accepted_risk / ignored
report status   unevaluated / evaluating / passed / failed / blocked / needs_human_review
没有权威总分：以 gate 结论 + blocking issue 数量为准
```
