# NovelForge V4 — LLM Contract（设计稿）

> 状态：**V4-00 设计 / V4-02 已实施**（实现差异见 §13）
> 依据：`docs/v4/V4_ARCHITECTURE.md` §4、§5（LLM 边界）
> 硬约束：**业务 Service 不允许直接调用模型 SDK 或 HTTP 端点。**

### 0.1 V4-02 实施状态

```text
已实施（src/novelforge/ai/）：
  LLMGateway / LLMResult / LLMContract / PromptSpec / ValidationPolicy
  ModelPolicy / ModelRoute / ModelRouter
  LLMProvider 协议 + OpenAICompatibleProvider（配置驱动，不按厂商复制）
  ProviderConfig / ModelSpec / ProviderRegistry / resolve_secret / redact_secrets
  StructuredOutput（JSON fence 剥离 + strict 解析 + schema 校验）
  RetryPolicy（可重试分类 + 上限 + 可注入 sleep）
  UsageRecord / TraceRecord / InMemoryModelTraceStore / JsonlModelTraceStore
  CacheKey / InMemoryCache（保守默认：contract 未声明 cacheable 就不缓存）
  errors（LLMError 家族）/ factory / legacy_support
  application.services.utility（最小 app-services → ai 集成路径）

尚未实施（后续阶段）：
  provider 级 max_retries 与 contract attempts 的联动（当前 attempts 只由 contract 决定）
  落盘缓存 / revision-aware 缓存（revision 已进 cache key）
  embedding / summary 专用 contract（V4-03 Memory）
  成本预算闸门（Novel / Daily / Operation Budget，V4-05 / V4-07）
  业务 prompt 模板库（V4-04 才设计故事 prompt）
```

---

## 1. 为什么需要这一层

### 1.1 当前的代码事实

| 事实 | 位置 | 问题 |
| --- | --- | --- |
| 唯一真实模型调用是一个 `urllib` HTTP 请求，端点和模型名写死在模块常量里 | `story_engine/spec/llm.py`（`DEFAULT_MODEL = "deepseek-chat"`、`DEFAULT_ENDPOINT = "https://api.deepseek.com/chat/completions"`、`BACKOFF = (2.0, 5.0, 10.0)`） | 换 provider = 改业务模块；无法统计 token / cost；无 trace |
| 三处业务模块用鸭子类型 `provider.generate_structured(...)` 调模型 | `story_engine/creative.py`、`story_engine/settings_gen.py`、`story_builder/ai_recommendations.py` | 没有统一 contract、没有超时/重试策略、没有 usage 记录 |
| 产品路径的模型能力恒为关闭 | `creative.py:243` / `settings_gen.py:301` 返回 `AI_UNAVAILABLE`；`README.md` 与 `.env.example` 明确说明 | 说明「模型接入」是一件被刻意推迟的事，V4 要一次做对 |
| 依赖里没有任何 LLM SDK | `requirements.txt` | 说明 provider 边界可以由我们自己定义（不必被 SDK 形态绑架） |

### 1.2 目标

```text
业务代码写一次：
    result = llm.generate(contract=ChapterPlanContract(), context=ctx, model_policy=policy)

之后：
  换模型      → 改 policy，不改业务代码
  换厂商      → 加 provider adapter，不改业务代码
  加缓存      → 在 gateway 内完成
  加成本上限  → 在 gateway 内完成
  加 trace    → 在 gateway 内完成
```

---

## 2. 组件清单

| 组件 | 职责 | 明确不做 |
| --- | --- | --- |
| `LLMGateway` | 唯一对外入口；编排 contract → context → policy → provider → 校验 → usage/trace/cache | 不做业务判断、不写任何 truth |
| `LLMProvider` | 厂商适配：把统一请求翻译成厂商 API，把响应翻译回统一结构 | 不知道 NovelForge 业务概念 |
| `ModelRouter` | 按任务类型 / policy 选模型（creative / critic / repair / utility） | 不做成本核算（由 policy 决定） |
| `ModelPolicy` | 质量优先 / 成本优先 / 速度优先 / 本地优先 / 指定模型 / 预算上限 | 不定义 prompt |
| `GenerationContract` | 输入输出契约：prompt 模板 id、输出 schema、必需上下文块、禁止项 | 不持有具体小说内容 |
| `StructuredOutput` | JSON → strict schema → domain validation | 不解析自由文本 |
| `Retry / Timeout` | 统一重试与超时策略（含 schema 失败重试） | 不做无限重试（必须有上限） |
| `Usage` | `input_tokens` / `output_tokens` / `cost` / `latency` / `model` | 默认不保存完整敏感 prompt |
| `Trace` | `request_id` / `operation` / `context_refs` / `prompt_contract` / 结果状态 | 不成为业务事实 |
| `Cache` | 只缓存可安全缓存的结果（见 §8） | 不缓存受 StoryState 驱动的正文生成（除非 revision 一致） |

---

## 3. 核心调用形态

```python
# 设计稿：V4-02 才实现。业务 Service 只允许这样调用模型。
result = llm.generate(
    contract=CHAPTER_PLAN_CONTRACT,     # 输出结构 + prompt 模板 id + 必需上下文
    context=context_bundle,             # 由 memory.context_builder 产出
    model_policy=ModelPolicy.balanced(
        task="chapter_plan",
        budget=Budget(max_tokens=18_000, max_cost_usd=0.08),
    ),
)

result.value        # 已验证的 domain 对象（例如 ChapterPlan）
result.usage        # model / input_tokens / output_tokens / cost / latency
result.trace_id     # 与 observability 关联
result.quality      # 可选：预处理阶段的门禁结论（Q0）
```

### 3.1 禁止形态

```python
# ❌ 业务模块直接调用厂商
import urllib.request
urllib.request.urlopen("https://api.deepseek.com/chat/completions", ...)

# ❌ 业务模块自己拼 prompt
prompt = "你是小说助手…" + json.dumps(state)

# ❌ 业务模块自己重试
for attempt in range(3): ...

# ❌ 业务模块解析自由文本
m = re.search(r"标题[:：]\s*(.+)", text)
```

> 现状提醒：以上四种形态**当前都存在于 V3**（`spec/llm.py` 的前两种、
> `creative.py` 的 `_prompt()` 属于第三种、`spec/llm.py` 的 `BACKOFF` 属于第四种）。
> V4-02 的目标就是消灭它们。

---

## 4. 数据契约（设计稿）

```python
class LLMRequest:                    # 输入
    request_id: str
    operation: str                   # generate_chapter_plan / evaluate_continuity /
                                     # repair_chapter_goal / summarize_chapter …
    contract_id: str                 # 指向 GenerationContract 注册表
    contract_version: int
    context: ContextBundle           # 结构化上下文（不是拼接好的字符串）
    model_policy: ModelPolicy
    expected_revision: int | None    # 与写操作联动（见 V4_ARCHITECTURE.md §7.3）
    idempotency_key: str | None

class LLMResponse:                   # 输出
    request_id: str
    ok: bool
    value: Any                       # 已验证的 domain 对象
    raw_digest: str                  # 原始响应摘要（默认不落全文）
    usage: Usage
    attempts: int
    errors: list[LLMError]
    cache_hit: bool

class Usage:
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    cost_usd: float | None           # provider 不返回价格时为 None（不猜）
    latency_ms: int
```

### 4.1 GenerationContract

```python
class GenerationContract:
    contract_id: str                  # 例如 "chapter_plan.v1"
    version: int
    task_kind: Literal["creative", "critic", "repair", "utility"]
    output_model: type[BaseModel]     # 必须指向既有模型（见 §5）
    required_context: tuple[str, ...] # 例如 ("chapter_plan", "story_state", "canon_refs")
    forbidden: tuple[str, ...]        # 例如 ("invent_new_entity_id", "rewrite_canon")
    prompt_template_id: str           # prompt 不写在业务模块里
    max_attempts: int = 3
    timeout_s: float = 60.0
    cacheable: bool = False
```

### 4.2 ModelPolicy

```python
class ModelPolicy:
    task: str
    profile: Literal["quality_first", "cost_first", "speed_first", "local_first", "pinned"]
    pinned_model: str | None
    budget: Budget | None            # max_tokens / max_cost_usd / daily 上限
    fallback_chain: tuple[str, ...]  # 主模型失败时的降级顺序（可为空 = 不降级）
    allow_downgrade: bool = False
```

### 4.3 ModelRouter 决策规则（设计稿）

| 任务 | 默认 profile | 说明 |
| --- | --- | --- |
| 创意 / 正文（premise / settings / outline / draft） | `quality_first` | 创作内容质量优先 |
| 评估（critic：一致性 / 重复 / 逻辑） | `quality_first` + 独立模型 | **critic 与 creative 不应是同一模型**（避免自我确认偏差） |
| 定向修复（repair） | `quality_first` | 需保留字段约束 |
| 摘要 / 分类 / 标签 / 结构转换 | `cost_first` | 可降级 |
| embedding | `cost_first` 或 `local_first` | 见 `V4_MEMORY_ARCHITECTURE.md` |

---

## 5. StructuredOutput：必须指向既有模型

V4 **不新造**领域模型（见 `V4_ARCHITECTURE.md` CHALLENGE-07）。结构化生成的目标类型就是：

| 生成任务 | 目标模型（已存在） | 已有严格 gate |
| --- | --- | --- |
| 创意 / 设定 | `ContentPack`（`story_engine/content.py`） | `settings_gen.validate_pack_draft` |
| 章纲 | `ChapterSemanticIR`（`story_engine/chapter_ir/models.py`） | `chapter_ir/schemas.py` + `validator.py` + `evidence.py` |
| 规划 | `StoryPlanningIR`（`story_engine/planning/models.py`） | `planning/schemas.py` + `planning/validator.py` |
| 四级大纲 | `OutlinePackage`（`story_builder/models.py`） | `outline_forge` 质量门禁（标题唯一性 / 字段标签黑名单 / 来源一致性） |
| 写作 | `WriterPackage` + writer 输出声明（`story_engine/writer.py`） | `validate_writer_output` |
| 规格提案 | `SpecProposal`（`story_engine/spec/models.py`） | `SpecProposal.model_validate(strict=True)` |

处理链：

```text
model text
   ↓ JSON 解析（失败 → 重试，计入 attempts）
strict pydantic（失败 → 重试）
   ↓
domain validator（失败 → 不再重试，进入 Quality / Repair）
   ↓
proposal 返回业务层（不写 truth）
```

---

## 6. 错误分类（必须显式区分）

| 类别 | 例子 | 重试 | 后续 |
| --- | --- | --- | --- |
| `TRANSPORT` | 网络超时、5xx | 是（backoff，上限 `max_attempts`） | 超限 → `LLM_UNAVAILABLE` |
| `AUTH` | key 缺失 / 401 | 否 | 立即失败，提示配置 |
| `RATE_LIMIT` | 429 | 是（更长 backoff） | 超限 → 降级模型（若 policy 允许） |
| `SCHEMA` | JSON 不合法 / schema 不符 | 是（可附错误信息） | 超限 → Quality `Q0` 失败 |
| `DOMAIN` | 引用不存在实体 / 违反不变量 | 否 | 进入 Repair（定向修复） |
| `BUDGET` | 超 token / 成本 / 配额 | 否 | 停止并上报（不静默降级） |
| `CONTENT_POLICY` | 模型拒绝 | 否 | 返回可读原因 |

> 关键：`DOMAIN` 失败**不能靠重试解决**。V3 的 `writer.fallback_text()`（确定性降级文本）
> 正是「用降级掩盖失败」的例子；V4 要求 fallback 必须在 Result Envelope 中显式标记，
> 且**永不静默进入交付物**。

---

## 7. Retry / Timeout 策略（设计稿）

```text
max_attempts  : 契约级默认 3（创意类）/ 2（评估类）—— 不做无限重试
backoff       : 指数 + 抖动；429 使用更长退避
timeout       : 契约级（默认 60s）；批量任务可覆盖
总预算闸门    : attempts 总和不得突破 Budget（tokens / cost / wall clock）
幂等          : 携带 idempotency_key 时，同 key 的重试不得产生第二次写入
```

现状对照：`spec/llm.py` 的 `BACKOFF = (2.0, 5.0, 10.0)` 是硬编码值，V4 应改为 policy 参数，
并把「schema 失败重试」与「transport 失败重试」分开计数。

---

## 8. Cache 规则

允许缓存：

```text
embeddings
章节摘要 / 记忆压缩结果（带 source revision）
不可变实体描述（canon fact 的文本化结果，fact revision 不变即可复用）
评估结果（同一 revision + 同一 contract version + 同一模型）
```

不允许缓存（或必须严格限定）：

```text
当前 StoryState 驱动的正文生成
任何依赖“最新 revision”的创造性输出
```

Cache key 必须包含：

```text
novel_id
revision
contract_id + contract_version
model + provider
context_digest
```

---

## 9. 成本控制

```text
Novel Budget     每部作品总预算
Daily Budget     每日预算
Operation Budget 单次操作预算（可选）
到达预算 → stop（默认）或 downgrade（仅当 policy.allow_downgrade = true）
```

Context Builder 的责任：**优先检索相关信息，而不是无限扩大 prompt**
（`V4_MEMORY_ARCHITECTURE.md` §5 给出第 N 章的上下文预算示例）。

---

## 10. Trace 与隐私

默认记录：

```text
request_id, operation, novel_id, model, provider,
input_tokens, output_tokens, latency, cost,
prompt_contract (id + version), context_refs (id 列表),
quality_result, revision_before, revision_after
```

默认**不**记录：

```text
完整 prompt / 完整响应正文（仅 debug mode 且显式开启时记录）
作者未发表正文（除非 debug mode 且作品标记允许）
api key（永不记录，永不写入任何 artifact）
```

---

## 11. V3 → V4 迁移点

| V3 现状 | V4 动作 | 阶段 |
| --- | --- | --- |
| `spec/llm.py`（urllib + 硬编码端点 + SYSTEM_PROMPT） | ✅ 改为经 `ai.legacy_support.chat_completion_via_gateway` 调用；`DEFAULT_MODEL` / `DEFAULT_ENDPOINT` 已删除 | V4-02（done） |
| `planning/plot_synthesis.py`、`planning/route_candidates.py`（V4-02 新盘点的另外两处 urllib 调用） | ✅ 同样接入 `ai.legacy_support`；不再自带 HTTP 客户端与写死端点 | V4-02（done） |
| `ai/providers/deepseek.py`（本文件原设计） | ❌ 不创建 —— 协议完全兼容，用配置驱动的 `openai_compatible.py` 一个 adapter 覆盖全部兼容服务 | V4-02 |
| `creative.CreativeIdeaProvider._prompt()` / `settings_gen.SettingsProvider._prompt()` | prompt 移入 contract 注册表；业务模块只传 `contract_id` | V4-02 |
| `ai_recommendations.AIRecommendationSupplementer` | 改为 gateway 消费者；保留「AI 只能补充既有候选」的合并规则 | V4-02 |
| `writer.fallback_text()` / `render_scene()` | 保留为显式降级路径，必须在 Result Envelope 标记 `fallback_used`，且不得进入交付物 | V4-05 / V4-06 |
| `README.md` / `.env.example` 的「模型不生效」说明 | 接入后同步更新（README、`.env.example`、UI 文案） | V4-02 完成时 |

### 11.1 一条不能违反的边界

```text
LLM Provider → 不允许依赖 domain / application / persistence
```

Provider 只允许看到：messages、模型名、采样参数、超时。
任何「让 provider 理解 ChapterIR」的设计都是错的。

---

## 12. 验收判据（V4-02）

```text
[ ] 业务模块中不存在 urllib / requests / httpx / openai / anthropic 的直接引用
    （源码守卫测试可机械检查）
[ ] 所有模型调用经过 llm.generate(contract, context, model_policy)
[ ] 每个 contract 有 id + version + output_model + required_context + forbidden
[ ] 每次调用产生 usage 与 trace（可在 observability 中查询）
[ ] schema 失败与 transport 失败分别计数
[ ] Budget 超限时停止并上报（无静默降级）
[ ] provider 单测完全离线（注入 fake transport）
[ ] 无 API key 时行为可读且不产生半成品 artifact
```
