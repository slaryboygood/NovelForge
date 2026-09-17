# NovelForge V4 — MCP Spec（设计稿）

> 状态：**V4-00 Architecture / Proposed**，已按 **V4-01 作者决策**对齐（2026-09-17）
> 依据：`docs/v4/V4_ARCHITECTURE.md` §1.2、§4、§5（MCP 边界）
> 硬约束：**MCP 不是业务层。** 每个 tool 必须调用 `application.services`，
> 禁止直接 import `domain.*` / `persistence.*` 或读写文件。

### 0.1 V4-01 对齐

```text
Resource 根对象 = Story Blueprint（/blueprint、/scenes、/quality），不是正文
Tools：generate_draft / continue_draft / rewrite_text 不再作为 V4 核心 tool
       （改为 expand_blueprint_node / rewrite_blueprint_node / save_revision）
```

| 位置 | V4-00 原文 | V4-01 修正 |
| --- | --- | --- |
| §3.3 资源清单 | 含 `/chapters/{id}/revisions`（正文 revision） | 改为 `/blueprint`、`/scenes`；正文 revision 资源移除 |
| §4.2 Tool 清单 #Writer | `generate_draft` / `continue_draft` / `rewrite_text` / `save_revision` | 改为 Blueprint 节点级：`expand_blueprint_node` / `rewrite_blueprint_node` / `save_revision` / `restore_revision` |
| §9 阶段顺序 | V4-07 ownership + DeliveryValidator | 不变（V4-01 已完成路径/ownership 参数化与历史数据删除） |

---

## 1. 三方职责划分

| MCP 概念 | 语义 | NovelForge 中的对应 | 是否可写 |
| --- | --- | --- | --- |
| **Resources** | 只读状态，Agent 可以读但不会因此改变系统 | 作品 / 状态 / Canon / 章节 / 大纲 / 质量 / 偏好 | 否（read-only by construction） |
| **Tools** | 操作（可能有副作用） | 生成 / 评估 / 修复 / 保存 / 导出 / 修订 | 是（按声明分级） |
| **Prompts** | 可选的 agent 引导模板 | 「如何续写第 N 章」「如何做质量评审」等既有 contract 的人类可读版本 | 否 |

裁决规则（写进实现规范）：

```text
能只靠读表达的能力       → Resource
需要产生副作用的能力     → Tool
只是给 Agent 的说明/模板 → Prompt（可选，不允许成为唯一能力入口）
```

---

## 2. 为什么 MCP 不可能成为业务层

```text
现有业务路径只有一条：
  UI / REST → api/story_builder_routes.py → story_builder/* + story_engine/*

V4 之后：
  UI  / REST  ─┐
               ├→ application.services (唯一业务入口)
  MCP / Agent ─┘

所以：MCP tool 的实现体 <= 3 行（参数映射 + 调用 service + 包装 Result Envelope）
     任何超过 3 行的 tool 实现都说明业务逻辑漏进了协议层（应当在评审中被拒绝）
```

---

## 3. Resources

### 3.1 Master Plan 提议的资源清单（评估对象）

```text
novelforge://projects
novelforge://novels/{novel_id}
novelforge://novels/{novel_id}/state
novelforge://novels/{novel_id}/canon
novelforge://novels/{novel_id}/characters
novelforge://novels/{novel_id}/outline
novelforge://novels/{novel_id}/chapters
novelforge://novels/{novel_id}/quality
novelforge://novels/{novel_id}/memory
```

### 3.2 逐条评估（不机械接受）

| 资源 | 判定 | 理由与修正 |
| --- | --- | --- |
| `//projects` | ⚠️ **改名** | V3 中「作品身份」的唯一 id 是 `novel_id`（`profile.py`）。但 sessions / blueprints 用的是同值的 `project_id`（`sessions.py:91`、`models.py:316`）。**这是一个真实的所有权命名歧义**：V4 必须先裁定单一名称（建议 `project_id` 为根，`novel_id` 为其下的作品实体；或反之），否则资源树会同时出现两个概念。修正：`novelforge://projects` + `novelforge://projects/{project_id}/novels/{novel_id}` |
| `//novels/{id}` | ✅ 保留 | 作品元数据（title / genre / tone / content pack / revision） |
| `//novels/{id}/state` | ✅ 保留 | StoryState 只读投影（当前时间 / 地点 / 人物状态 / 资源 / 未解冲突） |
| `//novels/{id}/canon` | ✅ 保留 | 已确认事实（可按 category / status 过滤） |
| `//novels/{id}/characters` | ⚠️ **合并** | 与 `/canon` `/state` 高度重叠：角色 = Canon 身份 + StoryState 运行时状态。建议合并为 `/entities`（含 characters / locations / factions，带 `kind` 过滤），减少「同一实体三个资源」的歧义 |
| `//novels/{id}/outline` | ✅ 保留 | 四级大纲（book / volume / arc / chapter） |
| `//novels/{id}/chapters` | ⚠️ **必须歧义拆分** | V3 现在有四种「章节」：章纲（`OutlineItem`）、Chapter IR（`ChapterSemanticIR`）、历史 IR（570 章，frozen）、写作草稿（`WriterDraft`，preview）。建议：`/chapters`（章纲，planned）+ `/chapters/{chapter_id}/revisions`（正文，V4 新增）+ `/chapters/{chapter_id}/ir`（机器语义，可选） |
| `//novels/{id}/quality` | ⚠️ **拆分** | 应区分 `/quality`（最近一次 QualityResult 摘要）与 `/quality/issues`（可过滤的 issue 列表，Agent 最常用） |
| `//novels/{id}/memory` | ❌ **不应作为一等资源暴露（至少 V4-03 前不暴露）** | 理由：① 记忆是**派生、可重建、非权威**（`V4_MEMORY_ARCHITECTURE.md` §1）；② 直接暴露会让 Agent 把检索结果当事实，制造 canon drift；③ 体积不可控。建议：只暴露 `/memory/summary`（条数 / stale / 覆盖），真正的检索通过 **Tool** `search_memory`（带 scope 与预算）完成 |

### 3.3 V4 建议的 Resource 清单（修正版）

```text
novelforge://projects
novelforge://projects/{project_id}
novelforge://projects/{project_id}/novels/{novel_id}
novelforge://projects/{project_id}/novels/{novel_id}/journey          # JourneyProjection（唯一进度投影）
novelforge://projects/{project_id}/novels/{novel_id}/state
novelforge://projects/{project_id}/novels/{novel_id}/canon
novelforge://projects/{project_id}/novels/{novel_id}/entities          # characters / locations / factions
novelforge://projects/{project_id}/novels/{novel_id}/outline
novelforge://projects/{project_id}/novels/{novel_id}/chapters          # 章纲（planned）
novelforge://projects/{project_id}/novels/{novel_id}/chapters/{chapter_id}/revisions
novelforge://projects/{project_id}/novels/{novel_id}/quality
novelforge://projects/{project_id}/novels/{novel_id}/quality/issues
novelforge://projects/{project_id}/novels/{novel_id}/memory/summary
novelforge://projects/{project_id}/novels/{novel_id}/preferences
novelforge://projects/{project_id}/schemas/{schema_id}                 # 结构化契约（供 Agent 生成前读取）
```

### 3.4 Resource 通用规则

```text
1. 全部只读；resource 变更必须通过 Tool。
2. 每个 resource 返回 Result Envelope（§5），包含 revision 与 source_ids。
3. 大集合必须分页（limit / cursor），默认 limit ≤ 100。
4. 任何资源都不得包含其他 novel 的数据（见 §7 隔离要求）。
5. 未实现的 resource 必须返回明确错误，不得返回空对象冒充成功。
```

---

## 4. Tool Contract

### 4.1 每个 Tool 必须声明的字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `name` | string | `novelforge.<verb>_<object>`，例如 `novelforge.generate_chapter_plan` |
| `purpose` | string | 一句人类可读的用途 |
| `input_schema` | JSON Schema | 严格 schema（additionalProperties: false） |
| `output_schema` | JSON Schema | Result Envelope 内的 `result` 结构 |
| `permission` | enum | `reader` / `author` / `operator`（V4 先做三元） |
| `read_only` | bool | 是否无副作用 |
| `safe_write` | bool | 是否可在无确认下写入（append-only / 只写 planned 层） |
| `destructive` | bool | 是否可删除 / 覆盖既有 revision |
| `expensive` | bool | 是否消耗显著 token / 时间（需要预算检查） |
| `dry_run` | bool | 是否支持 `dry_run=true`（默认对 destructive / expensive 必须支持） |
| `request_id` | string | 调用方提供，用于幂等与追踪 |
| `idempotency_key` | string | 同一 key 的重试不得产生第二次副作用 |
| `expected_revision` | int \| null | 写入类 tool 必须；不匹配返回 conflict |
| `possible_errors` | string[] | 错误码清单（见 §6） |

### 4.2 Tool 清单（V4 目标，按能力分组）

```text
# Project
novelforge.list_novels          read_only
novelforge.create_novel         safe_write
novelforge.rename_novel         safe_write
novelforge.archive_novel        destructive   (dry_run 必须支持)
novelforge.get_journey          read_only
novelforge.get_context          read_only     (memory context bundle, 带预算参数)

# Creation
novelforge.generate_premise     expensive
novelforge.generate_settings    expensive
novelforge.generate_world       expensive
novelforge.generate_characters  expensive

# Story / Outline
novelforge.generate_story_arc   expensive
novelforge.generate_outline     expensive
novelforge.generate_chapter_plan expensive
novelforge.generate_scene_plan  expensive
novelforge.get_outline          read_only

# Simulation
novelforge.advance_runtime      safe_write     (expected_revision 必须)
novelforge.list_candidates      read_only

# Writer
novelforge.generate_draft       expensive
novelforge.continue_draft       expensive
novelforge.rewrite_text         expensive, safe_write(proposal)
novelforge.save_revision        safe_write     (author text；不可覆盖他人 revision)
novelforge.restore_revision     destructive, dry_run
novelforge.list_revisions       read_only

# Quality
novelforge.evaluate             expensive
novelforge.list_quality_issues  read_only
novelforge.repair_issue         expensive, safe_write
novelforge.verify_repair        read_only

# Memory
novelforge.search_memory        read_only
novelforge.add_memory           safe_write     (只允许 author 级；派生层)
novelforge.summarize_memory     expensive

# Export / Delivery
novelforge.validate_delivery    read_only
novelforge.export               expensive, safe_write(file), dry_run 必须支持
```

### 4.3 Tool 权限分级

| 级别 | 允许的操作 | 示例 |
| --- | --- | --- |
| `reader` | 只读 resource / read_only tool | `get_journey`、`list_quality_issues` |
| `author` | 写 planned 层 / 生成 proposal / 保存作者内容 | `generate_outline`、`save_revision`、`add_memory` |
| `operator` | 破坏性 / 归档 / 批量重生成 / 删除 revision | `archive_novel`、`restore_revision`、mass regenerate |

规则：

```text
operator 级操作必须 dry_run 或显式 confirm（二选一，需在 contract 中声明）
任何 tool 都不得直接写 StoryState / Canon（只能产生 proposal 或走既有 ActionResolver 路径）
```

---

## 5. Result Envelope（统一返回）

```json
{
  "ok": true,
  "operation": "generate_chapter_plan",
  "request_id": "req_01H…",
  "project_id": "…",
  "novel_id": "…",
  "revision_before": 41,
  "revision_after": 42,
  "result": { },
  "quality": { "status": "passed", "issues": [] },
  "usage": { "model": "…", "input_tokens": 0, "output_tokens": 0, "cost_usd": null },
  "artifacts": [ { "kind": "chapter_plan", "ref": "chapter_ir:ch_018@2", "revision": 2 } ],
  "warnings": [ "FALLBACK_USED" ],
  "errors": []
}
```

失败时：

```json
{
  "ok": false,
  "operation": "save_revision",
  "request_id": "req_01H…",
  "errors": [ { "code": "REVISION_CONFLICT", "message": "…", "expected": 41, "actual": 43 } ],
  "result": null,
  "quality": null,
  "usage": null,
  "artifacts": []
}
```

规则：

```text
1. REST 与 MCP 使用同一个 envelope（UI 也可用，减少三套返回格式）
2. 部分失败必须显式（不得 ok=true 且 errors 非空）
3. 任何 fallback（LLM 不可用 → 确定性文本）必须出现在 warnings，且带 FALLBACK_USED
4. artifacts 必须带 revision 与 ref，便于 Agent 后续引用
```

---

## 6. 错误码（可能的错误）

```text
NOT_FOUND                 作品 / 章节 / revision 不存在
INVALID_INPUT             schema 校验失败
REVISION_CONFLICT         expected_revision 不匹配（见 V4_ARCHITECTURE.md §7.3）
IDEMPOTENCY_CONFLICT      同一 idempotency_key 携带不同参数
PERMISSION_DENIED         权限级别不足
CONFIRMATION_REQUIRED     destructive 操作缺少 confirm / dry_run
BUDGET_EXCEEDED           token / cost / 配额超限
LLM_UNAVAILABLE           provider 不可用（含全部重试失败）
LLM_SCHEMA_FAILED         模型输出无法通过 strict schema
QUALITY_BLOCKED           Quality gate 返回 blocker
REPAIR_LIMIT_REACHED      修复次数超限，需要作者介入
DELIVERY_INCOMPLETE       交付校验未通过
LEGACY_READ_ONLY          试图写 frozen 历史证据
QUARANTINED_DATA          请求触及未归属数据（例如 novel/final 未导入）
INTERNAL_ERROR            未分类错误（必须带 request_id）
```

---

## 7. 数据隔离要求（MCP 放大了 V3 的串稿风险）

Agent 会主动遍历资源，因此「数据集隔离」必须比 UI 时代更严格：

```text
1. 每个 resource / tool 都必须显式携带 project_id + novel_id
2. 服务端必须校验 artifact 的 novel_id 与请求一致（不信任客户端参数）
3. 禁止跨 novel 的隐式 join：例如 canon DB 必须按 novel_id 打开
4. workspace/wasteland_001_exports/** 只能通过显式 legacy tool 访问（默认不可见）
5. novel/final/**（无 owner 手稿）默认不可见，导入后才能作为 revision 访问
```

**现状证据**：`export_package.py` 的 `RECON_DIR` / `PLANNING_INDEX` / `canon/wasteland_001.sqlite`
与 `historical_ir.HISTORY_DIR` 会把 **wasteland_001 的历史数据**带进**任意作品**的导出
（这正是 V3 已知缺陷 NR-002）。如果 MCP 直接暴露当前导出逻辑，Agent 会更容易把这些
数据当作当前作品事实。**MCP 必须先等 V4-07 完成 ownership 收敛。**

---

## 8. Agent 会话可见性（配合 V4-11）

```text
Agent 操作必须可被作者看见：
  正在调用哪个 tool
  修改了哪些数据（revision_before → revision_after）
  消耗了多少 token / 成本
  发现了哪些 quality issue
  做了哪些修复

支持：pause / approve / reject / rollback
```

这要求 tool 的 Result Envelope 足够自描述（§5），而不是靠日志文本推断。

---

## 9. 阶段顺序（不可颠倒）

```text
V4-01  service 层成立（没有 service，MCP 只能复制业务逻辑）
V4-02  LLM Gateway（tool 返回 usage 才有意义）
V4-05  Quality 契约（tool 才能返回 quality 字段）
V4-07  Ownership + DeliveryValidator（先解决串稿风险）
V4-08  MCP server（此时 tool 实现体 ≤ 3 行）
```

> 这条顺序与 Master Plan 的 V4-08 位置一致；本文补充的是**理由**：MCP 是放大器，
> 它会放大上游所有所有权与质量缺陷。

---

## 10. 验收判据（V4-08）

```text
[ ] 每个 tool 的实现 ≤ 3 行（参数映射 + service 调用 + envelope 包装）
[ ] tool 与 REST 调用同一个 service（可用测试：同一输入产生同一 result digest）
[ ] Resource 全部只读，且返回 revision
[ ] destructive / expensive tool 支持 dry_run
[ ] expected_revision / idempotency_key 生效（并发写测试通过）
[ ] 跨 novel 请求被拒绝（隔离测试）
[ ] fallback 出现在 warnings（不静默）
[ ] MCP 层不存在任何业务规则（源码守卫测试）
```
