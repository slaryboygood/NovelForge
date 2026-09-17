# V4-06 — Existing Writer / Editor Inventory

> 阶段：**V4-06 Blueprint Editor & Revision Workflow**
> 目的：在写任何新代码之前，把现有 writer / draft / diff / revision / restore 能力盘清楚（任务书 §3、§54）。
> 原则：**ADAPT idea only，不复用正文 writer 作为 Blueprint Editor 的底层。**

---

## 1. 现有模块总表

| Existing Module | Current Capability | Input | Output Shape | Deterministic? | V4-06 Action | Target |
| --- | --- | --- | --- | --- | --- | --- |
| `story_builder/writer_integration.py::WriterDraftService` | 正文草稿 create/list/get + Draft Fact Sync（只产生 proposal） | CreatorContext / claims / narration | `draft` JSON（preview 层，`truth_layer="preview"`） | 是 | **兼容保留（正文能力）**；**不作为** Blueprint Editor 底层 | — |
| `story_builder/writer_integration.py::WriterContextBuilder` | 分层 writer context（canon / story_state / planning / chapter_plan / guidance） | novel_id / chapter_id | 5 个 block + digest + validation | 是 | **不 ADAPT**（V4-03 已有 `ContextBuilder`；不得出现第二套上下文系统，§35） | V4-03 |
| `story_builder/writer_integration.py::writer_export_bundle` | Writer-ready package | novel_id | export manifest + context 摘要 | 是 | **KEEP**（V4-07 处理交付） | V4-07 |
| `story_builder/writer_integration.py` `WRITER_STORE_DIR` / `writer_store_path` | 正文草稿路径常量（`novel/authoring/story_engine/writer/...`） | — | Path | 是 | **KEEP**（正文草稿；**不**被 editor 复用，editor 路径走 `persistence.paths`） | — |
| `api/story_builder_routes.py` `/writer/context` `/writer/drafts*` | writer 路由 | HTTP | JSON | 是 | **KEEP**（legacy 产品面；V4-10 再决定去留） | V4-10 |
| `story_engine/outline_revision.py::restore_version` | 回退：旧版本内容写为**新**版本，历史保留 | package_id / version | `{outline, restored_from}` | 是 | **ADAPT idea**（V4-06 restore 语义与之一致：append-only + provenance `restored_from`） | `editor/service.restore` |
| `story_engine/outline_revision.py::impact_of_change` | 改上层条目 → 列出受影响下游包 + happened/planned 分类 | package_id / item_id | affected_downstream / affected_happened | 是 | **ADAPT idea**（→ `editor/impact.py ChangeImpact`，只报告不自动改） | `editor/impact.py` |
| `story_engine/outline_revision.py::revise_item` | 只允许改白名单字段（`EDITABLE_FIELDS`）+ 影响提示 + 新版本 | changes | 新 package + impact | 是 | **ADAPT idea**（→ patch 字段白名单 + protected fields） | `editor/patch.py` |
| `story_engine/outline_revision.py::diff_versions` | 结构化 item diff（added / removed / changed + changed_fields） | 两个版本 | `VersionDiff` | 是 | **ADAPT idea**（→ `editor/diff.py`，但对象是 Blueprint payload + list 级差异） | `editor/diff.py` |
| `story_engine/planning/versioning.py::build_diff` | 扁平化字段路径 diff（added/removed/modified + domain + supplied 保护） | 两个 IR | `PlanningDiff` | 是 | **ADAPT idea**（字段级确定性 diff；V4-06 增加 list 级 added/removed/reordered） | `editor/diff.py` |
| `story_engine/planning/versioning.py::PlanningVersionStore.rollback` | 回滚 = 复制目标内容生成新 revision + 旧者 superseded | revision_id | 新 revision | 是 | **ADAPT idea**（V4-06 的 undo = restore(parent_revision)） | `editor/service.undo` |
| `story_builder/outlines.py::StoryOutlineRepository` | 大纲版本存储（`v*.json` + latest + confirm） | — | outline package | 是 | **KEEP / 不复用**（不同 artifact；Blueprint 用 `BlueprintRepository`） | — |
| `story_builder/inspector.py::repair_diagnosis` | 修复中心诊断（findings → 建议动作） | pack / outline | issues + action | 是 | **KEEP**（V4-05 已用 QualityIssue 统一语义） | — |
| `story_engine/repair.py`（M11，frozen） | 570 章历史修复 | Historical IR | RepeairFinding | 是 | **FROZEN / 不复用**（§84） | — |
| `blueprint/repository.py`（V4-04） | 节点 append-only revision / index / idempotency / `set_status` | BlueprintNode | 新 revision | 是 | **直接复用（唯一 Blueprint truth）** | `editor` 全部写路径 |
| `generation/service.py`（V4-04） | 逐级生成 / `regenerate`（整节点）/ expected_revision / idempotency | GenerationRequest | GenerationResult | 否（LLM） | **扩展**：新增字段级 `rewrite_fields`（V4-06 §17–§20） | `generation/rewrite.py` |
| `quality/repair/*`（V4-05） | planner / executor / verifier（minimal scope + preserve） | QualityIssue | RepairPlan / Result | 混合 | **直接复用（经 Application 组合，§28 / §67）** | `application.services.editor` |

---

## 2. 现状结论（为什么必须新建 editor 模块）

```text
1. 「编辑」在 V3 只有两条路径：正文草稿（WriterDraftService）与大纲条目（outline_revision）。
   两者都不是 Blueprint 节点编辑；Blueprint 目前只能生成（V4-04）与修复（V4-05），不能手工改。
2. 已有 revision / restore / impact / diff 的**思路**（outline_revision / planning.versioning）
   值得 ADAPT，但它们服务于 outline package 与 planning IR，形态与 Blueprint 节点不同。
3. 冲突处理已有一致先例：outline「历史不可改写」、planning「rollback 产生新 revision」、
   Blueprint「append-only revision」。V4-06 沿用同一不变量，不发明第三套。
4. 审计信息在 V3 散落（draft 文件 / outline pending_questions / planning note）；
   V4-06 需要一处显式的 EditorOperationRecord，但**不得**塞进 Blueprint payload（§48）。
```

---

## 3. 处置清单

```text
ADAPT（思路，不复制实现）
  · restore 语义（旧内容 + 新 revision + restored_from）
  · change impact（依赖下游列表 + 不自动改写）
  · editable field 白名单 + protected fields
  · 结构化 diff（字段级 + list 级，零模型）

KEEP（保持现状，不在本阶段扩大范围）
  · WriterDraftService / WriterContextBuilder / writer 路由（正文能力，legacy 产品面）
  · StoryOutlineRepository / outline_revision（大纲 artifact）
  · inspector.repair_diagnosis

FROZEN / 不复用
  · story_engine/repair.py（M11）+ REPAIR_GATE_V1
  · story_engine/historical_ir.py / reconstruction.py

REPLACE_BY_EDITOR（后续阶段再删）
  · 「改大纲条目」类能力（revise_item / restore_version）在 V4 的对应物是 Blueprint Editor；
    但 outline 产品路径仍在（V3 UI + 测试），删除属 V4-10，本阶段只登记。
```

---

## 4. 与 V4-05 的边界

```text
V4-05 已实现（质量闭环）：
  QualityIssue / QualityReport / RepairPlan / RepairExecutor / RepairVerifier
  preserve 硬约束 + expected_revision + 新 revision + needs_human_review

V4-06 新增（作者掌控）：
  manual patch（field-level）/ batch patch / 结构化 diff / revision history /
  accept / reject / restore / undo / AI rewrite（只改 target fields）/
  change impact + quality invalidation / 审计记录

分界原则：**质量能发现问题，Editor 让作者决定怎么改**。
  quality_status = passed ≠ status = accepted（§69）；
  accepted 不是质量冻结（§70）。
```

