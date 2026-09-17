# ADR-021 — Editor Mutations Are Append-Only Revisions

```
Status    : Accepted（V4-06 实施完成）
Date      : 2026-09-18
Context   : V4-06 Blueprint Editor & Revision Workflow
Related   : ADR-006（revision model）；ADR-016（blueprint node graph）；
            ADR-019（repair is minimal-scope and revisioned）；
            ADR-023（restore creates a new revision）；V4_EDITOR_CONTRACT.md §3–§9
```

## Context

V4-06 第一次让作者**直接改** Blueprint。最省事的实现是就地修改节点 JSON：

```text
作者改 hook → 覆盖 ch_001.json
```

这与项目已经建立的三条边界冲突：`ADR-006`（写操作携带 expected_revision）、
`ADR-019`（V4-05 修复必须产生新 revision）、`AGENTS.md §12`（AI/工具修改绝不静默覆盖作者内容）。

## Decision

1. **所有 editor mutation 都是 append-only 新 revision**：`patch` / `patch_batch` /
   `rewrite` / `move` / `restore` / `undo` / `accept` 一律 `BlueprintRepository.save_revision`，
   `revision = current + 1`，`parent_revision = current`。
2. **写操作必须携带 `expected_revision`**；不匹配 → `EditorConflictError`
   （不覆盖、不自动 merge；conflict 返回 `expected_revision` / `actual_revision` /
   `node_id` 以及 current-vs-base 的结构化 diff）。
3. **新 revision 默认 `status=proposed`、`quality_status=unevaluated`**：
   编辑后不得沿用旧 revision 的质量结论。
4. **`idempotency_key` 重放不产生第二个 revision**（同一 key 命中已有 operation 直接返回原结果）。
5. **Editor 不拥有 canonical truth**：内容与 revision 序号只在 `BlueprintRepository`；
   editor 只额外保存 operation / review metadata（ADR-020 的同源原则）。

## Consequences

正面：

* 作者永远可以回到任意历史 revision，且任何改动都能解释来源；
* 与 V4-05 repair 语义一致（同一套 append-only + expected_revision + preserve）；
* 冲突成为显式事件，而不是静默数据丢失。

代价：

* 状态流转（accept）也产生 revision（payload 相同、status 变化），
  revision 数量比"就地改状态"多；
* 批量修改无法真正回滚已提交部分 → 必须显式报告 partial（§38）。

## Alternatives considered

| 方案 | 为什么不选 |
| --- | --- |
| 就地覆盖节点文件 | 违反 ADR-006 / ADR-019 / AGENTS.md §12；丢失作者已接受内容 |
| 只在 editor 侧存 diff、不写 Blueprint revision | 会出现两套 truth；导出 / MCP / UI 消费不一致 |
| 自动 merge 两侧创意字段 | 创意字段的语义合并必须由人确认（§45） |

## Evidence

```text
src/novelforge/editor/service.py             patch / move / restore 全部 save_revision
src/novelforge/editor/patch.py               build_edited_node（proposed + unevaluated）
src/novelforge/editor/service.py             _save → RevisionConflict → EditorConflictError
tests/editor/test_manual_edit.py             新 revision + 旧 revision 可读
tests/editor/test_concurrency.py             冲突不覆盖、无自动 merge
tests/editor/test_restore.py                 restore 产生新 revision
tests/editor/test_idempotency.py             重放不产生第二个 revision
```

