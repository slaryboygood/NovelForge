---
name: novelforge-v4.0.1.quality.list-quality-issues
description: 列出质量 issue（含 severity / gate / scope / evidence / repairable），定位到具体节点与 revision。
---

# list-quality-issues

- **Skill ID**: `novelforge-v4.0.1.quality.list-quality-issues`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `quality`
- **Product owner**: `src/novelforge/application/services/review.py::ReviewService.list_issues/issues_for_node`

## Purpose

把"质量有问题"变成可执行的清单：哪些 issue、属于哪个 gate、证据是什么、能不能自动修。

## Use when

- 准备修复（`plan-repair` 需要 issue_ids）。
- 需要向作者解释某条意见的依据。

## Do not use when

- 只要 gate 级别结论 → `inspect-quality-report`。

## Preconditions

```text
存在至少一次质量评估
```

## Required inputs

| 输入 | 必填 | 说明 |
| --- | --- | --- |
| `novel_id` | 是 | 目标作品 |
| `gate` | 否 | 过滤（Q0–Q9） |
| `status` | 否 | `open` / `repairing` / `resolved` / `accepted_risk` / `ignored` |
| `node_id` | 否 | 单节点视角（`GET /editor/nodes/{id}/quality`） |

## Authoritative interfaces

```text
UI           「检查」issue 列表；节点抽屉质量问题
REST         GET /studio/quality（issues[]）；GET /editor/nodes/{node_id}/quality
Application  ReviewService.list_issues(gate, status) / issues_for_node(node_id)
MCP          resources .../quality/issues（分页）；.../quality
```

## Procedure

```text
1 GET /studio/quality?novel_id=<id>[&gate=Q6][&status=open]
2 对每条 issue 读 issue_id / code / gate / severity / status / reason
3 读 scope（node_ids / node_types / revision / kind）—— 这是修复范围依据
4 读 evidence[]（evidence_id / kind / explanation / node_ids / revision / excerpt / metric）
5 读 repairable：true 才能期望自动修复；false 需要作者决定
6 next：plan-repair（issue_ids = 选中的 open + repairable）
```

## Expected result

```json
[{"issue_id":"qi_7f…","code":"CONTINUITY_TIME_CONFLICT","gate":"Q3","severity":"major",
  "status":"open","scope":{"node_ids":["sc_003_2"],"revision":2,"kind":"nodes"},
  "evidence":[{"evidence_id":"ev_…","kind":"timeline","explanation":"…"}],
  "repairable":true}]
```

## Verification

```text
· 每条 issue 的 code 在 issue code registry 内，gate 与 code 的注册 gate 一致
· evidence 非空（"没有证据的 blocker"不合格）
· issue 的 revision 与节点当前 revision 的关系被记录（决定要不要重评）
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| issue 指向 revision 1，但节点已到 3 | 评估过期 | 重新评估后再修 |
| repairable=false | 该 code 属非自动修（例如 SCHEMA_INVALID / CIRCULAR_DEPENDENCY） | 需要作者决定或先改结构 |
| 拿不到 issue_id | 用了节点视图（只给摘要） | 用 /studio/quality 取 issue_id |

## Safety / invariants

```text
issue 是结论不是真相：不修改节点内容
不要为了"清空列表"把 issue 标记 ignored —— accepted_risk / ignored 需要作者决定
```

## Side effects

无。

## Related skills

`inspect-quality-report`、`understand-quality-gates`、
`novelforge-v4.0.1.repair.plan-repair`、`novelforge-v4.0.1.repair.apply-repair`

## Source references

```text
src/novelforge/quality/store.py、codes.py
src/novelforge/application/services/review.py
src/novelforge/interfaces/mcp/resources/quality.py
tests/quality/test_quality_contracts.py
```
