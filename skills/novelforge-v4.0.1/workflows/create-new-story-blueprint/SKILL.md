---
name: novelforge-v4.0.1.workflows.create-new-story-blueprint
description: 端到端流程：从零开始把一本书写成可接受的 Story Blueprint（前提 → 世界/人物 → 故事/场景 → 检查 → 接受）。
---

# create-new-story-blueprint

- **Skill ID**: `novelforge-v4.0.1.workflows.create-new-story-blueprint`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `workflows`（组合层）
- **Product owner**: 无（每步的 owner 见下）

## Purpose

把"我要写一本新书"变成一条可执行、每步可验证的路径。

## Use when

- 全新作品，从 0 到 1。
- 需要给作者展示完整产品能力范围。

## Do not use when

- 已有作品只需要局部修改 → 直接用对应 atomic skill。
- 需要正文写作 → V4 Core 不做（Non-goal）。

## Preconditions

```text
· Story Studio 可用（或 REST 可用）
· 若要走生成步骤：provider 已启用（否则会得到 GENERATION_UNAVAILABLE，属预期）
· 作品 id 已决定（自觉命名规范，不要用中文标题当 id）
```

## Required inputs

| 输入 | 必填 | 说明 |
| --- | --- | --- |
| `novel_id` | 是 | 新作品 id |
| `title` / `genre` | 建议 | 作品档案 |
| `instruction`（各生成步骤） | 否 | 作者方向 |
| `idempotency_key` | 建议 | 每个 mutation 步骤都带上 |

## Authoritative interfaces

```text
见各步骤所指 skill（UI / REST / Application / MCP 各自可用性以该 skill 为准）
```

## Procedure（只引用 skill ID）

```text
Step 1  novelforge-v4.0.1.project.create-novel            → 建立作品
Step 2  novelforge-v4.0.1.studio.inspect-overview         → 确认起点（应为空态/极少节点）
Step 3  novelforge-v4.0.1.generation.generate-premise     → 前提
Step 4  novelforge-v4.0.1.generation.generate-theme       → 主题
Step 5  novelforge-v4.0.1.generation.generate-world       → 世界
Step 6  novelforge-v4.0.1.generation.generate-character   → 人物（可多个，注意 index）
Step 7  novelforge-v4.0.1.generation.generate-character-arc（每个主要人物一次）
Step 8  novelforge-v4.0.1.generation.generate-story-arc   → 主线
Step 9  novelforge-v4.0.1.generation.generate-structural-unit（可多个）
Step 10 novelforge-v4.0.1.generation.generate-chapter-plan（按单元）
Step 11 novelforge-v4.0.1.generation.generate-scene-plan  → 场景卡
Step 12 novelforge-v4.0.1.quality.evaluate-blueprint      → Q0–Q9
Step 13 如有 issue：novelforge-v4.0.1.workflows.review-and-repair-blueprint
Step 14 作者决定：novelforge-v4.0.1.editor.accept-revision（逐节点）
Step 15 需要交付：novelforge-v4.0.1.workflows.prepare-final-delivery
```

## Expected result

一本书拥有：premise / theme / world / character(+arc) / story_arc / unit / chapter / scene
节点，质量结论可解释，作者已接受的节点可交付。

## Verification

```text
· 每步都用该 skill 自己的 Verification 检查（不要只看 workflow 是否跑完）
· inspect-overview.blueprint.node_count 与 by_type 符合预期结构
· 默认不自动接受：accept 步骤必须有作者决定
· GAP-002 提醒：setup / payoff / causal_link 当前没有对外入口，Q5 相关 issue 属预期
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| Step 3 起全部 422 | provider 未启用 | `configure-llm-provider` 或接受离线失败 |
| 角色不是"多个人" | 没给 index | 重新生成时显式给 index |
| 场景挂在错误的章 | parent_id 传错 | 用 inspect-blueprint 确认 chapter id |

## Safety / invariants

```text
所有生成结果都是 proposal；accept 是作者决定
不写 Canon / StoryState（规划 ≠ 已发生）
workflow 不复制 atomic 细节；要改行为改 atomic skill 或产品代码（不是这里）
```

## Side effects

与各步骤相同（逐步累积 Blueprint revision；可能产生模型调用）。

## Related skills

`review-and-repair-blueprint`、`prepare-final-delivery`

## Source references

```text
skills/novelforge-v4.0.1/{project,generation,quality,editor,delivery}/*
README.md（V4 核心能力与 Non-goals）
docs/v4/V4_04_GENERATION_INVENTORY.md
```
