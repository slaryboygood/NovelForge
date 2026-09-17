# V4-03 STORY MEMORY RESULT

> 阶段：**V4-03 Story Memory & Context Builder**
> 分支：`v4-03-memory-integration`
> 基线：`v4-02-llm-gateway`（V4-02 PASS，1004 passed / 7 skipped）
> 结论：**V4-03 = PASS**

---

## 1. Existing memory / retrieval inventory

| 位置 | 现状含义 | V4-03 处理 |
| --- | --- | --- |
| `story_engine/memory.py`（146 行） | **V2-E 三视角知识**：author / reader / character 的知识查询层（`knows` / `holders_of` / `unresolved_conflicts` / `outstanding_promises` / `open_foreshadows`）——属于 domain 事实，**不是** V4 Story Memory | **KEEP，不改名**（§28；V4-00 分类 KEEP）。V4 使用新的 `src/novelforge/memory/` 命名空间 |
| `story_engine/memory_view.py`（167 行） | 记忆面板只读投影（上面那层的视图） | KEEP（不动） |
| `story_builder/writer_integration.py`（`WriterContextBuilder`） | Writer 的 6 层 block + 跨块去重 + 每块 40 条上限 | **设计被继承**（分层/去重/预算思路），实现属于 V4-06 范围，本阶段不改 |
| `story_engine/canon/repository.py` + `canon/semantic.py` | Canon 事实存储与候选/关系分类 | 作为 Canon retrieval 的只读来源被 `CanonMemorySource` 使用 |
| `story_engine/*_view.py`（world / character / plot / progression / memory） | 只读快照投影 | 作为 StoryState retrieval 的只读来源被 `StoryStateMemorySource` 使用 |
| `story_engine/state.py`（`effect_log` / `knowledge` / `promises` / `plots`） | 已发生事实与状态 | episode 推导的 canonical 来源（`derive_episodes`） |
| `story_engine/chapter_ir/*`、`planning/*`、`outline_forge` | 章节语义 IR / 规划 IR / 大纲 | 通过稳定的 `source_type`（`chapter_ir` / `planning_ir` / `blueprint_node` / `outline`）进入同一契约，为 V4-04 预留 |
| `story_engine/reconstruction.py`、`historical_ir.py`、`repair.py` | 570 章历史 / M11 修复（数据已在 V4-01 删除） | **不作为**记忆来源（§7 明确禁止） |
| `novel/final/**` | 旧正文（V4-01 已删除） | **不作为**记忆来源 |

结论：V4-03 **不**复用 `story_engine/memory.py` 的语义，也不覆盖它；
新模块只做"派生检索 + 上下文选择"。

---

## 2. Public Memory contracts

`novelforge.memory.__all__`（28 个符号，刻意精简，§10）：

```text
入口        MemoryService / build_default_service
检索契约    MemoryItem / MemoryQuery / MemoryResult / MemoryScope / MemorySource / RetrievalPolicy
上下文      ContextBuilder / ContextRequest / ContextBundle / ContextBlock /
            CONTEXT_BUNDLE_SCHEMA_VERSION / BLOCK_PRIORITY_ORDER /
            DeterministicTokenEstimator / TokenEstimator
偏好        AuthorPreference / AuthorPreferenceService / PREFERENCE_SCOPE_ORDER
压缩        DeterministicTruncatingCompressor / GatewayCompressor / NullCompressor
版本/错误   MEMORY_SCHEMA_VERSION / MemoryError / MemoryIsolationError /
            MemorySourceError / PreferenceScopeError / StaleMemoryError
```

**未公开**（内部实现）：`MemoryIndex`、`IndexEntry`、`EpisodicStore`、`SemanticIndex`、
`LocalHashEmbedding` / `NullEmbeddingProvider`、`scoring.py`、`sources/*`、`retrieval.py` 等。
有测试断言这些不在 `__all__` 里。

---

## 3. Canon retrieval

```text
CanonMemorySource（memory/sources/canon.py）
  · 只读：按 novel_id 打开 Canon SQLite（persistence.paths.canon_db_path）
  · 投影：facts → canon_fact 条目，entities → canon_entity 条目
  · 每条带 source_id / revision / revision_key（canon:<novel_id>）
  · DB 不存在 → 返回空（不回退到别的作品、不创建文件）
```

守卫：`tests/memory/test_canon_retrieval.py` 断言 **Canon DB 的 mtime/size 在检索前后不变**
（Memory 不得修改 Canon）。

---

## 4. StoryState retrieval

```text
StoryStateMemorySource（memory/sources/story_state.py）
  · 只读：经 creator_context + world_snapshot / memory.unresolved_conflicts / outstanding_promises
  · 投影：timeline / location.current / character.* / resource.* / relationship.* /
          promise.* / conflict.*（open 标记）
  · revision_key = story_state:<novel_id>；revision = effect_log 条数
```

不维护第二套 StoryState：条目全部指向 `story_state` 来源（有测试断言）。

---

## 5. Episodic memory

```text
EpisodeEntry / EpisodicStore / derive_episodes（memory/episodic/store.py）
  · 来源：StoryState.effect_log 按 source（行动 / 事件）分组 + resolved/active events
  · 字段：episode_id / novel_id / revision / source_ids / chapter_id / scene_id /
          what_happened / who_acted / who_knows / state_changes /
          relationship_changes / new_information / setup / payoff / unresolved / tick
  · created_at + memory_schema_version + 可重建（created_at 可注入 → 纯函数）
  · 未来 Blueprint / Scene Card 通过同一契约进入（source_type="blueprint_node"）
```

明确**不读**：正文、`novel/final`、570 章历史（有测试断言条目中不含这些来源）。

---

## 6. Semantic memory

```text
SemanticIndex / SemanticEntry（memory/semantic/index.py）
  · 结构化 metadata + 关键词重叠（含子串匹配），可选 embedding 加成
  · embedding 通过 EmbeddingProvider 协议注入；默认 NullEmbeddingProvider（不产生向量）
  · LocalHashEmbedding(dim=32) 为离线确定性伪向量，仅用于验证 hybrid 管道与 tie-break
  · 对外条目统一表现为 source_type="semantic"，origin 保留在 metadata（provenance）
  · 只返回**命中**条目（无全量回退），并由 ContextBuilder 的 semantic block 使用
```

向量数据库**未引入**（§24）：本地、确定性、无网络、可重建。

---

## 7. Author preferences

```text
AuthorPreference（scope / scope_id / key / value / source / inferred / created_at / updated_at）
AuthorPreferenceService（set / add_many / all / relevant / resolve / as_items / save / load）
作用域与优先级：Operation Override > Novel > Project > Global（deterministic merge）
```

规则与验证：

```text
· operation 作用域只对**匹配**的 operation 生效；未指定 operation 时不参与（有测试）
· 同作用域下 explicit 优先于 inferred；inferred 必须显式标记（有测试）
· 值必须可 JSON 序列化（否则报 PreferenceScopeError）
· 存储经 persistence.paths.memory_preferences_path（memory 不自行拼路径）
· 按 novel 隔离：A 的偏好不进入 B（有测试）
```

V4-03 只实现**显式偏好**；自动学习（§16）不在范围内。

---

## 8. Context Builder

```python
context = ContextBuilder(memory, preferences=..., compressor=...).build(ContextRequest(...))
```

组装出的 block（顺序固定）：

```text
required.canon / required.story_state / required.target /
relevant.characters / recent.episodes / relevant.setup_payoff /
relevant.locations / relevant.semantic / preferences
```

* 输出是结构化 `ContextBundle`（blocks + source_ids + revision + importance +
  token_estimate + selection_reason + provenance + dropped + budget），**不是 prompt**。
* `to_memory_context()` 给 `LLMContract` 提供结构化 context（prompt 仍由 contract 负责）。
* 跨 block 去重：同一 memory_id 只保留优先级最高的 block，重复项记入 `dropped`。
* current-state 与 open-setup 分离：promise/conflict/open episode 归 `relevant.setup_payoff`，
  不再重复出现在 story_state 块。

---

## 9. Token budgeting

```text
固定优先级（数值越小越先保留）：
  required.canon(0) > required.story_state(1) > required.target(2) >
  relevant.characters(3) > recent.episodes(4) > relevant.setup_payoff(5) >
  relevant.locations(6) > relevant.semantic(7) > preferences(8) > background(9)

保护块（永不被静默删除）：required.canon / required.story_state / required.target
超预算：先删低优先级条目（dropped 记录 budget_exceeded），保护块超预算则报告 overflow
估算：DeterministicTokenEstimator（ASCII 4 字符/token，非 ASCII 1.5 字符/token，保守）
```

测试覆盖：低优先级先删、保护块保留、overflow 报告、非法预算拒绝。

---

## 10. Compression

```text
DeterministicTruncatingCompressor   默认：确定性截断，标注 original_chars / compressor
GatewayCompressor                   可选：经 novelforge.ai（contract memory.summary.v1，cacheable）
NullCompressor                      不压缩
```

压缩结果**不是** source of truth：保留 `source_id` / `revision` / `contract_version` /
`compressed_at`，并在 `selection_reason` 标注 `compressed:*`。有测试断言摘要不丢来源、
同摘要命中缓存（同一 contract 只调用 1 次）。

---

## 11. Invalidation

```text
每条派生条目带 source.revision + metadata.revision_key（canon:<novel> / story_state:<novel> /
episodes:<novel>）
MemoryService.refresh_staleness()      按 canonical 当前 revision 自动标记 stale
MemoryService.stale_report()           报告漂移条目（indexed vs current）
MemoryService.rebuild()                重建索引（幂等：同一 canonical 状态 → 同 digest）
search() 默认排除 stale；include_stale=True 时仍会带 stale 标记并排在最后
```

有测试覆盖：revision 漂移 → stale；stale 默认排除；include_stale 时排序惩罚；
rebuild 恢复 freshness；rebuild 幂等。

---

## 12. Provenance

```text
MemoryItem.source       : source_type / source_id / revision / label / metadata
MemoryResult.provenance : memory_id / source_id / source_type / revision /
                          retrieval_reason / relevance
ContextBundle.provenance: 上述 + block_id + selection_reason
```

`selection_reason` 取值可解释（§35）：`required_canon` / `current_state` / `target_node` /
`entity_match` / `recent_episode` / `open_setup` / `location_match` / `semantic_match` /
`author_preference`（以及打分细节如 `keyword_hits=2`）。

---

## 13. AI Gateway integration

```text
允许：memory → novelforge.ai（Public Contract）
用途：压缩 / 摘要（GatewayCompressor 使用 cacheable contract memory.summary.v1@v1）
禁止：memory 直接 import provider 实现 / HTTP client；ai → memory 反向依赖
```

守卫：

```text
tests/v4/isolation/test_memory_ownership.py::test_memory_module_boundaries
tests/v4/isolation/test_memory_ownership.py::test_domain_and_ai_do_not_import_memory
tests/v4/isolation/test_module_boundaries.py（ai 边界 + provider SDK 归属）
```

单测使用本地 StubProvider（零网络、零真实模型，§32）。

---

## 14. Persistence integration

```text
新增（persistence/paths.py）：
  memory_dir(project_root, novel_id)        novel/authoring/story_engine/memory/<novel_id>
  memory_preferences_path / memory_episodes_path / memory_manifest_path
  artifact_kind 增加 "memory"
```

memory 自身**不含**任何路径字面量（守卫测试用 AST 断言 memory 包内不存在
`novel/...` / `workspace/...` 字符串字面量），全部经 `persistence.paths`。

---

## 15. Ownership isolation

```text
novel_id 过滤发生在**打分之前**（index 分区；service 与 query 都要求显式 novel_id）
跨作品请求 → MemoryIsolationError（service 与 ContextBuilder 两处都有测试）
```

`tests/v4/isolation/test_memory_ownership.py` 用**同名角色 + 同规则文本**的两本作品，
只给 B 加一条独有事实，断言：

```text
A 的检索结果 / ContextBundle 不含 B 的独有事实，也不含 "novel_beta"
B 的检索结果含该事实
A 的偏好不出现在 B 的 bundle 中
```

---

## 16. Module boundary verification

新增/扩展的机械守卫（`tests/v4/isolation/`）：

```text
test_memory_ownership.py
  · memory 不 import api / application / ai.providers / fastapi / mcp / HTTP client
  · domain（story_engine / story_builder）、ai、core、persistence 不得 import memory
  · memory 不自行拼 artifact 路径（AST 字符串字面量检查）
test_module_boundaries.py（扩展）
  · test_memory_does_not_depend_on_interface_or_application
  · test_domain_and_ai_do_not_import_memory
```

---

## 17. Tests

```text
pytest -q                          1074 passed / 7 skipped / 0 failed（360s）
tests/memory/**                      61 passed（全部离线、零真实模型）
tests/v4/**                          50 passed（含 6 个 memory 守卫）
python scripts/validate_project.py   PASS
tests/test_v2_frozen_guard.py        6 passed
tests/test_v3_frozen_guard.py        6 passed
```

tests/memory 覆盖（§32 清单）：

```text
contracts        公开契约精简 / 必填 novel_id / provenance 字段 / policy 校验 / schema version
canon retrieval  只读（DB fingerprint 不变）/ facts+entities 投影 / 缺失 DB 为空 / 关键词命中 / 跨作品
state retrieval  timeline·location·character·resource·promise / 不复制 truth / revision / open 标记 / 确定性
episodic         effect_log 推导 / 可重建（created_at 注入）/ Blueprint 契约 / 不读正文 / 可检索
semantic         结构化+关键词+子串 / novel 隔离 / Null embedding 默认 / 本地伪向量 hybrid / 从条目构建
preferences      作用域优先级 / inferred vs explicit / 校验 / 持久化 / novel 隔离 / provenance
context builder  golden 断言（canon/state/episode/setup/preference）/ 无关项排除 / 无 prompt 字符串 /
                 确定性 digest / 可解释 reason / revision / 去重 / 预算标记 / 跨作品拒绝
budget           估算确定性 / 固定优先级 / 低优先级先删 / 保护块 / overflow / 非法预算
compression      确定性截断保留来源 / Gateway 摘要（contract_version）/ 缓存命中 / 接入 ContextBuilder
invalidation     漂移标记 / 默认排除 / 排序惩罚 / rebuild 恢复 / 幂等
retrieval        结构化 items / 确定性 digest / tie-break / source_type 过滤 / top_k / required 不丢
```

### 17.1 测试数量变化解释（V4-02 → V4-03）

| 类别 | 变化 | 原因 |
| --- | --- | --- |
| `tests/memory/**` | **+61** | 本阶段新增（契约 / 检索 / episode / semantic / preferences / context / budget / compression / invalidation） |
| `tests/v4/isolation/**` | **+9** | 6 个 memory 隔离与边界用例 + 2 个 module boundary 用例 + 1 个 domain/ai 反向依赖守卫 |
| 既有测试 | ±0 | memory 不改动任何既有模块行为；`persistence.paths` 为纯新增函数 |

---

## 18. Frozen boundary

```text
novelforge-product-v3-final tag        未移动
novel/authoring frozen digest          未变化（guard PASS）
frozen Repair Contract / REPAIR_GATE_V1 未修改
StoryState / Canon 语义                 未修改（memory 只读投影，有 fingerprint 测试）
story_engine/memory.py                  未改名、未覆盖（§28）
```

---

## 19. Files created

```text
src/novelforge/memory/__init__.py
src/novelforge/memory/errors.py
src/novelforge/memory/contracts.py
src/novelforge/memory/scoring.py
src/novelforge/memory/index.py
src/novelforge/memory/retrieval.py
src/novelforge/memory/service.py
src/novelforge/memory/embedding.py
src/novelforge/memory/sources/__init__.py
src/novelforge/memory/sources/canon.py
src/novelforge/memory/sources/story_state.py
src/novelforge/memory/episodic/__init__.py
src/novelforge/memory/episodic/store.py
src/novelforge/memory/semantic/__init__.py
src/novelforge/memory/semantic/index.py
src/novelforge/memory/preferences/__init__.py
src/novelforge/memory/preferences/service.py
src/novelforge/memory/context/__init__.py
src/novelforge/memory/context/builder.py
src/novelforge/memory/context/budget.py
src/novelforge/memory/context/compression.py
tests/memory/support.py
tests/memory/test_contracts.py
tests/memory/test_retrieval_contract.py
tests/memory/test_canon_retrieval.py
tests/memory/test_story_state_retrieval.py
tests/memory/test_episodic.py
tests/memory/test_semantic.py
tests/memory/test_preferences.py
tests/memory/test_invalidation.py
tests/memory/test_context_builder.py
tests/memory/test_budget.py
tests/memory/test_compression.py
tests/v4/isolation/test_memory_ownership.py
docs/v4/adr/ADR-014-memory-is-derived-canon-remains-authoritative.md
docs/v4/adr/ADR-015-context-builder-owns-model-context-selection.md
docs/v4/V4_03_STORY_MEMORY_REPORT.md（本文件）
```

## 20. Files modified

```text
src/novelforge/persistence/paths.py      新增 memory 路径解析（唯一路径来源）
src/novelforge/persistence/__init__.py   导出上述函数
tests/v4/isolation/test_module_boundaries.py  扩展 memory 边界守卫
docs/v4/V4_MEMORY_ARCHITECTURE.md        §0.2 实施状态
docs/v4/V4_MODULE_BOUNDARIES.md          §3.8 memory 模块边界 + 状态台账
docs/v4/V4_ARCHITECTURE.md               Memory 边界行
docs/v4/V4_ARCHITECTURE_RISKS.md         R-06 / R-07 状态
docs/v4/V4_BRANCH_STRATEGY.md            V4-03 任务分支声明
docs/v4/adr/README.md                    ADR-014 / ADR-015 索引
```

## 21. Files deleted

```text
无。
（`story_engine/memory.py` 按 §28 保留原名原义；`novel/final` 与 570 章 historical 已在 V4-01 删除。）
```

---

## 22. Git branches

```text
v4-03-memory-integration（本阶段唯一分支）
```

任务书 §1 建议的 `v4-03a…v4-03e` 以**线性提交序列**实现（见 §23）：
单 agent 顺序执行时，分叉 + 合并只会产生无意义的合并提交；
提交边界即模块边界，且每个提交都保持默认测试套件可运行。

## 23. Git commits

```text
（1）docs(v4): freeze story memory contracts
（2）feat(memory): add retrieval contracts and stores
（3）feat(memory): add author preferences, context builder and service
（4）test(memory): add retrieval and context coverage
（5）test(v4): enforce memory module boundaries
（6）docs(v4): record v4-03 result
```

---

## 24. Remaining risks

| 风险 | 状态 | 说明 |
| --- | --- | --- |
| 记忆索引仅在进程内（无落盘） | 计划内 | 目录与路径已预留；落盘/缓存策略属于后续阶段（依赖真实使用数据） |
| embedding 未接入真实服务 | 有意 | 需要 V4-02 Gateway 先增加 embedding contract；当前用 Null + 本地确定性伪向量验证管道 |
| 语义检索仍是关键词/结构化，非向量召回 | 有意（§23–§24） | 命中率不足时再引入 embedding 加成，接口已就绪 |
| `LocalHashEmbedding` 不是语义相似度 | 已标注 | 明确写为"伪向量，仅验证管道与 tie-break"，不得用于质量判断 |
| 预算估算为字符启发式（非真实 tokenizer） | 已知 | 偏差方向保守（偏大）；真实 tokenizer 可在 V4-04 依据模型族接入 |
| Context Builder 尚未与真实生成任务接线 | 计划内 | V4-04 才定义 Story Blueprint 生成 contract |
| 4 处鸭子类型 provider（creative / settings_gen / ai_recommendations / outline_forge） | 未动（§38） | 仍属 V4-04 |
| `writer_integration.WriterContextBuilder` 与新 ContextBuilder 并存 | 已知 | 前者属 Writer/V4-06 范围；V4-03 未改动它，避免越界 |
| `memory.semantic` 需要显式构建/登记 | 已知 | 默认 `rebuild()` 只索引已有 semantic 条目；未来 Blueprint adapter 用 `add_semantic()` |

---

## 25. V4-04 readiness

§44 的验收问题，现在可以稳定回答：

```text
"我要设计下一场戏时，哪些已经确认的事实不能违反？"
  → required.canon（+ required_source_ids 强制入选）
"当前角色和世界状态是什么？"
  → required.story_state（timeline / location / character / resource）
"最近哪些事件会直接影响这一场？"
  → recent.episodes（由 StoryState effects 推导，带 source_ids 与 revision）
"哪些伏笔还没有回收？"
  → relevant.setup_payoff（open promise / conflict / open episode）
"作者明确要求避免什么？"
  → preferences（scope + inferred 标记 + provenance）
"在有限 Token 下哪些信息最值得送给模型？"
  → 固定优先级 + 保护块 + dropped 原因 + overflow 报告
"这些信息分别来自哪里、哪个 revision？"
  → provenance（source_type / source_id / revision / retrieval_reason / block_id）
```

```text
[x] memory 是独立模块，Public Contract 精简（28 个符号）
[x] memory 不拥有 Canon / StoryState；domain 与 ai 都不依赖 memory
[x] 四类检索（canon / story_state / episodic / semantic）全部可测、带 provenance
[x] 作者偏好四作用域 + 确定性 merge + explicit/inferred 区分
[x] ContextRequest / ContextBundle / token budget / 优先级 / 去重 / 确定性输出 / 非 prompt
[x] 失效：revision 可追踪、stale 可识别、canonical 变化不会静默当真
[x] AI 集成：摘要经 LLMGateway；单测零网络；memory 不直接调用 provider
[x] 默认测试套件 1074 passed / 7 skipped / 0 failed；frozen guards PASS
```

V4-04 可以开始：**Structured Story Blueprint Generation**（premise / character /
character arc / world / story arc / act·volume·arc / chapter plan / scene plan），
开工前按 `V4_BRANCH_STRATEGY.md` §3 填写任务分支声明（Primary Module = `generation`），
并直接消费本阶段的 `ContextBuilder` + `MemoryService`。

---

# V4-03 = PASS

