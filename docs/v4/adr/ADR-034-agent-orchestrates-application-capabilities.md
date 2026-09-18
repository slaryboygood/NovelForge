# ADR-034 Agent Orchestrates Application Capabilities, It Does Not Own Business Logic

> 状态：**Accepted**（V4-11 实施完成）　日期：2026-09-18　阶段：V4-11 Agent Mode
> 相关：ADR-001（canonical service layer）、ADR-032（Story Studio 主产品面）、
> `docs/v4/V4_AGENT_CONTRACT.md`

## 背景

「Agent」最容易变成第二个业务层：直接读 repository、直接写 store、直接调 provider。
那会让 V4-01→V4-10 建立的 revision / quality / approval / delivery 语义全部失效。

## 决策

```text
User Goal → Agent Planner → Agent Plan → Agent Executor →
Agent Ports（窄 Protocol）→ Existing Application Services →
Generation / Quality / Editor / Delivery
```

```text
· Agent core 只认识 agent.ports（AgentReadPort / GenerationPort / EditorPort /
  QualityPort / DeliveryPort）；不 import application / repository / store / provider / api / mcp
· Port 的实现在 application.services.agent（composition），因此无循环依赖
· 所有 mutation 经 Generation / Editor / Quality / Delivery 正式能力（append-only revision）
· Agent 不通过 MCP 调业务（MCP 与 Agent 是平级消费者）
· 创意内容仍由 generation contracts 产生；Planner 只决定调用哪个 task
```

## 备选方案

| 方案 | 否决理由 |
| --- | --- |
| Agent 直接持有 ApplicationServices | 等于交出全部业务能力（与插件最小权限原则冲突） |
| Agent 通过 MCP tool 调业务 | 引入协议层自调用；MCP 会被误当作核心 API |
| Agent 直接调 LLMGateway 生成内容并保存 | 绕过 generation contract 与 revision 语义 |

## 后果

```text
正面：业务语义唯一；Agent 可替换；边界可机械验证（tests/v4/isolation/test_agent_boundaries.py）
负面：新增能力需要先有 Application facade / Port；Planner 不能"顺手"造步骤
```
