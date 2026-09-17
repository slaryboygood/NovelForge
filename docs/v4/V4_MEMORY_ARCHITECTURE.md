# NovelForge V4 — Memory Architecture（设计稿）

> 状态：**V4-00 Architecture / Proposed — 只设计，不实现**
> 依据：`docs/v4/V4_ARCHITECTURE.md` §4（`memory/*` 只允许依赖 persistence 只读 + ai.gateway）、§6

---

## 1. 反目标（先说清楚不做什么）

```text
❌ Memory = 一堆 embeddings
❌ Memory = 把整本小说塞进 prompt
❌ Memory = 第二套事实来源
❌ Memory 可以被 Agent 直接写入并当作事实使用
```

正式定位：

```text
Memory = 派生检索层（derived retrieval layer）
  · 可以重建（可从 Canon / StoryState / 正文 revision / 大纲重算）
  · 永不权威（任何与 Canon / StoryState 冲突的检索结果必须以 truth 为准）
  · 有归属（每条记忆带 novel_id + source revision）
```

---

## 2. 五类记忆与权威关系

| 记忆类型 | 内容 | 是否 truth | 来源（V4） | V3 现状 |
| --- | --- | --- | --- | --- |
| **Canon Memory** | 不可变事实：身份 / 世界规则 / 已确认历史 / 已发生事件 / 已死亡角色 / 重要物品 / 固定关系 | **是**（由 Canon 拥有） | `persistence.canon_repo`（现 `canon/repository.py`） | 已存在（SQLite，但路径硬编码单作品） |
| **Story State Memory** | 可变当前状态：时间 / 地点 / 人物状态 / 资源 / 关系 / 已知信息 / 未解决冲突 / 当前目标 | **是**（由 StoryState 拥有） | `persistence.story_state`（现 `story_engine/storage.py`） | 已存在 |
| **Episodic Memory** | 按章 / 场景：发生了什么、谁知道什么、谁做了什么、后果 | 否（派生，来源是章节 revision + StoryState effect_log） | 章节 revision + `state.effect_log` | **不存在**（V3 没有任何章级摘要存储） |
| **Semantic Memory** | 长期可检索信息：人物特征 / 地点 / 世界设定 / 关系 / 伏笔 / 主题 / 作者偏好 / 文风 | 否（派生索引） | Canon + ContentPack + 大纲 + 章节 revision | 部分：`*_view.py` 快照可即时计算，无持久索引 |
| **Author Preferences** | 作者长期偏好：文风、对话比例、章节长度、节奏、视角、禁用表达、偏好冲突类型、不希望出现的套路 | 否（配置态，author-owned） | 作者显式设置 | **不存在**（只有 `profile.tone` / `themes` 与浏览器 localStorage moodboard） |

### 2.1 权威层级图

```text
                    ┌──────────────────────────────┐
   truth（唯一）    │ Canon（不可变事实）           │
                    │ StoryState（可变当前状态）     │
                    └──────────────┬───────────────┘
                                   │ 只读派生
                    ┌──────────────▼───────────────┐
   derived          │ Episodic / Semantic / Index   │  ← 可重建、可丢弃、永不覆盖 truth
                    └──────────────┬───────────────┘
                                   │ 检索
                    ┌──────────────▼───────────────┐
   consumption      │ Context Builder → LLM Gateway │
                    └──────────────────────────────┘
```

**不变式（V4 必须可机械校验）**

```text
IMMUTABLE_FACT_FLOWS_ONE_WAY      Canon → memory → context，不得反向
MUTABLE_STATE_HAS_ONE_OWNER       StoryState 只能由 ActionResolver 写
MEMORY_NEVER_OVERWRITES_TRUTH     检索冲突时以 truth 为准并记录冲突
DERIVED_MEMORY_MUST_BE_REBUILDABLE 删除整个 memory 层不应丢任何事实
```

---

## 3. 命名冲突与处理（必须先做）

**现状**：`story_engine/memory.py` + `memory_view.py` 已经是「三视角知识」
（谁知道什么 / 伏笔 / 义务），并被 `writer_integration._state_block()` 消费。

**决定**：

```text
旧 story_engine/memory.py      → domain/knowledge.py    （故事内知识事实，属于 StoryState 语义）
旧 story_engine/memory_view.py → application/projections/knowledge.py
V4 memory/*                    → 全新的派生检索层
```

理由：同一个词在 V4 里只能有一个含义（`AGENTS.md` §5 canonical identity 原则的直接应用）。

---

## 4. 各层设计

### 4.1 Canon Memory

```text
owner      : persistence.canon_repo（唯一写 SQL 处）
读接口     : facts / events / entities / knowledge / foreshadows / graph / lineage
不可变     : happened 事实一旦确认不可改写（既有 Canon 语义，KEEP）
可变       : status（planned → happened 的提升走 CanonService）
索引       : memory 层可建立只读索引（实体 → fact_id），但 fact 本身只在 Canon
```

V4 必须修复的现存缺陷：`canon/wasteland_001.sqlite` 路径硬编码出现在 4 处
（`canon_routes.py`、`export_package.py`、`writer_integration.py`、`inspector.py`）。
按 `novel_id` 参数化后，Canon Memory 才能对任意作品成立。

### 4.2 Story State Memory

```text
owner      : persistence.story_state（唯一写入口 ActionResolver）
读接口     : world_snapshot / character_snapshot / plot_snapshot / progression_snapshot /
             memory_snapshot（现 *_view.py，全部只读）
结构       : timeline / location / characters / relationships / knowledge / resources /
             abilities / factions / flags / identities / promises / events / plots /
             effect_log / delayed_effects
```

**`effect_log` 是 episodic memory 的事实来源**：每次推进记录 op / target / source / tick，
可追溯数值来源。V4 的章节摘要必须在 `source_ids` 里指向对应 effect_log 条目，
而不是「模型自己回忆」。

### 4.3 Episodic Memory（V4 新增，当前完全缺失）

```text
单位      : 章 / 场景
字段      : chapter_id, revision, summary, who_learned_what, who_did_what,
            consequences, open_threads, source_ids（effect_log / chapter revision / canon refs）
生成方式  : 章节 revision 落盘后由 utility 模型生成摘要（contract: chapter_summary.v1）
校验      : 摘要中出现的实体 id 必须存在于 Canon / StoryState（否则标记 unresolved，不猜）
可重建    : 可从章节正文 + effect_log 重新生成
```

> **现状证据（缺口）**：`WriterContextBuilder.TRUTH_BLOCKS` 的 6 个 block 是
> `canon_truth / story_state / historical_repair / planning / chapter_plan / writer_guidance`
> —— **没有「最近 N 章发生了什么」这一块**。这意味着 V3 写第 87 章时，模型看不到第 84–86 章
> 的具体内容（只能看到 chapter_plan 与 story state 摘要）。这是 V4 记忆层最直接的收益点。

### 4.4 Semantic Memory

```text
对象      : 人物 / 地点 / 势力 / 关系 / 世界设定 / 伏笔 / 主题
来源      : Canon fact + ContentPack + 大纲 + 章节 revision
形态      : 结构化索引（entity → 出现位置 / 属性 / 相关章节）
可选增强  : embedding（仅作为「候选召回」手段，不作为裁判）
检索协议  : 返回 (id, kind, text, source_refs, score)，score 只用于排序
```

关系到大纲/伏笔时，语义记忆必须复用既有模型（`Foreshadow`、`ProgressionTree`、
`Relationship`），**不新造平行实体**。

### 4.5 Author Preferences

```text
作用域    : Global Author Preference → Project → Novel → Chapter Override
优先级    : Chapter > Novel > Project > Global
内容      : 文风 / 对话比例 / 章节长度 / 节奏 / 视角 / 禁用表达 / 偏好冲突类型 /
            不希望出现的套路 / 人物塑造偏好 / 题材习惯
写入方式  : 只能由作者显式确认（AI 不得自行推断并保存偏好）
来源保护  : 偏好属于 config（`DESIGN INTENT`），不等于 Canon 事实
```

> 现状证据：V3 只有 `NovelProfile.tone` / `themes`（`profile.py`）与浏览器
> `localStorage` 的 moodboard（`novelforge.moodboard.<novel_id>`，见 `docs/DATA_MODEL.md`）。
> 这些是**碎片**，不能构成合同意义上的「作者偏好记忆」。

---

## 5. Context Builder：生成第 N 章时，上下文从哪里来？

这是 DoD 的必答项。以下为 V4 的目标装配（对照 V3 现状）。

| 上下文块 | 来源（V4） | V3 现状 | 预算建议 |
| --- | --- | --- | --- |
| 当前章节计划 | `OutlinePackage` / `ChapterSemanticIR` / `StoryPlanningIR`（planned） | ✅ `chapter_plan` block | 1 条 + 信息变更列表 |
| 最近 3 章 episodic | `memory.episodic`（派生） | ❌ **缺失** | 3 条摘要，每条 ≤ 300 字 |
| 相关角色 | `Canon` + `StoryState.characters` + `memory.semantic` | ✅ `story_state` block（全部角色，无筛选） | 相关角色 ≤ 8 |
| 相关地点 | `StoryState.location.known` + `Canon` | ✅ `story_state` block（全部地点） | 当前 + 相关 ≤ 6 |
| 当前 StoryState | `world_snapshot()` | ✅ `story_state` block（摘要 1 条 + 知识 ≤ 10） | 摘要 + 关键字段 |
| 相关 Canon | `CanonRepository.facts(novel_id)` | ✅ `canon_truth` block（前 40 条） | 相关性筛选后 ≤ 20 |
| 未完成伏笔 | `StoryState.foreshadows` | ✅（经 story_state） | 全部未回收 |
| 作者风格偏好 | `memory.author_preferences` | ❌ **缺失** | ≤ 10 条规则 |
| writer 指导（必做/禁做/创作空间） | `WriterPackage` | ✅ `writer_guidance` block | 全部 |
| 历史修复证据 | `legacy.historical_ir` | ✅ `historical_repair` block | 仅相关章节 |

### 5.1 检索而非全量（V3 已经有的正确做法）

V3 的 `WriterContextBuilder` 已经实现了三件对的事（V4 必须继承，不能回退）：

```text
1. 分层（truth_layer: occurred / historical_repair / planned / ui_derived）
2. 跨块去重（同一 key 只出现在最高优先级 block，记录 dropped_block）
3. 预算（BLOCK_BUDGET = 40 items/block，超出记 dropped_count）
```

V4 在此基础上增加两件：

```text
4. 相关性筛选（按 chapter plan 的实体 / 地点 / 伏笔引用筛选，而不是取前 N 条）
5. 冲突检测（检索结果与 truth 不一致时记录 conflict，不静默采用）
```

### 5.2 上下文预算示例（生成第 87 章）

```text
chapter_plan        1 条（目标 / 冲突 / 转折 / 钩子 / 信息释放）
episodic            87-1, 87-2, 87-3 摘要（各 ≤ 300 字）
characters          出场角色 + 被引用角色（≤ 8）
locations           当前地点 + 本章涉及（≤ 6）
story_state         时间 / 地点 / 资源 / 未解冲突摘要
canon_refs          与出场角色 / 地点 / 伏笔相关的 facts（≤ 20）
foreshadows         全部未回收（通常 < 10）
author_preferences  ≤ 10 条规则
writer_guidance     全部 required / forbidden / creative_space
```

反例（禁止）：

```text
❌ 把整本 120 章正文拼进 prompt
❌ 把全部 500 条 Canon fact 无条件塞入
❌ 用 embedding top-k 直接替代「角色 / 地点 / 伏笔」的结构化筛选
```

---

## 6. 生命周期与失效

```text
产生     : 章节 revision 落盘 / Canon 变更 / 作者改偏好 / 大纲变更
失效     : source revision 变化 → 对应记忆条目标记 stale（不立即删除）
重建     : 支持「全量重建」命令（删除 memory 层后重算，结果应等价）
一致性   : memory 层自检报告（条数 / stale 数 / 冲突数 / 覆盖率）
```

---

## 7. 存储归属

```text
novel/authoring/<novel_id>/memory/
  episodic/<chapter_id>@<revision>.json
  semantic/index.json
  preferences.json           （作者偏好；也可回落到 profile，需二选一并文档化）
  embeddings/…               （可选，纯缓存，可删除）
  MANIFEST.json              （novel_id / built_at / source_digests / rebuildable: true）
```

硬约束：

```text
memory 目录可被完整删除而不影响任何 truth（MUST be verifiable by test）
memory 中的内容不得出现在 export 的「事实」分区（只能出现在阅读用派生分区）
```

---

## 8. 与 Quality / Export 的关系

```text
Quality  ← 用 episodic / semantic 做重复与连续性检查（Q3 / Q6）
           但结论必须能回到 source_ids（evidence 链）
Export   ← ExportService 只读 truth + 显式允许的派生分区
           记忆摘要可以出现在「阅读用派生信息」，不得伪装成事实
```

---

## 9. 验收判据（V4-03）

```text
[ ] 删除 memory 目录后，Canon / StoryState / 大纲 / 正文 revision 完全不变
[ ] 第 N 章上下文包含「最近 3 章 episodic」，且每条摘要带 source_ids
[ ] 检索结果与 truth 冲突时有显式 conflict 记录（不静默采用）
[ ] Author Preference 只能由作者写入（无 AI 自动写偏好路径）
[ ] `story_engine/memory.py` 已改名，全仓不存在两个 `memory` 语义
[ ] 上下文规模与 token 数有预算上限，且超限时按相关性裁剪（有测试）
[ ] Canon 路径按 novel_id 参数化（非 wasteland_001 作品可正确检索）
```

