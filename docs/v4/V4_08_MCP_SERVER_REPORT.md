# V4-08 MCP SERVER RESULT

> 阶段：**V4-08 MCP Server & Machine Interface**
> 分支：`v4-08-mcp-server`（integration branch，单 Agent 顺序执行）
> 基线：`v4-07-delivery-export`（V4-07 PASS，1463 passed / 7 skipped / 0 failed）
> 结论：**V4-08 = PASS**

---

## 1. Application capability inventory

见 [`V4_08_MCP_CAPABILITY_INVENTORY.md`](V4_08_MCP_CAPABILITY_INVENTORY.md)。要点：

```text
可直接调用（V4-01→V4-07 的 Application Service 已足够）
  BlueprintService.generate_task / EditorService.* / ReviewService.* / ExportService.delivery*
本阶段补的 Application facade（§58）
  ApplicationServices（能力束）/ summary() / delivery_selection() /
  EditorService.reviews() / review_for() / ExportService.blueprint_view() /
  DeliveryService.machine_representation()（只读）
明确 DEFER：Memory resource、正文 writer tool、legacy 导出 tool、Agent 自主编排
```

## 2. MCP architecture

```text
MCP Client（Claude / Codex / IDE agent / automation）
      ↓ stdio（官方 MCP Python SDK，mcp==1.9.4）
interfaces/mcp/
├── server.py          create_mcp_server / run_stdio（SDK 薄适配）
├── dispatch.py        MCPDispatcher（参数校验 / novel scope / 错误映射 / observability）
├── registry.py        MCPToolRegistry / MCPResourceRegistry
├── contracts.py       ToolSpec / ResourceSpec / ToolResult / 版本
├── uri.py             URI 规范 + 分页
├── serialization.py   净化（secret / 路径）/ MIME / envelope
├── payloads.py        ResourcePayload（JSON / 二进制）
├── tools/             generation / editor / quality / delivery（薄封装）
└── resources/         interface / blueprint / quality / delivery
      ↓
application.services.facade.ApplicationServices（唯一业务依赖）
      ↓
blueprint / generation / quality / editor / delivery（V4-01→V4-07）
```

## 3. Public MCP contracts

```text
MCPDispatcher / ResourcePayload / create_mcp_server / create_dispatcher
MCPToolRegistry / MCPResourceRegistry / ToolSpec / ResourceSpec / ToolResult
parse_uri / ResourceTarget / paginate / map_error / MCPError 家族
MCP_INTERFACE_VERSION（=1）/ InvocationRecord
```

## 4. MCP version

```text
MCP_INTERFACE_VERSION = 1（独立于 BLUEPRINT_SCHEMA_VERSION / DELIVERY_SCHEMA_VERSION）
server = "novelforge"；transport = stdio；启动 = python -m novelforge.interfaces.mcp
依赖：requirements.txt 记录 `mcp>=1.9,<2` + `sse-starlette<2` + `starlette<0.47`
      （mcp 2.x / sse-starlette 3.x 会要求 starlette>=1，破坏 fastapi 0.115；故固定区间）
```

## 5. Resources

13 项（1 静态 + 12 模板）：`novelforge://interface`、novel 摘要、blueprint（分页）、
node、node revision、scenes（分页）、quality、quality/issues（分页）、
review（分页）、delivery（分页）、delivery snapshot、manifest、artifact。

全部只读；SQL/文件/Canon/StoryState 均不可达；artifact 只按 snapshot_id + 登记路径读取。

## 6. Resource URI scheme

```text
novelforge://interface
novelforge://novels/{novel_id}
novelforge://novels/{novel_id}/blueprint[?mode=current|accepted&limit=&cursor=]
novelforge://novels/{novel_id}/blueprint/nodes/{node_id}
novelforge://novels/{novel_id}/blueprint/nodes/{node_id}/revisions/{revision}
novelforge://novels/{novel_id}/scenes
novelforge://novels/{novel_id}/quality
novelforge://novels/{novel_id}/quality/issues
novelforge://novels/{novel_id}/review
novelforge://novels/{novel_id}/delivery
novelforge://novels/{novel_id}/delivery/{snapshot_id}
novelforge://novels/{novel_id}/delivery/{snapshot_id}/manifest
novelforge://novels/{novel_id}/delivery/{snapshot_id}/artifacts/{artifact_path}
```

SSOT：`V4_MCP_CONTRACT.md` §5（`V4_MCP_SPEC.md` 已降级为设计输入）。

## 7. Tools

23 个（§78 工具表见 `V4_MCP_CONTRACT.md` §4）：9 个生成、7 个编辑、4 个质量、
3 个交付；每个声明 `read_only / mutation / requires_revision / supports_dry_run /
idempotent / permission / expensive / possible_errors / service`。

## 8. Generation tools

`generate_premise / theme / world / character / character_arc / story_arc /
structural_unit / chapter_plan / scene_plan`
→ `BlueprintService.generate_task` → `generation` → `LLMGateway`（MCP 不接触模型）。
未配置 gateway → `MCP_LLM_UNAVAILABLE`（明确失败，不降级创作）。

## 9. Editor tools

`patch_blueprint_node` / `rewrite_blueprint_node` / `regenerate_blueprint_node` /
`accept_revision` / `reject_revision` / `restore_revision` / `diff_revisions`(RO)。
字段级 patch 只接受 `changes`（不接受整节点覆盖）；改写只改 `target_fields`。

## 10. Quality / repair tools

`evaluate_blueprint` / `plan_repair`(RO, dry-run) / `repair_issue` / `verify_repair`(RO)
→ `ReviewService` / `EditorService`（不调用 evaluator / RepairExecutor internals）。
不收敛或需人工 → `MCP_OPERATION_REQUIRES_REVIEW`（原样返回，不扩大 scope）。

## 11. Delivery tools

`validate_delivery`(RO) / `create_delivery_snapshot` / `deliver_blueprint`（dry_run 支持）
→ `ExportService` → `DeliveryService`；默认 `selection_mode="accepted"`；
blocked → `MCP_DELIVERY_BLOCKED`（cause=`DELIVERY_VALIDATION_FAILED`）；
不暴露 legacy 导出（§72）。

## 12. Revision semantics

```text
mutation tool 必须携带 expected_revision（新建顶层节点除外，需 idempotency_key）
冲突 → MCP_REVISION_CONFLICT + details{node_id, expected_revision, actual_revision,
       conflict_diff}；禁止自动 merge（测试覆盖）
accept 幂等（已 accepted 再次 accept 不产生 revision）
reject 只记录评审（不写 revision）
restore 产生新 revision（历史保留）
```

## 13. Idempotency

```text
idempotency_key 透传到业务层：patch / rewrite / accept / reject / restore / repair /
deliver / generate；重试命中已产生的结果，不产生第二个 revision 或 package
（测试：MCP patch 重放、deliver 重放）
```

## 14. Dry-run semantics

```text
patch(dry_run) → 0 mutation；rewrite(dry_run) → 0 mutation + 0 model call；
plan_repair 默认 dry_run；validate_delivery 只读；deliver(dry_run) → 0 artifact
```

## 15. Approval semantics

```text
quality pass ≠ accepted（envelope summary 明示）；generate/rewrite 结果一律 proposed；
accept / reject 只能显式调用；reject 不改 Blueprint status
```

## 16. Error mapping

```text
MCP_* 稳定码 + cause（底层业务 code）+ 白名单 details（§30、§68）
未分类异常 → MCP_INTERNAL_ERROR（cause=异常类名）
返回体永不含 traceback / pydantic stack / 绝对路径（有测试断言）
```

## 17. Security

```text
输入不接受 filesystem path / 数据库路径 / provider base_url / API key / import / shell
输出经 sanitize（secret key 直接丢弃、绝对路径 redacted）；artifact 二进制按 MIME 返回
package / payload 自检（assert_no_secrets）
```

## 18. Ownership isolation

```text
每个 novel resource / tool 显式携带 novel_id；跨作品 → MCP_OWNERSHIP_MISMATCH
两本作品 node_id 相同也不串（测试：A/B 资源内容互不出现对方 novel_id）
未知名作品 → MCP_NODE_NOT_FOUND / MCP_RESOURCE_NOT_FOUND
```

## 19. Pagination

```text
limit 默认 50 / 上限 200（超出 → MCP_INVALID_ARGUMENT）；cursor 为 offset 的不透明编码；
响应含 count / total / limit / offset / next_cursor / has_more
（blueprint / scenes / issues / review / delivery 列表均分页）
```

## 20. Serialization

```text
统一 Result Envelope（ok / operation / request_id / novel_id / revision /
revision_before / dry_run / result / issues / warnings / resources / usage /
errors / summary / tool_version / read_only）
结构化优先，summary 仅补充（§49–§50）
SDK 1.x 无 structuredContent → envelope 以 JSON 文本块返回；失败时 isError=true
```

## 21. MIME handling

```text
json → application/json；markdown → text/markdown；docx → …wordprocessingml.document；
nfpack → application/zip；artifact 资源按 manifest 记录的 mime_type 返回（二进制走 blob）
```

## 22. Observability

```text
InvocationRecord：request_id / kind(tool|resource) / name / novel_id / operation /
status / error_code / cause / latency_ms（内存记录，接口层 observability，§69–§70）
不记录 prompt / secret / 完整故事上下文；与 EditorOperationRecord 分离
```

## 23. Module boundaries

`tests/v4/isolation/test_mcp_boundaries.py`（10 项）：MCP 只依赖 application.services / core；
不 import 业务模块 / REST 框架 / HTTP client；不拼路径、不读文件、不构造下层对象；
application 与业务模块不反向 import interfaces.mcp；不通过 HTTP 调自己的 REST；
Public Contract 精简；requirements 记录官方 SDK 与 starlette 兼容区间。

---

## 24. Tests

```text
tests/mcp/**                                 48 passed
  test_mcp_contracts.py      9   契约 / 注册表 / envelope / 净化 / MIME / URI / 分页
  test_mcp_resources.py     10   资源读取 / 分页 / MIME / 隔离 / artifact 路径防护
  test_mcp_tools.py         20   工具注册 / 参数校验 / 冲突 / 幂等 / preserve / dry-run /
                                 审批 / 质量 / repair / 交付
  test_mcp_server.py         9   SDK 断言 / in-process client session / 缺 SDK 报错 /
                                 server 构造不触盘 / Golden MCP 全链路 / revision pinning
tests/v4/isolation/test_mcp_boundaries.py    10 passed
```

## 25. Impact-based validation strategy（§80–§81）

```text
Validation Strategy: impact-based testing

MCP module                      PASS（tests/mcp 48）
Affected application services    PASS（facade / editor reviews / export blueprint_view /
                                       delivery machine_representation）
Editor / Quality / Delivery      PASS（tests/editor 110 / tests/quality 122 / tests/delivery 60）
V4 boundary guards               PASS（tests/v4 全量）
Frozen guards                    PASS（v2 + v3 = 12）
validate_project                 PASS

环境变更（安装官方 MCP SDK）→ 触发 Full Regression Gate（见 §26）
```

## 26. Frozen boundary

```text
novelforge-product-v3-final tag   未移动
novel/authoring frozen digest     未变化（frozen guards PASS）
story_engine/repair.py / REPAIR_GATE_V1  未修改
Canon / StoryState 语义            未修改（MCP 只读；无写路径）
Blueprint / Delivery 语义          未修改（MCP 只透传既有契约）
环境：安装官方 MCP SDK（mcp 1.9.4）+ 固定 starlette<0.47
     —— 因依赖环境变化，按 §80 执行了全量回归（见 §29.1）
```

---

## 27. Files created

```text
src/novelforge/interfaces/__init__.py
src/novelforge/interfaces/mcp/{__init__,__main__,contracts,errors,uri,serialization,
                               payloads,registry,dispatch,server}.py
src/novelforge/interfaces/mcp/tools/{__init__,generation,editor,quality,delivery}.py
src/novelforge/interfaces/mcp/resources/{__init__,interface,blueprint,quality,delivery}.py
src/novelforge/application/services/facade.py
tests/mcp/{mcp_support,test_mcp_contracts,test_mcp_resources,test_mcp_tools,
           test_mcp_server}.py
tests/v4/isolation/test_mcp_boundaries.py
docs/v4/V4_08_MCP_CAPABILITY_INVENTORY.md
docs/v4/V4_MCP_CONTRACT.md
docs/v4/V4_08_MCP_SERVER_REPORT.md（本文件）
docs/v4/adr/ADR-027-mcp-is-an-interface-adapter-not-a-business-layer.md
docs/v4/adr/ADR-028-mcp-mutations-preserve-revision-and-approval-semantics.md
```

## 28. Files modified

```text
src/novelforge/application/services/__init__.py   导出 ApplicationServices / application_services
src/novelforge/application/services/editor.py     reviews() / review_for()（接口层只读访问）
src/novelforge/application/services/export.py     blueprint_view()（只读机器视图）
src/novelforge/delivery/service.py                machine_representation()（只读，不写 artifact）
requirements.txt                                  官方 MCP SDK + starlette 兼容区间
docs/v4/V4_MCP_SPEC.md                            降级为设计输入（SSOT → V4_MCP_CONTRACT.md）
docs/v4/V4_MODULE_BOUNDARIES.md                   §3.15 interfaces.mcp + 禁令 + 守卫清单
docs/v4/V4_ARCHITECTURE.md                        §4.1 表 / §5（MCP 边界 → 已落地）
docs/v4/V4_BRANCH_STRATEGY.md                     V4-08 分支行 + 分支声明
docs/v4/adr/README.md                             ADR-027/028 登记
```

## 29. Files deleted

```text
无
```

## 29.1 全量回归（环境变更触发）

```text
pytest -q   1521 passed / 7 skipped / 0 failed (607s)
测试数量变化（V4-07 → V4-08）：1463 → 1521 = **+58**
  · tests/mcp/**                  +48（contracts 9 / resources 10 / tools 20 / server 9）
  · tests/v4/isolation/**         +10（test_mcp_boundaries.py）
  · 其余套件（editor 110 / quality 122 / delivery 60 / generation 57 / memory 61 /
    ai 90 / 其它）与基线一致：未新增、未删除、未削弱
触发 Full Regression Gate 的原因：安装了新的运行时依赖（官方 MCP SDK + starlette 固定），
属于依赖环境变更；结果 PASS，说明 legacy REST / 既有产品路径未被破坏。
```

---

## 30. Git branch

```text
v4-08-mcp-server（integration branch，单 Agent 顺序执行）
```

## 31. Git commits

```text
（1）docs(v4): freeze mcp interface contracts
（2）feat(mcp): add server and resource registry
（3）feat(mcp): expose blueprint and review resources
（4）feat(mcp): expose generation editor and quality tools
（5）feat(mcp): expose delivery resources and tools
（6）test(mcp): add resource tool and protocol coverage
（7）test(v4): enforce mcp module boundaries
（8）docs(v4): record v4-08 result
```

---

## 32. Remaining risks

| 风险 | 状态 | 说明 |
| --- | --- | --- |
| MCP SDK 与 FastAPI 的 starlette 依赖冲突 | 已处理并记录 | 固定 `mcp<2` + `sse-starlette<2` + `starlette<0.47`；升级 SDK 时必须重跑 REST 回归 |
| SDK 1.x 无 structuredContent | 已知 | envelope 以 JSON 文本块返回；失败时 isError=true（契约 §6 明确说明） |
| Memory resource / search_memory | 明确 DEFER | 需要先补带预算与 scope 的 Application memory facade（inventory §3） |
| 无鉴权 / 权限分级（reader·author·operator） | 本阶段不做 | MCP 目前信任宿主注入的 project_root；tool 声明了 permission 元数据但未强制。属 V4-09/V4-11 与部署问题 |
| 长时间运行的服务缓存 | 已知 | `ApplicationServices` 按 novel 缓存（惰性构造）；提供 `forget_services()` 释放 |
| 大作品 Blueprint 资源分页上限 200 | 已知 | 超出需翻页；未来可加服务端 filter（node_type / status） |
| 浏览器 / 外部 MCP 客户端联调 | 未执行 | 本环境无 node_modules、无外部 MCP 客户端（Claude / codex CLI 等）；用官方 SDK in-process server+client session、`list_tools/list_resources/read_resource/call_tool` 全链路与 `python -m novelforge.interfaces.mcp` 入口覆盖。外部客户端联调建议在部署环境补做 |

---

## 33. V4-09 readiness

```text
[x] interfaces/mcp 是独立模块；只调用 application.services；无反向依赖
[x] Resource / Tool 分离；Resource 全部只读且版本化结构化输出
[x] 23 tools / 13 resources 覆盖生成 / 编辑 / 质量 / 修复 / 交付
[x] expected_revision / idempotency / dry-run / preserve / approval 语义完整保留
[x] delivery 默认 accepted + revision-pinned；无 legacy export tool
[x] 稳定错误码 + cause；无 traceback / secret / 绝对路径
[x] 显式 novel scope + 跨作品拒绝；artifact 路径防护
[x] 分页 / MIME / envelope / observability / 边界守卫齐备
[x] tests/mcp 48 + mcp 边界守卫 10；全量回归 1521 passed / 7 skipped / 0 failed

V4-09（Plugin Platform）可复用：
  · MCPToolRegistry / MCPResourceRegistry 的注册接口（插件注册 tool / resource）
  · ExporterRegistry（V4-07）与 tool 声明的 permission / capability 元数据
  注意：V4-08 不实现插件加载、权限强制与动态第三方代码执行（§75）。
```

---

# V4-08 = PASS
