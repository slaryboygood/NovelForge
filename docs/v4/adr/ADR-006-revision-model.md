# ADR-006 — Revision Model

```
Status   : Proposed
Date     : 2026-09-17
Context  : V4-00 Architecture
Related  : V4_ARCHITECTURE.md §7；V4_ARCHITECTURE_RISKS.md R-09/R-17
```

## Context

V3 已经有多套「版本」机制，各自实现、语义不一：

```text
StoryState    v%06d.json + branch 文件
Blueprint     v*.json + 状态（DRAFT / CONFIRMED）
Outline       v*.json + version diff / restore / merge
Planning IR   不可变 revision + index
PhaseSnapshot write-once + digest manifest
WriterDraft   无 revision（仅 draft_id = 内容哈希）
```

Agent 接入后并发写会变常态，而当前写入没有 `expected_revision` 协议 —— 后写者无条件覆盖。

## Decision

统一定义 revision 语义（`core/revision.py`）：

```json
{
  "project_id": "…",
  "novel_id": "…",
  "revision": 42,
  "created_at": "…",
  "source_ids": ["story_state:runtime_x@12", "chapter_ir:ch_018@3"]
}
```

写入协议：

```text
request.expected_revision == current_revision  → 产生新 revision（append-only）
request.expected_revision != current_revision  → REVISION_CONFLICT（不覆盖、不自动合并）
```

迁移策略：不引入新的版本字段体系，而是**复用既有机制**（StoryState 的文件序号、Planning 的不可变
revision、Blueprint/Outline 的版本目录），统一其在 API 与 envelope 中的表达。

## Consequences

正面：并发写安全；Agent 重试安全（配合 idempotency_key）；历史可追溯。

代价：所有写端点需要新增 `expected_revision` 参数（兼容期可缺省为「不校验」并在响应中提示）。

## Alternatives considered

| 方案 | 为什么不选 |
| --- | --- |
| 最后写入胜出（现状） | 会静默覆盖作者内容 —— 与原则 1.8 冲突 |
| 引入数据库事务 / 乐观锁框架 | 当前是单进程文件存储；先统一语义比换引擎更划算（CHALLENGE-06） |
| 每类 artifact 各自实现 | 已经如此，正是当前问题 |

## Evidence

```text
src/novelforge/story_engine/storage.py             StoryState v%06d + 单进程锁
src/novelforge/story_builder/blueprints.py         Blueprint 版本目录
src/novelforge/story_builder/outlines.py           Outline 版本 + restore + merge
src/novelforge/story_engine/planning/repository.py 不可变 revision + index
src/novelforge/story_engine/phase_snapshot.py      write-once + digest
src/novelforge/story_builder/writer_integration.py WriterDraftService（无 revision）
```

