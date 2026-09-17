# ADR-005 — Quality Contract

```
Status   : Proposed
Date     : 2026-09-17
Context  : V4-00 Architecture
Related  : V4_QUALITY_CONTRACT.md；V4_ARCHITECTURE_RISKS.md R-13/R-14
```

## Context

V3 已经有相当扎实的质量能力，但形态各异、彼此不相识：

```text
settings_check.CheckFinding            （content 可运行性）
planning.findings.GraphFinding         （规划图）
chapter_ir.verifier.Verdict            （语义验证）
canon.validator.SourceReferenceValidator（引用支持）
canon.prose / chapter_ir.evidence      （证据完整性）
outline_forge findings                 （标题质量）
v3_projection 导出就绪度 6 步          （交付前置）
```

结果是：UI 无法统一展示、导出无法统一校验、修复流程无法统一追踪。

## Decision

定义统一 Quality Contract（`QualityIssue` / `QualityEvidence` / `Scope` / `RepairContract` /
`QualityResult`）与 **Q0–Q9** 门禁编号，并通过 adapter 把既有实现注册到对应 Gate：

```text
deterministic 优先（identity / 引用 / 守恒 / DAG）
LLM-assisted 仅用于「语义是否相同 / 行为是否合理」
需要价值判断 → requires_author = true
```

**不重写既有 validator**（`AGENTS.md` §20：不得为通过测试削弱规则）。

## Consequences

正面：统一对象使 UI / MCP / Export 复用同一语义；每章可追溯「哪些门禁跑过、结论是什么」。

代价：需要一个 adapter 层（既有 findings → QualityIssue），并且要防止「Gate 编号」变成第二套逻辑。

## Alternatives considered

| 方案 | 为什么不选 |
| --- | --- |
| 只保留现有分散 validator，UI 各自处理 | 每个消费者都要理解 9 种 finding 形态 |
| 用 LLM 做统一评估 | 结构化 identity / 守恒 / DAG 判定交给 LLM 会引入不确定性（违反既有 deterministic 原则） |
| 新建一套质量模型完全替代旧实现 | 会让同一质量结论出现两个来源，且违反 §20 |

## Evidence

```text
src/novelforge/story_engine/canon/validator.py    注释：「第一层永远是 deterministic：用结构化 identity 判断」
src/novelforge/story_engine/chapter_ir/verifier.py §7 AGREE / DISAGREE / AMBIGUOUS 判定
src/novelforge/story_engine/settings_check.py      CheckFinding（code/severity/message/hint/target）
src/novelforge/story_builder/v3_projection.py      导出就绪度 6 步
docs/V3_FINAL_FREEZE.md                            NF-003（语义重复）作为 V4 首个质量目标
```

