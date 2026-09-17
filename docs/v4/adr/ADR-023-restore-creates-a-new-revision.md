# ADR-023 — Restore Creates A New Revision

```
Status    : Accepted（V4-06 实施完成）
Date      : 2026-09-18
Context   : V4-06 Blueprint Editor & Revision Workflow
Related   : ADR-006（revision model）；ADR-021（append-only revisions）；
            V4_EDITOR_CONTRACT.md §8
```

## Context

"恢复旧版本"在普通编辑器里通常是**移动指针**：

```text
current → r2（r3 / r4 仍在磁盘上但不再可达）
```

在 Blueprint 里这样做有三个具体问题：

1. 与 append-only timeline 冲突：`list_revisions` / provenance / 审计会出现"被跳过的历史"；
2. 无法回答"谁在什么时候恢复了哪一版"（因为什么都没写）；
3. 与 `expected_revision` 语义冲突：指针回退会让并发写者以为自己基于最新版本。

项目已有先例：`story_engine/outline_revision.restore_version` 与
`planning.versioning.rollback` 都是"复制旧内容生成新版本"。

## Decision

1. **restore / undo 都产生新 revision**：

   ```text
   restore r2 → r7（payload = r2 的内容）
   provenance = {operation: restore, restored_from: 2, source_revision: 6}
   ```

2. `undo` = `restore(current.parent_revision)`（不是数据库级 rollback）。
3. **只恢复内容字段**：结构 identity（scene.chapter_id / character_arc.character_id /
   payoff.resolves_setup_ids …）不一致时拒绝（`EditorPreserveViolation`）；
   结构变化只能走 `move_node`。
4. 恢复后的 revision：`status=proposed`、`quality_status=unevaluated`
   （恢复不等于作者接受，也不等于质量重新通过）。

## Consequences

正面：

* revision timeline 永远 append-only，历史可枚举、可审计；
* 恢复行为本身可追溯（谁恢复、从哪一版、什么时候）；
* 与 ADR-021 的并发语义一致（写操作仍然基于 current + expected_revision）。

代价：

* revision 数量会随"来回恢复"增长（换来的是可审计性）；
* 需要显式区分"恢复内容"与"移动结构"（不接受两者混在一个操作里）。

## Alternatives considered

| 方案 | 为什么不选 |
| --- | --- |
| current 指针回退 | 破坏 append-only；无法审计；并发语义混乱 |
| 物理删除新版本 | 违反"历史不可改写" |
| 恢复时一并改变父节点 / sequence | 结构变化必须显式（§39），否则会静默移动创意图 |

## Evidence

```text
src/novelforge/editor/service.py        _restore：payload=source，structure=current
src/novelforge/editor/service.py        undo → restore(parent_revision)
src/novelforge/editor/service.py        _assert_structural_identity
tests/editor/test_restore.py            r1..r4 全在；r4 内容 == r1；restored_from=1
tests/editor/test_quality_integration.py  Golden workflow 的 restore 步骤
```

