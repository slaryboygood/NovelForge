---
name: novelforge-v4.0.1.quality.inspect-quality-report
description: 读取最新质量报告与 gate 行，判断这本作品当前是 passed / failed / blocked / unevaluated。
---

# inspect-quality-report

- **Skill ID**: `novelforge-v4.0.1.quality.inspect-quality-report`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `quality`
- **Product owner**: `src/novelforge/application/services/review.py::ReviewService.latest_report/stats`

## Purpose

给出"这本书现在能不能继续往下走"的只读答案，以及每个 gate 的结论与阻塞情况。

## Use when

- 交付前确认 gate 状态。
- 判断是否还有未评估的必需 gate。

## Do not use when

- 需要 issue 明细 → `list-quality-issues`。

## Preconditions

```text
至少评估过一次（否则 status=unevaluated）
```

## Required inputs

| 输入 | 必填 | 说明 |
| --- | --- | --- |
| `novel_id` | 是 | 目标作品 |
| `gate` | 否 | 只看某个 gate（Q0–Q9） |
| `status` | 否 | 只看某状态的 issue |

## Authoritative interfaces

```text
UI           「检查」页 gate 列表
REST         GET /api/story-builder/studio/quality?novel_id=&gate=&status=
Application  ReviewService.latest_report() / stats() / registered_gates()
MCP          resources novelforge://novels/{novel_id}/quality
```

## Procedure

```text
1 GET /studio/quality?novel_id=<id>
2 读 status（报告级）与 summary（open_issues / open_blockers 等）
3 读 gates[]：每个 gate 的 status / issues / blockers / evaluator_ids / duration_ms
4 标记 gate.status == "unevaluated" 的必需 gate（需要在交付前评估）
5 next：有 blocker → plan-repair；全部满足 → accept / promote 或 delivery
```

## Expected result

```json
{"novel_id":"novel_alpha","status":"failed",
 "gates":[{"gate":"Q0","status":"passed","issues":0,"blockers":0},
          {"gate":"Q9","status":"failed","issues":3,"blockers":1}],
 "summary":{"open_issues":6,"open_blockers":1},"policy":{…}}
```

## Verification

```text
· gates 覆盖 registered_gates（Q0–Q9 全集），缺评估的显示 unevaluated 而不是省略
· summary.open_blockers == 各 gate blockers 里有 blocker 的计数口径一致
· report 与 issue 列表一致（同一份 Quality Store）
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 全为 unevaluated | 还没跑过评估 | `evaluate-blueprint` |
| 报告与节点不一致 | 评估后节点被改过（revision 变新） | 重新评估 |
| gate 显示 skipped | policy 关闭 / 无适用节点 | 检查 policy |

## Safety / invariants

```text
只读；UI 不重算 gate 结论（ADR-033）
quality passed ≠ accepted（ADR-022）
```

## Side effects

无。

## Related skills

`evaluate-blueprint`、`list-quality-issues`、
`novelforge-v4.0.1.delivery.validate-delivery`

## Source references

```text
src/novelforge/api/studio_routes.py::quality、_gate_rows
src/novelforge/application/services/review.py
ui/src/studio/workspaces/Quality.tsx
tests/studio/test_studio_api.py
```
