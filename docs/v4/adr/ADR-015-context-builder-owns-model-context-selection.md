# ADR-015 — Context Builder Owns Model Context Selection

```
Status    : Accepted（V4-03 实施完成）
Date      : 2026-09-17
Context   : V4-03 Story Memory & Context Builder
Related   : V4_MEMORY_ARCHITECTURE.md §5；ADR-012（LLM Gateway）；ADR-014（Memory derived）
```

## Context

V4-00 已确认：V3 的 `WriterContextBuilder` 用「分层 block + 跨块去重 + 每块 40 条上限」
装配上下文，但它是为 Writer 准备的，且每个业务模块仍可自行拼上下文。

V4-04 之后，Story Blueprint 的每个生成节点（premise / arc / chapter / scene）都需要上下文。
如果允许各 generator 自己拼，会出现：

```text
· 同一事实在不同任务里被重复/冲突地使用
· 上下文规模不可控（prompt 爆炸）
· 无法回答"模型为什么看到/没看到某条事实"（V4-05 repair 与 Agent 都需要）
```

## Decision

1. 建立唯一 `ContextBuilder`：

   ```python
   context = context_builder.build(ContextRequest(...))  # → ContextBundle
   ```

2. ContextBuilder 负责：选择什么信息 / 排序 / 去重 / 压缩 / token budget / provenance。
   **不负责**：写故事、决定 Story Blueprint、调用 provider、质量评分、修改 Canon/StoryState。
3. 输出是**结构化 `ContextBundle`**（blocks + source_ids + revision + importance +
   token_estimate + selection_reason），**不是最终 prompt**；prompt 仍由
   `LLMContract.prompt`（PromptSpec）负责。
4. 预算优先级固定，且保护块（required canon / story_state / target）永不被静默删除：

   ```text
   required.canon > required.story_state > required.target > relevant.characters >
   recent.episodes > relevant.setup_payoff > relevant.locations > relevant.semantic >
   preferences
   ```

5. 每个被选中的条目都带 `selection_reason`（§35），可用于 Agent / Debug UI 解释
   "为什么这条信息被送给模型"。

## Consequences

正面：

* V4-04 的生成器只写 contract + 请求，不写上下文装配逻辑。
* V4-05 的 repair 与未来的 Agent 可以引用同一份 provenance 解释上下文。
* 预算行为可测试（保护块、drop 原因、overflow 报告）。

代价：

* 业务侧必须提供结构化请求（novel_id / revision / operation / target / characters…），
  不能随手塞一整段文本。
* ContextBuilder 需要同时理解 memory 检索契约与预算语义（但**不理解**故事语义）。

## Alternatives considered

| 方案 | 为什么不选 |
| --- | --- |
| 各 generator 自己拼上下文（V3 现状） | 无法保证一致性、预算与可解释性；V4-05 无从复现"当时模型看到了什么" |
| ContextBuilder 直接返回拼好的 prompt 字符串 | 会与 `LLMContract` 的 prompt 责任重叠，并丢失结构化 provenance |
| 用 embedding top-k 直接决定上下文 | 无结构化保证（可能漏 required canon），且不可解释 |

## Evidence

```text
src/novelforge/memory/context/builder.py   ContextRequest / ContextBlock / ContextBundle / build()
src/novelforge/memory/context/budget.py    固定优先级 + 保护块 + overflow 报告
src/novelforge/memory/context/compression.py 压缩保留来源与 contract_version
src/novelforge/memory/service.py           search_semantic（只返回命中项）
tests/memory/test_context_builder.py       golden 场景 + provenance + 确定性 + 去重
tests/memory/test_budget.py                优先级 / 保护块 / 超预算
```

