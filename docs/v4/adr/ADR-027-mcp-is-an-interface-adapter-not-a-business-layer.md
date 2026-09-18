# ADR-027 — MCP Is An Interface Adapter, Not A Business Layer

```
Status    : Accepted（V4-08 实施完成）
Date      : 2026-09-18
Context   : V4-08 MCP Server & Machine Interface
Related   : ADR-002（LLM Gateway boundary）；ADR-005（quality contract）；
            ADR-007（artifact ownership）；V4_MCP_CONTRACT.md §1–§2、§10
```

## Context

给每个 Python 函数套一层 MCP tool 是最省事的做法：

```text
MCP → BlueprintRepository / QualityStore / DeliveryService(内部步骤) / LLMGateway
```

后果很具体：MCP 变成第二业务层，REST 与 MCP 出现两套规则（revision / preserve /
approval / ownership 各自实现），且任何业务改动都要改两处。

## Decision

1. **MCP 只是 interface adapter**：`interfaces/mcp → application.services` 是唯一依赖。
   tool / resource 的实现只做：参数校验 → 调用 Application Service → 包装 Result Envelope。
2. **禁止** MCP import blueprint / generation / quality / editor / delivery / memory / ai /
   persistence / story_engine / api；也不允许通过 HTTP 调自己的 REST（平级 adapter）。
3. **缺口补在 Application 层**：本阶段为 MCP 补了 `ApplicationServices`（能力束）、
   `summary()`、`delivery_selection()`、`reviews()`、`blueprint_view()`、
   `machine_representation()`，而不是让 MCP 直接读底层。
4. **机械守卫**：`tests/v4/isolation/test_mcp_boundaries.py` 断言依赖方向、禁止构造
   业务对象、禁止自行拼路径 / 读文件。

## Consequences

正面：

* REST / MCP / 未来 Agent 共享同一批业务规则与同一批错误语义；
* MCP 的表层变更（协议 / SDK）不影响业务；业务变更不需要改两遍；
* 边界可机械验证（不靠评审记忆）。

代价：

* 某些能力需要先在 Application 层补一个薄 facade（本阶段补了 5 处）；
* tool 实现受"薄封装"约束，复杂的多步编排必须由调用方（或 V4-11 Agent）组合。

## Alternatives considered

| 方案 | 为什么不选 |
| --- | --- |
| MCP 直接调用 repository / evaluator | 第二业务层；与 REST 行为分叉；frozen/approval 语义易被绕过 |
| MCP 通过 HTTP 调 REST | 多余进程与网络依赖；错误语义二次映射；测试成本高 |
| 每个 Python 函数一个 tool | 暴露内部实现细节（§86），客户端可绕过 approval / preserve |

## Evidence

```text
src/novelforge/interfaces/mcp/dispatch.py        只调用 services_factory 注入的能力束
src/novelforge/interfaces/mcp/tools/*.py         tool = DTO 校验 + context.<service> 调用
src/novelforge/application/services/facade.py    ApplicationServices（接口层的唯一依赖）
tests/v4/isolation/test_mcp_boundaries.py        依赖方向 / 禁止构造业务对象 / 禁止读文件
tests/mcp/test_mcp_tools.py                      同一输入下 tool 行为与业务语义一致
```

