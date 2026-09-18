# NovelForge V4 — MCP Contract（V4-08 冻结，SSOT）

> 状态：**V4-08 MCP Server & Machine Interface**（2026-09-18 实施完成）
> 定位：MCP 接口的**最终 SSOT**。`docs/v4/V4_MCP_SPEC.md`（V4-00 设计稿）自本文件起
> 降级为**设计输入 / 历史依据**，不再声称自己是 SSOT。
> 依据：任务书 §2–§61；ADR-027 / ADR-028

---

## 1. 铁律

```text
MCP IS NOT THE BUSINESS LAYER.

MCP Client → MCP Adapter（interfaces/mcp） → Application Services → V4 modules
```

```text
· MCP 只做：协议解析 / 参数校验 / novel scope 绑定 / 调用 application services /
          错误映射 / 资源与结果序列化
· MCP 不做：故事生成逻辑 / memory retrieval / quality 判断 / repair planning /
          blueprint mutation / delivery selection
· MCP 不调用 LLM Gateway（生成与改写经 Application Service → generation → gateway）
· MCP 不写 Blueprint / Canon / StoryState；不做任何 mutation 决策
```

---

## 2. Public Contract

```text
src/novelforge/interfaces/mcp/__init__.py

MCPDispatcher / ResourcePayload        协议无关调用入口（in-process 测试与 SDK server 共用）
create_mcp_server / create_dispatcher  服务工厂（注入 project_root / services_factory）
MCPToolRegistry / MCPResourceRegistry  tool / resource 注册表（唯一 SSOT）
ToolSpec / ResourceSpec / ToolResult   声明与统一 Result Envelope
parse_uri / ResourceTarget / paginate  URI 规范与分页
map_error / MCPError 家族              稳定错误映射
MCP_INTERFACE_VERSION                  接口版本（独立于 blueprint / delivery schema）
InvocationRecord                       接口层 observability
```

Application 侧依赖（唯一）：`application.services.facade.ApplicationServices`。

---

## 3. MCP 版本（§53）

```text
MCP_INTERFACE_VERSION = 1（独立于 BLUEPRINT_SCHEMA_VERSION 与 DELIVERY_SCHEMA_VERSION）
server 名称：novelforge；启动：python -m novelforge.interfaces.mcp（stdio transport）
```

---

## 4. Tool 表（SSOT，§78）

| Tool | Mutation | Application Service | Revision | Idempotency | Dry Run |
| --- | --- | --- | --- | --- | --- |
| `generate_premise` | ✅ | `blueprint.generate_task` | 新建（无） | ✅ | — |
| `generate_theme` | ✅ | `blueprint.generate_task` | 新建 | ✅ | — |
| `generate_world` | ✅ | `blueprint.generate_task` | 新建 | ✅ | — |
| `generate_character` | ✅ | `blueprint.generate_task` | 新建 | ✅ | — |
| `generate_character_arc` | ✅ | `blueprint.generate_task` | 新建 | ✅ | — |
| `generate_story_arc` | ✅ | `blueprint.generate_task` | 新建 | ✅ | — |
| `generate_structural_unit` | ✅ | `blueprint.generate_task` | 新建 | ✅ | — |
| `generate_chapter_plan` | ✅ | `blueprint.generate_task` | 新建 | ✅ | — |
| `generate_scene_plan` | ✅ | `blueprint.generate_task` | 新建 | ✅ | — |
| `patch_blueprint_node` | ✅ | `editor.patch` | ✅ required | ✅ | ✅ |
| `rewrite_blueprint_node` | ✅ | `editor.rewrite` | ✅ required | ✅ | ✅ |
| `regenerate_blueprint_node` | ✅ | `editor.regenerate` | ✅ required | ✅ | — |
| `accept_revision` | ✅ | `editor.accept` | concurrency（可选） | ✅ | — |
| `reject_revision` | ✅（仅记录评审） | `editor.reject` | — | ✅ | — |
| `restore_revision` | ✅ | `editor.restore` | ✅ required | ✅ | — |
| `diff_revisions` | ❌ read-only | `editor.diff` | — | — | — |
| `evaluate_blueprint` | ✅（质量结论） | `review.evaluate` / `editor.evaluate` | — | — | — |
| `plan_repair` | ❌ read-only | `editor.plan_repair` | — | — | ✅（默认） |
| `repair_issue` | ✅ | `review.repair_issue` | ✅ required | ✅ | ✅ |
| `verify_repair` | ❌ read-only | `editor.verify_repair` | — | — | — |
| `validate_delivery` | ❌ read-only | `export.validate_delivery` | — | — | — |
| `create_delivery_snapshot` | ✅（写快照） | `export.create_snapshot` | — | ✅ | — |
| `deliver_blueprint` | ✅（写 artifact） | `export.deliver` | — | ✅ | ✅ |

明确不提供（§17、§71、§72）：正文写作类 tool（`generate_draft` / `continue_draft` / `rewrite_text` / `write_chapter`）、legacy planning export、writer bundle、outline export、Agent 自主多步编排（V4-11）。

---

## 5. Resource 表（SSOT，§78）

| Resource | Read Source via Application | Pagination | MIME |
| --- | --- | --- | --- |
| `novelforge://interface` | MCP 注册表元数据（工具表 / 资源表） | — | application/json |
| `novelforge://novels/{novel_id}` | `ApplicationServices.summary` | — | application/json |
| `.../blueprint` | `ExportService.blueprint_view`（机器视图） | ✅ limit/cursor | application/json |
| `.../blueprint/nodes/{node_id}` | 同上（filtered） | — | application/json |
| `.../blueprint/nodes/{node_id}/revisions/{revision}` | `EditorService.get_node` | — | application/json |
| `.../scenes` | `ExportService.blueprint_view`（visible 字段） | ✅ | application/json |
| `.../quality` | `ReviewService.latest_report` / `stats` | — | application/json |
| `.../quality/issues` | `ReviewService.list_issues` | ✅ | application/json |
| `.../review` | `EditorService.reviews` / `operations` | ✅ | application/json |
| `.../delivery` | `ExportService.delivery_snapshots` | ✅ | application/json |
| `.../delivery/{snapshot_id}` | `ExportService.delivery_snapshot` | — | application/json |
| `.../delivery/{snapshot_id}/manifest` | `ExportService.delivery_manifest` | — | application/json |
| `.../delivery/{snapshot_id}/artifacts/{artifact_path}` | `ExportService.delivery_artifact` | — | 按格式（json / markdown / docx / zip） |

```text
· Resource 全部只读（read-only by construction）
· artifact 只接受 Delivery Store 已登记的相对路径；拒绝 ../ / 绝对路径 / 盘符（§67）
· 分页：limit 默认 50、上限 200；cursor 为不透明游标（offset 编码）（§47）
· 资源粒度明确：不提供 novelforge://everything（§48）
· Memory 资源本阶段 DEFER（见 V4_08_MCP_CAPABILITY_INVENTORY §3）
```

---

## 6. Result Envelope（§29、§49–§50）

```json
{
  "ok": true,
  "operation": "patch_blueprint_node",
  "request_id": "mcp_…",
  "novel_id": "novel_alpha",
  "revision": 4,
  "revision_before": 3,
  "dry_run": false,
  "result": {},
  "issues": [],
  "warnings": [],
  "resources": ["novelforge://novels/novel_alpha/blueprint/nodes/ch_001"],
  "usage": {},
  "errors": [],
  "summary": "人类可读补充（结构化字段才是 contract）",
  "tool_version": 1,
  "read_only": false
}
```

```text
· errors 非空 ⇒ ok=false（不允许"部分失败但 ok=true"）
· SDK 1.x 无 structuredContent → envelope 以 JSON 文本块返回；
  失败时 isError=true 且文本仍是同一个 envelope（客户端解析方式一致）
· 摘要只做补充，不替代结构化数据（§50）
```

---

## 7. 稳定错误（§30–§31、§68）

```text
MCP_INVALID_ARGUMENT / MCP_NODE_NOT_FOUND / MCP_RESOURCE_NOT_FOUND /
MCP_TOOL_NOT_FOUND / MCP_REVISION_CONFLICT / MCP_OWNERSHIP_MISMATCH /
MCP_PRESERVE_VIOLATION / MCP_QUALITY_BLOCKED / MCP_DELIVERY_BLOCKED /
MCP_OPERATION_REQUIRES_REVIEW / MCP_OPERATION_REJECTED / MCP_LLM_UNAVAILABLE /
MCP_INTERNAL_ERROR
```

```text
· cause 字段保留底层业务 code（例如 EDITOR_REVISION_CONFLICT、DELIVERY_VALIDATION_FAILED）
· details 只包含白名单键（node_id / expected_revision / actual_revision / conflict_diff /
  fields / structural_fields / issues / blocking_reason …）
· 未分类异常 → MCP_INTERNAL_ERROR（cause=异常类名）；返回体永不含 traceback / 绝对路径
```

---

## 8. 语义保留（§21、§33–§36、§65）

```text
expected_revision   mutation tool 必须透传（§33）；冲突 → MCP_REVISION_CONFLICT + conflict_diff
idempotency_key     所有 mutation tool 透传（§35）；重试不产生第二个 revision / package
dry_run             patch / rewrite / plan_repair / repair / validate / deliver 支持；
                    dry-run 0 mutation（生成/改写同时 0 model call，若业务契约如此定义）
preserve            改写与修补的 preserve 硬约束由业务层执行（§20）；违反 → MCP_PRESERVE_VIOLATION
approval            accept / reject 必须显式调用；quality pass ≠ accepted（§21）：不自动接受
human review        needs_human_review / 无法自动修复 → 原样返回
                    （MCP_OPERATION_REQUIRES_REVIEW），不扩大 repair scope（§24）
delivery            §26：默认 selection_mode="accepted"；不因客户端方便改成 current
```

---

## 9. 安全与隔离（§32、§43–§46、§66–§67）

```text
· 每个 novel 相关 resource / tool 必须显式携带 novel_id（禁止"当前作品"推断）
· 跨作品 → MCP_OWNERSHIP_MISMATCH（读 / 写 / 打包全部拒绝）
· 输入不接受：filesystem path / 数据库路径 / provider base_url / API key /
             Python import / shell 命令（§43）
· 输出不含：secret / Authorization / 完整 prompt / raw provider response /
             绝对内部路径（序列化层递归净化 + 运行期自检）
· artifact 只按 snapshot_id + 登记路径读取（§45、§67）
```

---

## 10. 边界与启动（§2、§39–§42、§59–§61、§74）

```text
interfaces.mcp → application.services / core（ids·errors）/ MCP SDK
禁止           → blueprint / generation / quality / editor / delivery / memory / ai /
                 persistence / story_engine / api / 自行 HTTP
禁止           → application 与各业务模块 import interfaces.mcp
守卫测试       → tests/v4/isolation/test_mcp_boundaries.py

启动：NOVELFORGE_PROJECT_ROOT=<root> python -m novelforge.interfaces.mcp（stdio transport）
注入：create_mcp_server(project_root, services_factory=…, gateway=…, memory=…)
惰性：每次调用按 novel_id 构造 ApplicationServices（不预加载全部作品、不在 import 时扫描项目）
```

