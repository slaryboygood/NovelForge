---
name: novelforge-v4.0.1.quality.understand-quality-gates
description: 掌握 Q0–Q9 gate、severity → 放行规则、issue code registry 与 evidence 模型，正确解读质量结论。
---

# understand-quality-gates

- **Skill ID**: `novelforge-v4.0.1.quality.understand-quality-gates`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `quality`
- **Product owner**: `src/novelforge/quality/contracts.py` + `codes.py` + `registry.py`

## Purpose

避免误读质量结果（例如把"分数"当结论、把 passed 当 accepted、以为可以随便新增 code）。

## Use when

- 需要判断某个 issue 是否应该阻塞流程。
- 需要解释 evaluator 的 deterministic / llm_assisted 差异。
- 要写新的 evaluator（插件扩展点）。

## Do not use when

- 只是要跑评估 → `evaluate-blueprint`。

## Preconditions

```text
无
```

## Required inputs

```text
无
```

## Authoritative interfaces

```text
UI           「检查」页（只展示）
REST         N/A（知识型）
Application  novelforge.quality（GATES / ISSUE_CODES / CODE_REGISTRY / EvaluatorRegistry）
MCP          N/A
```

## Procedure（读法顺序）

```text
1 先看 report.status：unevaluated / passed / failed / blocked / needs_human_review
2 再看每个 gate 的 status 与 blocker 数（Q9 是交付就绪度）
3 blocking 规则来自 QualityPolicy.blocking_severities（默认 blocker + major）
4 issue.code 必须来自 ISSUE_CODES（LLM 不得自由生成 code）；插件 code 必须 namespaced
   plugin.<plugin_id>.<CODE>，且不得覆盖 Core code
5 evidence 是一等对象：kind / explanation / node_ids / revision / excerpt / metric
6 deterministic evaluator 永远跑；hybrid / llm_assisted 需要 policy 显式启用
7 质量结论与故事真相分离：Quality Store 不写回 Blueprint（ADR-020）
8 修复不是 evaluator 的职责：evaluator 只读，修复走 Repair Contract
```

## Expected result

能正确回答：

```text
· Q0 blocker 意味着什么？（结构不合法，必须先修结构，不可交付）
· 为什么没有总分？（gate-based，总分会让作者拿平均分掩盖 blocker）
· 为什么 Q6 说场景重复但节点没变？（evaluator 只读，只能提 issue）
```

## Verification

```text
· 交叉核对 src/novelforge/quality/contracts.py（GATES / SEVERITIES / QUALITY_STATUSES）
· 交叉核对 src/novelforge/quality/codes.py（ISSUE_CODES / register_plugin_code）
· 交叉核对 src/novelforge/quality/registry.py（build_default_registry）
· 契约文档 docs/v4/V4_QUALITY_CONTRACT.md §2–§4
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 想新增 issue code | LLM / 调用方不得自造 | 用已有 code；插件按 namespace 注册 |
| 拿 deterministic 结果当"全部结论" | llm_assisted critic 未启用 | 需要时显式启用 policy |
| 用 gate 数量替代严重性判断 | 误解 | 以 blocker / major 是否阻塞为准 |

## Safety / invariants

```text
不削弱 gate（不为了通过而删 assertion / 模糊检查）
不把 derived 统计冒充真实质量结论
插件 evaluator 只能追加，不能覆盖 Core
```

## Side effects

无。

## Related skills

`evaluate-blueprint`、`inspect-quality-report`、`list-quality-issues`、
`novelforge-v4.0.1.repair.understand-repair-contract`

## Source references

```text
src/novelforge/quality/contracts.py、codes.py、registry.py、evaluators/*
docs/v4/V4_QUALITY_CONTRACT.md
docs/v4/adr/ADR-018-quality-is-gate-based-not-score-based.md
docs/v4/adr/ADR-020-quality-evidence-is-separate-from-story-truth.md
tests/quality/test_quality_registry.py
```
