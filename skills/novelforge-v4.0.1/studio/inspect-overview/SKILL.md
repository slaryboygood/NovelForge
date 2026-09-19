---
name: novelforge-v4.0.1.studio.inspect-overview
description: 读取 Story Studio 总览（节点计数 / 质量状态 / setup-payoff / 交付 / 下一步），判断这本书现在做到哪里。
---

# inspect-overview

- **Skill ID**: `novelforge-v4.0.1.studio.inspect-overview`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `studio`
- **Product owner**: `src/novelforge/api/studio_routes.py::overview`（消费 application services）

## Purpose

一次调用拿到「这本书现在做到哪里 + 下一步建议」，作为 Agent 计划的第一条只读证据。

## Use when

- 开始任何多步工作之前（先看全貌）。
- 需要判断是先做生成、先修质量，还是先交付。

## Do not use when

- 需要逐节点细节 → `inspect-blueprint` / `inspect-node`。
- 需要 issue 细节 → `list-quality-issues`。

## Preconditions

```text
novel_id 已确认（inspect-novels）；只读
```

## Required inputs

| 输入 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- |
| `novel_id` | 是 | — | 目标作品 |
| `mode` | 否 | `current` | 选择模式（`accepted` / `current` / `explicit_revisions` 语义来自 Delivery） |

## Authoritative interfaces

```text
UI           「总览」（Overview.tsx）
REST         GET /api/story-builder/studio/overview?novel_id=&mode=
Application  ExportService.blueprint_view + ReviewService.stats/latest_report +
             JourneyService.next_action + ExportService.delivery/delivery_snapshots
MCP          resource novelforge://novels/{novel_id}（摘要）与 .../blueprint（节点级）
```

## Procedure

```text
1 call GET /studio/overview?novel_id=<id>&mode=current
2 读 blueprint.{node_count, by_type, by_status, accepted, proposed, digest}
3 读 quality.{status, issues, gates[], open_blockers}
4 读 setup.counts / payoff.counts / delivery.{snapshots, last}
5 读 next_action.{title, reason, target_view, deep_link} —— 这是后端给的下一步，不要自己另算
6 next：按 next_action.target_view 选择对应 skill（generation / repair / delivery）
```

## Expected result

```json
{"novel_id":"novel_alpha","title":"…",
 "blueprint":{"node_count":18,"by_type":{"chapter":3,"scene":7},"accepted":5,"proposed":13},
 "quality":{"status":"failed","issues":6,"open_blockers":1},
 "setup":{"counts":{"open":2,"paid":1}},"delivery":{"snapshots":1},
 "next_action":{"title":"…","target_view":"quality"},"read_only":true}
```

## Verification

```text
· novel_id 与请求一致；read_only == true
· digest 与 inspect-blueprint（同 mode）返回的 digest 一致
· 计数与 by_type 求和一致（node_count == sum(by_type.values())）
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 全为 0 且 by_type 空 | 这本书还没生成蓝图 | `generate-premise` |
| quality.status = `unevaluated` | 还没跑质量 | `evaluate-blueprint` |
| 400 `STUDIO_*` | novel_id 过短（<3）或不存在 | `inspect-novels` 确认 |

## Safety / invariants

```text
只读：0 mutation、0 model call
不把 next_action 当命令自动执行 —— 它只是后端建议（protected action 仍需作者批准）
```

## Side effects

无。

## Related skills

`inspect-blueprint`、`inspect-quality-report`、`list-delivery-snapshots`、
`novelforge-v4.0.1.workflows.create-new-story-blueprint`

## Source references

```text
src/novelforge/api/studio_routes.py
ui/src/studio/workspaces/Overview.tsx
tests/studio/test_studio_api.py
docs/v4/V4_UI_CONTRACT.md §4（UI_STATUS_MAP）
```
