---
name: novelforge-v4.0.1.generation.generate-premise
description: 生成故事前提（premise）节点：核心冲突、主角目标、赌注、戏剧问题与故事承诺。
---

# generate-premise

- **Skill ID**: `novelforge-v4.0.1.generation.generate-premise`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `generation`
- **Product owner**: `src/novelforge/generation/tasks/premise.py::premise_spec`（contract `blueprint.premise.v1`）

## Purpose

把一本书的"要讲什么"变成结构化前提节点。它是整个 Blueprint 的根，其它节点都引用它。

## Use when

- 新作品的第一条内容。
- 前提变了，需要重做（用 `regenerate` 保留 id，不新增第二个 premise）。

## Do not use when

- 还没建立作品 → 先 `create-novel`。
- 只想改前提的某个字段 → `patch-node`（不要重新生成整节点）。

## Preconditions

```text
· 作品存在（inspect-novels）
· 至少一个 provider enabled；否则会得到 GENERATION_UNAVAILABLE(422)（不是缺陷）
· 若已有 premise：本调用会写入新 revision（append-only，不覆盖历史）
```

## Required inputs

| 输入 | 必填 | 说明 |
| --- | --- | --- |
| `novel_id` | 是 | 目标作品 |
| `task` / `node_type` | 是（REST） | `premise` |
| `instruction` | 否 | 作者方向（写入 `task_input.task`） |
| `idempotency_key` | 否 | 强烈建议：重试不产生第二个节点 |

## Authoritative interfaces

```text
UI           「创造」→ 生成前提
REST         POST /api/story-builder/studio/generate  {"novel_id","task":"premise","instruction"}
Application  BlueprintService.generate_task("premise", …) / BlueprintGenerationService.generate
MCP          tool generate_premise
```

## Procedure

```text
1 resolve novel_id（inspect-novels）
2 confirm provider enabled（否则先 configure-llm-provider）
3 POST /studio/generate {novel_id, task:"premise", instruction?, idempotency_key}
4 校验返回 ok=true、node.node_id == "premise"、revision ≥ 1、next_status == "proposed"
5 inspect-node premise（读 payload.premise / central_conflict / protagonist_goal / stakes /
  dramatic_question / story_promise / genre / tone / constraints）
6 next：generate-theme 或直接 patch-node 微调，然后 accept-revision
```

## Expected result

```json
{"ok":true,"operation":"premise","novel_id":"novel_alpha",
 "node":{"node_id":"premise","node_type":"premise","revision":1,"status":"proposed",
         "payload":{"premise":"…","central_conflict":"…","stakes":"…"}},
 "revision":1,"contract":"blueprint.premise.v1","model":"…","provider":"…","next_status":"proposed"}
```

## Verification

```text
· node_id == "premise"（单例）；inspect-blueprint?node_type=premise 恰好 1 条
· status == proposed（不会被自动接受）
· 重复调用同一 idempotency_key → 返回同一 revision（warnings 含 IDEMPOTENT_REPLAY）
· 跨作品请求 → GENERATION 报错（novel_id 不匹配时拒绝）
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 422 `GENERATION_UNAVAILABLE` | 没有 enabled provider（默认行为）或模型不可达 | 配置 provider；这是稳定错误码，不要绕过 |
| 409 / `check_expected_revision` 失败 | 传入过期 expected_revision | 重新读当前 revision |
| 生成结果泛化 | 模型输出模板化 | Q8 issue → `plan-repair` |

## Safety / invariants

```text
AI 产出是 proposal：不自动接受、不写 Canon / StoryState
dry_run 未实现（GAP-001）：调用即产生 revision
模型不得自造 id：node_id 由系统分配
```

## Side effects

写一个新 revision（`novel/authoring/**/blueprint/<novel_id>/`）+ 一次模型调用（若启用 provider）。

## Related skills

`generate-theme`、`generate-world`、`generate-story-arc`、
`novelforge-v4.0.1.editor.patch-node`、`novelforge-v4.0.1.editor.accept-revision`

## Source references

```text
src/novelforge/generation/tasks/premise.py
src/novelforge/generation/service.py（default_registry / DEFAULT_PIPELINE）
src/novelforge/interfaces/mcp/tools/generation.py
tests/generation/test_generation_service.py
```
