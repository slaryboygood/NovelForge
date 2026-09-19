# NovelForge V4.0.1 — Skill / Interface Gaps

> 本任务**不修 Runtime**（§4、§86）。发现的不一致一律记录在这里，继续 Skill 工作。
> 每项都给出：现象、证据、影响、建议处置（属未来产品任务）。

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
