# NovelForge V4 — Blueprint Editor Contract（V4-06 冻结）

> 状态：**V4-06 Blueprint Editor & Revision Workflow**（2026-09-18 实施完成）
> 依据：任务书 §6–§13、§38–§49；ADR-019 / ADR-021 / ADR-022 / ADR-023
> 定位：`editor` 模块与 `application.services.editor` 的 **Public Contract SSOT**。

---

## 1. 一句话定义

```text
Editor = 让作者安全地掌控 AI 生成的大纲：
         读 revision、改字段、比较、接受 / 拒绝、恢复、定向 AI 改写、记录审计。
```

不变量：

```text
EDITOR_OWNS_NO_TRUTH        canonical Blueprint 永远在 BlueprintRepository
APPEND_ONLY                 任何编辑产生新 revision；accepted 不被静默覆盖
OPTIMISTIC_CONCURRENCY      写操作携带 expected_revision；冲突不覆盖、不自动 merge
PRESERVE_IS_HARD            结构 identity / provenance 不可通过 patch 修改
QUALITY_IS_NOT_APPROVAL     quality_status = passed ≠ status = accepted
AUDIT_IS_NOT_STORY_TRUTH    operation / review 记录写在 editor metadata
```

Editor **不是**正文编辑器：V3 的 `WriterDraftService`（preview 草稿）保持兼容，
不成为 Blueprint Editor 的底层（见 `V4_06_EDITOR_INVENTORY.md` §3）。

---

## 2. Public Contract

```text
src/novelforge/editor/__init__.py（精简导出，不导出 PatchApplier / DiffWalker 等内部实现）

BlueprintEditorService                  编辑能力（读 / 改 / 比较 / 记录）
EditRequest / EditResult                手工字段级修改
BatchEditRequest / BatchEditResult      多节点修改（all_or_rollback / partial）
DiffRequest / BlueprintDiff             结构化比较（零模型、确定性）
RewriteRequest / RewriteResult          AI 只改指定字段
ApprovalResult                          accept / reject
RestoreResult                           restore / undo
ChangeImpact                            修改影响面（只报告）
RevisionView / RevisionHistory          revision 导航
EditorOperationRecord / ReviewDecision  审计记录（editor metadata）
EditorSession / MoveNodeRequest         轻量会话（内存）/ 结构移动
EditorStore / EditorError 家族          metadata 存储 / 错误模型
```

Application 层（接口层的唯一入口）：

```text
application.services.EditorService / editor_service
  get_node / get_history / list_revisions / diff / change_impact / operations / stats
  patch / patch_batch / rewrite / regenerate / accept / reject / restore / undo / move
  get_quality / evaluate / plan_repair / repair / verify_repair / evaluate_and_repair
```

---

## 3. Manual Edit（§8–§10）

```text
EditRequest(novel_id, node_id, expected_revision, changes, actor, reason,
            idempotency_key, dry_run)
   ↓ 校验（零写入）
1. changes 必须是非空字段字典
2. 受保护字段 → EditorPreserveViolation
   node_id / novel_id / node_type / parent_id / sequence / revision / parent_revision /
   schema_version / status / quality_status / source_ids / context_digest /
   generation_contract(+version) / provenance / created_at / updated_at
3. 结构 identity 字段 → EditorPreserveViolation（hint：使用 move_node）
   scene→chapter_id；chapter→characters；character_arc→character_id；
   causal_link→source/target；payoff→resolves_setup_ids
4. 未知字段 / 类型不合法 → EditorValidationError（pydantic 报错不外泄）
5. parent ↔ identity 一致性（例如 scene.chapter_id == parent_id）
6. reference / ownership 校验（blueprint.require_valid）
   ↓
新 revision：status=proposed，quality_status=unevaluated，parent_revision=旧 revision
```

```text
r1(ai_generation) --patch--> r2(human, proposed, unevaluated)：其它字段逐字节不变，r1 永久可读
```

批量（§38）：先全量校验（零写入）再统一提交；
`all_or_rollback` 任一校验失败 → 不写任何 revision（status=`rejected`）；
`partial` 写入通过项并显式列出冲突节点（status=`partial`，notes 说明 append-only 无法回滚）。

---

## 4. Revision / History（§11–§13）

```text
RevisionView = node_id / revision / parent_revision / status / quality_status /
               created_at / updated_at / source / author / operation / request_id /
               summary / changed_fields / source_ids / generation_contract /
               restored_from / review_status / review_note / is_current
author ∈ human | ai_generation | ai_repair | ai_rewrite | restore | system
```

来源分工：canonical 内容与 revision 序号来自 `BlueprintRepository`；
operation / request_id / review 来自 editor metadata。**不复制一份 history store**。

---

## 5. Diff（§14–§16）

```text
BlueprintDiff = added_fields / removed_fields / changed_fields / unchanged_fields /
                field_changes(before, after, nested) /
                list_changes(added, removed, reordered) /
                status·quality_status(before→after) / digest
```

```text
· 零模型：字段级差异由确定性算法决定（模型不决定"哪些字段变了"）
· 跨节点比较 → EditorValidationError（DIFF_CROSS_NODE）
· 跨作品比较 → EditorOwnershipError
· diff 可关联 before/after/resolved/new issues，issue 来源是 Quality Store（§33）
```

---

## 6. AI Rewrite（§17–§21）

```text
editor.rewrite(RewriteRequest)
   ↓ generation.rewrite_fields(...)      ← 唯一 LLM 入口（editor 不直接调模型 / provider）
contract = blueprint.<task>.rewrite.v1（输出仍按 payload 模型做 schema 校验）
   ↓ 模型输出与当前 revision 对比
除 target_fields 之外任何字段变化 → RewriteViolationError → **不写入任何 revision**
   ↓ 只把 target_fields 合并进当前 payload
新 revision：proposed / unevaluated / provenance{operation=ai_rewrite, contract_id,
             target_fields, preserve, model, provider, context_digest, source_ids,
             quality_issue_ids, source_revision}
```

| | rewrite | regenerate |
| --- | --- | --- |
| 范围 | 只改 `target_fields` | 整节点重新生成 |
| contract | `blueprint.<task>.rewrite.v1` | `blueprint.<task>.v1` |
| preserve | 除 target 外全部字段必须不变（违反即拒绝） | 只保证结构校验通过 |
| 典型输入 | "只增强转折，不要改人物关系" | 重写整场 |

`dry_run`：不调用模型、不写 revision；返回 target / preserve / 预计模型任务数 / 影响面。

---

## 7. Accept / Reject（§22–§24、§68–§70）

```text
accept(node_id, revision=None, expected_revision=None)
  → repository.set_status(node_id, "accepted")     （Blueprint lifecycle 是唯一状态机）
  → 新 revision（payload 不变，status=accepted）+ ReviewDecision(accepted)
  → 已是 accepted 再次 accept → status="recorded"，不重复产生 revision

reject(node_id, revision=.., reason=..)
  → 只写 ReviewDecision(rejected) 到 editor metadata
  → revision 保留、Blueprint status 不变
```

为什么 reject 不进入 lifecycle（§23 的评估结论）：

```text
BlueprintNode.status 是"当前 revision"的状态，而 set_status 会 append 一个新 revision。
因此"给某个旧 revision 打 rejected"无法用 lifecycle 表达（会变成新 revision 的状态），
而"拒绝"是**针对某个 revision 的 review 决定** → 属于 editor metadata。
Blueprint lifecycle enum 保持 proposed / draft / accepted / superseded 不变。
```

两条互相独立的事实（§69 / §70）：

```text
quality_status = passed   ≠   status = accepted
accepted                  ≠   质量永久通过（上游变化后可以 stale / unevaluated）
```

---

## 8. Restore / Undo（§25–§26、§60）

```text
restore(node_id, from_revision)  用旧 revision 的内容创建**新** revision
undo(node_id)                    = restore(current.parent_revision)
provenance = {operation: restore|undo, restored_from: N, source_revision: M}
```

```text
· current 指针不回退；历史 revision 全部保留（append-only timeline）
· 只恢复内容字段；结构 identity 不一致 → EditorPreserveViolation
· 恢复后的 revision：status=proposed / quality_status=unevaluated
```

---

## 9. Move（§39）

```text
MoveNodeRequest(novel_id, node_id, expected_revision, parent_id, sequence, ...)
  · parent 类型必须符合 ALLOWED_PARENT_TYPES；sequence 必须为正整数
  · 与父绑定的结构 identity 同步更新（scene.chapter_id / character_arc.character_id）
  · 产生新 revision（proposed / unevaluated）
patch 一律拒绝 parent_id / sequence（结构关系只能走本契约）
```

---

## 10. Change Impact / Quality Invalidation（§71–§74）

```text
ChangeImpact = direct node + changed_fields + dependent_nodes +
               quality_invalidations + reasons + summary（auto_modified=false）
```

| 关系 | reason |
| --- | --- |
| 子节点 | `child_of_changed_node` |
| 同一章的其他 Scene | `same_chapter_scene` |
| Scene 的父章节 | `scene_changed_under_chapter` |
| 端点被改的 causal link | `causal_endpoint_changed` |
| 回收被改 setup 的 payoff | `resolves_changed_setup` |
| 链接到被改节点的 character arc | `arc_links_changed_node` |

**只报告，不自动修改下游**。编辑后新 revision `quality_status = unevaluated`；
旧 revision 的 issue 在 Editor 视图里标记 `historical`（§29）。

---

## 11. Audit（§47–§49）

```text
EditorOperationRecord = operation_id / operation / node_id / actor / request_id /
                        source_revision / result_revision / changed_fields / reason /
                        status / idempotency_key / created_at / ai{} / impact / extra
ReviewDecision        = node_id / revision / decision / actor / reason /
                        operation_id / resulting_revision / created_at

novel/authoring/story_engine/editor/<novel_id>/
├── operations/<operation_id>.json
├── reviews/<node_id>__r<revision>.json
└── MANIFEST.json
```

审计回答：谁改的 / 什么时候 / 从哪一版 / 改了什么 / 为什么 / 是否 AI / 用了哪个模型 /
是否关联 QualityIssue；**不保存完整敏感 prompt**（沿用 V4-02 §60）。

---

## 12. Application Service 与 REST（§7、§51、§52、§67）

```text
application.services.EditorService
        ├── novelforge.editor          （编辑 / diff / restore / audit）
        ├── novelforge.generation      （rewrite / regenerate；gateway 由宿主注入）
        └── novelforge.quality + repair（evaluate / issue / plan / repair / verify）
editor_service(project_root, novel_id, *, gateway=None, memory=None)  ← 唯一装配入口
```

```text
GET   /api/story-builder/editor/nodes/{node_id}
GET   /api/story-builder/editor/nodes/{node_id}/revisions
GET   /api/story-builder/editor/nodes/{node_id}/diff
GET   /api/story-builder/editor/nodes/{node_id}/quality
PATCH /api/story-builder/editor/nodes/{node_id}
POST  /api/story-builder/editor/nodes/{node_id}/rewrite
POST  /api/story-builder/editor/nodes/{node_id}/accept
POST  /api/story-builder/editor/nodes/{node_id}/reject
POST  /api/story-builder/editor/nodes/{node_id}/restore
novel_id 必须显式传入（服务端不做磁盘推断）
错误映射：404 not found / 403 ownership / 409 conflict 或 preserve / 422 validation
```

---

## 13. 错误模型（§75）

```text
EditorError                EDITOR_ERROR
EditorValidationError      EDITOR_VALIDATION_FAILED
EditorOwnershipError       EDITOR_OWNERSHIP_MISMATCH
EditorNotFoundError        EDITOR_NODE_NOT_FOUND
EditorConflictError        EDITOR_REVISION_CONFLICT（details 含 conflict_diff）
EditorPreserveViolation    EDITOR_PRESERVE_VIOLATION
EditorOperationRejected    EDITOR_OPERATION_REJECTED
（接口层不会看到 KeyError / FileNotFoundError / pydantic 原始报错）
```

---

## 14. 验收判据（V4-06）

```text
[x] editor 是独立模块；没有自己的 Blueprint store；Application 负责组合 Editor / Quality
[x] generation / quality 不反向依赖 editor；interface 只经 application.services.editor
[x] field-level patch + schema / reference 校验 + expected_revision + append-only
[x] 结构 identity 受保护（patch / rewrite / restore 都遵守）
[x] revision history / RevisionView / provenance / optimistic concurrency / conflict_diff
[x] 确定性结构化 diff（含 list 级）+ 跨节点 / 跨作品拒绝
[x] AI rewrite 只改 target fields；preserve 违反 → 拒绝且不落盘；经 generation / Gateway
[x] accept 产生新 revision；reject 只记录；quality pass ≠ accepted
[x] restore / undo 产生新 revision，历史全部可读，provenance 记录 restored_from
[x] issue 归属 revision（旧 revision 标记 historical）；repair preview / repair / verify
[x] change impact + quality invalidation（只报告）；跨作品完全隔离
```

