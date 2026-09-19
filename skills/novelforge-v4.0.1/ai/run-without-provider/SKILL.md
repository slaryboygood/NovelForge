---
name: novelforge-v4.0.1.ai.run-without-provider
description: 在未启用任何 provider 的情况下正确理解与验证产品行为（稳定错误码，不静默降级）。
---

# run-without-provider

- **Skill ID**: `novelforge-v4.0.1.ai.run-without-provider`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `ai`
- **Product owner**: `src/novelforge/ai/gateway.py` + `generation/service.py`（错误映射）

## Purpose

把"没有模型"当成一个明确的、可断言的状态来使用，而不是期待规则式假内容。

## Use when

- 离线验证流程（CI / 测试 / 演示）。
- 需要确认产品在无模型时不会伪造内容。

## Do not use when

- 需要真实内容 → `configure-llm-provider`。

## Preconditions

```text
providers.json 全部 enabled=false（默认）
```

## Required inputs

```text
无
```

## Authoritative interfaces

```text
UI           Story Studio 生成按钮 → 错误提示
REST         POST /studio/generate → 422 {"code":"GENERATION_UNAVAILABLE"}
Application  GenerationUnavailableError（生成 / 改写）
MCP          tool generate_* / rewrite_blueprint_node → MCP_LLM_UNAVAILABLE
```

## Procedure

```text
1 确认无 provider：inspect-llm-provider-config
2 调用一次生成：POST /studio/generate {novel_id, task:"premise"}
3 期望：422 + code=GENERATION_UNAVAILABLE（不是 200，也不是伪造内容）
4 期望：Blueprint 没有新节点（0 mutation）
5 只读路径仍可用：inspect-blueprint / inspect-quality-report / list-delivery-snapshots 正常
6 next：要么配置 provider，要么只用确定性能力（Canon 校验 / 交付查看 / 质量读取）
```

## Expected result

```json
{"detail":{"code":"GENERATION_UNAVAILABLE","message":"当前未配置模型能力，无法生成（§58 稳定错误码）"}}
```

## Verification

```text
· HTTP 422 且 code 稳定（可断言）
· Blueprint 节点数与 digest 不变（0 mutation）
· 不存在 V2 规则式"假生成"路径（Story Builder 后端已退休）
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 200 但内容像模板 | 期望错误：属缺陷（可能是旧 legacy 路径复活） | 记录到 GAPS，检查是否引入第二套生成 |
| 报错信息含路径 / traceback | 泄露 | 记录到 GAPS（接口层应净化） |

## Safety / invariants

```text
不静默降级为规则式创意内容（V3 的确定性创作链已退休）
无模型 ≠ 允许伪造：宁可稳定失败
```

## Side effects

无（失败调用不产生 artifact）。

## Related skills

`inspect-llm-provider-config`、`configure-llm-provider`、
`novelforge-v4.0.1.quality.evaluate-blueprint`（deterministic 路径仍可用）

## Source references

```text
src/novelforge/generation/service.py（GenerationUnavailableError）
src/novelforge/api/studio_routes.py（_CODE_STATUS / GENERATION_UNAVAILABLE 422）
src/novelforge/interfaces/mcp/errors.py（MCP_LLM_UNAVAILABLE）
README.md（默认不启用 provider 的说明）
tests/ai/test_gateway.py、tests/studio/test_studio_api.py
```
