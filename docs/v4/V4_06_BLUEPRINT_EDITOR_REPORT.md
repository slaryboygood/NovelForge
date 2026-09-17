# V4-06 BLUEPRINT EDITOR RESULT

> 阶段：**V4-06 Blueprint Editor & Revision Workflow**
> 分支：`v4-06-blueprint-editor`（integration branch，单 Agent 顺序执行）
> 基线：`v4-05-quality-loop`（V4-05 PASS，1272 passed / 7 skipped / 0 failed）
> 结论：**V4-06 = PASS**

---

## 1. Existing Writer / editor inventory

见 [`V4_06_EDITOR_INVENTORY.md`](V4_06_EDITOR_INVENTORY.md)。要点：

| 既有能力 | 处置 |
| --- | --- |
| `writer_integration.WriterDraftService`（正文草稿 + Draft Fact Sync） | **兼容保留**（正文能力）；**不作为** Editor 底层 |
| `writer_integration.WriterContextBuilder` | 不 ADAPT（V4-03 `ContextBuilder` 已是唯一上下文入口，§35） |
| `writer_integration.writer_export_bundle` / writer 路由 | KEEP（V4-07 / V4-10 再评估） |
| `outline_revision.restore_version` | **ADAPT idea** → restore = 旧内容 + 新 revision + `restored_from` |
| `outline_revision.impact_of_change` | **ADAPT idea** → `ChangeImpact`（只报告下游） |
| `outline_revision.revise_item`（`EDITABLE_FIELDS` 白名单） | **ADAPT idea** → patch 字段白名单 + protected fields |
| `outline_revision.diff_versions` / `planning.versioning.build_diff` | **ADAPT idea** → 确定性结构化 diff（字段级 + list 级） |
| `planning.versioning.rollback`（复制内容生成新 revision） | **ADAPT idea** → undo = restore(parent_revision) |
| `story_engine/repair.py`（M11）、historical IR | **FROZEN / 不复用** |

结论：**没有复用正文 writer 作为 Blueprint Editor 的底层**；editor 是独立模块。

---

## 2. Editor architecture

```text
src/novelforge/editor/
├── __init__.py       Public Contract（精简导出）
├── errors.py         EditorError 家族（§75）
├── contracts.py      EditRequest/Result、Batch、Diff、Rewrite、Approval、Restore、
│                     ChangeImpact、RevisionView/History、OperationRecord、ReviewDecision、
│                     EditorSession、MoveNodeRequest
├── diff.py           确定性结构化 diff（零模型）
├── patch.py          protected fields + 字段白名单 + schema 校验 + 新 revision 构造
├── history.py        RevisionView / author 判定（来源 = BlueprintRepository）
├── impact.py         ChangeImpact（依赖感知，只报告）
├── operations.py     EditorStore（operation / review / manifest）
└── service.py        BlueprintEditorService（patch / batch / rewrite / accept / reject /
                      restore / undo / move / diff / history / session）
src/novelforge/generation/rewrite.py      字段级 rewrite contract（blueprint.<task>.rewrite.v1）
src/novelforge/application/services/editor.py  EditorService（组合 editor + quality + generation）
src/novelforge/api/editor_routes.py       最小 REST（thin routes）
```

依赖方向（守卫测试机械校验）：

```text
editor      → blueprint / generation / core / persistence.paths
application → editor / quality / generation（组合）
禁止        → generation / quality / blueprint / ai / memory / domain → editor
```

---

## 3. Public contracts

```text
BlueprintEditorService / EditorStore
EditRequest / EditResult · BatchEditRequest / BatchEditResult
DiffRequest / BlueprintDiff / FieldChange / ListChange
RewriteRequest / RewriteResult · ApprovalResult · RestoreResult · ChangeImpact
RevisionView / RevisionHistory · EditorOperationRecord / ReviewDecision · EditorSession
MoveNodeRequest · EditorError 家族
```

不导出 `PatchApplier` / `DiffWalker` / `RewritePromptBuilder` 之类的内部实现（有守卫测试）。

## 4. Manual edit

```text
字段级 patch（不接受整节点覆盖）→ 受保护字段 / 结构 identity 拒绝 →
schema + reference + parent↔identity 校验 → 新 revision（proposed / unevaluated）
```

真实结果：`ch_001 r1 → patch(goal) → r2`，其它字段逐字节不变，`r1` 永久可读。

## 5. Revision history

```text
list revisions / get revision / current / RevisionView / provenance
author ∈ human | ai_generation | ai_repair | ai_rewrite | restore | system
来源：BlueprintRepository（canonical）+ editor metadata（operation / review）
```

## 6. Diff engine

```text
added / removed / changed / unchanged fields + nested 路径
list_changes：added / removed / reordered
状态与质量状态的前后对比；digest 稳定
跨节点 → DIFF_CROSS_NODE；跨作品 → EDITOR_OWNERSHIP_MISMATCH
零模型（守卫测试断言 diff 模块不引用 ai / gateway）
```

## 7. AI rewrite

```text
editor.rewrite → generation.rewrite_fields（contract=blueprint.<task>.rewrite.v1）
只把 target_fields 合并进当前 payload；其余字段变化 → RewriteViolationError（不落盘）
新 revision：proposed / unevaluated（author=ai_rewrite，provenance 带 contract / model / provider /
context_digest / quality_issue_ids）
dry_run：0 次模型调用、0 次写入
```

## 8. Preserve enforcement

```text
PROTECTED_FIELDS（metadata）+ STRUCTURAL_IDENTITY_FIELDS（blueprint SSOT）双保险
patch / rewrite / restore 三条路径都校验（§63）
V4-05 repair 复用同一份 SSOT（quality/repair/planner.py 改为引用 blueprint 常量，去掉重复定义）
```

## 9. Accept / reject

```text
accept  → repository.set_status(accepted) → 新 revision（payload 不变）+ ReviewDecision
          已 accepted 再次 accept → recorded（不重复产生 revision）
reject  → 只写 ReviewDecision（revision 保留、status 不变）
quality_status = passed ≠ status = accepted；accepted ≠ 质量冻结（ADR-022）
```

## 10. Restore / undo

```text
restore r1 → r4（payload = r1，结构 = current，provenance.restored_from = 1）
undo = restore(parent_revision)
历史全部保留；结构 identity 不一致 → 拒绝
```

## 11. Quality integration

```text
EditorService.get_quality(node, revision)     当前 revision 的 issue；旧 revision 标记 historical
EditorService.evaluate(node)                  对节点 scope 执行 Q0–Q9
EditorService.plan_repair(node / issue_ids)   repair preview（问题 / 目标节点 / 允许字段 /
                                              保留字段 / 复核 gate / 预计模型任务数）
EditorService.repair(issue_ids)               执行 V4-05 repair，并把结果记入 editor audit
EditorService.verify_repair(issue_ids)        复核 resolved / remaining / new
```

## 12. Repair preview

`plan(dry_run=True)` 的 5 个答案（问题是什么 / 改哪些节点 / 允许改什么 / 保留什么 /
复核哪些 Gate）通过 `EditorService.plan_repair` 统一暴露；测试断言 preview 不写 revision、
不调用模型。

## 13. Change impact

```text
direct + dependent_nodes（子节点 / 同章场景 / 父章节 / causal 端点 / payoff 绑定 / arc 链接）
+ quality_invalidations + reasons + summary；auto_modified = false
```

## 14. Quality invalidation

```text
编辑 / 改写产生的新 revision：quality_status = unevaluated（不沿用旧 passed）
旧 revision 的 issue 在 Editor 视图标记 historical（不冒充当前问题）
下游节点的 quality invalidation 只报告（不自动重新生成）
```

## 15. Revision conflict

```text
expected_revision 不匹配 → EditorConflictError（details: expected / actual / node_id /
conflict_diff = current vs base 的结构化 diff）
不覆盖、不自动 merge（创意字段的合并必须由人确认）
batch：写冲突显式报告 status="partial" + conflict_node_ids
```

## 16. Idempotency

```text
patch / patch_batch / rewrite / accept / reject / restore / undo 均支持 idempotency_key
重放：命中已有 operation → 返回原结果（不产生第二个 revision，不重复调用模型）
被拒绝（rejected）的操作没有产生 revision → 允许用同一 key 重试
```

## 17. Audit / provenance

```text
EditorOperationRecord（operation / actor / request_id / source_revision / result_revision /
changed_fields / reason / status / idempotency_key / created_at / ai / impact / extra）
ReviewDecision（accepted / rejected + reviewed revision + resulting revision）
节点 provenance 只留指针（operation / source_revision / changed_fields / contract_id / model /
provider / context_digest / target_fields / preserve），完整历史在 editor metadata
不保存完整敏感 prompt（§13）
```

## 18. Persistence

```text
novel/authoring/story_engine/editor/<novel_id>/
├── operations/<operation_id>.json
├── reviews/<node_id>__r<revision>.json
└── MANIFEST.json
路径全部经 persistence.paths（新增 editor_dir / editor_operations_dir /
editor_reviews_dir / editor_manifest_path；ARTIFACT_KINDS += "editor"）
顺带清理：ARTIFACT_KINDS 中重复的 "blueprint" 条目
```

## 19. Ownership isolation

```text
两本作品 node_id 完全相同 → 读 / 改 / diff / restore / rewrite 全部隔离
EditorStore / EditorService 均要求显式 novel_id；跨作品 → EditorOwnershipError
（测试覆盖 domain 层与 REST 层）
```

## 20. Application service

```text
EditorService（application.services.editor）
  get_node / get_history / list_revisions / diff / change_impact / operations / stats
  patch / patch_batch / rewrite / regenerate / accept / reject / restore / undo / move
  get_quality / evaluate / plan_repair / repair / verify_repair / evaluate_and_repair
editor_service(project_root, novel_id, *, gateway=None, memory=None) 唯一装配入口
REST（thin）：GET node / revisions / diff / quality；PATCH node；
              POST rewrite / accept / reject / restore（novel_id 显式）
错误映射：404 / 403 / 409 / 422；不泄露 traceback / pydantic 原始报错
```

## 21. Legacy writer handling

```text
WriterDraftService / WriterContextBuilder / writer 路由 / writer_export_bundle：KEEP（正文能力）
writer 路径常量：KEEP（editor 不复用，editor 走 persistence.paths）
novel/final/**：V4-01 已删除（作者决策 A）；V4-06 未新增任何正文依赖
旧 draft 数据：未迁移、未改写
删除计划已登记（docs/v4/V4_DELETION_PLAN.md §3）
```

## 22. Module boundary verification

`tests/v4/isolation/test_editor_boundaries.py`（10 个永久守卫）：

```text
editor 不 import api / application / ai / memory / story_engine / quality / HTTP client
editor 不自行拼 artifact 路径；只经 persistence.paths
editor 不写 Canon / StoryState
core / persistence / domain / ai / memory / blueprint / generation / quality 不得 import editor
generation 不得 import editor / quality
editor 顶层不 import application / api / ai / memory / quality
Public Contract 精简；REST 路由只调用 application.services.editor（+ 错误模型）
editor metadata store 不含 BlueprintNode（不是第二套 truth）
```

---

## 23. Tests

```text
pytest -q                                1392 passed / 7 skipped / 0 failed（407s）
tests/editor/**                            110 passed（含 REST）
tests/v4/**                                79 passed（含 10 个 editor 边界守卫）
tests/quality/**                           122 passed（未受影响）
tests/generation/**                         57 passed（新增 rewrite 后仍全绿）
tests/memory/**                             61 passed
tests/ai/**                                 90 passed
python scripts/validate_project.py          PASS
tests/test_v2_frozen_guard.py + v3          12 passed
```

### 23.1 测试数量变化解释（V4-05 → V4-06）

| 类别 | 变化 | 原因 |
| --- | --- | --- |
| `tests/editor/**` | **+110** | 本阶段新增：contracts / manual edit / revision history / diff / restore / accept-reject / ai rewrite / preserve / idempotency / concurrency / change impact / quality integration / application service / REST |
| `tests/v4/isolation/**` | **+10** | 新增 editor 模块边界守卫 |
| 既有测试 | ±0 | 只新增模块与服务；blueprint / quality / generation 的行为仅做「复用同一 SSOT」的小重构（有测试覆盖） |

离线保证（§78）：全部测试使用 StubProvider，`0` 次真实 API 调用。

---

## 24. Frozen boundary

```text
novelforge-product-v3-final tag        未移动（git tag 仍只有该 tag）
novel/authoring frozen digest          未变化（V2/V3 frozen guard PASS）
story_engine/repair.py                 未修改（M11 边界保持；V4-05 repair 与 V4-06 均不引用它）
REPAIR_GATE_V1                         未修改
Canon / StoryState 语义                 未修改：editor 只写 Blueprint proposal
Blueprint lifecycle enum                未新增 rejected（rejection 记在 editor metadata）
```

---

## 25. Files created

```text
src/novelforge/editor/{__init__,errors,contracts,diff,patch,history,impact,operations,service}.py
src/novelforge/generation/rewrite.py
src/novelforge/application/services/editor.py
src/novelforge/api/editor_routes.py
tests/editor/{editor_support,test_editor_contracts,test_manual_edit,test_revision_history,
              test_diff,test_restore,test_accept_reject,test_ai_rewrite,test_preserve,
              test_idempotency,test_concurrency,test_change_impact,test_quality_integration,
              test_application_service,test_editor_api}.py
tests/v4/isolation/test_editor_boundaries.py
docs/v4/V4_06_EDITOR_INVENTORY.md
docs/v4/V4_EDITOR_CONTRACT.md
docs/v4/V4_06_BLUEPRINT_EDITOR_REPORT.md（本文件）
docs/v4/adr/ADR-021-editor-mutations-are-append-only-revisions.md
docs/v4/adr/ADR-022-quality-pass-does-not-mean-author-accepted.md
docs/v4/adr/ADR-023-restore-creates-a-new-revision.md
```

## 26. Files modified

```text
src/novelforge/persistence/paths.py          新增 editor 路径 + 去重 ARTIFACT_KINDS
src/novelforge/persistence/__init__.py       导出 editor 路径函数
src/novelforge/blueprint/contracts.py        STRUCTURAL_IDENTITY_FIELDS（结构 identity SSOT）
src/novelforge/blueprint/__init__.py         导出上述常量
src/novelforge/quality/repair/planner.py     改为复用 blueprint 的 SSOT（去重）
src/novelforge/generation/service.py         rewrite_fields + NODE_TYPE_TASK + GenerationResult.target_fields
src/novelforge/generation/errors.py          RewriteViolationError
src/novelforge/generation/__init__.py        导出 rewrite 契约
src/novelforge/application/services/__init__.py 导出 EditorService / editor_service
src/novelforge/api/app.py                    安装 editor 路由
docs/v4/V4_BLUEPRINT_CONTRACT.md             §3.2 编辑与状态语义（rejection 不进 lifecycle）
docs/v4/V4_MODULE_BOUNDARIES.md              §3.13 editor + 依赖矩阵 + 明文禁令 + 守卫清单
docs/v4/V4_ARCHITECTURE.md                   §1.8 / §4.1 表 / §5 Editor 边界
docs/v4/V4_MIGRATION_PLAN.md                 V4-06 段按 ADR-011 决策重写
docs/v4/V4_DELETION_PLAN.md                  writer_integration / outline_revision 评估登记
docs/v4/V4_BRANCH_STRATEGY.md                V4-06 分支行 + 分支声明
docs/v4/adr/README.md                        ADR-021/022/023 登记
```

## 27. Files deleted

```text
无（未删除任何 V3 模块；正文 writer 与 outline_revision 保持 compatibility，移除条件已登记）
```

---

## 28. Git branches

```text
v4-06-blueprint-editor（integration branch，单 Agent 顺序执行）
未创建 v4-06a…f 子分支（§2：单 Agent 时一个 integration branch 即可）
```

## 29. Git commits

```text
（1）docs(v4): freeze blueprint editor contracts
（2）feat(editor): add editor mutation and revision contracts
（3）feat(editor): add structured blueprint diff
（4）feat(editor): add manual edit and restore workflow
（5）feat(editor): add ai rewrite and preserve enforcement
（6）feat(application): expose blueprint editor service
（7）test(editor): add revision diff rewrite and conflict coverage
（8）test(v4): enforce editor module boundaries
（9）docs(v4): record v4-06 result
```

---

## 30. Remaining risks

| 风险 | 状态 | 说明 |
| --- | --- | --- |
| Rejected revision 不是 lifecycle 状态 | 设计如此（ADR-022 / 契约 §7） | 用 editor metadata 表达"针对某 revision 的拒绝"；UI 需要读 `review_status` |
| 没有复杂 redo stack | 设计如此（§27） | undo = restore(parent)；拒绝引入前端式 transient history |
| REST 只有最小链路（无批量 / move / diff-by-quality 端点） | 计划内 | 本阶段只验证 thin-route 契约；完整 API 面属 V4-10 |
| 语义 merge / 自动合并 | 明确禁止（§45） | 冲突交由人处理；未来 Agent Mode 也只能提议 |
| Editor metadata 与 Blueprint 不同步（无事务） | 已知 | 先写 revision 再写 operation；若进程中断，operation 记录可能缺失（Blueprint truth 不受影响） |
| `move` 对 causal_link / setup 的父级语义有限 | 已知 | 只支持节点自身的 parent/sequence + 与父绑定的 identity 字段联动；更复杂的结构重组属后续阶段 |
| writer / outline 双编辑路径共存 | 已登记（V4_DELETION_PLAN §3） | V4-10 完成 UI 切换后再删除 |
| `quality_status` 仍未被自动投影写入节点 | 计划内 | Editor 只保证"编辑后 unevaluated"；投影写入属 lifecycle 决策（V4-10 / 后续） |

---

## 31. V4-07 readiness

```text
[x] editor 是独立模块；没有自己的 Blueprint store；Application 负责组合
[x] generation / quality 不反向依赖 editor；interface 只经 application.services.editor
[x] field-level patch + schema / reference 校验 + expected_revision + append-only revision
[x] 结构 identity 受保护；preserve 在 patch / rewrite / restore / repair 全线生效
[x] revision history / RevisionView / provenance / optimistic concurrency / conflict_diff
[x] 确定性结构化 diff（含 list 级）+ 跨节点 / 跨作品拒绝
[x] AI rewrite 只改 target fields；preserve 违反不落盘；经 generation / Gateway（0 真实 API 调用）
[x] accept 产生新 revision；reject 只记录；quality pass ≠ accepted；accepted 不被静默覆盖
[x] restore / undo 产生新 revision，历史全部可读，provenance 记录 restored_from
[x] issue 归属 revision（historical 标记）；repair preview / repair verify / change impact
[x] 跨作品完全隔离；审计可回答"谁改的 / 从哪一版 / 改了什么 / 是否 AI / 关联哪个 issue"
[x] 1392 passed / 7 skipped / 0 failed；validate_project PASS；frozen guards PASS
```

V4-07（Delivery / Export）可以直接消费：

```text
EditorService.get_node / get_history / diff / get_quality（交付前展示 revision 与质量结论）
RevisionView.status / quality_status / review_status（区分提案 / 已接受 / 质量状态）
ChangeImpact.quality_invalidations（交付前确认没有 stale 结论）
EditorOperationRecord（交付物的来源与审计链）
```

---

# V4-06 = PASS
