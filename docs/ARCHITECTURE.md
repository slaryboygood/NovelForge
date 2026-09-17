# NovelForge — 架构

> 本文件是架构 SSOT。当前产品状态与版本历史见 `README.md` 与 `docs/CHANGELOG.md`；
> 数据权威关系见 `docs/DATA_MODEL.md`；兼容边界见 `docs/LEGACY_COMPAT.md`。

## 分层

```text
Domain（故事引擎）
   StoryState / 行动-条件-效果 / 事件 / 延迟后果 / 伏笔 / 成长 / 导演 / 路线事实 / 大纲
        ↓  只读投影 + 受控操作
Application（应用层）
   设定生成与自检 · 会话与蓝图 · ui_flow（UI 只读投影）· inspector（检查 / 修复诊断）
   export_package（Planning Export）· writer_integration（Writer context / draft / fact sync）
   cross_genre_e2e（跨题材验证 harness）
   v3_projection（V3 工作台只读投影：Command Center / 实体 / 推演 / 大纲 / 检查 / 导出就绪度）
        ↓  typed DTO
API（FastAPI）
   src/novelforge/api/story_builder_routes.py（唯一业务入口：/api/story-builder/*）
        ↓  typed payloads
UI（React + TypeScript）
   ui/src/v3/（Novel Landing → Command Center → 工作区 · Design System · ViewModel）
   ui/src/（既有面板：高级工具 bridge）
```

依赖方向单向：**UI → API → Application → Domain**。
UI 不解析 Canon / 不判断 StoryState truth / 不读 repair artifact；需要新投影时先加应用层。

## V3 工作台（当前产品界面）

```text
入口            ui/src/v3/V3App.tsx（URL 路由唯一解析入口：navModel.parseRoute）
应用层投影      src/novelforge/story_builder/v3_projection.py（只读）
ViewModel       ui/src/v3/viewmodel.ts（DTO → ViewModel：文案 / 状态语义 / 排序，不做 domain 判断）
Design System   ui/src/v3/design-system/（tokens · Card · Button · Progress · Badge ·
                IconRegistry · ObjectiveCard · NextActionCard · EntityVisual · ContextPanel）
视觉资源契约    design-system/assets/artworkManifest.ts
                real story asset → product default artwork → semantic icon
```

工作区（每个都遵循「ONE SCREEN / ONE PRIMARY GOAL / ONE PRIMARY CTA」）：

```text
Novel Landing · Command Center · Creation · World · Characters · Story ·
Simulation · Outline/Chapter · Review/Repair · Export · Advanced Tools（bridge）
```

Objective / Next Action 属于**应用层派生状态**：完成度只来自真实 state / validation /
deterministic rules，不由 LLM 决定。

## Domain（Story Engine）

| 区域 | 模块 | 职责 |
| --- | --- | --- |
| 状态 | `story_engine/state.py`、`storage.py` | StoryState（world / timeline / location / characters / relationships / knowledge / resources / abilities / factions / flags / promises / events / effect_log / delayed_effects）；单进程原子写 |
| 因果 | `actions.py`、`conditions.py`、`effects.py`、`resolver.py` | 行动合法性由引擎判定；事务与回滚；客户端不能自证 |
| 事件 | `events.py`、`delayed.py` | 事件卡与触发、延迟后果 |
| 伏笔 / 成长 | `foreshadow.py`、`progression.py` | 生命周期与七类 progression |
| 调度 | `director.py`、`characters.py` | 候选池评分、节奏、角色决策上下文与反应 |
| 路线 | `route_lab.py` | 分支试演 / 对比 / 合并 / 冻结（分支事实独立存储） |
| 大纲 | `outline_forge.py`、`outline_revision.py`、`outline_export` | 四级大纲（BOOK → VOLUME → ARC → CHAPTER）+ 版本 / 修订 / 导出 |
| 实例分层 | `profile.py`、`templates.py`、`content.py`、`wizard.py`、`linkage.py` | NovelProfile / Genre Template / ContentPack / 路线事实 → 大纲联动 |
| 历史层（**V4-01 起仅保留源码，不再是产品路径**） | `historical_ir.py`、`repair.py`、M11/M12 服务 | 570 章 Historical Chapter IR、repair replay、冻结的修复 lineage；对应数据资产已在 V4-01 删除（作者决策 B），产品侧不再引用 |

## Application

| 组件 | 文件 | 说明 |
| --- | --- | --- |
| UI 只读投影 | `story_builder/ui_flow.py` | 引导流状态、设定影响范围、设定总览、区域卡、关系图；`GET /guided-flow`、`/settings/impact|overview|regions|relationships` |
| Inspector / Repair | `story_builder/inspector.py` | 跨层只读检查（Canon / StoryState / 570 章历史 IR + provenance）与修复诊断；`GET /inspector/*`、`/repair/diagnosis|history` |
| Planning Export | `story_builder/export_package.py` | 单一 export projection（Story Bible / 卡片 / Timeline / 四级大纲 / planning / canon_refs）+ json/markdown/docx serializer + validation。**V4-01 起不再包含 spine / historical_ir 分区**（历史资产已删除，跨作品污染缺陷 NR-002 已结构性修复）；唯一调用入口是 `application.services.export.ExportService` |
| Writer Integration | `story_builder/writer_integration.py` | `WriterContextBuilder`（6 层 truth block + 去重 + 预算）、草稿入口、Draft Fact Sync（proposal-only） |
| Writer Store（SSOT） | `story_builder/writer_integration.py` | 写作草稿的**唯一**存储：`novel/authoring/story_engine/writer/<novel_id>/index.json` + `drafts/*.json`。写入（`WriterDraftService`）与读取（`v3_projection` 投影、导出、UI）共用同一个常量。**V4-01 起不再有历史目录回退**（`workspace/wasteland_001_exports/writer_v1` 已删除）；注意草稿属于 preview 层，V4 的 canonical 创作产物是 Story Blueprint（ADR-011） |
| 作者语言映射 | `novelforge/author_language.py` | 内部标识 → 作者语言的**唯一**展示层映射（角色 / 地点 / 支线 / 伏笔 / 资源 / 状态 / 行动类别）。引擎生成文案、V3 投影、导出与 API 错误文案全部走它，避免同一 id 在不同位置一半被翻译 |
| 作品级管理 | `story_builder/novel_admin.py` | 重命名（只改 `NovelProfile.title`）与删除（= 整体归档到 gitignored `workspace/archived_novels/`，可恢复、不留孤儿产物） |
| 跨题材验证（Cross-genre E2E） | `story_builder/cross_genre_e2e.py` | `CrossGenreE2ECase` / `CrossGenreE2ERunner`：3 题材 13 步产品链；Inspector / Repair / Planning Export / Writer Integration 均由本层统一提供入口 |
| 会话 / 蓝图 | `story_builder/sessions.py`、`blueprints.py`、`design_tree.py` | 十步目录、设计树、蓝图编译（设计态） |
| Milestone 验收 | `story_engine/milestone_acceptance.py`、`m1X_*.py` | freeze guard / baseline / phase snapshot（write-once）/ acceptance / readiness |
| V3 工作台投影 | `story_builder/v3_projection.py` | Command Center / 作者旅程 / Objective / Next Action / 实体（角色·地点·势力·关系）/ 推演 / 大纲与章节 / 检查与修复 / 导出就绪度；全部只读，供 `ui/src/v3/` 消费 |

## API 边界

```text
GET  /api/story-builder/...            只读投影（catalog / creator 面板 / inspector / repair 诊断 / export / writer context）
POST /api/story-builder/...            受控操作（novels / sessions / runtime / outline / repair 执行 / writer drafts）
```

* 写操作只调用既有正式能力（ActionResolver / outline forge / settings repair / writer draft）。
* Inspector 与诊断只读；Repair Center 执行仅走 `settings/check{repair:true}`，高风险项交作者。
* Writer 事实提议（`sync-facts`）只产生 `PROPOSED`，不写 StoryState / Canon。
* 服务器只挂载 `/api/story-builder/*`、`/api/health`、首页与静态资源。

## UI 边界

```text
V3 工作台（ui/src/v3/）  Novel Landing / Command Center / Creation / World / Characters /
                      Story / Simulation / Outline / Review / Export（见上节）
StoryBuilderPage      既有面板（高级工具 bridge）：分组页签 + 顶部阶段条
GuidedFlowPanel       单页引导流（创意 → 设定 → 自检 → 开始推演）
共享组件              CandidateCard（候选卡）、TruthLayerBadge（事实层标签）、ProvenanceList（出处）、
                      useApiData/PanelState（加载 / 错误 / 空状态）
可视化                VisualOverviewPanels（总览 / 区域 / 关系）、VisualOutputPanels（路线对比 / 大纲树 / 参考位）
检查与修复            InspectorPanels（Canon 检查器 / 修复中心）
深链接               guidedFlow.ts（novel_id / tab / branch_id / package_id / step / group 的 parse / serialize / restore）
```

导出工作区（`ui/src/v3/ExportFlow.tsx`）调用既有 `GET /export/package` 生成真实产物
（文件名 / 内容预览 / 下载）并管理写作草稿；`StoryBuilderPage` 对未知页签回落到默认面板，
不允许渲染空壳。Stage / Progress / Next Action 只有 `v3_projection._journey_projection()`
一个计算入口，Landing 卡片与 Command Center 都消费它。

## 验收与冻结基础设施

```text
PhaseSnapshotStore（story_engine/phase_snapshot.py）
  phase-scoped write-once snapshot + digest manifest + immutability 校验
milestone_acceptance.publish_phase_snapshot
  M13–M18 共用的 snapshot 发布（首次写入 / 幂等重跑 / 显式 maintenance refresh）
每个 milestone（M11–M18）
  baseline → preflight（freeze guard）→ 执行 → acceptance → readiness；artifact 只读且可重放

Release（V2 / V3）
  Product V2：M18 acceptance + freeze → release manifest（deterministic）→ tag（历史，见 LEGACY_COMPAT）
  Product V3：P0–P6 验收 + Visual Asset Gate → release commit + tag
  （证据：docs/V3_FULL_PRODUCT_ACCEPTANCE.json；不新增 milestone、不改 frozen truth）
```

## 测试与验收

```text
默认套件            pytest（当前产品测试；自包含，不需要本机作者数据）
V4 边界守卫          pytest -q tests/v4（跨作品隔离 / 废弃资产 / 模块依赖，默认运行）
历史里程碑验收       已随废弃资产删除（V4-01；marker 保留给 V4 里程碑复用）
浏览器门禁          tests/browser_v3_p0|p2|p3|p4|p5|p6_acceptance.cjs、
                    tests/browser_v3_visual_asset_gate.cjs、tests/browser_advanced_tools.cjs
Frozen guard        tests/test_v2_frozen_guard.py（V2 tag / release 记录 / authoring 未漂移）、
                    tests/test_v3_frozen_guard.py（route_lab 只读放宽边界）
视觉契约            tests/test_v3_visual_asset_contract.py + docs/V3_VISUAL_ASSET_REQUIREMENTS.json
```

## 部署与限制

* 单服务进程；写入使用原子替换与单进程锁，不承诺跨进程事务。
* `workspace/` 与 `novel/authoring/` 为运行 / 作者数据；frozen 证据不可修改。
* 不在引擎内做题材判断（源码守卫：`tests/test_story_engine_cross_genre.py`、
  `tests/test_story_engine_templates.py`）；题材差异只能来自 Template / ContentPack / NovelProfile。
