# NovelForge V4.0.1 — Skill / Interface Gaps

> 本任务**不修 Runtime**（§4、§86）。发现的不一致一律记录在这里，继续 Skill 工作。
> 每项都给出：现象、证据、影响、建议处置（属未来产品任务）。

> **2026-09-19 更新（Skill Dogfood / Operator Acceptance）**：
> 一次"只用 skill + 公开接口"的完整演练又发现 4 个新 gap（GAP-009 … GAP-012）与
> 3 个 P0 产品缺陷（delivery preflight 不按 issue status 过滤；agent approve 后 session
> 失败；MCP stdio 入口崩溃）。完整复现、证据、优先级与 V4.0.2 backlog 见
> `docs/v4/V4_0_1_SKILL_DOGFOOD_REPORT.md`（§8–§10）与
> `docs/v4/V4_0_1_SKILL_USABILITY_MATRIX.md`。下面 4 条是本轮新增记录的摘要。

## GAP-009 REST/UI 服务无法指定隔离 project root

```text
现象：scripts/start_novelforge_ui.py 没有 --root（skill 曾写成可传，已修），
      只有浏览器门禁用的 scripts/studio_ui_test_server.py 支持 --root。
影响：新操作者无法在"不碰作者 novel/authoring/**"的前提下起一套可操作的产品面演练；
      官方 REST 路径的隔离根只能自己拼 create_app(root) composition。
处置建议：给 start_novelforge_ui.py 增加 --root，或把 test server 正式化为"演练模式"。
```

## GAP-010 quality issue 生命周期没有"随最新报告自动关闭"的语义

```text
现象：GET /studio/quality?gate=Q9 继续返回历史 issue（含已被 verify 标为 resolved 的），
      与 skill 的 "report 与 issue 列表一致" 期望冲突；delivery preflight 也因此继续阻塞
      （见 dogfood report PB-1 / PB-5）。
影响：修复后仍无法交付，且 gate 视图无法反映"当前真相"。
处置建议：issue 生命周期补自动 supersede/close；preflight 只计 open 且属于最新 report 的 issue。
```

## GAP-011 `GENERATION_UNAVAILABLE` 一个 code 表示两类原因

```text
现象："没有 enabled provider" 与"模型输出未通过 schema 校验" 都返回 422
      GENERATION_UNAVAILABLE（message 不同、code 相同）。
影响：调用方（UI / MCP / Agent）无法程序化区分"该配模型"还是"该修 provider 输出"。
处置建议：拆分稳定错误码（例如 LLM_STRUCTURED_OUTPUT_ERROR / GENERATION_NO_PROVIDER）。
```

## GAP-012 create-delivery-snapshot 与 deliver-blueprint 共用 POST /delivery

```text
现象：两个 skill 指向同一个端点，行为差异完全由参数决定（dry_run / formats / policy）。
影响：catalog 层面看不出"建快照"与"正式交付"其实是同一入口的两种参数组合。
处置建议：至少在 catalog / 接口映射里点明共用端点；或产品侧分开更明确的路由。
```

## GAP-001 `/studio/generate` 声明 dry_run 但不生效

```text
现象：GenerateBody 有 dry_run 字段，route 实现从未使用它（既不做 dry-run 校验，
      也不拒绝该参数），客户端可能以为"预览生成"不会产生 revision。
证据：src/novelforge/api/studio_routes.py（GenerateBody.dry_run / generate() 函数体）
影响：UI / Agent / MCP 客户端可能对 0-mutation 预览产生错误预期。
处置建议：要么真正实现 dry-run（0 model call / 0 revision），要么从 wire contract 移除该字段。
Skill 处理：所有 generation skill 明确写「dry_run 未实现，不要依赖」，见 generation/README.md。
```

## GAP-002 确定性因果链能力没有对外入口

```text
现象：BlueprintService.build_links（setup / payoff / causal_link）只能由代码调用。
证据：src/novelforge/generation/service.py::build_links；REST /studio/generate 的
      STUDIO_TASK_IDS 不含 links；MCP 23 个 tool 中无对应条目。
影响：Q5（Causality）/ Q7（Narrative）/ Q9（Delivery readiness）依赖 setup / payoff 数据，
      但作者与 Agent 无法从产品界面触发这一确定性步骤。
处置建议：在 future 版本把 links 暴露为显式动作（REST + MCP），保持 deterministic（无 LLM）。
Skill 处理：不创建 Skill（无可达接口）；在 generation/README.md 与
      workflows/create-new-story-blueprint 中标注为「当前不可达，需注意 setup/payoff 可能为空」。
```

## GAP-003 Canon REST 路由不经 Application Services

```text
现象：/api/story-builder/canon/* 直接 import persistence.paths + story_engine.canon
      （CanonRepository / CanonBootstrap / CanonGraphValidator）。
证据：src/novelforge/api/canon_routes.py
影响：MCP Contract §2 与 UI Contract §5 的原则是「接口层只经 application services」；
      Canon 是唯一例外。这也意味着 Canon 能力没有 MCP surface（23 tools 中无 canon）。
处置建议：补 application/services/canon.py facade 后再决定是否开放 MCP resource。
Skill 处理：canon skill 的 Authoritative interfaces 只写 REST + canonical Python API，
      MCP 写 N/A，并显式说明这是当前边界而不是疏漏。
```

## GAP-004 Memory 没有 Application facade / REST / MCP 入口

```text
现象：V4-08 inventory 把 Memory 表面记为 DEFER；至今既无 facade 也无 endpoint。
证据：docs/v4/V4_08_MCP_CAPABILITY_INVENTORY.md §3；src/novelforge/memory/**（public API 存在）
影响：作者无法在 UI 里看清「这次生成到底读了什么上下文」。
处置建议：补带预算 / scope 参数的 application facade，再考虑只暴露 summary resource。
Skill 处理：memory skill 使用 documented public Python API（MemoryService / ContextBuilder），
      并在接口列写明 UI / REST / MCP = N/A。
```

## GAP-005 插件 install / enable / disable 没有 REST / MCP 入口

```text
现象：PluginService.approve / enable / disable / discover 存在，但没有 endpoint；
      /studio/plugins 只还原样展示只读状态。
证据：src/novelforge/application/services/plugins.py；src/novelforge/api/studio_routes.py
影响：operator 只能通过 Python Application Service 执行插件生命周期动作（安全敏感操作
      故意保留在 operator 边界，属 V4-09 DEFER 决定）。
处置建议：保持 DEFER，或提供受认证的 operator-only 通道（需作者决策）。
Skill 处理：plugins skill 标注 Application-only，并在安全章节写明需显式 operator 调用。
```

## GAP-006 部分 Editor Application 能力没有 wire 入口

```text
现象：EditorService.patch_batch / move / undo / change_impact / evaluate_and_repair
      以及 ReviewService.evaluate_and_repair（QualityLoopService）没有 REST / MCP 入口。
证据：rg "patch_batch|\.move\(|undo|change_impact|evaluate_and_repair" 在 api / interfaces/mcp 无命中
影响：Agent 与 MCP 客户端只能用单节点 patch / diff / repair loop 的原子能力。
处置建议：按真实需求逐个开放（每个都需要 preserve / revision 语义说明）。
Skill 处理：不创建 Skill；change_impact 作为 patch / rewrite 返回值的一部分被描述。
```

## GAP-007 Delivery 的 explicit_revisions / include_node_types 在 UI 无入口

```text
现象：DeliveryBody 支持 explicit_revisions / include_node_types / policy 开关，UI 只暴露
      selection_mode / profile / formats / require_* 开关。
证据：src/novelforge/api/delivery_routes.py；ui/src/api/studio.ts::studioApi.deliver
影响：UI 用户无法做「只导出某些节点」的精细交付（REST / MCP 客户端可以）。
处置建议：若确有需要，在 Studio 交付页增加高级选项（保持默认 accepted）。
Skill 处理：delivery skill 注明该参数仅在 REST / Application 层可用。
```

## GAP-008 StoryState 没有产品级读写入口

```text
现象：StoryState 的 canonical 读入口是 story_engine.context.resolve_novel_context +
      memory StoryStateMemorySource；没有 REST / MCP / UI 入口，也没有产品级写入路径。
证据：src/novelforge/story_engine/{context,state,storage}.py；src/novelforge/api/**
影响：StoryState 变化只能通过历史遗留 / 引擎侧流程发生；V4 生成不写 StoryState（符合
      PLANNING != OCCURRED TRUTH 原则）。
处置建议：保持只读；若未来需要写事实，必须先走作者审批边界。
Skill 处理：story-state skill 只做只读检查 + 边界说明。
```
