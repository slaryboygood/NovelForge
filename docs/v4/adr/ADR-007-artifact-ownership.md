# ADR-007 — Artifact Ownership

```
Status   : Proposed（含作者/产品待决项）
Date     : 2026-09-17
Context  : V4-00 Architecture
Related  : V4_EXPORT_SPEC.md §6；V4_ARCHITECTURE_RISKS.md R-11/R-16
```

## Context

V3 的产品代码里存在**按作品写死的路径**，且不存在统一的 `project_id` 概念：

```text
story_builder/export_package.py    RECON_DIR / PLANNING_INDEX / "canon/wasteland_001.sqlite"
story_builder/writer_integration.py CANON_DB = "…/canon/wasteland_001.sqlite"
story_builder/inspector.py          CANON_DB = "…/canon/wasteland_001.sqlite"
story_engine/historical_ir.py       HISTORY_DIR = "workspace/wasteland_001_exports/historical_chapter_ir_v1"
```

后果已经在 V3 验收中被记录为缺陷 NR-002：任意作品导出都会带 WASTELAND 的 spine / planning / canon 分区。
更严重的是 `novel/final/*.md`（另一部手稿）只能靠关键词启发式
（`historical_ir._has_wasteland_entities()`）排除。

命名上还存在 `project_id`（sessions / blueprints）与 `novel_id`（profile / canon / writer）双名同值。

## Decision

1. 所有 artifact 必须携带 `project_id` / `novel_id` / `revision` / `created_at` / `source_ids`。
2. 所有物理路径由 `persistence/paths.py` 生成，**禁止模块级单作品路径常量**。
3. 打开任何存储（含 Canon SQLite）必须按 `novel_id`；服务端校验请求 novel 与 artifact novel 一致。
4. 归属不明或跨作品的数据默认不可读/不可导出；只能在显式 `legacy` 命名空间中访问。
5. 移除关键词启发式归属判断，改为显式绑定。

## 作者决策更新（V4-01）

```text
novel/final/*.md        → DELETE（不迁移、不归档、不导入为 revision）
570 章 historical 数据   → DELETE（不导入、不做 fixture、不进 legacy/）
```

V4-01 起本 ADR 不再有「无 owner 手稿如何归属」的待决项：这两类资产被作者判定为**废弃**，
直接删除；对应代码路径必须同步移除，而不是保留为 fallback（见 `V4_DELETION_PLAN.md` §2.1）。

## Open question（产品决定，仍未定）

```text
project_id 与 novel_id 的最终关系：
  (a) project 为根，novel 为其下作品实体（支持一项目多作品）
  (b) 二者等价，保留一个名称（建议 novel_id，改动最小）
```

两种方案都会在 V4-01 建立兼容读取（同值映射），差别在于 MCP resource 树与导出包结构的最终形状。
V4-01 的**最低不变量**（无论最终选哪个方案）：

```text
任何 artifact / state / export / cache 不得通过全局硬编码路径
隐式混入其他作品或已删除的历史数据。
```

## Consequences

正面：导出可信；跨作品泄漏从「可能的 bug」变成「结构上不可能」。

代价：V4-01 需要遍历并参数化所有路径；V4-07 需要重构 export projection 的 section 来源。

## Evidence

```text
src/novelforge/story_builder/export_package.py:41-42,83   单作品路径
src/novelforge/story_builder/writer_integration.py:66     单作品 canon DB
src/novelforge/story_builder/inspector.py:29              单作品 canon DB
src/novelforge/story_engine/historical_ir.py:41           wasteland 历史目录
src/novelforge/story_builder/sessions.py:91               project_id 命名
docs/V3_FINAL_FREEZE.md                                   NR-002 记录
```
