# ADR-003 — Canonical Writer Store

```
Status   : Proposed（含作者待决项）
Date     : 2026-09-17
Context  : V4-00 Architecture
Related  : V4_MIGRATION_PLAN.md §4.1；V4_ARCHITECTURE_RISKS.md R-15；ADR-006
```

## Context

问「正文存在哪里」，V3 的答案是：**没有一个有 owner 的正文**。

```text
novel/authoring/story_engine/writer/<novel_id>/drafts/*.json    preview 草稿（无 revision）
workspace/wasteland_001_exports/writer_v1/<novel>/drafts/       legacy 只读
novel/final/chapter_XXXX_final.md                               69 个 tracked 正文文件（无 owner）
novel/source_text/                                              空目录
```

现有的 `WriterDraftService` 只有 `create_draft` / `list_drafts` / `get_draft` / `sync_facts`，
**没有 update**。也就是说 V3 事实上无法「写作」，只能生成 preview 草稿并导出。

## Decision

建立唯一 canonical writer store，内容为 append-only `ChapterRevision`：

```text
novel/authoring/<novel_id>/writer/<chapter_id>/r%06d.json
fields : chapter_id, revision, text, status(proposed|accepted|published),
         source_ids, author_accepted_at, model_usage_ref, parent_revision
```

规则：

1. 写入与读取共用同一 repository（沿用 V3 已做到的「单一常量」做法，并进一步收敛到 persistence）。
2. **append-only**：任何修改（人工或 AI）都产生新 revision，不覆盖旧 revision。
3. AI 产出默认 `status = proposed`；作者 accept 后才是 canonical。
4. legacy writer_v1 保持只读；旧 drafts 以只读 revision 视图呈现，不迁移、不重写、不重复计数。

## Consequences

正面：可回答「改了什么 / 谁改的 / 基于哪个 revision」；AI 无法静默覆盖作者文本。

代价：存储条目增长（需要保留策略，例如按 revision 数或时间归档，但不能删除 accepted 历史）。

## Open question（作者决定）

```text
novel/final/**（69 个 tracked 正文文件）与 V4 canonical writer store 的关系：
  (a) 导入为对应章节的 revision 0（成为作品正文历史的一部分）
  (b) 保持只读参考，不进入 revision 历史
  (c) 完全排除在 V4 之外
```

在作者裁定前，V4-06 **不得**自动导入或改写这些文件（见 `V4_MIGRATION_PLAN.md` BLOCKER-01）。

## Evidence

```text
src/novelforge/story_builder/writer_integration.py  WRITER_STORE_DIR / LEGACY_WRITER_STORE_DIR / WriterDraftService
src/novelforge/story_engine/historical_ir.py:527   读取 novel/final/chapter_XXXX_final.md（另一部手稿）
src/novelforge/story_engine/historical_ir.py:1822  _has_wasteland_entities() 关键词启发式防串稿
git ls-files novel/final                           69 个 tracked 文件
```

