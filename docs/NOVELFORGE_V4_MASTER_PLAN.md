# NovelForge V4 架构与实施总计划

> 状态：V4 规划稿  
> 基线：NovelForge V3 Final — Functional Closure  
> 目标：将 NovelForge 从“带 UI 的小说生成工具”重构为“Agent 可直接接入的小说创作系统 + MCP Server + 可插拔质量闭环平台”。

---

## 1. V4 的核心定位

NovelForge V4 不再只是一个前端应用。

V4 应同时具备四种身份：

1. **小说创作引擎**  
   负责项目、设定、人物、世界、故事状态、大纲、章节、写作、修订与导出。

2. **MCP Server**  
   让 Codex、ChatGPT、Claude、IDE Agent 或其他支持 MCP 的 Agent 可以直接读取 NovelForge 状态并执行创作操作。

3. **LLM 编排层**  
   统一接入一个或多个大模型 API，负责生成、评估、修订、摘要、重写、角色推演等任务。

4. **质量闭环系统**  
   所有生成内容必须经过结构校验、事实一致性、语义重复、人物一致性、因果逻辑、节奏、交付质量等检查，失败后进行定向修订，而不是直接进入最终结果。

V4 的核心原则：

```text
NovelForge 不替大模型“硬写小说”
NovelForge 负责约束、状态、记忆、编排、验证、修订和交付
```

---

# 2. V4 总体目标

## 2.1 必须实现

- 大模型 API 正式接入
- MCP Server
- Agent 可直接操作 NovelForge
- Plugin / 扩展机制
- 统一 LLM Gateway
- 结构化输出契约
- 小说长期记忆
- 项目上下文检索
- 生成质量闭环
- 自动定向修订
- Writer 真正可编辑
- 版本 / 修订历史
- 可恢复操作
- 统一 Export
- 结构化导出
- 交付质量验证
- 成本 / Token / 调用跟踪
- 统一日志和质量证据
- UI 简化
- MCP / API / UI 共用同一业务服务层
- 模块级目录隔离与明确依赖边界
- 支持按模块拆分并行任务分支，降低多 Agent / 多开发者冲突

---

# 3. V4 明确删除或弱化的 V3 结构

V4 不继续在 V3 的规则生成器上堆逻辑。

## 3.1 应逐步删除的内容

### A. 硬编码创作逻辑

例如：

- 固定章节标题模板
- “阶段目标 / 长期方向”式标题生成
- 同义词替换器
- 为避免重复而添加“第 N 次”
- 大量题材 specific `if/else`
- 人物原型固定文案
- 固定剧情摘要拼接
- 规则式文学表达
- 人工维护的大量 creative fallback

原则：

> 业务规则可以硬编码，创作内容不应该大量硬编码。

---

### B. 重复的状态计算

禁止重新出现：

```text
Landing 一套 progress
Workspace 一套 progress
Export 一套 progress
Agent 又一套 progress
```

V4 必须只有：

```text
JourneyProjection
```

作为唯一状态投影来源。

UI / API / MCP 全部消费同一个结果。

---

### C. 多套 Writer 存储

V4 只保留一个 canonical writer store。

旧路径只允许 migration / read-only compatibility。

---

### D. 多套 Export

所有导出必须统一经过：

```text
ExportService
```

UI、API、MCP 不允许各自拼导出内容。

---

### E. UI 中直接包含业务判断

UI 只负责：

- 展示
- 用户输入
- 发起 command
- 展示状态

业务规则必须在后端 service / domain 层。

---

### F. 自动加载历史作品作为当前小说数据

任何 legacy / historical source 必须：

```text
显式绑定到 novel_id
```

不得因为磁盘上存在旧目录就自动混入新作品。

---

# 4. V4 推荐目录结构

```text
src/novelforge/
│
├── core/
│   ├── ids.py
│   ├── errors.py
│   ├── events.py
│   ├── transactions.py
│   └── result.py
│
├── domain/
│   ├── novel.py
│   ├── character.py
│   ├── location.py
│   ├── faction.py
│   ├── canon.py
│   ├── story_state.py
│   ├── outline.py
│   ├── chapter.py
│   ├── scene.py
│   ├── draft.py
│   └── revision.py
│
├── ai/
│   ├── gateway.py
│   ├── provider.py
│   ├── router.py
│   ├── contracts.py
│   ├── structured_output.py
│   ├── retry.py
│   ├── cache.py
│   ├── usage.py
│   └── trace.py
│
├── memory/
│   ├── store.py
│   ├── retrieval.py
│   ├── compressor.py
│   ├── embeddings.py
│   ├── episodic.py
│   ├── semantic.py
│   └── author_preferences.py
│
├── generation/
│   ├── premise.py
│   ├── world.py
│   ├── characters.py
│   ├── story_arc.py
│   ├── outline.py
│   ├── chapter_plan.py
│   ├── scene_plan.py
│   └── draft.py
│
├── quality/
│   ├── contracts.py
│   ├── evaluator.py
│   ├── continuity.py
│   ├── repetition.py
│   ├── character_consistency.py
│   ├── causality.py
│   ├── pacing.py
│   ├── style.py
│   ├── delivery.py
│   ├── scoring.py
│   └── evidence.py
│
├── repair/
│   ├── planner.py
│   ├── executor.py
│   ├── contracts.py
│   └── verifier.py
│
├── services/
│   ├── project_service.py
│   ├── creation_service.py
│   ├── simulation_service.py
│   ├── outline_service.py
│   ├── writer_service.py
│   ├── review_service.py
│   ├── export_service.py
│   └── journey_service.py
│
├── plugins/
│   ├── base.py
│   ├── registry.py
│   ├── loader.py
│   └── builtin/
│
├── mcp/
│   ├── server.py
│   ├── tools/
│   ├── resources/
│   ├── prompts/
│   ├── schemas/
│   └── permissions.py
│
├── api/
│   ├── routes/
│   ├── schemas/
│   └── dependencies.py
│
├── persistence/
│   ├── repositories/
│   ├── migrations/
│   └── storage.py
│
└── observability/
    ├── logging.py
    ├── metrics.py
    ├── token_usage.py
    └── audit.py
```

## 4.1 模块化隔离原则

V4 的目录结构不仅用于整理文件，还必须成为正式的**模块边界**。

目标：

```text
一个主要能力 = 一个明确模块 = 一个独立目录 = 一组公开契约 = 一组独立测试
```

例如：

```text
ai/
memory/
generation/
quality/
repair/
writer/
export/
mcp/
plugins/
```

应尽量可以独立开发、独立测试、独立评审和独立合并。

禁止重新形成：

```text
一个巨型 service.py
一个巨型 utils.py
一个目录承担多个无关业务能力
跨目录直接读写其他模块内部状态
模块之间通过内部文件路径互相调用
```

每个模块建议至少具备：

```text
<module>/
├── contracts.py      # 对外契约 / DTO / Protocol
├── service.py        # 模块入口或 application service
├── domain.py         # 模块内部领域逻辑（需要时）
├── repository.py     # persistence port（需要时）
├── errors.py         # 模块错误
├── internal/         # 不允许其他模块直接依赖
└── tests/            # 模块级测试
```

实际目录可按模块复杂度调整，不要求机械复制模板。

核心要求是：

```text
模块内部实现可以变化
模块对外 Contract 必须稳定、明确、可测试
```

---

## 4.2 Public Contract 与 Internal Implementation

模块之间只允许通过公开接口协作。

例如：

```text
memory.contracts
quality.contracts
ai.contracts
writer.contracts
export.contracts
```

其他模块不得直接依赖：

```text
memory/internal/*
quality/internal/*
ai/provider 私有实现
writer 私有 persistence 实现
```

原则：

```text
Public Contract = 可跨模块依赖
Internal Implementation = 仅模块自身可见
```

如果某个跨模块需求只能通过读取另一个模块内部实现才能完成，说明模块边界设计存在问题，应先补 Contract，而不是建立隐式耦合。

---

## 4.3 模块依赖方向

V4-00 必须产出正式的依赖矩阵。

基本原则：

```text
Interface / Adapter
        ↓
Application / Service
        ↓
Domain / Contracts
        ↓
Ports
        ↓
Infrastructure Adapter
```

特别禁止：

```text
Domain → MCP
Domain → FastAPI
Domain → React
Domain → OpenAI / DeepSeek / Ark SDK
Memory → UI
Quality → MCP Tool implementation
Plugin → 核心数据库任意写入
```

模块之间如果存在双向依赖，应优先：

```text
提取 Contract
提取 Event
提取 Port
或重新划分模块责任
```

而不是保留循环依赖。

---

## 4.4 模块代码所有权

V4 应建立“目录级代码所有权”概念。

例如：

```text
src/novelforge/ai/**          → AI / LLM 模块
src/novelforge/memory/**      → Memory 模块
src/novelforge/quality/**     → Quality 模块
src/novelforge/repair/**      → Repair 模块
src/novelforge/mcp/**         → MCP Adapter 模块
src/novelforge/plugins/**     → Plugin Platform 模块
```

以后一个开发任务必须明确：

```text
Primary Module
Allowed Paths
Read-only Dependencies
Contract Changes
Cross-module Changes
```

这样 Codex、其他 Agent 或多人并行开发时，可以知道哪些目录属于自己的修改范围。

---

## 4.5 模块化任务分支策略

V4 后续开发默认采用：

```text
一个任务分支主要维护一个模块
```

例如：

```text
v4/02-llm-gateway
v4/03-memory
v4/04-generation
v4/05-quality
v4/05-repair
v4/06-writer
v4/07-export
v4/08-mcp
v4/09-plugins
v4/10-ui
v4/11-agent-mode
```

大型阶段可以继续拆成更小的模块任务：

```text
v4/03-memory-canon
v4/03-memory-story-state
v4/03-memory-context-builder

v4/05-quality-continuity
v4/05-quality-repetition
v4/05-quality-causality

v4/08-mcp-resources
v4/08-mcp-tools
v4/08-mcp-permissions
```

分支名反映：

```text
阶段 / 模块 / 任务
```

不要使用无法判断作用域的名称，例如：

```text
fix-v4
update-code
new-feature
refactor-all
```

---

## 4.6 单分支修改范围

每个任务分支开始前必须声明：

```text
Primary Module:
Primary Paths:
Allowed Shared Paths:
Forbidden Paths:
Required Contracts:
Expected Tests:
```

默认规则：

```text
Primary Module 内部文件      → 可修改
该模块 tests                 → 可修改
该模块 docs / contract       → 可修改
其他业务模块内部文件         → 默认不可修改
共享 core / domain contract  → 需要明确理由
数据库 schema               → 需要 migration plan
```

目的不是绝对禁止跨模块修改，而是避免“顺手重构”造成分支范围失控。

---

## 4.7 跨模块变更规则

如果任务必须同时修改多个模块，不允许直接在一个大分支里任意修改。

优先流程：

```text
1. 先定义 / 修改共享 Contract
2. 单独提交 Contract Change
3. 各模块分别适配 Contract
4. 独立运行模块测试
5. 最后运行 Integration / E2E
```

例如 Memory 与 Generation 同时需要新 Context：

```text
memory
    ↓ 暴露 ContextProvider Contract

generation
    ↓ 只消费 Contract
```

而不是：

```text
generation 直接 import memory 内部 store / SQL / embedding 实现
```

---

## 4.8 Shared Core 必须保持小

`core/` 不是公共垃圾桶。

只允许放真正跨模块且稳定的基础能力，例如：

```text
ID
Result
基础 Error
Event envelope
Transaction abstraction
Revision primitives
```

禁止因为两个模块都需要某个函数，就立即移动到：

```text
core/utils.py
```

共享代码至少满足：

```text
语义稳定
不存在模块所有权争议
不包含创作业务规则
不依赖具体 Adapter
```

---

## 4.9 并行开发与合并顺序

并行分支之间尽量通过 Contract 解耦。

推荐顺序：

```text
Contract / ADR
    ↓
Core Domain / Port
    ↓
Module Implementation
    ↓
Adapter
    ↓
Integration
    ↓
UI / MCP / Agent
```

对于存在依赖的两个模块，不应同时修改彼此内部实现来“对接”。

应该先冻结双方共享 Contract，再并行开发。

---

## 4.10 模块级测试要求

每个主要模块必须拥有自己的测试边界。

至少区分：

```text
Unit Test
Contract Test
Integration Test
E2E Test
```

模块分支原则上必须能够在不启动完整 NovelForge 的情况下运行自己的主要测试。

例如：

```text
Memory 模块测试不应要求启动 React
Quality 模块测试不应要求启动 MCP Server
LLM Router 测试不应要求真实写入小说数据库
MCP schema 测试不应承担生成质量测试
```

---

## 4.11 V4-00 必须确定模块边界

V4-00 Architecture 阶段必须额外回答：

```text
每个 V4 模块负责什么？
每个模块不负责什么？
模块公开哪些 Contract？
模块允许依赖谁？
谁允许依赖它？
模块的数据由谁拥有？
模块能否独立测试？
模块是否适合独立任务分支维护？
```

并新增正式产物：

```text
V4_MODULE_BOUNDARIES.md
V4_BRANCH_STRATEGY.md
```

其中 `V4_MODULE_BOUNDARIES.md` 至少包含：

```text
Module
Owned Paths
Responsibility
Public Contracts
Internal Components
Data Ownership
Allowed Dependencies
Forbidden Dependencies
Primary Tests
Likely Task Branches
```

`V4_BRANCH_STRATEGY.md` 至少包含：

```text
Branch Naming
Module Ownership
Allowed Path Rules
Cross-module Change Process
Contract-first Merge Process
Conflict Resolution
Integration Branch Policy
Definition of Done
```

---

# 5. 大模型 API 架构

## 5.1 单一 LLM Gateway

任何业务模块禁止直接调用模型 API。

统一：

```python
llm.generate(
    contract=...,
    context=...,
    model_policy=...
)
```

数据流：

```text
业务 Service
    ↓
LLM Gateway
    ↓
Model Router
    ↓
Provider Adapter
    ↓
LLM API
    ↓
Structured Output Validator
    ↓
Quality Pipeline
```

---

## 5.2 Provider 抽象

```text
LLMProvider
├── OpenAI-compatible
├── DeepSeek-compatible
├── Ark-compatible
├── Local model
└── Future Provider
```

NovelForge 业务层不能依赖具体模型厂商。

---

## 5.3 Model Router

根据任务选择模型：

```text
Creative Model
    人物 / 世界 / 情节 / 正文

Critic Model
    一致性 / 重复 / 逻辑 / 质量评估

Repair Model
    定向修订

Utility Model
    摘要 / 分类 / 标签 / 结构转换
```

支持：

- 质量优先
- 成本优先
- 速度优先
- 本地优先
- 指定模型

---

# 6. 结构化生成契约

模型输出尽量不使用自由格式文本作为机器输入。

例如章节规划：

```json
{
  "chapter_id": "ch_001",
  "title": "维修记录里的异常编号",
  "goal": "确认被删除的维修日志是否真实存在",
  "conflict": "主管拒绝开放旧记录",
  "turn": "主角发现日志编号仍存在于设备缓存",
  "outcome": "获得一条指向殖民区的线索",
  "hook": "缓存记录显示日志最后由一个已经死亡的人访问",
  "source_ids": ["..."]
}
```

模型输出：

```text
JSON
↓
Schema Validation
↓
Domain Validation
↓
Quality Validation
↓
保存
```

禁止：

```text
模型文本
↓
大量 Regex
↓
猜测结构
```

---

# 7. 记忆系统

V4 需要正式的小说记忆层。

不能每次把整本小说塞给模型。

## 7.1 四类记忆

### 1. Canon Memory

不可随意修改的事实：

- 人物身份
- 世界规则
- 已确认历史
- 已发生事件
- 已死亡角色
- 重要物品
- 固定关系

---

### 2. Story State Memory

当前故事状态：

- 当前时间
- 当前地点
- 人物状态
- 资源
- 关系
- 已知信息
- 未解决冲突
- 正在进行的目标

---

### 3. Episodic Memory

按章节 / 场景记录：

```text
发生了什么
谁知道什么
谁做了什么
造成了什么后果
```

---

### 4. Semantic Memory

模型需要检索的长期信息：

- 人物特征
- 地点
- 世界设定
- 关系
- 伏笔
- 主题
- 作者偏好
- 文风要求

---

# 8. Context Builder

任何模型调用不得由业务模块手工拼 Prompt。

统一：

```text
ContextBuilder
```

按任务构建上下文。

例如生成第 87 章：

```text
当前 Chapter Plan
+
最近 3 章 episodic memory
+
相关角色 memory
+
相关地点 memory
+
当前 StoryState
+
相关 Canon
+
未完成伏笔
+
作者风格偏好
```

而不是加载整本小说。

---

# 9. 作者偏好记忆

V4 应记录作者自己的长期创作偏好：

```text
喜欢 / 不喜欢的文风
对话比例
章节长度
节奏
视角
禁用表达
喜欢的冲突类型
不希望出现的套路
人物塑造偏好
题材习惯
```

作用域必须区分：

```text
Global Author Preference
Project Preference
Novel Preference
Chapter Override
```

优先级：

```text
Chapter
> Novel
> Project
> Global
```

---

# 10. Quality Contract

V4 的质量问题必须成为标准化对象。

```json
{
  "code": "CHAPTER_SEMANTIC_REPETITION",
  "severity": "major",
  "scope": {
    "novel_id": "novel_001",
    "chapter_ids": ["ch_018", "ch_019"]
  },
  "reason": "连续章节承担相同叙事动作",
  "evidence": [],
  "repair_contract": {
    "preserve": [
      "canon",
      "characters",
      "source_ids"
    ],
    "allow_change": [
      "chapter_goal",
      "conflict",
      "turn",
      "title"
    ]
  }
}
```

以后 UI、API、MCP 都使用同一 Quality Issue。

---

# 11. 质量闭环

V4 默认生成流程：

```text
Generate
   ↓
Schema Validate
   ↓
Fact / Canon Check
   ↓
Continuity Check
   ↓
Semantic Repetition Check
   ↓
Character Consistency
   ↓
Causality
   ↓
Pacing
   ↓
Style
   ↓
Delivery Check
   ↓
PASS
   └────→ Save
   ↓ FAIL
Repair Planner
   ↓
Targeted Repair
   ↓
Re-evaluate
```

---

# 12. 修订原则

禁止：

```text
发现一个标题问题
→ 整本小说重新生成
```

应该：

```text
Issue
↓
确定受影响 scope
↓
锁定 preserve fields
↓
只允许修改必要字段
↓
重新评估
```

例如：

```text
CHAPTER_SEMANTIC_REPETITION
```

只允许改：

- chapter goal
- conflict
- turn
- title

不能修改：

- 已发生 Canon
- 人物 ID
- 已确认世界规则
- source_ids

---

# 13. Quality Gate 层级

## Q0 Schema

结构是否有效。

## Q1 Safety / Integrity

数据是否损坏。

## Q2 Canon

是否违反事实。

## Q3 Continuity

前后是否矛盾。

## Q4 Character

人物行为是否合理。

## Q5 Causality

事件是否存在因果。

## Q6 Semantic

是否重复、模板化、空洞。

## Q7 Narrative

节奏、冲突、转折、悬念。

## Q8 Style

文风、语言、可读性。

## Q9 Delivery

最终导出物是否可以交付。

只有满足配置好的门禁，内容才能进入正式版本。

---

# 14. Writer V4

V4 Writer 必须成为真正的写作编辑器。

支持：

- 编辑正文
- 保存
- 自动保存
- 历史版本
- Diff
- Undo / Restore
- AI 继续写
- AI 重写
- 扩写
- 缩写
- 增强对白
- 增强冲突
- 改节奏
- 保持事实重新表达
- 选择部分文字修订
- 接受 / 拒绝 AI 修改

AI 不允许静默覆盖作者文本。

任何 AI 修改必须形成：

```text
Revision
```

---

# 15. NovelForge MCP Server

V4 要把 NovelForge 本身做成 MCP。

Agent 不需要操作浏览器也能驱动小说创作。

---

## 15.1 MCP Resources

只读资源示例：

```text
novelforge://projects
novelforge://novels/{novel_id}
novelforge://novels/{novel_id}/state
novelforge://novels/{novel_id}/canon
novelforge://novels/{novel_id}/characters
novelforge://novels/{novel_id}/outline
novelforge://novels/{novel_id}/chapters
novelforge://novels/{novel_id}/quality
novelforge://novels/{novel_id}/memory
```

---

## 15.2 MCP Tools

### Project

```text
novelforge.create_novel
novelforge.rename_novel
novelforge.archive_novel
novelforge.get_journey
```

### Creation

```text
novelforge.generate_premise
novelforge.generate_settings
novelforge.generate_characters
novelforge.generate_world
```

### Story

```text
novelforge.generate_story_arc
novelforge.generate_outline
novelforge.generate_chapter_plan
novelforge.generate_scene_plan
```

### Writer

```text
novelforge.generate_draft
novelforge.rewrite_text
novelforge.continue_draft
novelforge.save_revision
novelforge.restore_revision
```

### Quality

```text
novelforge.evaluate
novelforge.list_quality_issues
novelforge.repair_issue
novelforge.verify_repair
```

### Memory

```text
novelforge.search_memory
novelforge.add_memory
novelforge.update_memory
novelforge.summarize_memory
```

### Export

```text
novelforge.validate_delivery
novelforge.export
```

---

# 16. MCP 操作安全

Agent 写操作不能无限制执行。

每个 Tool 必须声明：

```text
read_only
safe_write
destructive
expensive
```

重要操作支持：

```text
dry_run=true
```

例如：

```text
archive novel
overwrite accepted chapter
mass regenerate
delete revision
```

要求明确确认。

所有 Tool 应支持：

```text
request_id
idempotency_key
revision
```

避免 Agent 重试导致重复写入。

---

# 17. MCP Result 标准

所有 Tool 返回统一 Envelope：

```json
{
  "ok": true,
  "operation": "generate_outline",
  "novel_id": "novel_001",
  "revision": 42,
  "result": {},
  "quality": {
    "status": "passed",
    "issues": []
  },
  "usage": {
    "model": "...",
    "input_tokens": 0,
    "output_tokens": 0
  },
  "artifacts": []
}
```

这样 Agent 不需要理解不同 API 的特殊返回格式。

---

# 18. Plugin Architecture

MCP 是外部接口。

Plugin 是 NovelForge 内部扩展机制。

## Plugin 类型

```text
GeneratorPlugin
EvaluatorPlugin
RepairPlugin
ExporterPlugin
GenrePlugin
ContextProviderPlugin
MemoryPlugin
ModelProviderPlugin
```

插件必须通过 Registry 注册。

禁止插件直接修改核心数据库。

---

# 19. Export V4

所有导出统一经过：

```text
ExportService
```

---

## 19.1 输出格式

基础：

- Markdown
- JSON
- DOCX

建议新增：

- EPUB
- YAML / structured package
- ZIP Project Package

---

## 19.2 Structured Export Package

建议 V4 定义：

```text
NovelForge Package
```

目录：

```text
novel-name.nfpack/
│
├── manifest.json
├── novel.json
├── canon.json
├── story_state.json
│
├── characters/
├── locations/
├── factions/
│
├── outline/
│   ├── book.json
│   ├── volumes.json
│   ├── arcs.json
│   └── chapters.json
│
├── chapters/
│   ├── ch001.md
│   ├── ch002.md
│   └── ...
│
├── memory/
│   └── semantic.json
│
├── quality/
│   ├── report.json
│   └── unresolved_issues.json
│
└── provenance/
    ├── model_usage.json
    └── source_map.json
```

这是 V4 最重要的“结构化结果导出”。

---

# 20. Export Ownership

每一个 artifact 必须带：

```text
novel_id
project_id
revision
created_at
source_ids
```

导出时：

```text
export(novel_id)
```

只能获取属于该 novel 的数据。

彻底解决 V3 中 historical data 混入其他作品的问题。

---

# 21. Delivery Validator

Export 之前检查：

- 是否有未处理 blocker
- 内部 ID 是否泄漏
- 是否存在 placeholder name
- 是否存在机器枚举
- 章节是否缺失
- StoryState 是否一致
- 章节标题是否大面积语义重复
- 是否混入其他 novel 数据
- 文档标题是否统一
- 是否含调试字段
- source trace 是否完整

---

# 22. UI V4 简化

V4 UI 不再不断增加 Tab。

普通用户建议只看到：

```text
创造
世界
故事
写作
检查
```

外加：

```text
导出
设置
```

Advanced Tools 独立隐藏。

---

# 23. Agent Mode

UI 中建议增加：

```text
Agent Session
```

用户可以看到：

```text
Agent 正在做什么
调用了哪个 MCP Tool
修改了哪些数据
调用了哪个模型
花费了多少 Token
发现了哪些问题
进行了哪些修订
```

支持：

```text
Pause
Approve
Reject
Rollback
```

---

# 24. Observability

每一次 AI 操作记录：

```text
request_id
operation
novel_id
model
provider
input_tokens
output_tokens
latency
cost
prompt_contract
context_refs
quality_result
revision_before
revision_after
```

默认不要永久保存完整敏感 Prompt。

支持 debug mode。

---

# 25. 成本控制

V4 必须支持预算。

例如：

```text
Novel Budget
Daily Budget
Operation Budget
```

达到预算：

```text
stop
或
降级模型
```

Context Builder 应优先检索相关信息，而不是无限扩大 prompt。

---

# 26. Cache

只缓存可安全缓存的结果：

- embeddings
- summaries
- immutable entity description
- evaluation result

不建议缓存：

- 当前 StoryState 驱动的正文生成

除非 revision 完全一致。

Cache key 必须包含：

```text
novel_id
revision
contract version
model
context digest
```

---

# 27. 数据版本

所有核心对象必须有：

```text
revision
```

Agent / UI 修改时：

```text
expected_revision
```

如果状态已经被其他操作更新：

返回 conflict。

防止 Agent 并发覆盖。

---

# 28. V4 使用现有开发 MCP

当前已有 MCP：

```text
chrome-devtools
context7
github
node_repl
playwright
shadcn
```

建议用途：

| MCP | V4 开发用途 |
|---|---|
| context7 | 查询 FastAPI / React / Pydantic / LLM SDK / MCP SDK 最新官方文档 |
| github | branch / PR / issue / diff / release |
| playwright | 完整 E2E / Writer / Export / Agent flow |
| chrome-devtools | UI / Network / Performance |
| node_repl | JS / TS / schema 快速实验 |
| shadcn | UI 组件体系 |

这些是**开发工具**，不应成为 NovelForge runtime 的强依赖。

---

# 29. 当前插件用途

现有插件建议：

| Plugin | 用途 |
|---|---|
| Figma | UI / 信息架构 |
| Computer Use | 真实用户验收 |
| Documents | DOCX 导出质量 |
| PDF | PDF 交付验证 |
| Visualize | Quality Dashboard |
| Spreadsheets | QA 数据分析 |
| Presentations | 非核心 |
| Remotion | 非核心 |
| Template Creator | 后续模板生态 |

---

# 30. V4 开发阶段

## V4-00 Architecture

只设计，不改业务。

产出：

```text
V4_ARCHITECTURE.md
V4_MODULE_BOUNDARIES.md
V4_BRANCH_STRATEGY.md
V4_LLM_CONTRACT.md
V4_MCP_SPEC.md
V4_PLUGIN_SPEC.md
V4_QUALITY_CONTRACT.md
V4_MEMORY_ARCHITECTURE.md
V4_EXPORT_SPEC.md
V4_MIGRATION_PLAN.md
V4_DELETION_PLAN.md
```

---

## V4-01 Core Cleanup

目标：

- 根据 V4-00 已完成的分类执行 KEEP / REWRITE / DELETE / MIGRATE
- 去掉重复 Service
- 去掉重复状态逻辑
- 落地新的 module boundary
- 将主要能力迁入独立目录，建立公开 Contract 与 internal 边界
- 为后续模块任务分支准备可独立维护、可独立测试的目录结构

暂时不改小说生成结果。

V4-01 完成后，后续阶段原则上按模块独立分支推进，不再使用一个长期“大 V4 分支”承载所有功能。

---

## V4-02 LLM Gateway

实现：

- Provider
- Router
- Structured output
- retry
- timeout
- usage
- trace
- cache

---

## V4-03 Memory

实现：

- Canon Memory
- Story State Memory
- Episodic Memory
- Semantic Memory
- Author Preferences
- Context Builder

---

## V4-04 Structured Generation

先实现：

- Character
- World
- Story Arc
- Chapter Plan

重点首先解决：

NF-003。

---

## V4-05 Quality Loop

实现：

- Quality Contract
- Evaluators
- Repair Planner
- Targeted Repair
- Re-evaluate

---

## V4-06 Writer

实现真正：

- edit
- save
- revisions
- AI rewrite
- accept / reject
- diff

---

## V4-07 Delivery

实现：

- ownership
- validator
- structured export
- nfpack
- clean markdown/docx/json

---

## V4-08 MCP Server

当内部 Contracts 稳定后再暴露。

实现：

- resources
- tools
- prompts
- permission
- dry-run
- revision control

---

## V4-09 Plugins

实现 Registry 与第一批 builtin plugins。

---

## V4-10 UI

根据稳定后端能力重构 UI。

---

## V4-11 Agent Mode

让 Agent 可以：

```text
读取项目
分析质量
提出计划
执行工具
等待确认
修订
导出
```

---

## V4 阶段与推荐主模块分支

V4-01 之后，阶段编号仍表示产品开发顺序，但代码实现尽量按模块拆分分支。

建议：

| 阶段 | 主模块 | 推荐分支 | 默认主要目录 |
|---|---|---|---|
| V4-02 | LLM Gateway | `v4/02-llm-gateway` | `ai/` |
| V4-03 | Memory | `v4/03-memory-*` | `memory/` |
| V4-04 | Structured Generation | `v4/04-generation-*` | `generation/` |
| V4-05 | Quality | `v4/05-quality-*` | `quality/` |
| V4-05 | Repair | `v4/05-repair-*` | `repair/` |
| V4-06 | Writer | `v4/06-writer-*` | Writer 对应独立模块目录 |
| V4-07 | Delivery / Export | `v4/07-export-*` | Export 对应独立模块目录 |
| V4-08 | MCP | `v4/08-mcp-*` | `mcp/` |
| V4-09 | Plugins | `v4/09-plugins-*` | `plugins/` |
| V4-10 | UI | `v4/10-ui-*` | frontend / UI 目录 |
| V4-11 | Agent Mode | `v4/11-agent-*` | Agent orchestration / adapter 目录 |

一个阶段允许多个并行分支，但每个分支必须有清晰模块所有权。

跨模块集成建议使用短生命周期 integration branch，例如：

```text
v4/integration-memory-generation
v4/integration-quality-repair
v4/integration-mcp-services
```

Integration branch 只负责验证 Contract 对接和解决必要冲突，不应继续开发新的模块内部功能。

---

## V4-12 Acceptance

必须覆盖：

```text
Fresh Clone
Fresh Novel
UI E2E
MCP E2E
Agent E2E
Writer
Memory
Quality Loop
Export
Performance
Model Failure
Network Failure
Concurrent Revision
Module Contract Tests
Cross-module Dependency Check
Parallel Branch Integration
```

---

# 31. V4 的完成定义

V4 不是：

```text
API 接上了
```

就算完成。

必须满足：

## Agent Ready

外部 Agent 能通过 MCP 完成：

```text
创建作品
→ 设定
→ 人物
→ 世界
→ 大纲
→ 质量检查
→ 修订
→ 写作
→ 导出
```

不用操作浏览器。

---

## Quality Closed Loop

内容不是：

```text
Generate → Save
```

而是：

```text
Generate → Evaluate → Repair → Verify → Save
```

---

## Memory

生成第 N 章时可以正确检索：

- 相关人物
- 最近剧情
- 已发生事实
- 未完成伏笔
- 作者偏好

不需要整本小说全部塞给模型。

---

## Export

最终结果：

- 只属于当前小说
- 不带内部机器字段
- 不带其他小说历史数据
- 结构完整
- 可追溯
- 可以交给其他 Agent / 工具继续处理

---

# 32. V4 最重要的三个架构边界

## 1. LLM 不是数据库

模型生成内容。

NovelForge 保存事实。

---

## 2. MCP 不是业务层

MCP 只是协议入口。

UI / REST / MCP 必须调用同一 Service。

---

## 3. Quality 不是测试脚本

Quality 是正式业务架构。

每一个生成产物都有：

```text
quality status
quality issues
quality evidence
repair history
```

---

## 4. 模块目录就是维护边界

V4 不允许再次形成“所有功能都能互相直接调用”的大应用结构。

原则：

```text
模块拥有自己的目录
模块拥有自己的内部实现
模块通过公开 Contract 与其他模块协作
模块的数据所有权必须明确
模块应尽量可以独立测试
模块应尽量可以由独立任务分支维护
```

Git 分支不是架构边界本身，但代码结构必须支持：

```text
多个 Agent / 多个开发者
在不同模块分支并行工作
并通过稳定 Contract 最后集成
```

如果一个模块任务经常必须修改大量其他模块内部文件，说明模块边界需要重新设计。

---

# 33. V4 最终目标

最终 NovelForge 应从：

```text
小说生成软件
```

升级成：

```text
Novel Creation Runtime
+
Story State Engine
+
Long-term Memory
+
LLM Orchestrator
+
Quality Engine
+
MCP Server
+
Plugin Platform
```

这样 Codex、ChatGPT、Claude 或其他 Agent 都可以把 NovelForge 当作小说创作系统直接调用，而不是只能通过浏览器模拟用户点击。
