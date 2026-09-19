---
name: novelforge-v4.0.1.canon.validate-canon-integrity
description: 校验 Canon 图与来源引用的一致性，得到 findings 与 promotion conflicts（只读）。
---

# validate-canon-integrity

- **Skill ID**: `novelforge-v4.0.1.canon.validate-canon-integrity`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `canon`
- **Product owner**: `src/novelforge/story_engine/canon/graph.py::CanonGraphValidator` +
  `validator.py::SourceReferenceValidator`

## Purpose

回答"Canon 自身是否自洽"：时序 / 因果是否成立，声明的事实是否真有来源支撑，
planned → occurred 的升级是否会撞车。

## Use when

- 改动前评估 Canon 健康度。
- Q2/Q3 质量问题需要 Canon 侧证据。

## Do not use when

- 想"修复" findings → Canon 属受保护边界，需要作者决定。

## Preconditions

```text
canon db 存在
```

## Required inputs

| 输入 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- |
| `novel_id` | 否 | `novel_project` | 目标作品 |

## Authoritative interfaces

```text
UI           N/A
REST         GET /api/story-builder/canon/validate?novel_id=
Application  CanonGraphValidator(graph).run() + SourceReferenceValidator(repository)
MCP          N/A
```

## Procedure

```text
1 GET /canon/validate?novel_id=<id>
2 读 ok（= 无 findings 且无 promotion conflicts）
3 读 findings[]（图级问题：时序 / 因果 / 依赖）
4 读 promotion_conflicts[]（planned → occurred 的冲突来源）
5 读 schema（Canon schema 摘要）
6 next：把相关证据交给 quality 语境（Q2 Canon / Q3 Continuity），由作者决定是否调整规划
```

## Expected result

```json
{"novel_id":"novel_alpha","ok":false,
 "findings":[{"code":"…","message":"…","nodes":["FACT_ab12"]}],
 "promotion_conflicts":[],"schema":{…}}
```

## Verification

```text
· ok == (len(findings)==0 and len(promotion_conflicts)==0)
· 只读：调用前后 canon db 与文件一致
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| ok=false 但没有 findings | 有 promotion conflicts | 检查两项 |
| 与 Q2 结论不一致 | 两者关注面不同（Canon 自洽 vs 蓝图↔Canon） | 以 Q2 issue evidence 为准解释蓝图侧问题 |

## Safety / invariants

```text
只读校验，不自动修改 Canon
发现真实冲突 → 交作者（需要作者决定，AGENTS.md §12.2）
```

## Side effects

无。

## Related skills

`inspect-canon-truth`、`validate-planning-against-canon`、
`novelforge-v4.0.1.quality.list-quality-issues`

## Source references

```text
src/novelforge/story_engine/canon/graph.py、validator.py
src/novelforge/api/canon_routes.py::validate_canon
tests/test_source_reference_validator.py
```
