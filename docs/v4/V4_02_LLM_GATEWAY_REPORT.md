# V4-02 LLM GATEWAY RESULT

> 阶段：**V4-02 LLM Gateway**
> 分支：`v4-02-llm-gateway`
> 基线：`v4-01-boundary-foundation`（V4-01 PASS）
> 结论：**V4-02 = PASS**

---

## 1. Repository LLM call inventory

按 `docs/v4/V4_BRANCH_STRATEGY.md` §3.1 的声明开工（Primary Module = `ai`），
先用 rg 扫描 `openai / deepseek / ark / chat completions / api_key / httpx / urllib /
completion / generate_structured` 等模式，结果如下（**不假设只有一个入口**）：

| # | 位置 | 形式 | 发现方式 |
| --- | --- | --- | --- |
| 1 | `story_engine/spec/llm.py` | `urllib` 直连 + 写死 `deepseek-chat` / 端点 / backoff / SYSTEM_PROMPT | V4-00 已记录 |
| 2 | `story_engine/planning/plot_synthesis.py:109` | **同样的 `urllib` + 写死端点**（M6 plot 提案） | V4-02 边界守卫新盘点 ✅ |
| 3 | `story_engine/planning/route_candidates.py:244` | **同样的 `urllib` + 写死端点**（M7 route 提案） | V4-02 边界守卫新盘点 ✅ |
| 4 | `story_engine/creative.py:248` | 鸭子类型 `provider.generate_structured(...)`（无 HTTP） | V4-00 记录 |
| 5 | `story_engine/settings_gen.py:304` | 同上 | V4-00 记录 |
| 6 | `story_builder/ai_recommendations.py:95` | 同上 | V4-00 记录 |
| 7 | `story_engine/outline_forge.py:889` | 同上（章纲润色） | V4-02 补充 |
| — | `requirements.txt` | 无任何 LLM SDK（只有 httpx） | V4-00 记录 |
| — | `.env.example` | `DEEPSEEK_API_KEY` / `ARK_API_KEY` | V4-00 记录 |

结论：真实 HTTP 调用点是 **3 个**（1–3），其中 2 个此前未被记录；
鸭子类型 provider 调用点是 **4 个**（4–7），它们本身不发 HTTP，属于 V4-04 的迁移对象。

---

## 2. Public AI contracts

`novelforge.ai`（`__all__` 共 47 个符号）：

```text
Gateway        LLMGateway / LLMResult
Provider       LLMProvider / LLMRequest / ProviderResponse
Contract       LLMContract / PromptSpec / ValidationPolicy / ContractRegistry /
               DEFAULT_CONTRACTS / GenerationMode / resolve_contract
Router         ModelPolicy / ModelRoute / ModelRouter
Config         ProviderConfig / ModelSpec / ProviderRegistry / KNOWN_CAPABILITIES /
               load_provider_configs / resolve_secret / redact_secrets
Assembly       build_gateway / build_gateway_from_configs / build_provider / build_providers
Legacy bridge  chat_completion_via_gateway / map_legacy_error_code
Structured     parse_and_validate / parse_json_text / strip_json_fence
Retry          RetryPolicy / run_with_retry / should_retry
Usage / Trace  UsageRecord / ModelPricing / TraceRecord / TraceSink / NullTraceSink
Cache          CacheKey / InMemoryCache / build_cache_key / cache_allowed
Errors         LLMError + 9 个子类（配置 / 鉴权 / 限流 / 不可用 / 模型缺失 / 超时 /
               结构化输出 / 重试耗尽 / 非法请求）
```

内部实现：`ai/providers/*`（HTTP client 唯一允许位置）。业务层只依赖 `novelforge.ai`。

---

## 3. Provider architecture

```text
LLMProvider（Protocol）
   complete(LLMRequest) -> ProviderResponse

LLMRequest（归一化）  request_id / operation / model / system / user /
                      temperature / max_output_tokens / timeout_s / expect_json / metadata
ProviderResponse      text / model / usage_raw / finish_reason / raw_safe（安全子集）
```

Provider 负责：请求序列化、鉴权、API 调用、超时、provider 错误归一化、响应抽取、token usage 抽取。
Provider 不负责：业务 prompt、故事逻辑、质量评分、记忆检索、业务模型选择。

`raw_safe` 只允许安全字段（当前仅 `id`）—— provider 原始响应不会泄漏成业务依赖。

---

## 4. Provider implementations

```text
src/novelforge/ai/providers/openai_compatible.py   OpenAICompatibleProvider
```

* **一个** adapter 通过配置支持 OpenAI / DeepSeek / Ark-compatible / 任意兼容服务
  （按 §8 要求，不复制 `deepseek_provider.py` / `ark_provider.py`）。
* `default_transport` 用 httpx，**connect timeout 与 read timeout 分开**（§16）；
  transport 可注入 → 单测完全离线（73 个 provider/gateway 测试无网络）。
* 错误归一化：401/403 → `AuthenticationError`；429 → `RateLimitError`；
  5xx / 连接错误 → `ProviderUnavailableError`；超时 → `RequestTimeoutError`；
  400/422 → `InvalidRequestError`；404 → `ModelUnavailableError`。
* secret 只进 `Authorization` header，并在错误 body / transport 异常文本中被
  `redact_secrets()` 抹掉（有专门测试）。

---

## 5. Gateway implementation

```python
result = llm.generate(contract=..., context=..., model_policy=..., operation=..., request_id=...)
```

链路（与实际代码一致）：

```text
resolve contract → router.route(policy) → cache lookup（仅 cacheable contract）
  → prompt render（context 缺键即报 ProviderConfigurationError）
  → retry loop { provider.complete → structured output parse/validate }
  → usage 归一化 → trace 落 sink → cache put（若允许）
  → LLMResult(provider, model, contract, output, usage, trace, cache, raw_metadata)
```

* 签名只接受 `contract / context / model_policy / operation / request_id / revision /
  contract_version` —— 有测试断言参数名里不出现 novel / chapter / scene / canon / blueprint。
* `LLMResult.as_dict()` 是统一 envelope（§22）。
* 失败也写 trace（status=error + error_code + error_chain 根因 + attempt_count）。

---

## 6. Router policies

| profile | 语义 | 排序键（确定性） |
| --- | --- | --- |
| `quality_first` | 质量优先 | −cost_tier → −context_tokens → provider_id → model_id |
| `cost_first` | 成本优先 | cost_tier → speed_tier → provider_id → model_id |
| `speed_first` | 速度优先 | speed_tier → cost_tier → provider_id → model_id |
| `local_first` | 本地优先 | local（True 先）→ cost_tier → provider_id → model_id |
| `explicit_model` | 指定模型（可指定 provider） | 精确匹配，缺失 → `ModelUnavailableError` |

capability 过滤：`structured_output / large_context / creative / critic / repair / utility`
（仅是 routing metadata，不代表 V4-02 实现故事任务）。disabled provider 永不入选；
没有任何 enabled provider 时抛配置错误。同输入多次路由结果一致（有测试）。

---

## 7. Structured output

```text
raw text → 最小清洗（剥 ```json fence）→ strict json.loads → pydantic schema 校验 → typed output
```

* 不做"自动修 JSON"黑魔法：`StructuredOutputError` 带明确 reason
  （`EMPTY_RESPONSE` / `JSON_INVALID` / `SHAPE_INVALID` / `SCHEMA_MISMATCH`）。
* provider-native structured output：`expect_json=True` 且模型 `supports_json_mode` 时请求
  `response_format={"type":"json_object"}`（本地模型可声明不支持）。
* `text` contract 必须显式 `ValidationPolicy(require_json=False)`，
  否则 contract 构造即报错（避免"声明 text 却偷偷解析 JSON"的歧义）。

---

## 8. Retry / timeout

```text
可重试    : RequestTimeoutError / RateLimitError / ProviderUnavailableError
不可重试  : ProviderConfigurationError / AuthenticationError /
            InvalidRequestError / ModelUnavailableError
contract  : StructuredOutputError（由 contract.validation.retry_on_structured_output 决定）
上限      : max_attempts ≤ 5（硬上限，RetryPolicy 构造时校验）；backoff 可注入（测试不 sleep）
耗尽      : 可重试错误耗尽 → RetryExhaustedError（保留根因错误码 last_error_code）
```

timeout：contract 级 `timeout_s`（默认 60s，legacy 适配器用 150s 兼容旧行为），
provider 配置可再加 `connect_timeout_s`；两者都记进 trace。
**不存在无限等待**：每次调用必有 timeout。

---

## 9. Usage tracking

```text
UsageRecord: provider / model / input_tokens / output_tokens / total_tokens /
             request_id / operation / contract_id / contract_version /
             estimated_cost / currency / pricing_version
```

* 兼容 `prompt_tokens|completion_tokens|total_tokens` 与
  `input_tokens|output_tokens` 两种命名。
* 价格来自 provider 配置的 `pricing_*`；**没有配置时 `estimated_cost = null`**（不猜价格）。
* 每个 `LLMResult.usage` 与 trace.usage 同源。

---

## 10. Trace / privacy

```text
TraceRecord: request_id / operation / provider / model / contract_id + version /
             status(ok|error|cache_hit) / latency_ms / attempt_count / timeout_s /
             usage / error_code / error_chain / context_digest / context_size /
             schema_id / cache_key / created_at
```

* 默认**不**保存 system / user prompt、API key、headers、小说上下文；
  只保存 `context_digest` 与字节量级。有测试断言 prompt 文本不出现在 trace 里。
* Sink：`InMemoryModelTraceStore`（默认，环形缓冲）+ 可选 `JsonlModelTraceStore`
  （作者显式启用才落盘）。只建最小能力，未创建 metrics / dashboard / audit 平台（§19）。

---

## 11. Cache

```text
CacheKey = provider | model | contract_id | v{contract_version} | context_digest |
           policy_digest [| r{revision}]
```

* key 只含 digest，**不含**正文 / prompt / 人物数据（有测试断言）。
* 准入：`cache_allowed(contract_cacheable, generation_mode)` —— contract 必须显式
  `cacheable=True`；创意类默认 False，因此不会被错误缓存（有测试）。
* 当前实现是进程内 `InMemoryCache`（LRU 上限 256，hits/misses 统计）；
  落盘缓存与 revision-aware 缓存留待后续阶段（revision 已进 key）。

---

## 12. Legacy LLM migration

按 §24「先扫描 → 建 Gateway → 迁移 → 确认无调用 → 再决定删除」执行：

| 位置 | 处理 |
| --- | --- |
| `story_engine/spec/llm.py` | ✅ 改为经 `ai.legacy_support.chat_completion_via_gateway`；`DEFAULT_MODEL` / `DEFAULT_ENDPOINT` 删除；`urllib` import 删除；保留 `chat` 注入 seam 与错误码 |
| `story_engine/planning/plot_synthesis.py` | ✅ 同样迁移；写死端点与 `model="deepseek-chat"` 删除 |
| `story_engine/planning/route_candidates.py` | ✅ 同样迁移 |
| 3 个 legacy provider | 登记进 `legacy/manifest.py`（status = compatibility_adapter，含移除条件）；`ai/legacy_support.py` 成为"legacy → Gateway"的唯一桥 |
| 4 处鸭子类型 provider（creative / settings_gen / ai_recommendations / outline_forge） | **未改**（属于 V4-04 结构化生成；本阶段只登记，不越界） |

**没有**先删再修测试：`chat` 注入路径与既有错误码在迁移后仍被原测试覆盖（12 个 spec 测试全绿），
新增测试覆盖 gateway 路径（含空响应 / schema 重试 / 错误码映射）。

---

## 13. Module boundary verification

`tests/v4/isolation/test_module_boundaries.py` 新增 4 条机械守卫：

```text
1. ai 不得 import domain / application / persistence / api / mcp / observability
   （observability 依赖 ai 的 TraceSink，而不是反向 —— 这条守卫在实现中真的抓到过一次反向依赖）
2. HTTP client / provider SDK（httpx / requests / urllib / aiohttp / openai / anthropic）
   只允许出现在 ai/providers/ —— 这条守卫直接盘出了 plot_synthesis / route_candidates 两处未记录调用
3. domain 不得在模块顶层 import novelforge.ai；只有 3 个 legacy 适配器允许函数内惰性 import
   （白名单在测试里显式登记，只减不增）
4. legacy LLM 适配器必须存在且确实通过 ai 调用（不能"迁移"成死代码）
```

另外 `tests/ai/test_application_integration.py` 断言 `ai` 不依赖 `application`，
`test_gateway.py` 断言 Gateway 签名不含业务语义参数。

---

## 14. Tests

```text
pytest -q                              1004 passed / 7 skipped / 0 failed（331s）
tests/ai/**                              90 passed（全部离线，无网络）
tests/v4/**                              41 passed（含 4 条新 ai 守卫）
tests/test_novel_spec_compiler.py        12 passed（legacy 适配器兼容面）
python scripts/validate_project.py       PASS
tests/test_v2_frozen_guard.py            6 passed
tests/test_v3_frozen_guard.py            6 passed
```

tests/ai 覆盖（对应 §28 清单）：

```text
Provider Contract : 归一化请求/响应、错误归一化、secret redaction、缺 key 不发请求
Gateway           : route 选择、provider 调用、结构化校验、usage、trace、
                    envelope 字段、错误 trace、未注册 provider、context 缺键、
                    contract_id 字符串解析、request_id 贯通、签名无业务语义
Router            : quality/cost/speed/local/explicit、capability 过滤、disabled、
                    未知模型/provider、确定性
Retry             : timeout/429/5xx 重试、auth/非法请求不重试、耗尽、policy 边界、
                    provider max_retries 收紧
Structured Output : 合法 JSON、fence、非法 JSON、空响应、schema mismatch、
                    gateway 集成、policy 决定是否重试
Cache             : key 稳定性与敏感度、key 不含原文、hit/miss、context 变化失效、
                    creative 默认不缓存、淘汰与统计
Config            : 缺 key、非法 base_url、enabled 必填项、disabled 合法、
                    未知 kind / provider_id、重复 id、未知 model、default_model、
                    timeout / retry / capability / tier 校验、env JSON 来源、
                    无配置不崩、仓库示例配置合法且全 disabled、secret redaction
Legacy Migration  : 无 HTTP client / 无写死模型、经 gateway 调用、schema 重试语义、
                    缺 key / 缺模型 / 缺端点、错误码映射、空响应、
                    plot / route provider 同样迁移 + chat seam 仍可用
Application       : utility service 只用 Gateway、越界标签过滤、cache hit、输入校验、
                    ai 不依赖 application
```

### 14.1 测试数量变化解释（V4-01 → V4-02）

| 类别 | 变化 | 原因 |
| --- | --- | --- |
| `tests/ai/**` | **+90** | 本阶段新增：provider / gateway / router / retry / structured output / cache / config / legacy migration / application integration |
| `tests/v4/isolation/test_module_boundaries.py` | **+4** | 新增 ai 边界守卫（依赖方向、SDK 归属、domain→ai 白名单、legacy 适配器存在性） |
| 既有测试 | ±0 | 唯一改动是 legacy 适配器内部实现；其公开行为与错误码保持，原测试全部继续通过 |

---

## 15. Frozen boundary

```text
novelforge-product-v3-final tag       未移动（annotated tag f214647 → f02ca8c）
novel/authoring frozen digest         未变化（guard PASS）
frozen Repair Contract / REPAIR_GATE_V1 未修改
StoryState / Canon 语义                未修改
```

本阶段没有为了接模型改动任何 frozen story logic；legacy 适配器只替换了"如何发请求"，
prompt 文本、schema 校验与作者确认门禁保持不变。

---

## 16. Files created

```text
src/novelforge/ai/__init__.py
src/novelforge/ai/errors.py
src/novelforge/ai/contracts.py
src/novelforge/ai/provider.py
src/novelforge/ai/config.py
src/novelforge/ai/router.py
src/novelforge/ai/gateway.py
src/novelforge/ai/factory.py
src/novelforge/ai/structured_output.py
src/novelforge/ai/retry.py
src/novelforge/ai/usage.py
src/novelforge/ai/trace.py
src/novelforge/ai/cache.py
src/novelforge/ai/legacy_support.py
src/novelforge/ai/providers/__init__.py
src/novelforge/ai/providers/openai_compatible.py
src/novelforge/observability/__init__.py
src/novelforge/observability/model_trace.py
src/novelforge/application/services/utility.py
novel/config/ai/providers.json
tests/ai/fake_provider.py
tests/ai/test_provider_contract.py
tests/ai/test_gateway.py
tests/ai/test_router.py
tests/ai/test_retry.py
tests/ai/test_structured_output.py
tests/ai/test_cache.py
tests/ai/test_config.py
tests/ai/test_legacy_migration.py
tests/ai/test_application_integration.py
docs/v4/adr/ADR-012-unified-llm-gateway.md
docs/v4/adr/ADR-013-provider-config-and-secret-boundary.md
docs/v4/V4_02_LLM_GATEWAY_REPORT.md（本文件）
```

## 17. Files modified

```text
src/novelforge/story_engine/spec/llm.py               legacy 适配（经 Gateway 调用）
src/novelforge/story_engine/planning/plot_synthesis.py  同
src/novelforge/story_engine/planning/route_candidates.py 同
src/novelforge/legacy/manifest.py                     登记 3 个 legacy LLM 适配器
src/novelforge/application/services/__init__.py       导出 UtilityService
tests/v4/isolation/_guard_utils.py                    新增 module_level_imports
tests/v4/isolation/test_module_boundaries.py          新增 ai 边界守卫
docs/v4/V4_LLM_CONTRACT.md                            实施状态 + 迁移结果
docs/v4/V4_MODULE_BOUNDARIES.md                       ai / observability 模块边界（§3.7）
docs/v4/V4_ARCHITECTURE.md                            LLM 边界行更新
docs/v4/V4_ARCHITECTURE_RISKS.md                      R-03 / R-04 / R-05 状态
docs/v4/V4_BRANCH_STRATEGY.md                         登记 V4-02 任务分支声明
docs/v4/adr/README.md                                 ADR-012 / ADR-013 索引
README.md / .env.example                              「默认不启用 provider」的准确表述
```

## 18. Files deleted

```text
无。
（legacy 适配器按 §24 保留：先迁移、确认无调用后再谈删除；其移除条件已写入 legacy manifest。）
```

---

## 19. Git branch

```text
v4-02-llm-gateway
```

## 20. Git commits

```text
e4961d7  feat(ai): add unified llm gateway
d14a2c1  refactor(ai): route legacy llm calls through gateway
a99ea4f  test(ai): add gateway contract and provider coverage
a240a00  test(v4): extend module boundary guards for ai
（+ docs(v4): record v4-02 llm gateway result）
```

> 与 §33 建议提交列表的映射：建议把 ai 实现拆成 4 个提交，
> 但 `ai/__init__.py` 是唯一 public contract 入口，拆分会让中间提交的 import 不成立；
> 因此合并为 1 个自洽提交（feat），其余按 legacy / tests / docs 拆分。

---

## 21. Remaining risks

| 风险 | 状态 | 说明 |
| --- | --- | --- |
| 4 处鸭子类型 provider 仍在业务模块（creative / settings_gen / ai_recommendations / outline_forge） | 未处理（计划内） | 它们不直接发 HTTP，迁移属于 V4-04 结构化生成；本阶段未越界 |
| legacy 适配器仍保留自己的错误码与 prompt 常量 | 已登记 | `legacy/manifest.py` 写明移除条件 |
| provider 级 `max_retries` 未与 contract attempts 联动 | 未实现 | 当前 attempts 只由 contract 决定（≤5）；已记入 V4_LLM_CONTRACT §0.1 待办 |
| 缓存仅进程内、无 revision-aware 落盘 | 未实现 | 计划内；revision 已在 cache key 中 |
| 成本预算闸门（Novel / Daily / Operation） | 未实现 | 属于 V4-05 / V4-07 |
| 真实模型链路未做 live 验证 | 有意 | 单测/CI 禁止真实调用（§27）；本机无 key，且 V4-02 PASS 不依赖 live 调用 |
| 没有 prompt 模板库 | 计划内 | V4-04 才设计业务 prompt；本阶段只提供 `PromptSpec` |
| `ai` 与 `observability` 的单向依赖容易被误写反 | 已被守卫覆盖 | 实现期真实发生过一次反向依赖（ai 默认 trace sink 想 import observability），被守卫拦住并修正 |

---

## 22. V4-03 readiness

```text
[x] 唯一模型入口存在且可测试（LLMGateway + 47 个公开符号）
[x] contract 版本化（LLMContract.contract_id + version；registry 可解析）
[x] 结构化输出 + schema 校验可复用（V4-03 的 summary/extraction contract 直接落在这层）
[x] usage / trace / request_id 贯通（Memory 的摘要调用可被计量与追踪）
[x] cache 契约就绪（embedding / summary 可声明 cacheable）
[x] 错误分类明确（Memory 可区分"上下文缺失"与"provider 故障"）
[x] 边界守卫就绪（新增 memory 模块不会破坏 ai 的 leaf 地位）
[x] 默认不调用模型（CI / 单测零成本、零网络）
```

V4-03 可以开始：**Story Memory（Canon retrieval / Story State Memory / Episodic /
Semantic / Author Preferences / Context Builder）**，开工前按 `V4_BRANCH_STRATEGY.md` §3
填写任务分支声明（Primary Module = `memory`）。

---

# V4-02 = PASS

