# V4-04 — Existing Generation Inventory

> 阶段：**V4-04 Structured Story Blueprint Generation**
> 目的：在写任何新生成代码之前，把 V3 现有「生成能力」的事实盘清楚，
> 并逐项给出 KEEP / ADAPT / REPLACE 判定（任务书 §4）。

---

## 1. 总表

| Current Module | Current Capability | Structured Contract | Hardcoded Creativity | LLM Usage | KEEP / ADAPT / REPLACE | Target Module |
| --- | --- | --- | --- | --- | --- | --- |
| `story_engine/creative.py` | 创意入口：题材 / 基调 / 卖点候选 + `CreativeBrief` | `CreativeBrief` / `GenreCandidate` / `ToneCandidate` / `SellingPointCandidate`（pydantic） | `GENRE_KEYWORDS`（题材关键词表）、`TONE_RULES`（6 条基调规则）、`SELLING_POINT_TEMPLATES`（7 条固定卖点）、`REASON_BY_GENRE` | 鸭子类型 `provider.generate_structured(...)`（L248）；默认 `provider=None` → `AI_UNAVAILABLE` | **ADAPT**：结构契约保留；创意文案表 → compatibility（登记移除条件）；LLM 路径迁到 Gateway | `generation/tasks/premise.py`（V4）+ legacy adapter |
| `story_engine/settings_gen.py` | 设定候选：世界规则 / 主角 / 角色 / 势力 / 关系 / 成长 / 矛盾 / 主线 / 伏笔 + `ContentPack` 骨架 | `SettingSeed` / `Candidate` / `ContentPack`（严格 schema + id 规则） | `RULE_TEMPLATES`(5)、`PROTAGONIST_ROLES`(5)、`SUPPORT_ROLES`(4)、`FACTION_SHAPES`(3)、`CONFLICT/RESOURCE/FACTION/RELATION_MARKERS`、`content_pack_draft()` 固定骨架（`起点场所` / `act_ask` / `ev_first_pressure`） | 鸭子类型 provider（L304）；默认无 provider | **ADAPT**：schema / id / 校验保留（业务约束）；固定骨架文案 → compatibility + 由 V4 Character/World 生成替代 | `generation/tasks/characters.py` + `generation/tasks/world.py` |
| `story_engine/outline_forge.py` | 四级大纲锻造（BOOK→VOLUME→ARC→CHAPTER）+ 质量门禁 | `OutlinePackage` / `OutlineItem`（成熟四级模型）+ `StructureSpec` | `NARRATIVE_BEATS`(8 个固定 beat)、`ChapterTitleLedger` 的「（第 N 次）」兜底、`第{number}章：{body}` 标题格式、`FIELD_LABEL_BLACKLIST` | 鸭子类型 provider（L889）只做标题/摘要润色；默认无 provider | **ADAPT**：结构模型与门禁 KEEP；标题/beat 模板 → 由 V4 Chapter/Scene 结构化生成替代 | `generation/tasks/chapter.py` |
| `story_builder/ai_recommendations.py` | 十步设计推荐的 AI 补充（只补文案，不新增结构） | `AIRecommendationDraft` / `AIOptionReason` / `AICustomSuggestion`（严格 schema） | prompt 文本（`_prompt`）；无固定创意表 | 鸭子类型 `StructuredRecommendationProvider`（L95） | **ADAPT**：合并/校验逻辑 KEEP（「AI 只能补充」）；provider 迁到 Gateway | legacy adapter（V4-04 迁移），未来并入 `generation` |
| `story_engine/journey.py` | 旅程场景渲染（rev1/rev2 固定场景文本 + 三原型建议） | `JourneyScene`（pydantic） | `suggestions_for()` 三原型硬编码行动、`scene()` 固定场景文本、`_success()` fallback 文案 | 无 | **REPLACE_BY_LLM（后续）**：V4-04 不迁移（属 Scene/正文边界）；登记 compatibility | V4-06 / V4-10 由 Scene Card + 外部写作承接 |
| `story_engine/spec/llm.py` | M3 SpecProposal provider | `SpecProposal`（严格 schema） | `SYSTEM_PROMPT` 常量 | V4-02 已迁到 `ai.legacy_support` | COMPATIBILITY（V4-02 已登记） | — |
| `story_engine/planning/chapter_compiler.py` | ArcPlan → Chapter Semantic IR（确定性渲染 writer-ready 字段） | `ChapterSemanticIR`（KEEP） | 字段拼接文案 | 无 | **ADAPT**：IR 模型 KEEP；渲染由 V4 Chapter/Scene 生成替代 | `generation/tasks/chapter.py` 的输出可编译成 ChapterIR |
| `story_engine/planning/outline_compiler.py` / `spine_builder.py` | Spine → Volume/Arc（proposal-only，确定性） | `StoryPlanningIR`（KEEP） | 结构模板（预算/分段，非创意文案） | 无 | **ADAPT**：结构约束 KEEP；V4 StructuralUnit 与其对齐 | `generation/tasks/story.py` |
| `story_engine/canon/*` | Canon 稳定身份 / 校验 / 图 | `CanonFact` / `CanonEntity` …（KEEP） | 无 | 无 | **KEEP**（作为 Blueprint 的只读 Canon 约束来源） | — |
| `story_engine/chapter_ir/*` | Chapter Semantic IR + 严格 gate + evidence | `ChapterSemanticIR`（KEEP） | 无 | 可选 judge/verifier（Null 默认） | **KEEP / ADAPT**：作为 Scene/Chapter 生成的落地结构之一 | `blueprint` ↔ `chapter_ir` 映射 |
| `novel/config/**` | 题材模板 / 内容包 / 十步目录 | YAML/JSON 数据契约 | 题材数据（属**数据**，不是代码硬编码） | 无 | **KEEP**（Blueprint 的 genre/tone 约束来源） | — |
| `story_engine/creative.py::deterministic_*`、`settings_gen.deterministic_seed` | 无模型时的确定性降级创作 | 同上 | 是（固定模板） | 无 | **COMPATIBILITY**（V3 产品默认路径；见 §3） | legacy（登记移除条件） |

---

## 2. 现有结构化契约（优先 ADAPT，不重写）

| 契约 | 位置 | 成熟度 | V4-04 处理 |
| --- | --- | --- | --- |
| `ContentPack` | `story_engine/content.py` | 严格 schema + 校验 + 运行时消费 | **KEEP**：Blueprint 的 World/Character 提案可通过 `content_pack_draft` 的校验规则验证 |
| `NovelProfile` | `story_engine/profile.py` | 作品身份唯一来源 | **KEEP**（不改） |
| `OutlinePackage` / `OutlineItem` | `story_builder/models.py` | 四级大纲 + 版本 + 导出 | **ADAPT**：V4 `ChapterCard` 可编译成 `OutlineItem`；不新建平行大纲模型 |
| `ChapterSemanticIR` | `story_engine/chapter_ir/models.py` | 严格 gate + evidence + compiler | **ADAPT**：V4 `SceneCard` 的字段与之一致（purpose/goal/conflict/turn/outcome/setup/payoff） |
| `StoryPlanningIR` | `story_engine/planning/models.py` | 不可变 revision + 严格 validator | **ADAPT**：V4 `StoryArc` / `StructuralUnit` 字段与 `Spine/Arc/Chapter` 概念对齐 |
| `StoryState` / `CanonFact` | `story_engine/state.py` / `canon/*` | 事实权威 | **KEEP**：只作为生成上下文（经 Memory），生成结果**不**写入 |

---

## 3. 硬编码创作内容：分类与处置

分类依据（任务书 §41）：业务约束 / schema-enum → KEEP；创意 fallback / 固定文案 / 同义词替换 /
固定标题模板 / genre-specific 创意 if-else → REPLACE_BY_LLM 或 DELETE（compatibility）。

| 位置 | 内容 | 判定 | V4-04 动作 |
| --- | --- | --- | --- |
| `creative.GENRE_KEYWORDS` | 题材→关键词表 | **业务约束**（把创意匹配到真实模板 / 内容包） | **KEEP**（不是创意内容） |
| `creative.TONE_RULES` / `SELLING_POINT_TEMPLATES` / `REASON_BY_GENRE` | 固定基调与卖点文案 | **创意内容** | **REPLACE_BY_LLM**：LLM 路径已迁 Gateway；确定性表降级为 compatibility（模型不可用时的 V3 产品默认路径） |
| `settings_gen.RULE_TEMPLATES` / `PROTAGONIST_ROLES` / `SUPPORT_ROLES` / `FACTION_SHAPES` / `*_MARKERS` | 固定候选文案 | **创意内容** | **REPLACE_BY_LLM**：由 V4 `character` / `world` 结构化生成取代；表保留为 compatibility |
| `settings_gen.content_pack_draft()` 固定骨架 | 固定地点 / 行动 / 事件 id 与文案 | **创意内容 + schema 骨架** | **ADAPT**：schema 与 id 规则 KEEP；文案由 V4 生成；固定骨架降级为 compatibility |
| `outline_forge.NARRATIVE_BEATS` | 8 个固定叙事 beat | **创意内容** | **REPLACE_BY_LLM**：V4 `ChapterCard.scene_function` 由 LLM 决定（结构化枚举） |
| `outline_forge.ChapterTitleLedger`（`（第 N 次）`） | 标题去重兜底 | **创意内容（NF-003 根因）** | **DELETE（后续）**：V4 标题来自 LLM；V4-04 不再使用该兜底生成新内容；旧路径保留 compatibility |
| `journey.suggestions_for()` / `scene()` 固定文本 | 场景与建议文案 | **创意内容** | **REPLACE_BY_LLM（V4-06 之后）**：本阶段不动，只登记 |
| `FIELD_LABEL_BLACKLIST` | 「字段标签不得进入标题」 | **业务约束（质量规则）** | **KEEP**（V4 生成后仍用它做结构性校验） |

> **本阶段的范围决定（如实说明）**：V4-04 **不删除** V3 的确定性创作表，
> 因为它们仍是 V3 产品面（UI / 浏览器门禁 / 900+ 测试）在"未配置模型"时的默认行为；
> 删除它们属于 V4-05/V4-10 的产品决策。V4-04 的动作是：
> ① 建立结构化 Blueprint 生成路径（新内容默认走 LLM）；
> ② 把四处鸭子 provider 迁到 Gateway（配置模型时不再有第二条调用路径）；
> ③ 为这些表登记 removal condition（见 `src/novelforge/legacy/manifest.py`）。

---

## 4. LLM 调用现状（V4-02 遗留四处）

```text
creative.py:248            CreativeIdeaProvider.enrich(...)        → prompt + context → Mapping（校验越界 id）
settings_gen.py:304        SettingsProvider.enrich(...)           → prompt + context → Mapping（校验越界 id）
ai_recommendations.py:95   AIRecommendationSupplementer.recommend → prompt + public context → AIRecommendationDraft
outline_forge.py:889       OutlineForge polish                    → prompt → 只改写既有 item 的标题/摘要/勾子
```

共同点：`generate_structured(chapter_id=..., stage=..., skill_name=..., prompt=...,
context=..., output_model=..., workspace=...)`，返回 `(?, draft)`，draft 可为 Mapping 或模型实例。

V4-04 处置（§14）：提供一个 **Gateway 支撑的兼容 provider**（`ai.legacy_support.GatewayStructuredProvider`），
四处调用点在生产配置下使用它；调用点自身不含 HTTP / provider 实现，行为与校验逻辑保持不变。

---

## 5. 目标模块映射（V4-04 之后）

```text
blueprint/     Blueprint 节点模型（premise/theme/world/character/arc/story_arc/unit/chapter/scene/
               causal_link/setup/payoff）+ Repository（canonical store）+ validation + lifecycle
generation/    BlueprintGenerationService + 版本化 LLM Contract（blueprint.*.v1）+ tasks/*
application/services/blueprint.py   业务入口（REST / MCP / Agent 将来共用）
legacy/        V3 规则生成器（compatibility，登记移除条件）
```

