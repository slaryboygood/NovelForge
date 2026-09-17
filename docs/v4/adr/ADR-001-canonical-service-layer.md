# ADR-001 — Canonical Service Layer

```
Status   : Proposed
Date     : 2026-09-17
Context  : V4-00 Architecture
Related  : V4_ARCHITECTURE.md §4、§5；ADR-008；V4_DELETION_PLAN.md（AD-003）
```

## Context

V3 的唯一业务入口是 `src/novelforge/api/story_builder_routes.py`（1,545 行）。
它同时承担 HTTP 协议转换、用例编排、业务判断与跨模块调用。`scripts/validate_project.py`
甚至把「所有路由必须在 `/api/story-builder/*` 下」写成了断言。

V4 要让 UI / REST / MCP / Agent / Plugin 共用业务能力。若路由继续持有编排逻辑，
那么 MCP tool 只有两种结局：复制编排（产生第二套业务路径），或直接调用 domain（绕过应用层）。

## Decision

引入 `application/services/*` 作为**唯一业务入口**：

```text
interfaces/api  → application.services
interfaces/mcp  → application.services
plugins         → application.services（经 PluginHost.call_service）
UI              → interfaces/api
```

* 路由函数只做：参数校验（pydantic）、调用 service、包装 Result Envelope、错误码映射。
* service 负责：用例编排、事务边界、revision 校验、质量循环触发、audit/trace 记录。
* domain 不允许被 interfaces 直接 import。

## Consequences

正面：

* MCP tool 实现体可以做到 ≤ 3 行（可机械检查）。
* 质量循环、revision 校验、trace 只在 service 层实现一次。
* UI 与 REST 的字段形状可以共用 Result Envelope。

代价：

* V4-01 需要一次性搬迁 100+ 路由体（高风险、必须逐段迁移并保持行为不变）。
* 短期内会出现「旧内联实现 + 新 service」并存，需要 feature flag 控制。

## Alternatives considered

| 方案 | 为什么不选 |
| --- | --- |
| 保持路由为中心，MCP 直接复用路由函数 | 路由强绑定 FastAPI Request/Response 与 HTTP 语义，MCP 需要另一套错误与 envelope 语义；会让 MCP 层出现业务分支 |
| 让 UI 直连 domain，REST 只做转发 | 违反 V3 已验证的「UI 不解析 Canon / 不判断 StoryState truth」边界 |
| 为 MCP 单独写一套 service | 第二套业务路径 —— `AGENTS.md` 明令禁止 |

## Evidence

```text
src/novelforge/api/story_builder_routes.py        1,545 行，含内联编排
src/novelforge/api/app.py                          22 行（挂载点清晰，可直接扩展）
scripts/validate_project.py                        路由前缀断言（V4 需扩展而非替换）
docs/ARCHITECTURE.md                               「依赖方向单向：UI → API → Application → Domain」
```

