---
name: novelforge-v4.0.1.generation.generate-theme
description: 生成主题（theme）节点：主题陈述、反主题与母题。
---

# generate-theme

- **Skill ID**: `novelforge-v4.0.1.generation.generate-theme`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `generation`
- **Product owner**: `src/novelforge/generation/tasks/premise.py::theme_spec`（contract `blueprint.theme.v1`）

## Purpose

把 premise 的冲突上升到"这本书在讨论什么"，供后续 chapter / scene 的
`story_function` 对齐。

## Use when

- premise 已存在，需要主题层。
- 主题表述要改（重生成，保留 `theme` id）。

## Do not use when

- 还没有 premise → 先 `generate-premise`。

## Preconditions

```text
作品存在；provider enabled；已有 premise 时主题更稳定（可挂 premise 为父）
```

## Required inputs

| 输入 | 必填 | 说明 |
| --- | --- | --- |
| `novel_id` | 是 | 目标作品 |
| `task` / `node_type` | 是 | `theme` |
| `instruction` | 否 | 主题方向 |
| `idempotency_key` | 否 | 建议 |

## Authoritative interfaces

```text
UI           「创造」
REST         POST /studio/generate {"task":"theme"}
Application  BlueprintService.generate_task("theme", …)
MCP          tool generate_theme
```

## Procedure

```text
1 确认 premise 已存在（inspect-blueprint?node_type=premise）
2 POST /studio/generate {novel_id, task:"theme", instruction?}
3 校验 node.node_id == "theme"、status == proposed
4 读 payload.{theme, statement, counter_theme, motifs}
5 next：generate-world / generate-character
```

## Expected result

`theme` 单例节点 r1（或新 revision），状态 proposed。

## Verification

```text
· inspect-blueprint?node_type=theme 恰好 1 条
· statement 与 premise.central_conflict 语义一致（不矛盾）
· 未被自动接受（status == proposed）
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 422 `GENERATION_UNAVAILABLE` | 未配置 provider | `configure-llm-provider` |
| 主题与前提冲突 | 模型自由发挥 / 上下文不足 | `patch-node` 修正，或补齐 premise 后再重生成 |

## Safety / invariants

```text
proposal only；不写 Canon / StoryState；不自动接受
主题不能变成"事实声明"（DESIGN INTENT != CANON FACT）
```

## Side effects

新 revision + 一次模型调用（provider 启用时）。

## Related skills

`generate-premise`、`generate-world`、`novelforge-v4.0.1.editor.patch-node`

## Source references

```text
src/novelforge/generation/tasks/premise.py
src/novelforge/generation/service.py
tests/generation/test_generation_pipeline.py
```
