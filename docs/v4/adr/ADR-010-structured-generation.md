# ADR-010 — Structured Generation over Existing Models

```
Status   : Proposed
Date     : 2026-09-17
Context  : V4-00 Architecture
Related  : V4_LLM_CONTRACT.md §5；V4_ARCHITECTURE.md CHALLENGE-07
```

## Context

V3 的创作内容由规则与模板产出，而且是在**自由文本层**拼装：

```text
settings_gen.content_pack_draft()   固定骨架（起点场所 / act_ask / ev_first_pressure）
outline_forge.NARRATIVE_BEATS       固定 beat 表
outline_forge.ChapterTitleLedger    f"{base}（第 {count} 次）" 兜底
journey.JourneyRuntime.scene()      rev1 / rev2 固定场景文本
```

同时 V3 已经拥有一批成熟的结构化契约与严格 gate：

```text
ChapterSemanticIR  + chapter_ir/schemas.py + validator.py + evidence.py
StoryPlanningIR    + planning/schemas.py + validator.py
ContentPack        + settings_check.validate_pack_draft
OutlinePackage     + outline_forge 标题与来源门禁
```

如果 V4 用 LLM 生成新的一套 schema，就会与这些 canonical model 冲突。

## Decision

结构化生成**必须指向既有模型**；`generation/*` 只负责「调用 gateway → 产出既有模型对象」，
不新增领域模型：

```text
model text → JSON → strict pydantic → domain validator → proposal
```

失败分类：

```text
SCHEMA 失败 → 重试（计入 attempts）
DOMAIN 失败 → 不重试，进入 Quality / Repair
```

首个目标：NF-003（章节标题语义重复 + 字段标签进入正文）。

## Consequences

正面：验收标准变成「能否通过既有 validator」，而不是「新 schema 是否好看」；
生成质量的改进可以被既有测试网捕获。

代价：LLM 输出必须适配既有模型（字段映射工作），初期 prompt 设计难度略高。

## Alternatives considered

| 方案 | 为什么不选 |
| --- | --- |
| 为 LLM 单独定义一批新模型 | 与 canonical model 冲突（`AGENTS.md` §5） |
| 让 LLM 输出自由文本再用正则解析 | 脆弱、不可校验 —— 正是 V3 模板化问题的另一面 |
| 保留模板生成，仅让 LLM 润色文案 | 无法解决「语义重复 / 模板化」根因（NF-003） |

## Evidence

```text
src/novelforge/story_engine/chapter_ir/schemas.py    "planner / legacy migration 输出都必须过这一层"
src/novelforge/story_engine/canon/gate.py            "Planner / LLM 输出的严格 Schema Gate"
src/novelforge/story_engine/spec/llm.py              strict schema + 最多 3 次重试 + 作者确认（既有先例）
src/novelforge/story_engine/outline_forge.py:62      NARRATIVE_BEATS（待替换）
src/novelforge/story_engine/outline_forge.py:120     f"{base}（第 {count} 次）"（NF-003 根因）
```

