---
name: novelforge-v4.0.1.canon.validate-planning-against-canon
description: 用 Canon 校验一批章节计划（chapter plan）：来源引用 / 声称事实 / 时间截点 / 语义重复候选。
---

# validate-planning-against-canon

- **Skill ID**: `novelforge-v4.0.1.canon.validate-planning-against-canon`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `canon`
- **Product owner**: `src/novelforge/story_engine/canon/gate.py::validate_chapter_plan` +
  `validator.py` + `semantic.py`

## Purpose

在写进任何 store 之前，检查"这份计划是否与已发生事实冲突"，并给出重复事件候选
（避免同一事件被表达两次）。

## Use when

- 外部流程 / 规划稿需要在纳入 Blueprint 前做 Canon 对照。
- 需要检查时间截点（`temporal_cutoff`）之后的信息泄漏。

## Do not use when

- 想直接改 Canon / 写事件 → 不允许。

## Preconditions

```text
canon db 存在；准备待校验的 chapters 列表（结构化计划，不是自由文本）
```

## Required inputs

| 输入 | 必填 | 说明 |
| --- | --- | --- |
| `novel_id` | 是（REST 必填） | 目标作品 |
| `chapters` | 是 | chapter plan 列表（含 canon_source_refs / canon_fact_ids / participants / goal / location） |
| `temporal_cutoff` | 否 | 只允许使用该时间点之前的事实 |

## Authoritative interfaces

```text
UI           N/A
REST         POST /api/story-builder/canon/validate-outline?novel_id=<id>
             body {"chapters":[…],"temporal_cutoff":123}
             （novel_id 是 **query 参数**，放在 body 里会 422 extra_forbidden）
Application  validate_chapter_plan + SourceReferenceValidator.validate_refs + LocalSemanticIndex
MCP          N/A
```

## Procedure

```text
1 准备 chapters（结构化 schema；schema 不合法的章节会得到 CHAPTER_SCHEMA_INVALID）
   每章至少需要：`chapter_uuid`（不是 chapter_id）+ ≥3 条互不相同的 `concrete_events`；
   其余（title / goal / location / participants / canon_source_refs / canon_fact_ids）可选。
2 POST /canon/validate-outline?novel_id=<id> {chapters, temporal_cutoff?}
3 读 ok 与 findings[]（来源引用缺失 / 时间截点越界 / 声称事实不被支持）
4 读 duplicate_candidates[]（语义相似的历史 / 计划事件候选）
5 有 conflict → 调整规划（不是改 Canon）；重复候选 → 用不同事件或显式合并
6 next：规划定稿后走 generation / editor 写 Blueprint
```

## Expected result

```json
{"novel_id":"novel_alpha","ok":false,
 "findings":[{"code":"…","chapter":"…","message":"…"}],
 "duplicate_candidates":[{"chapter":"…","candidates":[{"event_id":"EVENT_c3d4","score":0.83}]}]}
```

## Verification

```text
· ok == (len(findings) == 0)
· duplicate_candidates 只保留有候选的条目
· 只读：不写 canon、不写 Blueprint
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| CHAPTER_SCHEMA_INVALID | chapter plan 不符合 schema | 修正字段后重试 |
| 大量 temporal 越界 | 用了未来事实 | 调整计划或提高 temporal_cutoff（需作者决定） |
| 重复候选命中 | 事件表达重复 | 合并/改写计划，避免第二套真相 |

## Safety / invariants

```text
只读检查：不产生事实
计划 ≠ 事实：通过检查不代表内容已经发生
不确定是否同一事件时不要合并（AMBIGUOUS_DO_NOT_MERGE）
```

## Side effects

无。

## Related skills

`inspect-canon-truth`、`validate-canon-integrity`、
`novelforge-v4.0.1.generation.generate-chapter-plan`

## Source references

```text
src/novelforge/story_engine/canon/gate.py、semantic.py、validator.py
src/novelforge/api/canon_routes.py::validate_outline
tests/test_canon_outline_integration.py、tests/test_chapter_schema.py
```
