# NovelForge V4.0.1 — Interface Map（UI / REST / Application / MCP）

> 来源（运行期真实状态）：`create_app(...)` 的 route 表、`ui/src/api/studio.ts`、
> `ui/src/studio/nav.ts`、`build_tool_registry()`、`build_resource_registry()`。
> 不存在的接口一律写 `N/A`，禁止虚构。
> REST 前缀省略重复部分：`/studio/*` = `/api/story-builder/studio/*`，`/editor/*` =
> `/api/story-builder/editor/*`，`/delivery/*` = `/api/story-builder/delivery/*`，
> `/agent/*` = `/api/story-builder/agent/*`，`/canon/*` = `/api/story-builder/canon/*`。

## 1. 用户动作 → 接口

| User Action | UI | REST | Application | MCP |
| --- | --- | --- | --- | --- |
| 打开 Story Studio | `#/studio`（Landing） | `GET /` | — | N/A |
| 新建作品 | 「新建作品」→ `studioApi.createNovel` | `POST /novels` | `ProjectService.create_novel` | N/A |
| 列出 / 选择作品 | Landing 作品卡 | `GET /novels` | `ProjectService.list_novels` | resource `novelforge://novels/{novel_id}`（单个摘要） |
| 查看作品档案 | Overview / Studio 头部 | `GET /novels/{novel_id}` | `ProjectService.get_novel` | resource `novelforge://novels/{novel_id}` |
| 重命名作品 | Studio 头部 | `PATCH /novels/{novel_id}` | `ProjectService.rename_novel` | N/A |
| 删除（归档）作品 | 「删除」+ 二次确认 | `DELETE /novels/{novel_id}?confirm=true` | `ProjectService.archive_novel` | N/A |
| 看总览 / 下一步 | 「总览」 | `GET /studio/overview` | `ExportService.blueprint_view` + `ReviewService` + `JourneyService.next_action` | resource `novelforge://novels/{novel_id}` |
| 看蓝图某一类节点 | 世界 / 人物 / 故事 / 场景页 | `GET /studio/blueprint?node_type=` | `ExportService.blueprint_view` | resource `.../blueprint`、`.../scenes` |
| 看单个节点 | 节点抽屉 | `GET /editor/nodes/{node_id}` | `EditorService.get_node` | resource `.../blueprint/nodes/{node_id}` |
| 看 revision 历史 / 评审 | 节点抽屉「历史」 | `GET /editor/nodes/{node_id}/revisions` | `EditorService.get_history` | resource `.../revisions/{revision}`、resource `.../review` |
| 比较两个 revision | 节点抽屉 diff | `GET /editor/nodes/{node_id}/diff` | `EditorService.diff` | tool `diff_revisions` |
| 生成前提 / 主题 | 「创造」 | `POST /studio/generate` | `BlueprintService.generate_task` | tools `generate_premise` / `generate_theme` |
| 生成世界 | 「世界」 | 同上 | 同上 | tool `generate_world` |
| 生成人物 / 人物弧 | 「人物」 | 同上 | 同上 | tools `generate_character` / `generate_character_arc` |
| 生成故事弧 / 结构单元 / 章节卡 | 「故事」 | 同上 | 同上 | tools `generate_story_arc` / `generate_structural_unit` / `generate_chapter_plan` |
| 生成场景卡 | 「场景」 | 同上 | 同上 | tool `generate_scene_plan` |
| 重新生成节点 | 节点抽屉「重新生成」 | `POST /studio/generate`（node_id + expected_revision） | `BlueprintService.regenerate` / `EditorService.regenerate` | tool `regenerate_blueprint_node` |
| 手改字段 | 节点抽屉编辑 | `PATCH /editor/nodes/{node_id}` | `EditorService.patch` | tool `patch_blueprint_node` |
| AI 改写字段 | 节点抽屉「AI 改写」 | `POST /editor/nodes/{node_id}/rewrite` | `EditorService.rewrite` | tool `rewrite_blueprint_node` |
| 接受 revision | 节点抽屉「接受」 | `POST /editor/nodes/{node_id}/accept` | `EditorService.accept` | tool `accept_revision` |
| 拒绝 revision | 节点抽屉「拒绝」 | `POST /editor/nodes/{node_id}/reject` | `EditorService.reject` | tool `reject_revision` |
| 恢复历史 revision | 节点抽屉「恢复」 | `POST /editor/nodes/{node_id}/restore` | `EditorService.restore` | tool `restore_revision` |
| 跑质量检查 | 「检查」→ 运行检查 | `POST /studio/quality/evaluate` | `ReviewService.evaluate` | tool `evaluate_blueprint` |
| 看质量报告 / issue | 「检查」 | `GET /studio/quality` | `ReviewService.latest_report` / `list_issues` | resources `.../quality`、`.../quality/issues` |
| 看单节点质量 | 节点抽屉 | `GET /editor/nodes/{node_id}/quality` | `EditorService.get_quality` | resource `.../blueprint/nodes/{node_id}` |
| 修复预览 | 「检查」→ 修复预览 | `POST /studio/quality/repair`（`dry_run=true`） | `EditorService.plan_repair` | tool `plan_repair` |
| 执行修复 | 「检查」→ 执行修复 | `POST /studio/quality/repair` | `EditorService.repair` | tool `repair_issue` |
| 复核修复 | 「检查」→ 复核 | `POST /studio/quality/verify` | `EditorService.verify_repair` | tool `verify_repair` |
| 看交付格式 | 「交付」 | `GET /studio/delivery/formats` | `ExporterRegistry.specs` | N/A |
| 交付预检 | 「交付」→ 预检 | `POST /delivery`（`dry_run=true`） | `ExportService.deliver` | tool `validate_delivery` |
| 建立交付 / 快照 | 「交付」→ 交付 | `POST /delivery` | `ExportService.deliver` / `create_snapshot` | tools `create_delivery_snapshot` / `deliver_blueprint` |
| 看快照 / manifest | 「交付」列表 | `GET /delivery/snapshots`、`GET /delivery/{snapshot_id}/manifest` | `ExportService.delivery_snapshots` / `delivery_manifest` | resources `.../delivery`、`.../delivery/{snapshot_id}/manifest` |
| 下载交付物 | 「下载」 | `GET /delivery/{snapshot_id}/artifacts/{artifact_path}` | `ExportService.delivery_artifact` | resource `.../delivery/{snapshot_id}/artifacts/{artifact_path}` |
| 看插件状态 | 「插件」 | `GET /studio/plugins` | `PluginService.list_plugins` / `status` / `permission_model` | N/A |
| 批准 / 启用 / 禁用插件 | N/A（operator 接口） | N/A（DEFER） | `PluginService.approve` / `enable` / `disable` | N/A |
| Agent 计划预览 | 「Agent」→ 计划 | `POST /agent/plan` | `AgentService.plan` | N/A |
| Agent 启动 / 恢复 / 取消 | 「Agent」→ 执行 | `POST /agent/start`、`/agent/{session_id}/resume`、`/cancel` | `AgentService.start` / `resume` / `cancel` | N/A |
| Agent 审批 / 拒绝 | 「Agent」→ 批准 | `POST /agent/{session_id}/approve`、`/reject` | `AgentService.approve` / `reject` | N/A |
| Agent session 列表 / 详情 / 审计 | 「Agent」 | `GET /agent/sessions`、`GET /agent/{session_id}` | `AgentService.history` / `status` / `audit_records` | N/A |
| 查看 Canon 事实 / 事件 / 实体 / 知识 / 伏笔 | N/A（无 current UI） | `GET /canon/facts`、`/events`、`/entities`、`/knowledge`、`/foreshadows` | api 直连 `CanonRepository`（frozen canonical 读） | N/A |
| Canon 图 / 校验 | N/A | `GET /canon/graph`、`GET /canon/validate` | `CanonGraph` / `CanonGraphValidator` | N/A |
| Canon 重建 | N/A | `POST /canon/rebuild` | `CanonBootstrap.rebuild` | N/A |
| 规划对照 Canon | N/A | `POST /canon/validate-outline` | `validate_chapter_plan` + `SourceReferenceValidator` | N/A |
| 记忆检索 | N/A | N/A（DEFER） | `MemoryService.search` | N/A |
| 生成上下文装配 | N/A（generation 内部） | N/A | `ContextBuilder.build` | N/A |
| 配置模型 provider | N/A（改配置 + 重启） | N/A | `load_provider_configs` | N/A |
| 机器调用（工具） | N/A | 与 REST 平级 | `ApplicationServices` | 23 tools |
| 机器读取（资源） | N/A | 与 REST 平级 | `ApplicationServices` | 13 resources |
| 健康检查 | N/A | `GET /api/health` | — | N/A |

## 2. 前缀与版本事实

```text
REST 命名空间（唯一）：/api/story-builder/{novels,canon,editor,delivery,studio,agent} + /api/health
MCP：server=novelforge，stdio（python -m novelforge.interfaces.mcp），MCP_INTERFACE_VERSION=1
MCP 基线：23 tools / 13 resources（1 static + 12 template）
REST 与 MCP 平级：都只调用 application services，谁都不通过 HTTP 调对方
```

## 3. Skill 中必须使用的调用纪律

```text
优先 UI → REST → Application Service → MCP（按其存在性）
不直接编辑 Blueprint / Quality / Editor / Delivery 的落盘文件
不猜当前作品：每次调用显式携带 novel_id
mutation 调用带 expected_revision 与 idempotency_key
```
