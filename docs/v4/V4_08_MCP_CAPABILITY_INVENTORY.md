# V4-08 — Application Capability Inventory（MCP 前置盘点）

> 阶段：**V4-08 MCP Server & Machine Interface**
> 目的：编码前确认「哪些 Application Service 可以直接被 MCP 调用、哪些缺口需要先补 facade」（§6）。
> 原则：**MCP 只调用 Application Services；缺口补在 Application 层，不在 MCP 里绕过（§7、§58）。**

---

## 1. 能力总表

| Capability | Application Service | Read/Write | MCP Resource / Tool | Revision Required | Idempotency | V4-08 Action |
| --- | --- | --- | --- | --- | --- | --- |
| 作品摘要 / 进度 | `ProjectService.get_novel` / `JourneyService.projection` | Read | `novelforge://novels/{id}` | — | — | **ADAPT**：新增 `ApplicationServices.summary()` 组合 |
| Blueprint 有序视图 | `ExportService.blueprint_view`（新增，消费 `DeliveryService.machine_representation`） | Read | `/blueprint`、`/scenes` | — | — | **补 Application facade**（V4-07 machine representation 已存在） |
| 单节点 / revision | `EditorService.get_node` / `EditorService.get_history` | Read | `/blueprint/nodes/{id}`、`/revisions/{n}` | — | — | **直接可用** |
| 质量摘要 / issue | `ReviewService.stats` / `list_issues` / `latest_report` | Read | `/quality`、`/quality/issues` | — | — | **直接可用** |
| 评审 / 审计 | `EditorService.operations` / `reviews`（新增）/ `review_for` | Read | `/review` | — | — | **补 Application facade**（`reviews()` 本阶段新增） |
| 交付快照 / manifest / artifact | `ExportService.delivery_snapshots` / `delivery_snapshot` / `delivery_manifest` / `delivery_artifact` | Read | `/delivery/**` | — | — | **直接可用** |
| 生成（premise…scene） | `BlueprintService.generate_task` | Write | `generate_*`（9 个 tool） | 新节点无（需 idempotency_key） | ✅ | **直接可用** |
| 字段级编辑 | `EditorService.patch` / `patch_batch` | Write | `patch_blueprint_node` | ✅ expected_revision | ✅ | **直接可用** |
| AI 字段改写 | `EditorService.rewrite` | Write | `rewrite_blueprint_node` | ✅ | ✅ | **直接可用** |
| 整节点重生成 | `EditorService.regenerate` | Write | `regenerate_blueprint_node` | ✅ | ✅ | **直接可用** |
| 接受 / 拒绝 | `EditorService.accept` / `reject` | Write | `accept_revision` / `reject_revision` | 可选（accept 有 concurrency 语义） | ✅ | **直接可用** |
| 恢复历史 | `EditorService.restore` / `undo` | Write | `restore_revision` | ✅ | ✅ | **直接可用** |
| 结构化 diff | `EditorService.diff` | Read | `diff_revisions`（read-only tool） | — | — | **直接可用** |
| 质量评估 | `ReviewService.evaluate` / `EditorService.evaluate` | Write（质量结论） | `evaluate_blueprint` | — | — | **直接可用** |
| Repair 规划 / 执行 / 复核 | `EditorService.plan_repair` / `ReviewService.repair_issue` / `EditorService.verify_repair` | Write | `plan_repair` / `repair_issue` / `verify_repair` | ✅ | ✅ | **直接可用** |
| 交付校验 / 快照 / 交付 | `ExportService.validate_delivery` / `create_snapshot` / `deliver` | Write | `validate_delivery` / `create_delivery_snapshot` / `deliver_blueprint` | — | ✅ | **直接可用**（默认 accepted） |
| Story Memory 摘要 | —（无 Application facade） | Read（派生） | （本阶段不暴露） | — | — | **DEFER**：见 §3 |
| 正文 writer 能力 | `WriterDraftService`（domain 直接暴露，未进 Application） | Write | **不暴露**（§17、§71） | — | — | 明确排除 |
| legacy 导出（planning / outline / writer bundle） | `ExportService.projection` 等 | Read | **不暴露**（§72） | — | — | 明确排除 |
| MCP / Agent 自主多步 | — | — | **不暴露**（§37、§76） | — | — | V4-11 |

---

## 2. 结论（缺口与处置）

```text
已可直接调用（无需改动）
  EditorService：get_node / get_history / patch / patch_batch / rewrite / regenerate /
                  accept / reject / restore / undo / diff / evaluate / plan_repair /
                  verify_repair / operations
  ReviewService：evaluate / list_issues / latest_report / stats / repair_issue
  ExportService：delivery_selection / validate_delivery / create_snapshot / deliver /
                  delivery_snapshot(s) / delivery_manifest / delivery_artifact
  BlueprintService：generate_task / regenerate / accept / read / revisions / tree /
                  validate / stats / build_links / plan

本阶段补的 Application facade（§58）
  1. `application.services.facade.ApplicationServices`：把上述能力按 novel_id 组合成一个
     依赖注入束（MCP 只认识它，不认识 blueprint / editor / quality / delivery）
  2. `ApplicationServices.summary()`：作品摘要（project + journey + blueprint/quality/
     delivery 计数）
  3. `ApplicationServices.delivery_selection(...)`：接口层用协议参数构造 DeliverySelection
     （不 import delivery）
  4. `EditorService.reviews()` / `review_for()`：评审记录只读访问
  5. `ExportService.blueprint_view(...)` + `DeliveryService.machine_representation(...)`：
     只读机器视图（有序 Blueprint + 每节点 revision / status / review / quality）

绝不能由 MCP 绕过 Application 的能力
  · BlueprintRepository / QualityStore / EditorStore / DeliveryStore 的读写
  · Generation 任务与 LLM Gateway
  · Repair Planner / Executor / Verifier
  · Delivery 的 selection / snapshot / manifest 生成
  · Canon / StoryState 任何读写
```

---

## 3. 明确 DEFER（本阶段不暴露）

```text
Story Memory resource / search_memory tool
  理由：记忆是派生数据（ADR-014），直接作为一等资源会让客户端把检索结果当事实；
        且缺少 Application 层的 memory facade（§58 要求先补 facade 再暴露）。
  计划：需要时先补 application facade（带预算与 scope 参数），再按 §12 只暴露 summary。

正文 writer（generate_draft / continue_draft / rewrite_text）
  理由：V4 Core 是 Story Blueprint，不是正文（ADR-011、§17、§71）。

legacy 导出（/export/package、/export/writer-bundle、outline export）
  理由：§72：MCP 交付只走 Application ExportService → DeliveryService。

Agent 自主多步编排（generate → evaluate → repair → accept → deliver）
  理由：§37、§76：MCP 只提供原子能力；编排属于 V4-11。
```

---

## 4. 与 REST 的关系（§8）

```text
REST (/api/story-builder/**)  ─┐
                               ├→ application.services（唯一业务入口）
MCP (interfaces/mcp)          ─┘

两者平级：MCP 不通过 HTTP 调 REST；REST 不调 MCP。
同一输入下，MCP tool 与 REST 端点调用同一 service → 结果一致（有测试断言 payload 等价）。
```

