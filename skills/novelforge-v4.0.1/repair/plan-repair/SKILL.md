---
name: novelforge-v4.0.1.repair.plan-repair
description: 为指定的质量 issue 生成修复计划（dry-run，0 mutation），明确目标节点、允许改动与必须保持的字段。
---

# plan-repair

- **Skill ID**: `novelforge-v4.0.1.repair.plan-repair`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `repair`
- **Product owner**: `src/novelforge/quality/repair/planner.py` +
  `src/novelforge/application/services/editor.py::EditorService.plan_repair`

## Purpose

在改动任何东西之前先看清：要改哪些节点、允许改哪些字段、必须保持哪些字段、影响范围多大。

## Use when

- 拿到一批 open issue，准备修复。
- 需要向作者解释"自动修复会动什么"。

## Do not use when

- 已经知道计划、就是要执行 → `apply-repair`（但仍建议先 plan）。

## Preconditions

```text
存在 open issue（list-quality-issues）；issue.code 在 registry 内
```

## Required inputs

| 输入 | 必填 | 说明 |
| --- | --- | --- |
| `novel_id` | 是 | 目标作品 |
| `issue_ids` | 是（或给 node_id） | 待修 issue |
| `dry_run` | — | REST 默认 true（本 skill 就是 dry run） |

## Authoritative interfaces

```text
UI           「检查」→ 修复预览
REST         POST /api/story-builder/studio/quality/repair {"novel_id","issue_ids","dry_run":true}
Application  EditorService.plan_repair(issue_ids=…, dry_run=True) / ReviewService.plan_repair
MCP          tool plan_repair（默认 dry-run）
```

## Procedure

```text
1 取 issue_ids（list-quality-issues，status=open）
2 POST /studio/quality/repair {novel_id, issue_ids, dry_run:true}
3 读 preview.{status, issues, target_nodes, allowed_fields, preserve_fields,
  verification_gates, estimated_model_calls, steps[]}
4 检查 preserve_fields 是否覆盖了不希望被改动的内容（作者可见身份 / 结构字段）
5 若 preview.status 表示冲突（无法安全修）→ 不要执行，转作者决定
6 next：apply-repair（同一 issue_ids + idempotency_key）
```

## Expected result

```json
{"status":"planned","dry_run":true,"issue_ids":["qi_7f…"],
 "preview":{"target_nodes":["sc_003_2"],"allowed_fields":["conflict","turn","outcome"],
            "preserve_fields":["node_id","chapter_id","source_ids"],
            "verification_gates":["Q3","Q6"],"estimated_model_calls":1,
            "steps":[{"node_id":"sc_003_2","allow_change":["conflict","turn"],
                      "preserve":["node_id","chapter_id"]}]}}
```

## Verification

```text
· dry_run 下 0 mutation：Blueprint revision / Quality Store issue 状态不变
· allowed_fields 是该 code 注册的 allow_change 子集；preserve 非空
· target_nodes 都真实存在且属于本作品
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `REPAIR_NOT_ALLOWED` | 该 code repairable=false | 需作者决定（例如结构非法） |
| preview 为空 | issue_ids 不存在 / 已 resolved | 重新列 issue |
| 目标节点跨作品 | novel_id 不一致 | 统一 novel_id |

## Safety / invariants

```text
plan 是 0 mutation（不含模型调用结果的写入）
不为了"能修"扩大 allow_change
issue → plan 的对应关系必须保留（不批量塞入无关 issue）
```

## Side effects

无（dry run）。

## Related skills

`apply-repair`、`verify-repair`、`understand-repair-contract`、
`novelforge-v4.0.1.quality.list-quality-issues`

## Source references

```text
src/novelforge/quality/repair/planner.py、blast_radius.py
src/novelforge/application/services/editor.py::plan_repair
src/novelforge/api/studio_routes.py::quality_repair（dry_run 分支）
tests/quality/repair/test_planner.py
docs/v4/V4_REPAIR_CONTRACT.md §4–§5
```
