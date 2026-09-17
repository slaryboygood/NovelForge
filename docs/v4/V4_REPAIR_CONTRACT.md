# NovelForge V4 — Repair Contract（V4-05 冻结）

> 状态：**V4-05 Quality Closed Loop & Targeted Repair**（2026-09-17 实施完成）
> 依据：`ADR-019`（minimal-scope & revisioned）、`ADR-006`（revision）、`ADR-017`（proposal）
> 定位：`quality` 与 `quality.repair` 的 **Public Contract SSOT**。

---

## 1. 一句话定义

```text
Repair = 在最小 scope 内、保留全部 preserve 字段、经 Generation Public Contract
         产生一个新 revision，并由 Verifier 重新评估受影响 gate 的过程。
```

不变量：

```text
REPAIR_NEVER_OVERWRITES       任何修复都产生新 revision（append-only）
REPAIR_NEVER_TOUCHES_TRUTH    不写 Canon / StoryState（只改 Blueprint proposal）
PRESERVE_IS_HARD              模型输出违反 preserve → 上报，不静默接受
NO_MODEL_CALL_ON_CONFLICT     expected_revision 冲突在任何模型调用之前发现
IDEMPOTENT_BY_KEY             同一 idempotency_key 不产生第二个 revision
NO_INFINITE_LOOP              max_repair_rounds / token / cost 预算触顶即停
```

---

## 2. Public Contract

```python
RepairPlanner       # issues → RepairPlan（不写 revision、不调模型、支持 dry_run）
RepairBlastRadius   # direct / dependent / required verification gates
RepairExecutor      # plan → 新 revision（只经 generation.regenerate）
RepairVerifier      # 新 revision → 受影响 gate 重新评估 → VerificationResult

RepairContract      # 一条 issue 的修复边界
RepairStep          # 一个最小修复动作
RepairPlan          # Planner 输出
RepairResult        # Executor 输出
VerificationResult  # Verifier 输出
```

依赖边界（§34 / §68）：

```text
quality.repair → quality contracts → blueprint → generation Public Contract → core
generation     → 绝不 import quality / repair
```

---

## 3. RepairContract

```text
issue_ids          这条契约覆盖的 issue
scope              issue 的作用域（node_ids / node_types / kind）
node_ids           允许修改的最小节点集合
preserve           绝对不可改：canon / source_ids / node_id + 结构 identity 字段
allow_change       只允许改这些 payload 字段
must_resolve       必须被解决的 issue ids（= 验证的输入）
constraints        附加约束文本（进入 repair intent）
max_scope          允许触碰的最大节点集合
strategy           targeted | scope_regenerate | manual_only
requires_human_review
reason
```

### 3.1 preserve 的组成

| 来源 | 内容 |
| --- | --- |
| 固定 identity | `node_id` / `source_ids` / `canon` |
| issue registry 默认 | 每个 issue code 在 `quality/codes.py` 中声明的 `preserve` |
| 结构 identity（本阶段新增） | scene→`chapter_id`；chapter→`characters`；character_arc→`character_id`；causal_link→`source_node`/`target_node`；payoff→`resolves_setup_ids` |
| 用户 / 上层显式传入 | `make_issue(repair_contract={...})` |

`allow_change` **必须**是节点 payload 里真实存在的字段（否则 generation 无法执行）；
`preserve ∩ allow_change = ∅`。两者相交时 Planner 记录 conflict 并按
`allow_change` 去掉该字段——但**同时上报**，不静默处理。

### 3.2 冲突

```text
contract A: allow_change = [outcome, turn]
contract B: preserve    = [outcome]
→ RepairPlan.status = "conflict"
→ strict=True 时抛 RepairConflictError
```

不可自动修的 issue（例如 ownership 破坏 / 因果环）：

```text
RepairPlan.status = "needs_human_review"（steps 为空）
strict=True 时抛 RepairNotAllowedError
```

多节点 scope（无法确定唯一最小修复节点）同样进入 `needs_human_review`
（§5 `AMBIGUOUS_DO_NOT_MERGE`：不为减少步骤数强行合并）。

---

## 4. Blast Radius

```text
Direct Scope                计划直接改动的节点
Dependent Scope             结构上依赖这些节点的节点（必须一起复核）
Required Verification Gates 需要重新执行的 gate（确定性有序）
```

依赖规则（结构事实，不是策略）：

| 关系 | reason |
| --- | --- |
| 子节点 | `child_of_changed` |
| 同一章的其他 Scene | `same_chapter_scene` |
| 端点被改的 causal link | `causal_endpoint_changed` |
| 回收被改 setup 的 payoff | `resolves_changed_setup` |
| 附着在被改节点上的 setup / payoff | `attached_to_changed_node` |
| 链接到被改节点的 character arc | `arc_links_changed_node` |

复核 gate = `{Q0, Q1, Q9}`（基线）∪ issue 所属 gate ∪ 相关节点类型的 gate ∪ policy 的 required gate。
**scope 只覆盖 blast radius，不重跑整个 Blueprint**（§32 / §43）。

---

## 5. RepairPlan（§58 dry run）

```text
plan_id / novel_id / scope / status / steps / contracts / blast_radius /
conflicts / human_review_reasons / notes / dry_run / issue_ids / created_at
```

`dry_run=True`（Planner 默认）返回的 plan 回答四个问题，且**不写任何 revision、不调用模型**：

```text
将修改哪些节点        → target_node_ids
允许改什么字段        → steps[*].allow_change
预计重新验证哪些 Gate → blast_radius.gates
预计调用多少模型任务  → estimated_model_calls
```

`plan_id` 只由 issue ids + 步骤 + expected revision 决定（确定性、可复现 → 幂等键稳定）。

---

## 6. RepairExecutor

执行顺序是契约的一部分：

```text
1. ownership 校验（plan.novel_id 必须等于 executor.novel_id）
2. plan.dry_run / plan.status != planned → 直接返回，0 次模型调用
3. 预检（全部步骤，在任何模型调用之前）
     · idempotency_key 已存在 → 记为 replay（不再调用模型）
     · 否则 check_expected_revision（不匹配 → RevisionConflict）
4. 逐步执行：generation.regenerate(task, node_id, expected_revision,
                                   preserve=payload 字段 ∩ step.preserve,
                                   task_input={repair intent}, idempotency_key)
5. 新 revision 落盘后逐字段比对 preserve → 违反则记录 REPAIR_PRESERVE_VIOLATION
6. 汇总 usage / before-after revision / 写入 repair_history
```

结果状态：

```text
planned            dry run（无写入）
applied            全部步骤产生新 revision
idempotent_replay  全部步骤命中既有 idempotency_key
partial            部分步骤失败或被判 preserve 违规
needs_human_review 无步骤成功，或 plan 本身不可执行
empty              没有步骤
```

失败**不吞**：`RevisionConflict` 原样抛出；其他异常进入 `blocked_steps`
（含 `error` / `message` / `fields`），供 Application 层与未来 MCP 返回。

---

## 7. RepairVerifier

```text
输入：before_report（修复前评估）+ plan（可选）+ policy
重新评估：blast radius scope + blast radius gates ∪ policy.required_gates
输出：VerificationResult
```

| 字段 | 含义 |
| --- | --- |
| `original_issue_ids` | 本次要验证的 issue（plan.issue_ids 或显式传入） |
| `resolved_issue_ids` | 复核后消失的 issue |
| `remaining_issue_ids` | 仍然存在的 issue（修复失败） |
| `new_issue_ids` | 修复前**完全不存在**的 issue（与 before_report 全量比较） |
| `before_revisions` / `after_revisions` | 每个节点修复前后的 revision |
| `gates_rechecked` | 本次实际重新执行的 gate |
| `quality_status` | 复核后的 report 状态（passed / failed / blocked） |
| `status` | `resolved` / `partial` / `unresolved` / `regression` |

状态判定：

```text
新出现 blocking issue            → regression
仍有 remaining                   → partial
original 为空                    → unresolved
其余                             → resolved
```

Verifier 同时把 issue 状态同步回 Quality Store（`resolved` / `open`），
但**不**修改 Blueprint 节点。

---

## 8. Closed Loop（Application 层）

```text
ReviewService.evaluate_and_repair(...)
   ↓
evaluate(scope, policy)
   ↓ report.status == passed → return passed
for round in range(max_repair_rounds):
    plan = RepairPlanner.plan(open issues)         # dry_run 可选
    if plan.status != planned → needs_human_review
    result  = RepairExecutor.execute(plan)
    verify  = RepairVerifier.verify(plan)
    if report.passed          → passed
    if 目标 issue 全部解决     → repaired（剩余 blocking 仍需人工关注）
    if 没有解决任何 issue      → needs_human_review
    if 预算触顶               → needs_human_review
→ needs_human_review（达到 max_repair_rounds）
```

`needs_human_review` 的触发条件（§57）：修复轮次耗尽 / contract 冲突 /
preserve 阻止修复 / 预算耗尽 / 需要产品决策的 blocker / 高层结构需要重构。

---

## 9. Usage / Budget（§41）

```text
usage = { evaluation: {...}, repair: {...}, verification: {...}, total: {...} }
每个桶   = { input_tokens, output_tokens, cost, calls }
```

`QualityPolicy.token_limit` / `cost_limit` 触顶 → 不继续自动 repair → `needs_human_review`。
`estimated_cost` 只在 provider 配置了价格时非 null（沿用 V4-02：不猜价格）。

---

## 10. 与冻结 M11 Repair 的边界（§78）

| | M11 Repair（frozen） | V4 `quality.repair` |
| --- | --- | --- |
| 对象 | 570 章历史内容修复 | 当前 Blueprint 生成质量 |
| Gate | `REPAIR_GATE_V1`（frozen） | Q0–Q9（V4 定义） |
| 输入 | Historical IR + overlay + CDQ | QualityIssue + Blueprint 图 |
| 写权限 | 已 closeout，只读 | 只写 allow_change 字段，且产生新 revision |
| 实现 | `story_engine/repair.py` | `novelforge/quality/repair/*` |

```text
两者不得共用实现、不得互相 promote、不得为"命名统一"修改 frozen repair。
```

---

## 11. 验收判据（V4-05）

```text
[x] RepairContract / RepairStep / RepairPlan / RepairResult / VerificationResult 存在
[x] preserve / allow_change / max_scope 由 Planner 决定（模型不参与）
[x] blast radius = direct + dependent + required verification gates
[x] dry_run 不写 revision、不调用模型
[x] expected_revision 冲突 → RevisionConflict 且 0 次模型调用
[x] 同一 idempotency_key → 不产生第二个 revision
[x] accepted 节点不被静默覆盖（新 revision 为 proposed，旧 revision 永久可读）
[x] 修复后重新评估受影响 gate，确认 issue 消失 / 报告 regression
[x] max_repair_rounds / token / cost 预算可控，超限 needs_human_review
[x] 计划外节点 byte-for-byte 不变（§64）
```

