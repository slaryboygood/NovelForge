# ADR-013 — Provider Configuration And Secret Boundary

```
Status    : Accepted（V4-02 实施完成）
Date      : 2026-09-17
Context   : V4-02 LLM Gateway
Related   : V4_LLM_CONTRACT.md §9；ADR-012；novel/config/ai/providers.json
```

## Context

V4-00 记录的现状是：

```text
DEFAULT_MODEL = "deepseek-chat"
DEFAULT_ENDPOINT = "https://api.deepseek.com/chat/completions"
.env.example 里预置 DEEPSEEK_API_KEY / ARK_API_KEY（文档说"当前不生效"）
```

一旦真正接入模型，最危险的两个失误是：

1. 把厂商 / 模型 / 端点写进核心代码（换 provider 就要改业务模块）；
2. 让 API key 出现在仓库、日志、trace、cache key 或 API 响应里。

## Decision

**配置外部化 + secret 单向解析：**

```text
provider 配置来源（优先级）：显式 payload → 环境变量 NOVELFORGE_LLM_PROVIDERS → novel/config/ai/providers.json
provider 字段：provider_id / kind / base_url / api_key_env / default_model /
              timeout_s / connect_timeout_s / max_retries / enabled / models[]
每个 model 的元数据：capabilities / context_tokens / cost_tier / speed_tier /
                    local / supports_json_mode / pricing_*
```

规则：

```text
1. 核心实现不得出现固定生产 model / base_url / api_key（V4-02 已删除 DEFAULT_MODEL / DEFAULT_ENDPOINT）
2. api_key 只能通过 api_key_env 指向的 environment 变量解析（resolve_secret）
3. 配置默认 enabled=false —— 仓库内不存在被静默启用的 provider
4. secret 不写入 repository / trace / log / cache key / API 响应；
   错误与日志文本统一经 redact_secrets() 处理
5. 没有可靠价格配置时 estimated_cost = null（不猜价格）
6. 配置错误在**配置阶段**报出：缺 key / 非法 base_url / 未启用 / 未知 provider / 未知 model /
   重复 provider_id / 非法 timeout / 非法 retry 次数 / 未知 capability
```

## Consequences

正面：

* 同一个 OpenAI-compatible adapter 通过配置支持 OpenAI / DeepSeek / Ark-compatible / 本地模型，
  不需要按厂商复制 provider 文件。
* 密钥泄露面收敛到一处（`resolve_secret` + `redact_secrets`），并有测试覆盖。
* 「默认不调用模型」成为可机械验证的事实（示例配置 enabled=false + 测试）。

代价：

* 使用者必须显式配置 provider 才能真正调用模型（这是有意的，见下）。
* legacy 适配器仍需自己的 env 名（如 `NOVELFORGE_SPEC_MODEL`）作为过渡，已登记移除条件。

## Alternatives considered

| 方案 | 为什么不选 |
| --- | --- |
| 把 key 写进 `providers.json` | 会进入版本控制；与仓库 hygiene（AGENTS.md §24）冲突 |
| 用 `.env` 直接给核心代码读 key | 无法审计"谁用了哪个 key"；与 provider 抽象冲突 |
| 默认启用一个 provider 让功能"开箱可用" | 会让测试 / CI 意外产生真实调用与费用；必须显式启用 |

## Evidence

```text
src/novelforge/ai/config.py        ProviderConfig / ModelSpec / ProviderRegistry /
                                   load_provider_configs / resolve_secret / redact_secrets
novel/config/ai/providers.json     示例配置（enabled=false，无任何 secret）
tests/ai/test_config.py            12 个配置与 secret 测试（含仓库配置示例守卫）
tests/ai/test_provider_contract.py secret redaction 测试（HTTP 错误 / transport 异常两条路径）
```

