# Module: `ai` — LLM Gateway 与 provider 配置

```text
Module purpose     唯一模型入口：contract / 路由 / provider / 结构化输出 / retry / timeout /
                   usage / trace / cache / secret 边界
Authoritative owner src/novelforge/ai/**（gateway / router / provider / config / structured_output）
Owned skills       configure-llm-provider / inspect-llm-provider-config /
                   run-without-provider / understand-llm-gateway-boundary
Truth ownership    无。Gateway 不写 Story Blueprint / Canon / StoryState（由调用方写）
Public interfaces  Python API（LLMGateway.generate / load_provider_configs）；
                   config 文件 novel/config/ai/providers.json；env NOVELFORGE_LLM_PROVIDERS
Dependencies       observability（trace）、core；被 generation / quality(Q2 critic) / utilities 使用
Forbidden          业务模块直连厂商 / 自拼 prompt / 自行 retry / 解析自由文本 / 把 key 写进仓库
Related modules    generation（主要消费者）、quality（critic）、plugins（经 Host ai.invoke）
```

## 事实表

| 项 | 值 |
| --- | --- |
| provider kind | `openai_compatible`（当前唯一） |
| 配置优先级 | 显式 payload → env `NOVELFORGE_LLM_PROVIDERS` → 配置文件 |
| 默认 | **不启用任何 provider**（`enabled=false`） |
| secret | 只从 `api_key_env` 指定的环境变量读取；绝不写入仓库 / 日志 / 交付物 |
| model capability | `structured_output` / `large_context` / `creative` / `critic` / `repair` / `utility` |
| 错误码前缀 | `LLM_*`（PROVIDER_CONFIGURATION_ERROR / AUTHENTICATION_ERROR / MODEL_UNAVAILABLE / RATE_LIMIT / REQUEST_TIMEOUT / STRUCTURED_OUTPUT_ERROR / RETRY_EXHAUSTED …） |
