# NovelForge V4-11 — Agent Capability Inventory

> 状态：**V4-11 Agent Mode 盘点（编码前完成）**
> 依据：任务书 §7；`docs/v4/V4_AGENT_CONTRACT.md`（本阶段 SSOT）
> 结论：Agent 只用**已有** Application 能力；不新增业务语义，不通过 MCP 调业务。

---

## 1. Agent 原子能力（来自已有 Application Services）

| Agent Capability | Existing Service | Mutation | Approval | Revision | Idempotency | Agent Action |
| --- | --- | --- | --- | --- | --- | --- |
| 读取 Blueprint（节点 / 状态 / 质量 / 评审） | `ExportService.blueprint_view()`、`EditorService.get_node/get_history/get_quality` | 否 | 不需要 | 只读（带 revision） | n/a | `inspect_blueprint` |
| 逐级生成节点（premise…scene） | `BlueprintService.generate_task()` | 是（新节点，status=`proposed`） | 不需要 | 新节点 r1 | `idempotency_key` 支持 | `generate_node` |
| 重生成节点 | `BlueprintService.regenerate()` / `EditorService.regenerate()` | 是（新 revision） | 不需要 | `expected_revision` | 支持 | `regenerate_node` |
| 字段级修改 | `EditorService.patch()` | 是（新 revision） | 不需要（proposal） | `expected_revision` 必填 | 支持 | `patch_node` |
| AI 字段级改写 | `EditorService.rewrite()` | 是（新 revision） | 不需要 | `expected_revision` | 支持 | `rewrite_node` |
| 质量评估 | `ReviewService.evaluate()` | 是（Quality Store 报告 / issue） | 不需要 | 绑定评估的 node revisions | 支持（revision-aware cache） | `evaluate` |
| 修复计划（dry-run） | `EditorService.plan_repair()` / `ReviewService.plan_repair()` | 否 | 不需要 | 记录 target revisions | n/a | `plan_repair` |
| 执行修复 | `EditorService.repair()` → `ReviewService.repair_issue()` | 是（revision + repair history） | 不需要 | `expected_revisions`（planner 产出） | 支持 | `repair` |
| 修复复核 | `EditorService.verify_repair()` → `RepairVerifier` | 否 | 不需要 | before/after revisions | n/a | `verify_repair` |
| 请求接受（作者决定） | `EditorService.accept()` 的**前置**：Agent 只产生请求 | 否 | **是（protected）** | 绑定 revision | n/a | `request_accept` |
| 接受 revision | `EditorService.accept()` | 是（状态 + 新 revision） | **是（protected）** | `expected_revision` | 支持 | `accept_revision` |
| 交付预检 | `ExportService.delivery_selection()` + `DeliveryService.validate()` | 否 | 不需要 | 绑定 selection digest | n/a | `validate_delivery` |
| 正式交付 | `ExportService.deliver()` | 是（DeliverySnapshot + artifacts） | **是（protected，默认禁止）** | 绑定 snapshot | `idempotency_key` | `deliver` |

---

## 2. 哪些只是 MCP 包装（Agent 不得使用）

```text
MCP tools（interfaces/mcp/tools/**）        = 协议包装（30 个 tool 全部是 application.services 的薄封装）
MCP resources（interfaces/mcp/resources/**）= 只读包装
REST routes（api/**）                       = 协议包装
```

它们与 Agent 是**平级消费者**（任务书 §8）。Agent 只调用 Application Services /
Agent Ports，不启动 MCP client，也不经 REST 自调用。

---

## 3. 哪些真正属于 Application Service（Agent 的 Port 目标）

```text
BlueprintService   生成 / 重生成 / 读取 / children（结构读取）
EditorService      节点读取 / 历史 / diff / patch / rewrite / 接受 / 拒绝 / 恢复 / 质量关联
ReviewService      评估 / 计划修复 / 执行修复 / 复核
ExportService      交付选择 / 预检 / 交付 / 快照读取
JourneyService     下一步投影（规划输入，只读）
```

---

## 4. 哪些需要 Port（不直接把 ApplicationServices 交给 Agent）

| Port | 暴露方法（窄） | 底层 |
| --- | --- | --- |
| `AgentReadPort` | `snapshot(novel_id)` → 结构化只读状态 | `ExportService.blueprint_view` + `EditorService.get_quality` + `ReviewService.stats/latest_report` + `ExportService.delivery_snapshots` |
| `AgentGenerationPort` | `generate(task, parent_id, index, sequence, idempotency_key)`、`regenerate(node_id, expected_revision, idempotency_key)` | `BlueprintService` |
| `AgentEditorPort` | `node(node_id)`、`children(parent_id, node_type)`、`patch/rewrite(...)`、`accept/reject(...)` | `EditorService` |
| `AgentQualityPort` | `evaluate(gates, node_ids)`、`plan_repair(issue_ids)`、`repair(issue_ids, idempotency_key)`、`verify(issue_ids)` | `ReviewService` / `EditorService` |
| `AgentDeliveryPort` | `formats()`、`validate(selection)`、`deliver(selection, idempotency_key)` | `ExportService` |

设计约束（与 Plugin 最小权限一致）：

```text
· Port 只暴露 Agent 实际需要的方法；不暴露 repository / store / project_root / provider
· Agent core（contracts/planner/executor/verifier/registry）只依赖这些 Protocol
· Port 的**实现**放在 application 层（composition），因此 agent 不依赖 application，
  application 也不被 agent 反向依赖（只有 application.services.agent 依赖 agent）
```

---

## 5. 哪些绝不能开放给 Agent

```text
✗ BlueprintRepository.save_revision / set_status（绕过 Editor / Generation 语义）
✗ QualityStore / EditorStore / DeliveryStore 直接写入
✗ Canon / StoryState 写入（Agent 不产生故事事实）
✗ ai.providers / LLMGateway provider（Agent 只用 gateway capability，不直连 provider）
✗ memory internals（Canon 索引 / StoryState 索引；上下文经受控只读 capability）
✗ 文件系统 / shell / SQL / import_module（Agent 是 Story Blueprint Agent，不是通用 agent）
✗ 插件安装 / 启用 / 禁用（V4-09 operator boundary 未开放）
✗ 自动接受（`allow_auto_accept` 默认 false）
✗ 自动正式交付（`allow_delivery` 默认 false）
✗ 强制覆盖 revision（冲突必须 pause / replan / 请求作者）
✗ 大范围结构重写（large-scope structural rewrite 属 protected action）
```

---

## 6. Agent Action Registry（第一批，任务书 §22）

| action | mutation | protected | target 类型 | 底层能力 |
| --- | --- | --- | --- | --- |
| `inspect_blueprint` | 否 | 否 | novel | ReadPort |
| `generate_node` | 是 | 否 | parent 节点 / novel | GenerationPort |
| `regenerate_node` | 是 | 否（除非 accepted 高层节点 → protected） | node | GenerationPort |
| `patch_node` | 是 | 否（accepted 高层节点 → protected） | node | EditorPort |
| `rewrite_node` | 是 | 否（同上） | node | EditorPort |
| `evaluate` | 是（Quality Store） | 否 | novel / node 集合 | QualityPort |
| `plan_repair` | 否 | 否 | issue 集合 | QualityPort |
| `repair` | 是 | 否（conflicting repair contract → needs_human_review） | issue 集合 | QualityPort |
| `verify_repair` | 否 | 否 | issue 集合 | QualityPort |
| `request_accept` | 否 | 是（产生 approval 请求） | node | EditorPort（只读 + approval） |
| `accept_revision` | 是 | **是** | node | EditorPort |
| `validate_delivery` | 否 | 否 | novel | DeliveryPort |
| `deliver` | 是 | **是** | novel | DeliveryPort |

**永不存在的 action**：`run_shell` / `run_python` / `read_file` / `write_file` /
`execute_sql` / `import_module` / 任何未注册字符串（Planner 输出只能引用注册表）。
