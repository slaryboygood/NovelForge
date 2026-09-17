# ADR-012 — Unified LLM Gateway

```
Status    : Accepted（V4-02 实施完成）
Date      : 2026-09-17
Context   : V4-02 LLM Gateway
Related   : V4_LLM_CONTRACT.md；ADR-002（原设计）；ADR-013（配置与 secret 边界）；
            V4_MODULE_BOUNDARIES.md §3.7
```

## Context

V4-00 设计、V4-01 定界，V4-02 落地时发现真实情况比 V4-00 记录的更严重：

```text
src/novelforge/story_engine/spec/llm.py            urllib 直连 + 写死 deepseek-chat / 端点
src/novelforge/story_engine/planning/plot_synthesis.py   同样的 urllib + 写死端点（V4-02 才盘点出来）
src/novelforge/story_engine/planning/route_candidates.py 同上
以及 3 处鸭子类型 provider.generate_structured(...)（creative / settings_gen / ai_recommendations）
```

也就是说「只有一个模型调用入口」的假设是错的：模型调用散落在 3 个模块里，
各自实现 HTTP、backoff、错误码与 JSON 解析。

## Decision

建立 `src/novelforge/ai/` 作为**唯一正式 LLM boundary**：

```python
llm.generate(contract=..., context=..., model_policy=...)
```

* 业务侧只依赖 `novelforge.ai` 的 Public Contract（gateway / contract / provider 协议 /
  router / usage / trace / cache / 错误模型）。
* Provider 实现只存在于 `ai/providers/`；HTTP client 与 provider SDK 也只允许出现在那里
  （由 `tests/v4/isolation/test_module_boundaries.py` 机械守卫）。
* `ai` 不依赖 domain / application / persistence / interface；反之 legacy 调用点
  通过 `ai.legacy_support.chat_completion_via_gateway` 单向接入（domain 只允许**函数内**惰性 import）。
* Gateway 不理解业务概念（无 novel / chapter / scene / canon），只处理
  contract + context + policy + 请求元数据。

## Consequences

正面：

* 换 provider / 换模型 / 加预算 / 加缓存 / 加 trace 都不需要改业务代码。
* timeout / retry / 结构化输出 / usage / trace 只有一份实现。
* 3 个 legacy 调用点不再自带 HTTP 客户端与写死端点（下线了 2 处此前未盘点的调用）。

代价 / 约束：

* legacy 适配器仍是"鸭子类型 provider + 自己的错误码"，属于过渡形态；
  它们已登记进 `legacy/manifest.py`（status = compatibility_adapter）并写明移除条件。
* Gateway 必须保持无业务语义，否则 V4-04/V4-05 会把业务规则塞进基础设施层。

## Alternatives considered

| 方案 | 为什么不选 |
| --- | --- |
| 只把 `spec/llm.py` 改成 Gateway，保留另外两处 | 与「唯一入口」目标冲突；两处已盘点的重复实现会继续漂移 |
| 让 Gateway 感知业务（例如接受 novel_id / chapter 上下文） | 违反 §6 边界，会让 V4-03 Memory / V4-05 Quality 无法独立演进 |
| 引入第三方 LLM 框架（LangChain 等）承担编排 | 会把 provider 抽象、retry、trace 的所有权交给外部依赖；当前需求用 ~700 行即可闭合 |

## Evidence

```text
src/novelforge/ai/（errors / contracts / provider / config / router / gateway /
                   structured_output / retry / usage / trace / cache / factory /
                   providers/openai_compatible.py / legacy_support.py）
src/novelforge/observability/model_trace.py（trace sink，最小实现）
src/novelforge/application/services/utility.py（最小 app-services → ai 集成路径）
tests/ai/**（90 个离线测试）、tests/v4/isolation/test_module_boundaries.py（ai 边界守卫）
```

