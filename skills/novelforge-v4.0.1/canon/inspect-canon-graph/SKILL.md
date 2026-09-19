---
name: novelforge-v4.0.1.canon.inspect-canon-graph
description: 读取 Canon 依赖图摘要（节点 / 边 / 关系类型），用于判断某设定被哪些内容依赖。
---

# inspect-canon-graph

- **Skill ID**: `novelforge-v4.0.1.canon.inspect-canon-graph`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `canon`
- **Product owner**: `src/novelforge/story_engine/canon/graph.py::CanonGraph`

## Purpose

看清 Canon 内部的依赖关系（谁依赖谁、沿哪条 relation），为"改动影响面"提供证据。

## Use when

- 需要判断某条事实 / 事件的依赖范围。
- Q2 / Q3 问题排查的辅助证据。

## Do not use when

- 需要校验结构是否自洽 → `validate-canon-integrity`。

## Preconditions

```text
canon db 存在
```

## Required inputs

| 输入 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- |
| `novel_id` | 否 | `novel_project` | 目标作品 |
| `limit` | 否 | 100 | 节点 / 边返回上限（1..1000；计数是真实总数） |

## Authoritative interfaces

```text
UI           N/A
REST         GET /api/story-builder/canon/graph?novel_id=&limit=
Application  CanonGraph.from_repository(repository, novel_id)
MCP          N/A
```

## Procedure

```text
1 GET /canon/graph?novel_id=<id>&limit=200
2 读 node_count / edge_count（真实总数）与 nodes / edges（截断列表）
3 edges[].{from,to,relation} → 关系类型（例如依赖 / 因果 / 揭示）
4 定位目标 id，列出其出边 / 入边
5 next：需要一致性结论 → validate-canon-integrity
```

## Expected result

```json
{"novel_id":"novel_alpha","node_count":28,"edge_count":41,
 "nodes":["FACT_ab12","EVENT_c3d4"],
 "edges":[{"from":"EVENT_c3d4","to":"FACT_ab12","relation":"depends_on"}]}
```

## Verification

```text
· len(nodes) == min(node_count, limit)（截断语义明确）
· 图只包含该作品节点（无跨作品边）
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 节点/边为空 | 该书没有 Canon 关系 | 正常；不是错误 |
| 结果被截断看起来"少了" | limit 生效 | 用 node_count / edge_count 判断真实规模 |

## Safety / invariants

```text
只读；不重算 / 不写 Canon
图是证据，不是判据：结论必须结合 validate 与 issue evidence
```

## Side effects

无。

## Related skills

`inspect-canon-truth`、`validate-canon-integrity`

## Source references

```text
src/novelforge/story_engine/canon/graph.py
src/novelforge/api/canon_routes.py::graph_summary
tests/test_canon_graph.py
```
