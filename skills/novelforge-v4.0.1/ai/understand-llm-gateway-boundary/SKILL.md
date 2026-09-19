---
name: novelforge-v4.0.1.ai.understand-llm-gateway-boundary
description: 掌握 LLM Gateway 边界：唯一模型入口、结构化输出、retry / timeout / cache / trace / secret 规则。
---

# understand-llm-gateway-boundary

- **Skill ID**: `novelforge-v4.0.1.ai.understand-llm-gateway-boundary`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `ai`
- **Product owner**: `src/novelforge/ai/gateway.py` + ADR-012 / ADR-013

## Purpose

避免出现第二条模型调用路径，或在业务模块里重复实现 retry / prompt 拼装 / 文本解析。

## Use when

- 需要新增一个使用模型的业务能力。
- 需要解释 usage / trace / cache 字段来源。

## Do not use when

- 只是要跑一次生成 → 用对应 generation skill。

## Preconditions

```text
无
```

## Required inputs

```text
无
```

## Authoritative interfaces

```text
UI           N/A
REST         N/A
Application  LLMGateway.generate(contract=…, context=…, model_policy=…, operation=…, request_id=…)
MCP          N/A （MCP 不直接调 Gateway）
```

## Procedure（约束清单）

```text
1 唯一入口：所有模型调用经 novelforge.ai（业务模块禁止 import provider / 发 HTTP）
2 唯一上下文：context 由 ContextBuilder 产出（禁止第二套上下文选择）
3 结构化输出：contract 声明 schema；输出必须能被 pydantic 解析（不做自由文本解析）
4 路由：ModelPolicy（profile / required_capabilities）从已启用 provider 的模型里选
5 错误分类：显式区分 认证 / 限流 / 超时 / 结构错误 / 重试耗尽（LLM_* code）
6 重试与超时：由 Gateway 统一处理（业务模块不得自行 retry）
7 cache：按 contract + context digest 等键命中；命中会标记 cached
8 trace / usage：随结果返回，供 evidence 与成本统计（不得写入 key）
9 secret：只在请求头使用；任何日志 / trace / 响应 / 交付物都必须 redact
```

## Expected result

能正确回答：

```text
· 能不能在 generation task 里直接 requests.post 到模型？（不能）
· 模型返回文本但 schema 不匹配怎么办？（LLM_STRUCTURED_OUTPUT_ERROR，不解析）
· 想换 provider 要不要改业务代码？（不需要，改配置 + 路由）
```

## Verification

```text
· 交叉核对 tests/v4/isolation/test_generation_boundaries.py（generation 不直连 provider）
· 交叉核对 src/novelforge/ai/gateway.py 与 provider.py 的接口
· 交叉核对 docs/v4/adr/ADR-012-unified-llm-gateway.md、ADR-013
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 出现第二个调用路径 | 业务模块直连 | 收敛到 Gateway（属 architecture 问题） |
| cache 命中但内容不同 | 键拼错 / 未含 contract 版本 | 修正 cache key，不删缓存了事 |

## Safety / invariants

```text
UNIFIED_GATEWAY：唯一入口；UNIFIED_CONTEXT：唯一上下文系统
不把 raw provider response 写入 artifact / 日志
```

## Side effects

无。

## Related skills

`configure-llm-provider`、`inspect-llm-provider-config`、`run-without-provider`

## Source references

```text
src/novelforge/ai/{gateway,router,provider,structured_output,retry,cache,trace,usage}.py
docs/v4/V4_LLM_CONTRACT.md
tests/ai/test_gateway.py、tests/ai/test_router.py、tests/ai/test_cache.py
```
