# ADR-003 — Canonical Writer Store

```
Status   : Superseded by ADR-011（2026-09-17，V4-01 作者决策）
Date     : 2026-09-17（V4-00 原文）
Context  : V4-00 Architecture
Related  : ADR-011（Story Blueprint Is The Primary Creative Artifact）
```

> ## ⚠️ SUPERSEDED — 不得据此实施
>
> 作者在 V4-01 明确：**V4 的核心创作产物是 Story Blueprint，不是小说正文**。
>
> 本 ADR 以下内容不再作为 V4 方向：
>
> ```text
> ✗ canonical prose writer store（正文 ChapterRevision 链）
> ✗ novel/final/** 导入为 revision 0
> ✗ 以「可编辑正文 + AI 改写正文」为中心的 Writer
> ```
>
> 取而代之（ADR-011）：
>
> ```text
> StoryBlueprint = canonical creative artifact
> Writer        → Blueprint Editor / Story Studio
> novel/final/** → DELETE（不迁移 / 不归档 / 不导入）
> ```
>
> 仍然有效、并被 ADR-011 继承的推论：
>
> ```text
> · 唯一写入点 + append-only revision（不覆盖）
> · AI 产出默认 status = proposed，作者 accept 后才成为 canonical
> · legacy 旧存储只读，不迁移、不重写、不重复计数
> ```
>
> 以下为原文，仅作 V4-00 决策记录。

## Context（原文）

问「正文存在哪里」，V3 的答案是：**没有一个有 owner 的正文**。

```text
novel/authoring/story_engine/writer/<novel_id>/drafts/*.json    preview 草稿（无 revision）
workspace/wasteland_001_exports/writer_v1/<novel>/drafts/       legacy 只读
novel/final/chapter_XXXX_final.md                               69 个 tracked 正文文件（无 owner）
novel/source_text/                                              空目录
```

现有的 `WriterDraftService` 只有 `create_draft` / `list_drafts` / `get_draft` / `sync_facts`，
**没有 update**。也就是说 V3 事实上无法「写作」，只能生成 preview 草稿并导出。

## Decision（原文 / 已作废）

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

## Open question（原文；V4-01 已由作者裁定 → 见顶部 SUPERSEDED 说明）

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
