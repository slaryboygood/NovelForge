---
name: novelforge-v4.0.1.ai.inspect-llm-provider-config
description: 以只读方式查看 provider 配置与解析结果（哪些 provider 启用、哪些模型可用、能力标签）。
---

# inspect-llm-provider-config

- **Skill ID**: `novelforge-v4.0.1.ai.inspect-llm-provider-config`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `ai`
- **Product owner**: `src/novelforge/ai/config.py::load_provider_configs` + `ProviderRegistry`

## Purpose

在排查"为什么生成不可用"之前，先确认配置到底解析出了什么。

## Use when

- 生成报 `GENERATION_UNAVAILABLE` / `LLM_*` 时的第一步。
- 需要确认某能力（例如 `large_context`）有没有对应模型。

## Do not use when

- 需要改配置 → `configure-llm-provider`。

## Preconditions

```text
可读 novel/config/ai/providers.json（或 env NOVELFORGE_LLM_PROVIDERS / 显式 payload）
```

## Required inputs

```text
无（可指定 config_path / env 覆盖）
```

## Authoritative interfaces

```text
UI           N/A
REST         N/A
Application  load_provider_configs(...) → ProviderRegistry（enabled() / all() / ids() / resolve_model）
MCP          N/A
```

## Procedure

```text
1 registry = load_provider_configs(config_path=<root>/novel/config/ai/providers.json)
2 读 registry.ids() / enabled() / all()
3 对每个 provider 读 provider_id / kind / base_url / api_key_env / default_model / timeout / retries
4 对每个 model 读 model_id / capabilities / context_tokens / cost_tier / speed_tier / local
5 判断能力覆盖：生成需要 creative+structured_output；story_arc 还需要 large_context
6 结论：enabled 为空 → 生成类调用必然返回 GENERATION_UNAVAILABLE（预期行为）
```

## Expected result

```json
{"ids":["local_example","openai_compatible_example"],
 "enabled":[],
 "note":"默认 enabled=false：开箱不调用任何真实模型"}
```

## Verification

```text
· 只读：不修改 providers.json
· 输出中不出现任何 secret 值（只出现 api_key_env 名字）
· 与 .env.example 的变量名保持一致
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `LLM_PROVIDER_CONFIGURATION_ERROR` | JSON 结构不对 / 字段缺失 | 按 `{\"providers\":[…]}` 结构修正 |
| enabled 为空但以为已配置 | 忘了把 enabled 改 true | 显式开启 |
| 缺 large_context | 只有小模型 | 增加具备该能力的模型 |

## Safety / invariants

```text
只读；不打印 key；不写配置
不把"配置存在"等同于"模型可用"（还要 resolve_model + 真实调用成功）
```

## Side effects

无。

## Related skills

`configure-llm-provider`、`run-without-provider`

## Source references

```text
src/novelforge/ai/config.py
tests/ai/test_config.py、tests/ai/test_provider_contract.py
docs/v4/V4_LLM_CONTRACT.md §4、§9–§10
```
