# ADR-018 — Quality Is Gate-Based, Not Score-Based

```
Status    : Accepted（V4-05 实施完成）
Date      : 2026-09-17
Context   : V4-05 Quality Closed Loop & Targeted Repair
Related   : ADR-005（Quality Contract）；ADR-016（Blueprint node graph）；
            ADR-019（repair is minimal-scope and revisioned）；V4_QUALITY_CONTRACT.md §6–§10
```

## Context

V4-04 之后，NovelForge 第一次有了可生成的 canonical creative artifact（Story Blueprint）。
最直觉的质量实现是：

```text
让模型给大纲打分 → 82 分 → 通过
```

这条路有三个已经暴露过的具体问题：

1. **分数会互相抵消**：一个 Canon 冲突（角色已经死亡却出场）会被"节奏 95 分"平均掉。
2. **分数不可执行**：作者拿到"82 分"无法知道改哪里；修复流程也没有输入。
3. **分数不可复现**：LLM 打分不稳定，同一 revision 两次评估结果不同 → 无法做增量与回归。

项目已有事实：`planning/health.py` 刻意只给三态健康度而不给假精确总分；
`v3_projection` 的 readiness 是「步骤通过 / 未通过」而不是分数。

## Decision

1. **质量结论只有三种形态**：`passed` / `failed` / `blocked`（外加流程态
   `unevaluated` / `evaluating` / `needs_human_review`），由
   `decide_status(issues, policy, gates_run)` 决定。
2. **判定输入是 Gate + Severity + Policy**，不是平均分：

   ```text
   blocker issue                  → blocked
   policy.blocking_severities 命中 → failed
   required gate 未评估           → failed
   否则                           → passed
   ```

3. 分数可以作为 **diagnostic metric** 存在于 evidence 里（`similarity` /
   `confidence` / `run_length` / `chars`），但**不得**参与 PASS / FAIL 决策。
4. Gate 是固定的十层 Q0–Q9，每层显式声明 `deterministic / hybrid / llm_assisted`
   （见 `V4_QUALITY_CONTRACT.md` §3.3 矩阵）。

## Consequences

正面：

* Canon blocker 无法被平均掉；跨作品污染、ownership 破坏永远是 blocker；
* 判定可复现（deterministic 层给出一致的 issue id），因此可以做增量评估与回归对比；
* 修复有输入：issue → repair contract → minimal scope（ADR-019）。

代价：

* 没有"一个数字"给作者看 → 需要 UI 聚合（V4-10）把 gate 结论呈现成可读视图；
* 每个 gate 的 severity / 阈值必须进 policy，不能藏在 evaluator 里。

## Alternatives considered

| 方案 | 为什么不选 |
| --- | --- |
| 单一总分 + 阈值 | Canon blocker 会被平均掉；不可执行、不可复现（AGENTS.md §10） |
| 只用 LLM 综合评判 | 不稳定、不可复现、无法做增量；且 LLM 会自造 issue code |
| 全部 deterministic | 无法覆盖"语义是否重复 / 行为是否合理"（Q6–Q8 需要 hybrid） |

## Evidence

```text
src/novelforge/quality/contracts.py          decide_status（gate + severity + policy）
src/novelforge/quality/codes.py              code registry 固定 severity 与 gate
src/novelforge/quality/contracts.py          QualityPolicy.blocking_severities / required_gates
tests/quality/test_quality_contracts.py      blocker 不被 info/minor 抵消；未评估 gate → failed
tests/quality/test_quality_service.py        Q1 blocker → 下游 gate skipped
```

