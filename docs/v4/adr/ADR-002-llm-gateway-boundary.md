# ADR-002 — LLM Gateway Boundary

```
Status   : Proposed
Date     : 2026-09-17
Context  : V4-00 Architecture
Related  : V4_LLM_CONTRACT.md；ADR-010；V4_ARCHITECTURE_RISKS.md R-03/R-04/R-05
```

## Context

V3 里已经存在真实模型调用，但它写死在业务模块中：

* `story_engine/spec/llm.py`：`urllib` 直连 `https://api.deepseek.com/chat/completions`，
  `DEFAULT_MODEL = "deepseek-chat"`，`BACKOFF = (2.0, 5.0, 10.0)`，`SYSTEM_PROMPT` 为模块常量。
* `creative.py` / `settings_gen.py` / `ai_recommendations.py`：鸭子类型
  `provider.generate_structured(...)`，没有 contract、没有 usage、没有 trace。
* `README.md` / `.env.example` 明确声明「当前版本模型不生效」，说明接入被刻意推迟。

## Decision

建立 `ai/gateway` 作为**业务层唯一模型入口**：

```python
llm.generate(contract=..., context=..., model_policy=...)
```

* 业务模块只传 `contract_id` / 结构化 context / policy；不写 prompt、不选模型、不重试。
* provider 只认 messages / model / params / timeout；不知道任何 NovelForge 概念。
* 每次调用产出 `usage`（tokens / cost / latency）与 `trace`（request_id / context_refs）。
* 现有 `spec/llm.py` 的实现被拆入 `ai/providers/deepseek.py`，类名与签名保持兼容一段时间。

## Consequences

正面：换模型 / 换厂商 / 加缓存 / 加预算 / 加 trace 都不需要改业务代码。

代价：

* prompt 从业务模块迁移到 contract 注册表，需要一次全面梳理（5 个模块）。
* 需要为「无 key / 无网络」定义明确行为（V3 是 `AI_UNAVAILABLE` 降级，V4 要求可读错误 + 不产生半成品）。

## Alternatives considered

| 方案 | 为什么不选 |
| --- | --- |
| 直接用某厂商 SDK 并在业务模块调用 | provider 耦合；SDK 变更会波及业务代码 |
| 保持鸭子类型 provider，只加 typing | 无法统一 retry / timeout / usage / trace / cache |
| 在 domain 层做模型调用 | 违反「Domain 不依赖网络」的边界（V4_ARCHITECTURE.md §4.2） |

## Evidence

```text
src/novelforge/story_engine/spec/llm.py      DEFAULT_ENDPOINT / DEFAULT_MODEL / BACKOFF / SYSTEM_PROMPT
src/novelforge/story_engine/creative.py:243  notes.append("AI_UNAVAILABLE")
src/novelforge/story_engine/settings_gen.py:301  notes.append("AI_UNAVAILABLE")
requirements.txt                             无任何 LLM SDK（provider 边界可由我们定义）
.env.example                                 DEEPSEEK_API_KEY / ARK_API_KEY（当前不生效）
```

