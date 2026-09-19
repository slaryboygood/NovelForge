# NovelForge V4.0.1 — Current Feature Usage Catalog

> 阶段：**V4.0.1 Feature Usage Documentation + Modular Skill Library**
> 基线：`SKILL_BASELINE_START = afc57d8`（= tag `v4.0.1` = `main` = `v4`）
> 判据：`DISK STATE WINS / CURRENT CONTRACT WINS / CURRENT TESTS WIN / GIT GRAPH WINS`
> 本文件只描述**当前真实存在**的能力。V2/V3 Story Builder 后端已退休，不出现在本表。

## 1. 能力总表（Capability Inventory）

风险列：`low` = 只读或可回滚；`medium` = 产生 revision / 质量结论；`high` = 触碰交付物、
作品归档、插件启用或需要作者决定。

| Capability | Use Case | Owner Module | UI | REST | Application | MCP | Input | Output | Risk |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Project | 列出作品 | `application/services/project.py` | Studio Landing | `GET /api/story-builder/novels` | `ProjectService.list_novels` | — | — | novel summaries | low |
| Project | 新建作品 | 同上 | 「新建作品」 | `POST /api/story-builder/novels` | `ProjectService.create_novel` | — | `novel_id`(3..96) / title / genre / template_id / content_pack_id | novel profile | low |
| Project | 查看作品档案 | 同上 | Overview | `GET /api/story-builder/novels/{novel_id}` | `ProjectService.get_novel` | resource `novelforge://novels/{novel_id}`（摘要） | `novel_id` | profile | low |
| Project | 重命名作品 | 同上 | Studio 头部 | `PATCH /api/story-builder/novels/{novel_id}` | `ProjectService.rename_novel` | — | title(1..120) | profile（只改名字） | low |
| Project | 归档作品（删除按钮） | `application/services/novel_admin.py` | 「删除」+ 二次确认 | `DELETE /api/story-builder/novels/{novel_id}?confirm=true` | `ProjectService.archive_novel` | — | `confirm=true`（+ reason） | archive 结果（可恢复） | high |
| Studio | 打开产品面 | `ui/src/studio/StudioApp.tsx` | `http://127.0.0.1:8000/` → `#/studio` | `GET /` | — | — | — | Story Studio | low |
| Studio | 深链接工作区 | `ui/src/studio/nav.ts` | `#/studio/n/{novelId}/{view}` | — | — | — | novel_id + view | 视图（刷新不丢位置） | low |
| Studio | 总览 / 下一步 | `ui/src/studio/workspaces/Overview.tsx` | 「总览」 | `GET /api/story-builder/studio/overview` | `ExportService.blueprint_view` + `ReviewService` + `JourneyService.next_action` | resource `.../blueprint` | novel_id, mode | counts / gates / next_action | low |
| Studio | 旧 URL 回落 | `ui/src/App.tsx` | `?ui=v3` / `#/v3…` / `?ui=v2` / `#/story-builder…` | — | — | — | 旧 hash / query | 归一化到 Studio（不 404、无第二套 UI） | low |
| Blueprint | 查看蓝图节点列表 | `blueprint/repository.py` | 世界 / 人物 / 故事 / 场景页 | `GET /studio/blueprint` | `ExportService.blueprint_view` | resource `.../blueprint` | novel_id, node_type?, mode | 有序节点 + visible + 状态 | low |
| Blueprint | 查看场景卡 | 同上 | 「场景」页 | `GET /studio/blueprint?node_type=scene` | 同上 | resource `.../scenes` | novel_id | 场景 visible 字段 | low |
| Blueprint | 查看单节点 | 同上 | 节点抽屉 | `GET /editor/nodes/{node_id}` | `EditorService.get_node` | resource `.../blueprint/nodes/{node_id}` | novel_id, node_id, revision? | node + editable/protected fields + quality | low |
| Blueprint | 查看 revision 历史 | `blueprint/repository.py` | 节点抽屉 | `GET /editor/nodes/{node_id}/revisions` | `EditorService.get_history` | resource `.../revisions/{revision}` | novel_id, node_id | revisions + operations | low |
| Blueprint | 结构化 diff | `editor/diff.py` | 节点抽屉 | `GET /editor/nodes/{node_id}/diff` | `EditorService.diff` | tool `diff_revisions` | from_revision, to_revision? | field / list changes + quality delta | low |
| Generation | 生成前提 / 主题 | `generation/tasks/premise.py` | 「创造」 | `POST /studio/generate` | `BlueprintService.generate_task` | tools `generate_premise` / `generate_theme` | novel_id, task / node_type | 新节点（status=proposed, r1） | medium |
| Generation | 生成世界 | `generation/tasks/world.py` | 「世界」 | 同上 | 同上 | tool `generate_world` | novel_id | 同上 | medium |
| Generation | 生成人物 | `generation/tasks/characters.py` | 「人物」 | 同上 | 同上 | tool `generate_character` | + index / sequence | 同上 | medium |
| Generation | 生成人物弧 | 同上 | 「人物」 | 同上 | 同上 | tool `generate_character_arc` | parent character node | 同上（`character_id` 系统分配） | medium |
| Generation | 生成故事弧 | `generation/tasks/story.py` | 「故事」 | 同上 | 同上 | tool `generate_story_arc` | novel_id | 同上 | medium |
| Generation | 生成结构单元 | 同上 | 「故事」 | 同上 | 同上 | tool `generate_structural_unit` | unit_type, index | 同上 | medium |
| Generation | 生成章节卡 | `generation/tasks/chapter.py` | 「故事」 | 同上 | 同上 | tool `generate_chapter_plan` | parent unit, index | 同上 | medium |
| Generation | 生成场景卡 | `generation/tasks/scene.py` | 「场景」 | 同上 | 同上 | tool `generate_scene_plan` | parent chapter, sequence | 同上 | medium |
| Generation | 重生成已有节点 | `generation/service.py` | 节点抽屉「重新生成」 | `POST /studio/generate`（node_id + expected_revision） | `BlueprintService.regenerate` | tool `regenerate_blueprint_node` | node_id, expected_revision | 新 revision（proposed） | medium |
| Generation | 确定性因果链（setup / payoff / causal_link） | `generation/tasks/links.py` | N/A | N/A | `BlueprintService.build_links` | N/A | chapter_ids? | setup / payoff / causal_link 节点 | medium |
| Memory | 派生记忆检索 | `memory/service.py` | N/A | N/A（DEFER） | `MemoryService.search` | N/A | `MemoryQuery` + novel_id | `MemoryResult`（带 source_ids / revision） | low |
| Memory | 生成上下文装配 | `memory/context/builder.py` | N/A | N/A | `ContextBuilder.build`（generation 内部消费） | N/A | `ContextRequest` | `ContextBundle`（blocks + digest） | low |
| Memory | 记忆新鲜度 / 重建 | `memory/service.py` | N/A | N/A | `MemoryService.rebuild` / `stale_report` | N/A | novel_id | stale 报告 / 重建结果 | low |
| Quality | 运行 Q0–Q9 质量门禁 | `quality/service.py` + `quality/evaluators/*` | 「检查」→ 运行检查 | `POST /studio/quality/evaluate` | `ReviewService.evaluate` | tool `evaluate_blueprint` | novel_id, gates?, node_ids? | `QualityReport`（gate + issue + evidence） | medium |
| Quality | 查看报告 / issue 列表 | `quality/store.py` | 「检查」 | `GET /studio/quality` | `ReviewService.latest_report` / `list_issues` | resources `.../quality`、`.../quality/issues` | gate?, status? | report / issues | low |
| Quality | 查看单节点质量 | 同上 | 节点抽屉 | `GET /editor/nodes/{node_id}/quality` | `EditorService.get_quality` | resource `.../blueprint/nodes/{node_id}` | revision? | issues + blocking codes | low |
| Repair | 修复预览（dry run） | `quality/repair/planner.py` | 「检查」→ 修复预览 | `POST /studio/quality/repair`（`dry_run=true`） | `EditorService.plan_repair` | tool `plan_repair` | issue_ids / node_id | `RepairPlan`（target / preserve / allow_change） | low |
| Repair | 执行修复 | `quality/repair/executor.py` | 「检查」→ 执行修复 | `POST /studio/quality/repair` | `EditorService.repair` | tool `repair_issue` | issue_ids, idempotency_key | 新 revision + repair 记录 | medium |
| Repair | 复核修复 | `quality/repair/verifier.py` | 「检查」→ 复核 | `POST /studio/quality/verify` | `EditorService.verify_repair` | tool `verify_repair` | issue_ids | resolved / remaining / regressed | low |
| Editor | 字段级修改（patch） | `editor/patch.py` | 节点抽屉编辑 | `PATCH /editor/nodes/{node_id}` | `EditorService.patch` | tool `patch_blueprint_node` | changes + expected_revision | 新 revision（proposed） | medium |
| Editor | AI 字段级改写 | `generation/rewrite.py` | 节点抽屉「AI 改写」 | `POST /editor/nodes/{node_id}/rewrite` | `EditorService.rewrite` | tool `rewrite_blueprint_node` | target_fields + instruction | 新 revision（只改 target） | medium |
| Editor | 接受 revision | `editor/service.py` | 节点抽屉「接受」 | `POST /editor/nodes/{node_id}/accept` | `EditorService.accept` | tool `accept_revision` | revision? | status=accepted + 新 revision | high |
| Editor | 拒绝 revision | 同上 | 节点抽屉「拒绝」 | `POST /editor/nodes/{node_id}/reject` | `EditorService.reject` | tool `reject_revision` | revision, reason | review 记录（不改内容） | low |
| Editor | 恢复历史 revision | `editor/history.py` | 节点抽屉「恢复」 | `POST /editor/nodes/{node_id}/restore` | `EditorService.restore` | tool `restore_revision` | from_revision | 新 revision（历史不删） | medium |
| Editor | 变更影响 / 质量失效 | `editor/impact.py` | 节点抽屉提示 | N/A（随 patch / rewrite 返回） | `EditorService.change_impact` | — | node_id | dependents + invalidations | low |
| Delivery | 交付预检（不落盘） | `delivery/validation.py` | 「交付」preflight | `POST /delivery`（`dry_run=true`） | `ExportService.deliver` | tool `validate_delivery` | selection_mode / profile / formats | validation + blocking_reason | low |
| Delivery | 建立交付快照 | `delivery/store.py` | 「交付」→ 交付 | `POST /delivery` | `ExportService.deliver` / `create_snapshot` | tools `create_delivery_snapshot` / `deliver_blueprint` | formats, selection_mode, profile | snapshot + manifest + artifacts | high |
| Delivery | 查看快照 / manifest | `delivery/manifest.py` | 「交付」列表 | `GET /delivery/snapshots`、`GET /delivery/{snapshot_id}/manifest` | `ExportService.delivery_snapshots` / `delivery_manifest` | resources `.../delivery/**` | novel_id, snapshot_id | snapshot / manifest（checksum） | low |
| Delivery | 下载交付物 | `delivery/exporters/*` | 「下载」 | `GET /delivery/{snapshot_id}/artifacts/{path}` | `ExportService.delivery_artifact` | resource `.../artifacts/{artifact_path}` | snapshot_id, artifact_path | 文件字节（json / md / docx / nfpack） | low |
| Delivery | 交付格式清单 | `delivery/exporters/__init__.py` | 「交付」格式勾选 | `GET /studio/delivery/formats` | `ExporterRegistry.specs` | — | novel_id | 格式 + profile + owner | low |
| Canon | 查看 Canon 事实 / 事件 / 实体 / 知识 / 伏笔 | `story_engine/canon/repository.py` | N/A（无 current UI） | `GET /canon/facts`、`/events`、`/entities`、`/knowledge`、`/foreshadows` | api 层直连 `CanonRepository` | N/A | novel_id, limit / offset | Canon 记录 | low |
| Canon | Canon 图 / 校验 | `story_engine/canon/graph.py`、`validator.py` | N/A | `GET /canon/validate`、`GET /canon/graph` | `CanonGraphValidator` / `SourceReferenceValidator` | N/A | novel_id | findings / 图摘要 | low |
| Canon | Canon 重建（受控 mutation） | `story_engine/canon/bootstrap.py` | N/A | `POST /canon/rebuild` | `CanonBootstrap.rebuild` | N/A | state / content_pack / profile | rebuild 结果（失败保留原 DB） | high |
| Canon | 规划对照 Canon | `story_engine/canon/gate.py` | N/A | `POST /canon/validate-outline` | `validate_chapter_plan` + `SourceReferenceValidator` | N/A | chapters, temporal_cutoff | findings + duplicate candidates | low |
| StoryState | 读取 StoryState / 档案 / 模板 | `story_engine/state.py`、`profile.py`、`storage.py`、`templates.py` | 间接（生成上下文） | N/A | 经 `memory` / `generation` 消费 | N/A | novel_id | profile / state / 模板 | low |
| Plugins | 查看插件只读状态 | `plugins/manager.py` + `application/services/plugins.py` | 「插件」 | `GET /studio/plugins` | `PluginService.list_plugins` / `status` | N/A | — | 插件 + trust model + permissions | low |
| Plugins | 查看贡献（exporter / evaluator / MCP） | `plugins/adapters/*` | 「插件」（随列表） | N/A | `PluginService.contributions` | N/A | type? | contributions | low |
| Plugins | 批准插件 | `plugins/lifecycle.py` | N/A（operator 接口） | N/A（DEFER） | `PluginService.approve` | N/A | plugin_id, permissions | 批准记录（含 permission 集） | high |
| Plugins | 启用 / 禁用插件 | 同上 | N/A | N/A（DEFER） | `PluginService.enable` / `disable` | N/A | plugin_id（+ reason） | 状态 + 精确卸载 | high |
| Agent | 计划预览（0 mutation） | `agent/planner.py` + `application/services/agent.py` | 「Agent」 | `POST /agent/plan` | `AgentService.plan` | N/A（MCP 不暴露编排） | instruction, scope, policy | plan + steps（预览） | low |
| Agent | 启动有界执行 | `agent/executor.py` | 「Agent」→ 执行 | `POST /agent/start` | `AgentService.start` | N/A | session_id, max_batch_steps | 执行结果 / 审批请求 | medium |
| Agent | 审批 / 拒绝 protected step | `agent/policy.py` | 「Agent」→ 批准 | `POST /agent/{session_id}/approve`、`/reject` | `AgentService.approve` / `reject` | N/A | approval_id | 继续或终止 | high |
| Agent | 恢复 / 取消 session | `agent/checkpoint.py` | 「Agent」→ 恢复 | `POST /agent/{session_id}/resume`、`/cancel` | `AgentService.resume` / `cancel` | N/A | session_id | checkpoint 续跑 / 终止 | medium |
| Agent | 查看 session 与审计 | `agent/audit.py` | 「Agent」列表 | `GET /agent/sessions`、`GET /agent/{session_id}` | `AgentService.history` / `status` | N/A | novel_id, session_id | session 状态 + audit | low |
| MCP | 启动 MCP server | `interfaces/mcp/server.py` | N/A | N/A | 注入 `ApplicationServices` | 23 tools / 13 resources | project_root | stdio transport | low |
| MCP | 发现工具 / 资源 | `interfaces/mcp/registry.py` | N/A | N/A | 同上 | tool 表 / resource 表 | — | 元数据（`novelforge://interface`） | low |
| MCP | 读资源 / 调用工具 | `interfaces/mcp/{resources,tools}/*` | 与 REST 平级 | 与 REST 等价 | 同上 | 13 resources / 23 tools | URI / tool 参数 | JSON / 文件 / Result Envelope | medium |
| AI | 配置 provider | `ai/config.py` + `novel/config/ai/providers.json` | N/A | N/A | `load_provider_configs` | N/A | provider 条目（enabled / base_url / api_key_env） | `ProviderRegistry` | high |
| AI | 未配置模型时的稳定行为 | `ai/gateway.py` | 「创造」错误提示 | `POST /studio/generate` → `GENERATION_UNAVAILABLE`（422） | `LLMGateway` | 同名 tool 同错误码 | — | 稳定错误码（不静默降级） | low |
| AI | usage / trace / cache 观测 | `ai/{usage,trace,cache}.py` | N/A | N/A（随结果返回） | `LLMGateway` 结果字段 | Result Envelope `usage` | — | usage / trace / cache 命中 | low |

## 2. 当前不存在的接口（明确 N/A，禁止写进 Skill 作为 current 能力）

```text
正文写作：generate_draft / continue_draft / rewrite_text / write_chapter
legacy 导出：planning export / outline export / writer bundle
V3 Command Center / Journey 投影消费入口、v3_projection
V2 guided flow / session / design tree / route_lab / inspector
插件 install / enable / disable 的 REST 与 MCP 入口（DEFER，仅 Application Service）
Memory 的 REST / MCP surface（DEFER）
Agent 多步编排的 MCP tool（DEFER）
```

## 3. 与 frozen boundary 的关系

```text
本表不含任何 Canon / StoryState / legacy 源 / source Chapter IR 的「写入新事实」能力。
Canon rebuild 是唯一受控 mutation 入口（operator 显式调用，失败保留原 DB）。
quality pass ≠ author accepted（ADR-022）；交付默认 accepted 且 revision-pinned（ADR-024/025）。
```
