---
name: novelforge-v4.0.1.ai.configure-llm-provider
description: 配置一个 LLM provider（openai_compatible）：base_url / model / capability / api_key_env，绝不含 secret。
---

# configure-llm-provider

- **Skill ID**: `novelforge-v4.0.1.ai.configure-llm-provider`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `ai`
- **Product owner**: `src/novelforge/ai/config.py`（`ProviderConfig` / `load_provider_configs`）

## Purpose

让生成 / 改写 / critic 真正可用，同时保持 secret 边界与"不静默启用"的原则。

## Use when

- 需要真实模型能力（生成 / 改写 / Q2 critic）。

## Do not use when

- 只想离线验证流程 → 用 stub / 测试注入（不要为此改产品配置）。
- 想把 key 写进配置文件 → **禁止**（只能写环境变量名）。

## Preconditions

```text
已知 provider endpoint 与模型 id；已知要用的环境变量名
```

## Required inputs

| 输入 | 必填 | 说明 |
| --- | --- | --- |
| `provider_id` | 是 | 小写字母 / 数字 / `-` / `_`（`^[a-z][a-z0-9_\-]{1,63}$`） |
| `kind` | 是 | `openai_compatible` |
| `base_url` | 是（enabled 时） | http(s) 端点 |
| `api_key_env` | 是（enabled 时） | 环境变量名（全大写），例如 `NOVELFORGE_LLM_API_KEY` |
| `models[]` | 是 | 至少一个：`model_id` / `capabilities` / `context_tokens` / `cost_tier` / `speed_tier` |
| `enabled` | 是 | 显式 true（默认 false） |
| `timeout_s` / `max_retries` | 否 | timeout>0；retries 0..5 |

## Authoritative interfaces

```text
UI           N/A
REST         N/A
Application  novelforge.ai.config.load_provider_configs(payload=…, env=…, config_path=…)
MCP          N/A
```

## Procedure

```text
1 复制 novel/config/ai/providers.json 的 provider 结构（不要删掉示例注释语义）
2 填 provider_id / base_url / api_key_env / models[]，把 enabled 改为 true
3 设置环境变量（值不写进文件）：api_key_env 指向的变量
4 校验：load_provider_configs(payload=…) 通过（否则配置阶段就报错）
5 冒烟：调用一次生成类 skill；读返回的 model / provider / usage / trace
6 确认：交付物 / 日志 / 响应里都没有 key（redact_secrets 生效）
```

## Expected result

```json
{"providers":[{"provider_id":"local_llm","kind":"openai_compatible",
 "base_url":"http://127.0.0.1:11434/v1","api_key_env":"NOVELFORGE_LOCAL_LLM_API_KEY",
 "enabled":true,"default_model":"local-model",
 "models":[{"model_id":"local-model","capabilities":["structured_output","utility"],
            "context_tokens":32000,"cost_tier":1,"speed_tier":4,"local":true}]}]}
```

## Verification

```text
· 配置非法（缺 key 名 / 非法 base_url / 未声明模型 / 重复 provider_id）→
  LLM_PROVIDER_CONFIGURATION_ERROR（启动即失败，而不是运行期静默降级）
· 生成结果里 model / provider 字段与配置一致
· grep 仓库：providers.json 中不含任何真实 key 字符串
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 生成仍返回 `GENERATION_UNAVAILABLE` | provider enabled=false / 未注入 gateway | 检查配置与宿主注入 |
| `LLM_AUTHENTICATION_ERROR` | key 未设置或错 | 设置 `api_key_env` 指向的变量 |
| `LLM_STRUCTURED_OUTPUT_ERROR` | 模型不支持 json mode | 换支持 `structured_output` 的模型 |
| `LLM_MODEL_UNAVAILABLE` | 模型 id 不在 provider 的 models 里 | 修正 model_id |

## Safety / invariants

```text
NO_SECRET_IN_REPO：仓库里只有环境变量名，没有值
默认不启用：不允许"悄悄开始调用真实模型"
不引入第二条调用路径（业务模块只能经 Gateway）
```

## Side effects

修改 `novel/config/ai/providers.json`（配置文件，不是 story artifact）+ 环境变量（由用户设置）。

## Related skills

`inspect-llm-provider-config`、`run-without-provider`、
`novelforge-v4.0.1.generation.generate-premise`

## Source references

```text
src/novelforge/ai/config.py（ProviderConfig / ModelSpec / load_provider_configs）
novel/config/ai/providers.json
.env.example
tests/ai/test_config.py
docs/v4/adr/ADR-013-provider-config-and-secret-boundary.md
```
