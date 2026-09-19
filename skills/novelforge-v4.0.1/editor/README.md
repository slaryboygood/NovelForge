# Module: `editor` — 作者掌控的 Blueprint 编辑

```text
Module purpose     字段级 patch / AI 改写 / diff / accept / reject / restore（append-only）
Authoritative owner src/novelforge/editor/{patch,service,diff,history,impact,operations}.py
Owned skills       patch-node / rewrite-node / accept-revision / reject-revision /
                   restore-revision / diff-revisions
Truth ownership    写 Blueprint 新 revision；review 决定写在 Editor metadata（不改变 lifecycle enum）
Public interfaces  UI 节点抽屉；REST /editor/nodes/*；Application EditorService；
                   MCP tools patch_blueprint_node / rewrite_blueprint_node / accept_revision /
                   reject_revision / restore_revision / diff_revisions；resource .../review
Dependencies       blueprint（repository / validation）、generation（rewrite 契约）、quality（只读关联）
Forbidden          直接改 revision 落盘文件、绕过 expected_revision、把 review 状态塞进 payload
Related modules    quality / repair（发现问题 → 修）、delivery（只读 review metadata）
```

## 动作矩阵

| 动作 | 产生新 revision | 改 payload | 改 lifecycle status | 说明 |
| --- | --- | --- | --- | --- |
| `patch` | 是 | 是（白名单字段） | 否（新 revision = proposed） | 手工字段级修改 |
| `rewrite` | 是 | 是（仅 target_fields） | 否 | AI 改写，越界即拒绝写入 |
| `accept` | 是 | 否 | 是（→ accepted） | 作者接受某个 revision |
| `reject` | 否 | 否 | 否 | 只写 review 记录 |
| `restore` | 是 | 是（复制旧内容） | 否（proposed） | 历史内容写成新 revision |
| `diff` | 否 | 否 | 否 | 只读比较 |

## 不变量

```text
EVERY_MUTATION_APPENDS：历史 revision 永不删除、永不改写
EXPECTED_REVISION_REQUIRED：写操作带 expected_revision；冲突 → EditorConflictError（不覆盖、不 merge）
NEW_REVISION_IS_PROPOSED_UNEVALUATED：编辑后退回未评估状态（不沿用旧 passed）
PROTECTED_FIELDS_ONLY_VIA_CONTRACT：node_id / parent_id / status / provenance 等只能经专门的契约改
REJECTION_IS_METADATA：不存在 lifecycle "rejected" 状态（ADR-021）
```
