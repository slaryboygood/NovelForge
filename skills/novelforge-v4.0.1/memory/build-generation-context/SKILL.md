---
name: novelforge-v4.0.1.memory.build-generation-context
description: 用 ContextBuilder 组装一次生成要用的上下文包（blocks + digest），确认上下文选择而不是拼一个巨大 prompt。
---

# build-generation-context

- **Skill ID**: `novelforge-v4.0.1.memory.build-generation-context`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `memory`
- **Product owner**: `src/novelforge/memory/context/builder.py::ContextBuilder`

## Purpose

上下文选择只有一个 owner：ContextBuilder。本 skill 说明如何查看 / 复现一次生成实际选中的
上下文，以及 digest 如何成为生成 evidence。

## Use when

- 需要解释生成质量与上下文的关系。
- Agent 在计划里需要先确认"这本书现在有哪些可用上下文"。

## Do not use when

- 想绕过 ContextBuilder 自己拼 prompt 给模型 → **禁止**（V4-LLM contract §3.1）。

## Preconditions

```text
novel_id 已知；memory 与 ContextBuilder 可用（build_default_service）
```

## Required inputs

| 输入 | 必填 | 说明 |
| --- | --- | --- |
| `novel_id` | 是 | 目标作品 |
| `operation` | 否 | 例如 `chapter` / `scene`（供 policy 判断） |
| `revision` | 否 | 目标 revision（影响上下文新鲜度） |

## Authoritative interfaces

```text
UI           N/A（generation 内部使用）
REST         N/A
Application  ContextBuilder(memory, preferences=…).build(ContextRequest(...))
MCP          N/A
```

## Procedure

```text
1 from novelforge.memory import build_default_service, ContextBuilder, ContextRequest
2 memory = build_default_service(novel_id, project_root)
3 builder = ContextBuilder(memory, preferences=getattr(memory, "preferences", None))
4 bundle = builder.build(ContextRequest(novel_id=novel_id, operation="scene", revision=…))
5 读 bundle.order（blocks 顺序）、每块 kind（required / recent / relevant / preference）、
  bundle.digest、bundle.budget
6 与生成结果里的 evidence.context_digest 对比：一致才说明用了同一份上下文
```

## Expected result

结构化 `ContextBundle`：blocks + items + digest + budget 报告（**不是** 一个巨大字符串）。

## Verification

```text
· bundle.digest 可复现（同输入同 digest）
· 生成结果的 node.context_digest / evidence.context_digest 与 bundle.digest 一致
· 超出预算时按 BLOCK_PRIORITY_ORDER 裁剪（required 优先保留）
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| digest 与生成结果不一致 | revision 已变化 | 重新读该 revision 后重算 |
| 关键设定缺失 | 预算太小 / 来源未索引 | 提高预算或 `rebuild` 记忆 |
| 出现别的作品内容 | novel_id 不一致 | 统一 novel_id（memory 拒绝跨作品） |

## Safety / invariants

```text
ContextBuilder 是唯一上下文选择系统（ADR-015）；不得出现第二套
上下文是派生视图：不改真相、不把未发生内容当事实
```

## Side effects

无（纯计算 + 只读检索）。

## Related skills

`inspect-derived-memory`、`understand-truth-precedence`、
`novelforge-v4.0.1.generation.generate-scene-plan`

## Source references

```text
src/novelforge/memory/context/builder.py、budget.py
src/novelforge/generation/service.py::_build_context
tests/memory/test_context_builder.py、tests/memory/test_budget.py
docs/v4/adr/ADR-015-context-builder-owns-model-context-selection.md
```
