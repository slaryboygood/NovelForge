---
name: novelforge-v4.0.1.blueprint.understand-blueprint-model
description: 掌握 V4.0.1 Story Blueprint 的节点类型、父层级、状态机与 revision 语义，避免写出违反契约的调用。
---

# understand-blueprint-model

- **Skill ID**: `novelforge-v4.0.1.blueprint.understand-blueprint-model`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `blueprint`
- **Product owner**: `src/novelforge/blueprint/contracts.py`

## Purpose

在任何生成 / 编辑 / 修复之前建立正确的数据模型心智：哪些类型存在、谁能做谁的父节点、
id 怎么分配、状态与质量怎么区分。

## Use when

- 第一次接触这个仓库 / 这个版本。
- 需要判断一个操作是否合法（例如"能不能把 scene 挂在 unit 下"）。
- 需要解释为什么某个字段不能改。

## Do not use when

- 只是要读数据 → 直接 `inspect-blueprint` / `inspect-node`。

## Preconditions

```text
无（纯知识型 skill；结论全部来自代码 SSOT）
```

## Required inputs

```text
无
```

## Authoritative interfaces

```text
UI           N/A
REST         N/A
Application  novelforge.blueprint（PAYLOAD_MODELS / ALLOWED_PARENT_TYPES / NODE_ID_PREFIX）
MCP          N/A
```

## Procedure（速查顺序）

```text
1 类型：12 类（见 blueprint/README.md 的表）；PAYLOAD_MODELS 是 payload schema SSOT
2 父层级：ALLOWED_PARENT_TYPES；None 表示可以没有父节点；不在表里 = 必填父节点
3 id：NODE_ID_PREFIX（premise/theme/world/story_arc 单例；char_/arc_/unit_/ch_/sc_/cl_/
  setup_/payoff_ 由系统分配）；模型不得自造 id
4 状态：NodeStatus = proposed → draft → accepted → superseded
5 质量：quality_status 是 Quality Store 投影（unevaluated/passed/passed_with_issues/
  failed/blocked），与 status 独立
6 revision：每次写都 append；写操作带 expected_revision；冲突不覆盖
7 结构 identity：STRUCTURAL_IDENTITY_FIELDS 只能经 move_node / 系统分配改变
8 visible vs internal：INTERNAL_FIELDS（node_id / provenance / status …）不出现在交付正文
```

## Expected result

能正确回答：

```text
· 能不能生成 story_arc 的子节点 = unit？（能：structural_unit 允许 story_arc 父）
· scene 能不能没有父节点？（不能：scene 只允许 chapter 父，且必须声明 chapter_id）
· quality passed 是不是就 accepted？（不是，ADR-022）
· 用 patch 能不能改 parent_id？（不能，属结构 identity，需要 move / restore 契约）
```

## Verification

```text
· 交叉核对：src/novelforge/blueprint/contracts.py 的 ALLOWED_PARENT_TYPES / NODE_ID_PREFIX /
  NodeStatus / STRUCTURAL_IDENTITY_FIELDS
· 交叉核对：blueprint/validation.py 产出的 issue code（PARENT_TYPE_INVALID 等）
· 契约文档：docs/v4/V4_BLUEPRINT_CONTRACT.md §2–§4、§3.1–§3.2
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 生成时 task 需要 parent 却报错 | 该任务的 requires_parent=true | 先建父节点 |
| patch 报 `EDITOR_PRESERVE_VIOLATION` | 改了受保护 / 结构字段 | 改 payload 字段，结构关系走 move / restore |
| 质量 passed 但交付被拒 | 未 accepted | `accept-revision` |

## Safety / invariants

```text
以代码常量为准，不以聊天记忆或旧版本文档为准（CURRENT CONTRACT WINS）
不要为了"方便"发明新的节点类型或新的状态
```

## Side effects

无。

## Related skills

`inspect-blueprint`、`inspect-node`、
`novelforge-v4.0.1.generation.generate-premise`（生成侧口径）

## Source references

```text
src/novelforge/blueprint/contracts.py
src/novelforge/blueprint/validation.py
src/novelforge/blueprint/repository.py、lifecycle.py
docs/v4/V4_BLUEPRINT_CONTRACT.md
docs/v4/adr/ADR-016-story-blueprint-is-a-revisioned-node-graph.md
docs/v4/adr/ADR-017-generated-content-is-proposal-until-promoted.md
```
