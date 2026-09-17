# ADR-008 — MCP as Interface

```
Status   : Proposed
Date     : 2026-09-17
Context  : V4-00 Architecture
Related  : V4_MCP_SPEC.md；ADR-001；ADR-007；ADR-009
```

## Context

V4 要让 Agent（Codex / ChatGPT / Claude / IDE）直接驱动创作，而不是模拟点击 UI。
最自然的做法是把 NovelForge 做成 MCP server。风险在于：MCP 会立刻需要「读状态 / 写状态」，
若直接访问 domain 或文件系统，就会产生第二条业务路径。

同时 MCP 会**放大**上游缺陷：例如当前导出会混入 wasteland_001 数据（NR-002），
Agent 遍历资源时会把它当作当前作品事实。

## Decision

1. MCP 属于 `interfaces/`，与 REST 同级；tool 实现体 ≤ 3 行（参数映射 + service 调用 + envelope）。
2. Resource 全部只读；Tool 负责副作用；Prompt 只提供人类可读的 contract 说明。
3. 统一 `Result Envelope`（REST 与 MCP 同构），包含 revision_before / revision_after / quality / usage。
4. 写 tool 必须带 `request_id` + `idempotency_key` + `expected_revision`；
   destructive / expensive tool 必须支持 `dry_run`。
5. **MCP 在 V4-08 才暴露**，前置条件：service 层（V4-01）、Gateway（V4-02）、Quality（V4-05）、
   Ownership + DeliveryValidator（V4-07）全部完成。

## Consequences

正面：一个 envelope + 一套 service，Agent 无需理解多套返回格式；权限可显式分级。

代价：MCP 会迫使 service 层提前稳定（这也是把它放在后面的原因）。

## Alternatives considered

| 方案 | 为什么不选 |
| --- | --- |
| MCP 直接调用 domain / 读写文件 | 第二套业务路径；绕过 revision 与质量门 |
| MCP 复用 REST 的 HTTP 端点 | 引入本地 HTTP 依赖与双重序列化；错误语义不匹配 |
| 先做 MCP 再补 service 层 | 会让 MCP 成为事实上的业务层，之后极难拆 |

## Evidence

```text
src/novelforge/api/story_builder_routes.py  （当前唯一业务入口，1,545 行）
docs/ARCHITECTURE.md                         「依赖方向单向：UI → API → Application → Domain」
docs/v4/V4_EXPORT_SPEC.md §6                 ownership 规则（MCP 暴露的前置）
docs/v4/V4_MIGRATION_PLAN.md §3             V4-08 位置与理由
```

