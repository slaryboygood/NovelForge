# NovelForge V4 架构与实施总计划

> 状态：V4-00 Architecture 已完成并通过；进入 V4-01 Boundary Foundation & Legacy Cleanup  
> 基线：NovelForge V3 Final — Functional Closure  
> V4-00：PASS，业务代码 0 改动，frozen boundary 未触碰  
> 核心目标：将 NovelForge 从“小说正文生成工具”重构为“面向小说/影视式故事大纲的 Story Blueprint Runtime + LLM 编排层 + 质量闭环 + MCP Server + Plugin Platform”。

---

# 1. V4 的核心定位

NovelForge V4 的最终目标**不是自动写完一部长篇小说正文**。

V4 的核心产品是：

```text
高质量、可编辑、可验证、可持续修订的故事大纲 / Story Blueprint
```

它应像电影剧本开发阶段的“故事蓝图”一样，把创意逐层细化到：

```text
Premise
Theme
World
Characters
Character Arcs
Act / Volume / Arc Structure
Chapter Cards
Scene Cards
Causal Chain
Setup / Payoff
Knowledge State
Relationship Changes
Timeline
Quality Evidence
Revision History
```

NovelForge 负责：

```text
约束
状态
长期记忆
故事结构编排
模型调用编排
结构化输出
质量验证
定向修订
版本管理
交付
```

LLM 负责：

```text
创意生成
角色推演
情节方案
场景设计
结构重写
问题修复候选
```

核心原则：

```text
NovelForge 不替大模型“硬写小说正文”
NovelForge 负责把故事规划成可验证、可修订、可交付的 Story Blueprint
```

---

# 2. V4 的主要交付物：Story Blueprint

V4 的 canonical creative artifact 不再是完整正文 Draft，而是：

```text
StoryBlueprint
```

推荐分层：

```text
StoryBlueprint
├── Story Premise
├── Theme & Dramatic Question
├── World Rules
├── Character Bible
├── Character Arcs
├── Global Story Arc
├── Act / Volume / Arc Plans
├── Chapter Plans
├── Scene Plans
├── Setup / Payoff Graph
├── Causal Graph
├── Timeline
├── Story State Transitions
├── Knowledge State Changes
├── Relationship Changes
├── Quality Result
└── Revision History
```

场景级结果应足够细，使作者或其他 Agent 可以据此继续写作，但 V4 本身不以生成完整文学正文为完成条件。

建议 Scene Card 至少包含：

```json
{
  "scene_id": "sc_001",
  "chapter_id": "ch_001",
  "location": "...",
  "time": "...",
  "pov": "...",
  "participants": ["..."],
  "purpose": "这一场为什么存在",
  "setup": "进入场景前的状态",
  "goal": "角色在本场想得到什么",
  "conflict": "什么阻止目标",
  "escalation": "冲突如何升级",
  "turn": "场景发生的关键转折",
  "outcome": "场景结束后的新状态",
  "information_reveal": ["..."],
  "character_change": "...",
  "relationship_change": "...",
  "setup_ids": ["..."],
  "payoff_ids": ["..."],
  "next_hook": "...",
  "source_ids": ["..."]
}
```

---

# 3. V4 明确的非目标

V4 当前不把以下内容作为核心完成标准：

```text
完整长篇正文自动生成
文学文风打磨到出版级
逐章连续写满数十万字
旧 V3 正文资产迁移
旧 historical 章节资产保留
```

未来可以通过 Plugin / 外部 Agent / 下游写作工具使用 Story Blueprint 继续生成正文，但那不是 V4 核心架构的中心。

---

# 4. V4-00 后的作者决策冻结

以下决策覆盖 V4-00 中对应的待定项。

## 4.1 `novel/final/*.md`

作者确认：

```text
旧正文已无产品价值
不迁移
不保留为 canonical source
可删除
```

V4-01 应：

```text
删除 novel/final/*.md
删除只为这些旧正文服务的引用/路径/兼容逻辑
不得建立 ChapterRevision 正文迁移链
```

如存在仍被测试或运行时代码引用的路径，应先移除依赖，再删除资产。

---

## 4.2 570 章 historical

作者确认：

```text
570 章 historical 是废弃产物
不作为一等作品
不导入 V4
不做 migration
可删除
```

V4-01 应：

```text
删除 historical 内容
删除自动扫描 historical 的代码路径
删除针对该废弃作品的硬编码数据库/导出/路径依赖
```

它不再进入 Memory、Export、Quality、Regression Product Data。

必要测试数据应重新制作成最小、明确归属、可重复生成的 fixtures。

---

## 4.3 V4 最终产品目标

作者确认：

```text
最终目标 = 小说大纲 / 故事蓝图
形态接近电影剧本开发中的结构化故事规划
而不是完整小说正文
```

因此 V4 的 Writer、Quality、Export、MCP、Agent、Memory 都必须围绕 Story Blueprint 重定义。

---

# 5. V4 总体目标

V4 必须实现：

- 大模型 API 正式接入
- 统一 LLM Gateway
- Provider / Model Router
- 结构化生成契约
- Story Blueprint canonical model
- 世界 / 人物 / 人物弧 / 故事弧 / 章节 / 场景结构化生成
- Canon / StoryState / Episodic / Semantic Memory
- Context Builder
- 故事质量闭环
- 自动定向修订
- Blueprint Editor 真正可编辑
- 版本 / Revision / Diff / Restore
- MCP Server
- Agent 可直接操作 NovelForge
- Plugin / 扩展机制
- 统一 Export
- Story Blueprint Package
- 交付质量验证
- 成本 / Token / 调用跟踪
- 统一日志和质量证据
- UI 简化
- UI / REST / MCP 共用同一业务 Service
- 模块级目录隔离与依赖边界
- 支持按模块拆分并行任务分支

---

# 6. V4 最重要的架构原则

## 6.1 LLM 不是数据库

模型负责提出内容。

NovelForge 保存事实、状态、结构和版本。

---

## 6.2 MCP 不是业务层

MCP 只是协议 Adapter。

```text
UI
REST
MCP
Agent Adapter
      ↓
Application / Service Layer
      ↓
Domain / Story Engine
```

所有入口共享同一业务能力。

---

## 6.3 Quality 不是测试脚本

Quality 是正式业务架构。

每个 Story Blueprint artifact 都必须可以拥有：

```text
quality_status
quality_issues
quality_evidence
repair_history
```

---

## 6.4 模块目录就是维护边界

```text
一个主要能力
= 一个明确模块
= 一个独立目录
= 一组公开 Contract
= 一组独立测试
= 可由独立任务分支维护
```

---

## 6.5 大纲是核心产物，正文不是

任何新架构设计优先回答：

```text
它如何提升 Story Blueprint 的质量、可控性、可修订性或可交付性？
```

如果一个能力只服务旧正文生成流程，应优先评估删除或降级，而不是自动迁移。

---

# 7. V4-00 已确认的 V3 现状

V4-00 扫描结论：

```text
src/              188 py / 68,038 行
ui/src/            45 ts/tsx / 10,482 行
tests/             171 py + 20 cjs
```

基线：

```text
pytest -q → 892 passed / 687 deselected / 0 failed
validate_project.py → PASS
```

已确认结构问题：

1. 单作品/历史作品路径硬编码
2. 旧正文无 owner
3. 硬编码创作内容集中在多个模块
4. Route 承担业务编排
5. Export 多套拼装
6. 状态推导重复
7. project_id / novel_id 语义混乱
8. Quality finding 不统一
9. LLM 边界不存在
10. frozen 历史模块缺少清晰隔离

V4 的迁移策略是：

```text
继承稳定内核
建立边界
删除废弃资产
重写必要编排
逐步提升既有能力
避免 Big Bang Rewrite
```

---

# 8. 模块化架构

V4-00 已证明现有 `story_engine` 中有大量 KEEP 能力，因此 V4 不应为了目录“好看”机械新建一套平行 domain。

物理目录名称以：

```text
docs/v4/V4_MODULE_BOUNDARIES.md
```

为最终依据。

逻辑上至少需要以下独立模块边界：

```text
Core Primitives
Application Services
Story Engine / Domain
LLM Gateway
Story Memory
Story Blueprint / Structured Generation
Story Quality
Story Repair
Blueprint Editor
Delivery / Export
MCP Adapter
Plugin Platform
Persistence
Observability
Legacy Compatibility
UI
```

由于现有代码存在 `memory.py`、`repair.py` 等命名冲突，新目录命名应避免与 frozen V3 模块产生歧义；具体命名由 V4_MODULE_BOUNDARIES.md 决定，不在 Master Plan 中机械强制。

---

# 9. Public Contract 与 Internal Implementation

模块之间只允许通过公开 Contract 协作。

原则：

```text
Public Contract = 可跨模块依赖
Internal Implementation = 仅模块自身可见
```

禁止：

```text
跨模块直接 import internal implementation
跨模块读取其他模块私有文件路径
跨模块直接执行 SQL 修改对方状态
UI 直接推导业务事实
MCP Tool 自己实现业务逻辑
```

如果跨模块需求无法通过 Contract 完成：

```text
先修改 Contract
再分别适配模块
```

---

# 10. 模块依赖方向

推荐：

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

禁止：

```text
Domain → MCP
Domain → FastAPI
Domain → React
Domain → OpenAI / DeepSeek / Ark SDK
Memory → UI
Quality → MCP Tool implementation
Plugin → 核心数据库任意写入
```

出现双向依赖时优先：

```text
Contract
Event
Port
重新划分责任
```

而不是保留循环依赖。

---

# 11. Shared Core 必须保持小

`core/` 不是公共垃圾桶。

只放真正稳定、跨模块的 primitive：

```text
ID
Result
Error envelope
Event envelope
Revision primitive
Transaction abstraction
```

禁止建立万能：

```text
core/utils.py
```

共享代码必须满足：

```text
语义稳定
无明确模块所有权争议
不包含故事创作业务规则
不依赖具体 Adapter
```

---

# 12. 模块化任务分支策略

由于远端已存在 `origin/v4`，Git 不能同时安全使用 `v4/...` 层级分支。

V4 后续统一使用扁平命名：

```text
v4-01-boundary-foundation
v4-02-llm-gateway
v4-03-memory-canon
v4-03-memory-context-builder
v4-04-blueprint-generation
v4-05-quality-continuity
v4-05-quality-causality
v4-05-repair
v4-06-blueprint-editor
v4-07-delivery
v4-08-mcp-resources
v4-08-mcp-tools
v4-09-plugins
v4-10-ui
v4-11-agent
```

需要跨模块集成时使用短生命周期：

```text
v4-int-memory-blueprint
v4-int-quality-repair
v4-int-mcp-services
```

每个分支开始前必须声明：

```text
Primary Module
Primary Paths
Allowed Shared Paths
Forbidden Paths
Required Contracts
Expected Tests
```

默认一个任务分支主要维护一个模块。

---

# 13. 跨模块变更规则

如果任务必须跨模块：

```text
1. 先定义/修改 Contract
2. Contract 单独提交
3. 各模块分别适配
4. 各自运行模块测试
5. Integration / E2E 验证
```

禁止：

```text
一个大分支顺手修改五六个模块内部实现
```

---

# 14. 大模型 API 架构

所有业务模块禁止直接调用模型 API。

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
Business Service
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

Provider 抽象：

```text
LLMProvider
├── OpenAI-compatible
├── DeepSeek-compatible
├── Ark-compatible
├── Local model
└── Future Provider
```

Router 角色：

```text
Creative / Planning Model
    premise / character / world / arc / chapter / scene planning

Critic Model
    continuity / causality / character / repetition / pacing / setup-payoff

Repair Model
    targeted outline repair

Utility Model
    summary / classification / extraction / structure conversion
```

支持：

```text
质量优先
成本优先
速度优先
本地优先
指定模型
```

---

# 15. 结构化生成契约

机器消费的模型结果应优先结构化。

禁止：

```text
自由文本
↓
大量 Regex
↓
猜测故事结构
```

推荐：

```text
JSON
↓
Schema Validation
↓
Domain Validation
↓
Quality Validation
↓
Revision Save
```

核心 contract 至少包括：

```text
PremiseIR
CharacterIR
WorldIR
StoryArcIR
ActPlanIR
ChapterPlanIR
ScenePlanIR
StoryBlueprint
```

---

# 16. Story Blueprint 数据模型

V4 的故事结构至少区分：

```text
事实层：Canon
状态层：StoryState
规划层：StoryBlueprint
质量层：QualityResult
版本层：Revision
```

禁止把“计划发生的剧情”提前写进 Canon。

建议规则：

```text
Canon = 已确认事实 / 不应被普通修订随意改变
StoryState = 当前状态
StoryBlueprint = 未来故事计划与结构
```

只有故事计划被作者接受并推进到对应状态后，才根据业务规则更新事实/状态。

---

# 17. 记忆系统

V4 正式使用四类故事记忆。

## 17.1 Canon Memory

不可随意修改的事实：

- 人物身份
- 世界规则
- 已确认历史
- 已发生事件
- 已死亡角色
- 重要物品
- 固定关系

## 17.2 Story State Memory

当前状态：

- 当前时间
- 当前地点
- 人物状态
- 资源
- 关系
- 已知信息
- 未解决冲突
- 正在进行的目标

## 17.3 Episodic Memory

按章节/场景记录：

```text
发生了什么
谁知道什么
谁做了什么
产生了什么后果
```

## 17.4 Semantic Memory

用于长期检索：

- 人物特征
- 地点
- 世界设定
- 关系
- 伏笔
- 主题
- 作者偏好
- 结构偏好

Memory 是派生/检索能力，不得取代 Canon / StoryState / StoryBlueprint 的 source of truth。

---

# 18. Context Builder

业务模块不得手工散落拼 Prompt。

统一：

```text
ContextBuilder
```

例如生成第 87 章场景规划：

```text
当前 Story Arc
+
当前 Chapter Plan
+
最近相关 episodic memory
+
相关角色 memory
+
相关地点 memory
+
当前 StoryState
+
相关 Canon
+
未完成 setup/payoff
+
人物弧当前位置
+
作者结构偏好
```

而不是加载整本历史资产。

---

# 19. 作者偏好记忆

V4 记录的偏好重点转为“故事设计偏好”，包括：

```text
题材
节奏
章节长度目标
场景密度
对白占比偏好
冲突类型
人物塑造偏好
视角偏好
反感套路
禁用桥段
悬念强度
反转频率
结构模型偏好
```

作用域：

```text
Global
Project
Novel
Arc / Chapter Override
```

优先级：

```text
局部 Override > Novel > Project > Global
```

---

# 20. Quality Contract

Quality Issue 必须成为标准化业务对象。

```json
{
  "code": "SCENE_CAUSAL_GAP",
  "severity": "major",
  "scope": {
    "novel_id": "novel_001",
    "scene_ids": ["sc_018", "sc_019"]
  },
  "reason": "关键行为缺少足够动机或前置原因",
  "evidence": [],
  "repair_contract": {
    "preserve": ["canon", "character_identity", "source_ids"],
    "allow_change": ["scene_goal", "conflict", "turn", "outcome"]
  }
}
```

UI / API / MCP 使用同一 Quality Issue。

---

# 21. V4 的质量重点

V4 不把“文学文笔优美”作为最核心 Quality Gate。

质量闭环重点检查：

```text
结构完整性
Canon 一致性
时间/地点连续性
人物动机
人物弧连续性
因果链
冲突升级
剧情重复
场景功能
节奏
信息释放
setup / payoff
伏笔回收
章节/场景转折
悬念与 hook
故事状态变化
交付完整性
```

语言风格检查只服务于：

```text
大纲表达是否清晰
字段是否可理解
是否模板化/空洞
```

而不是追求最终小说 prose 风格。

---

# 22. Quality Gate 层级

```text
Q0 Schema
Q1 Integrity
Q2 Canon
Q3 Continuity
Q4 Character / Motivation
Q5 Causality
Q6 Semantic / Repetition
Q7 Structure / Pacing
Q8 Setup-Payoff / Narrative Function
Q9 Delivery
```

其中：

```text
Q0/Q1       → 尽量 deterministic
Q2/Q3       → deterministic + retrieval + LLM-assisted
Q4-Q8       → rule evidence + LLM-assisted critic
Q9          → deterministic 为主
```

---

# 23. 质量闭环

默认流程：

```text
Generate Blueprint Node
    ↓
Schema Validate
    ↓
Canon Check
    ↓
Continuity Check
    ↓
Character / Motivation Check
    ↓
Causality Check
    ↓
Semantic Repetition Check
    ↓
Structure / Pacing Check
    ↓
Setup / Payoff Check
    ↓
Delivery Check
    ↓ PASS
Revision Save
    ↓ FAIL
Repair Planner
    ↓
Targeted Repair
    ↓
Re-evaluate
```

必须限制 repair loop 次数和成本，禁止无限修订。

---

# 24. 修订原则

禁止：

```text
发现一个场景问题
→ 整部大纲全部重新生成
```

应该：

```text
Issue
↓
确定最小影响 scope
↓
锁定 preserve fields
↓
只修改必要节点/字段
↓
重新验证受影响邻域
```

例如重复场景只允许优先修改：

```text
scene purpose
goal
conflict
escalation
turn
outcome
hook
```

不能随意修改：

```text
已确认 Canon
人物 ID
世界规则
source_ids
无关章节
```

---

# 25. Blueprint Editor V4

原“Writer V4”重定义为：

```text
Blueprint Editor / Story Studio
```

它是故事结构编辑器，不是长篇正文编辑器。

必须支持：

- Premise / Theme 编辑
- Character / Character Arc 编辑
- Story Arc 编辑
- Act / Volume / Arc 编辑
- Chapter Card 编辑
- Scene Card 编辑
- 拖动/重排（在保持依赖校验的前提下）
- Save
- Auto Save
- Revision History
- Diff
- Undo / Restore
- AI 扩展一个节点
- AI 重写一个节点
- AI 提供替代方案
- AI 修复 Quality Issue
- Accept / Reject AI Change
- 显示受影响的 Canon / setup-payoff / downstream 节点

AI 不允许静默覆盖作者接受的 Story Blueprint。

每次 AI 修改形成 Revision。

---

# 26. Revision 模型

所有核心 Story Blueprint 对象必须有 revision awareness。

写操作：

```text
expected_revision
```

状态已变化时返回 conflict。

防止：

```text
UI 覆盖 Agent
Agent 重试重复写入
并行 repair 相互覆盖
```

Revision 至少记录：

```text
revision_id
parent_revision
operation
actor
created_at
changed_nodes
quality_before
quality_after
```

---

# 27. NovelForge MCP Server

MCP 是外部 Agent 的协议入口，不承担业务逻辑。

## 27.1 Resources

```text
novelforge://projects
novelforge://novels/{novel_id}
novelforge://novels/{novel_id}/state
novelforge://novels/{novel_id}/canon
novelforge://novels/{novel_id}/characters
novelforge://novels/{novel_id}/blueprint
novelforge://novels/{novel_id}/outline
novelforge://novels/{novel_id}/scenes
novelforge://novels/{novel_id}/quality
novelforge://novels/{novel_id}/memory
```

## 27.2 Tools

Project：

```text
novelforge.create_novel
novelforge.rename_novel
novelforge.archive_novel
novelforge.get_journey
```

Creation：

```text
novelforge.generate_premise
novelforge.generate_settings
novelforge.generate_characters
novelforge.generate_world
```

Blueprint：

```text
novelforge.generate_story_arc
novelforge.generate_outline
novelforge.generate_chapter_plan
novelforge.generate_scene_plan
novelforge.expand_blueprint_node
novelforge.rewrite_blueprint_node
novelforge.save_revision
novelforge.restore_revision
```

Quality：

```text
novelforge.evaluate
novelforge.list_quality_issues
novelforge.repair_issue
novelforge.verify_repair
```

Memory：

```text
novelforge.search_memory
novelforge.add_memory
novelforge.update_memory
novelforge.summarize_memory
```

Export：

```text
novelforge.validate_delivery
novelforge.export_blueprint
```

旧的正文型：

```text
generate_draft
continue_draft
rewrite_text
```

不再作为 V4 核心 MCP Tool。

未来若需要，可由非核心 Plugin 提供。

---

# 28. MCP 操作安全

每个 Tool 声明：

```text
read_only
safe_write
destructive
expensive
```

支持：

```text
dry_run
request_id
idempotency_key
expected_revision
```

高风险操作要求确认，例如：

```text
archive novel
mass regenerate blueprint
restore old accepted revision
bulk repair
```

---

# 29. MCP Result Envelope

所有 Tool 统一：

```json
{
  "ok": true,
  "operation": "generate_scene_plan",
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

---

# 30. Plugin Architecture

MCP 是外部接口。

Plugin 是内部扩展机制。

Plugin 类型：

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

可选未来插件：

```text
ProseDraftPlugin
ScreenplayFormatPlugin
DialogueExpansionPlugin
```

这些不能反过来改变 V4 的核心产品定位。

插件必须通过 Registry 注册。

禁止插件绕过 Service / Repository Contract 直接修改核心数据库。

---

# 31. Export V4

所有导出统一经过：

```text
ExportService
```

核心输出：

- Markdown Story Blueprint
- JSON
- DOCX
- YAML / structured package
- ZIP Project Package

EPUB 不再是 V4 核心优先级，因为 V4 不以完整小说正文为主要交付物。

未来可通过插件增加：

```text
Fountain
Final Draft compatible adapter
其他 screenplay-like formats
```

但不要求 V4 Core 实现。

---

# 32. Story Blueprint Package

推荐：

```text
novel-name.nfpack/
│
├── manifest.json
├── novel.json
├── canon.json
├── story_state.json
│
├── characters/
│   ├── characters.json
│   └── arcs.json
│
├── world/
│   ├── locations.json
│   ├── factions.json
│   └── rules.json
│
├── blueprint/
│   ├── premise.json
│   ├── story_arc.json
│   ├── acts.json
│   ├── chapters.json
│   ├── scenes.json
│   ├── causal_graph.json
│   ├── setup_payoff.json
│   └── timeline.json
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

---

# 33. Artifact Ownership

所有 artifact 必须带足够 ownership metadata：

```text
project_id
novel_id
revision
created_at
source_ids
```

但最终用户可见的大纲文档不得泄漏内部机器字段。

内部 metadata 和可读交付物必须分离。

---

# 34. Delivery Validator

Export 前检查：

- 是否有 unresolved blocker
- 是否有内部 ID 泄漏到用户文档
- 是否有 placeholder
- Story Blueprint 是否结构完整
- Character Arc 是否断裂
- Scene 是否缺少 purpose / conflict / turn / outcome
- 是否存在明显重复剧情功能
- setup 是否无 payoff
- payoff 是否无 setup
- 时间线是否冲突
- StoryState 是否一致
- 是否混入其他 novel 数据
- source trace 是否完整
- debug 字段是否泄漏

---

# 35. UI V4

普通用户建议只看到：

```text
创造
世界
人物
故事
场景
检查
```

外加：

```text
导出
设置
```

可进一步压缩成：

```text
创造
世界
故事
大纲
检查
```

Advanced Tools 单独隐藏。

原“写作”Tab 不再以正文编辑器为中心，应改为：

```text
大纲 / Blueprint / Story Studio
```

---

# 36. Agent Mode

Agent 可以：

```text
读取项目
分析故事结构
读取 Canon / StoryState
提出大纲计划
生成或修改 Blueprint 节点
执行 Quality 检查
提出 Repair Plan
等待确认
定向修订
重新验证
导出 Story Blueprint
```

用户可以看到：

```text
Agent 正在做什么
调用了哪个 MCP Tool
修改了哪些 Blueprint 节点
调用了哪个模型
Token / Cost
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

# 37. Observability

每次 AI 操作记录：

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
contract_version
context_refs
quality_result
revision_before
revision_after
changed_nodes
```

默认不永久保存完整敏感 Prompt。

支持 debug mode。

---

# 38. 成本控制

支持：

```text
Novel Budget
Daily Budget
Operation Budget
Repair Loop Budget
```

达到预算：

```text
stop
或降级模型
或只执行 deterministic checks
```

Context Builder 优先检索相关事实，避免无限扩大上下文。

---

# 39. Cache

适合缓存：

- embeddings
- summaries
- immutable entity description
- deterministic evaluation result
- revision-stable critic result

不建议缓存：

- 当前 StoryState / Blueprint revision 驱动的生成结果

除非 revision 完全一致。

Cache key 至少包含：

```text
novel_id
revision
contract_version
model
context_digest
```

---

# 40. Legacy 策略

V4-00 发现大量 frozen V3 模块。

V4-01 不应该为了目录整齐就移动所有 frozen 文件。

正确策略：

```text
Frozen V3 Module
        ↑
Legacy Adapter / Compatibility Boundary
        ↑
V4 Service
```

只有在对应能力完成替换、测试稳定、frozen contract 不再需要后，才删除或移动。

但作者已明确判定的废弃**数据资产**不需要保留：

```text
novel/final/*.md
570 章 historical
```

这两类进入 V4-01 直接清理范围。

---

# 41. V4 开发阶段

## V4-00 Architecture — COMPLETED / PASS

已完成：

```text
V4_CODEBASE_INVENTORY.md
V4_MODULE_CLASSIFICATION.md
V4_ARCHITECTURE.md
V4_LLM_CONTRACT.md
V4_MCP_SPEC.md
V4_PLUGIN_SPEC.md
V4_QUALITY_CONTRACT.md
V4_MEMORY_ARCHITECTURE.md
V4_EXPORT_SPEC.md
V4_MIGRATION_PLAN.md
V4_DELETION_PLAN.md
V4_ARCHITECTURE_RISKS.md
ADR-001 ... ADR-010
```

V4-00 之后需根据作者新决策更新对应 ADR / 文档：

```text
旧正文删除
historical 删除
Story Blueprint 成为核心交付物
Writer → Blueprint Editor
```

---

## V4-01 Boundary Foundation & Legacy Cleanup

目标：

```text
先建立 V4 稳定边界
删除明确废弃资产
不改变核心故事生成结果
不接入新 LLM
```

范围：

- 同步 V4-00 文档与作者决策
- 删除 `novel/final/*.md`
- 删除 570 章 historical 废弃数据
- 删除/改写只为这些废弃数据服务的硬编码路径
- 建立 Application Service 边界骨架
- 收编 JourneyProjection 为唯一状态投影入口
- 参数化 persistence/path ownership
- 建立 revision primitive
- 建立 legacy adapter namespace / boundary
- 落地模块目录与 Public Contract / internal 边界
- 为后续独立模块分支准备测试结构
- 建立 cross-novel / cross-project contamination 防护测试（即使未来是否完整支持多作品仍未最终决定）

暂时不做：

```text
LLM Gateway
Memory V4
Quality Loop V4
Blueprint Generation V4
MCP Server
UI 大改
```

---

## V4-02 LLM Gateway

实现：

- Provider
- Router
- Structured Output
- retry
- timeout
- usage
- trace
- cache
- contract versioning

---

## V4-03 Story Memory

实现：

- Canon retrieval
- Story State Memory
- Episodic Memory
- Semantic Memory
- Author Preferences
- Context Builder

---

## V4-04 Structured Story Blueprint

优先实现：

```text
Premise
Character
Character Arc
World
Story Arc
Act / Volume / Arc
Chapter Plan
Scene Plan
Causal Graph
Setup / Payoff
Timeline
```

重点不是“多生成内容”，而是形成稳定 Story Blueprint contract。

---

## V4-05 Quality Loop

实现：

- Quality Contract
- Schema / Integrity
- Canon
- Continuity
- Character / Motivation
- Causality
- Semantic Repetition
- Structure / Pacing
- Setup / Payoff
- Repair Planner
- Targeted Repair
- Re-evaluate

---

## V4-06 Blueprint Editor

实现真正可编辑的 Story Studio：

- edit
- save
- revisions
- diff
- restore
- AI expand node
- AI rewrite node
- alternatives
- accept / reject
- quality issue repair entry

---

## V4-07 Delivery

实现：

- ownership
- Delivery Validator
- Markdown / JSON / DOCX
- structured export
- nfpack
- clean Story Blueprint deliverable

---

## V4-08 MCP Server

内部 Contract 稳定后再暴露：

- resources
- tools
- prompts
- permission
- dry-run
- revision control
- idempotency

---

## V4-09 Plugins

实现 Registry 与第一批 builtin plugins。

---

## V4-10 UI

根据稳定后端能力重构 UI。

核心 UI 围绕：

```text
Story Blueprint
Scene Cards
Character Arcs
Quality Issues
Revision
```

---

## V4-11 Agent Mode

让 Agent 可以完整执行：

```text
读取项目
→ 理解设定/角色/状态
→ 生成 Story Blueprint
→ 质量检查
→ Repair
→ Verify
→ 人工确认
→ 导出
```

---

## V4-12 Acceptance

必须覆盖：

```text
Fresh Clone
Fresh Project / Novel
UI E2E
MCP E2E
Agent E2E
Blueprint Editor
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
Legacy data absence
No historical leakage
No obsolete final正文 dependency
```

---

# 42. V4 阶段与推荐模块分支

| 阶段 | 主模块 | 推荐分支 | 主要责任 |
|---|---|---|---|
| V4-01 | Boundary | `v4-01-boundary-foundation` | Service / path / revision / legacy boundary |
| V4-02 | LLM | `v4-02-llm-gateway` | LLM Gateway |
| V4-03 | Memory | `v4-03-memory-*` | Story Memory / Context |
| V4-04 | Blueprint | `v4-04-blueprint-*` | Structured Story Blueprint |
| V4-05 | Quality | `v4-05-quality-*` | Evaluators |
| V4-05 | Repair | `v4-05-repair-*` | Targeted Repair |
| V4-06 | Editor | `v4-06-blueprint-editor-*` | Story Studio |
| V4-07 | Delivery | `v4-07-delivery-*` | Export / Validator |
| V4-08 | MCP | `v4-08-mcp-*` | MCP Adapter |
| V4-09 | Plugins | `v4-09-plugins-*` | Plugin Platform |
| V4-10 | UI | `v4-10-ui-*` | UI |
| V4-11 | Agent | `v4-11-agent-*` | Agent orchestration |

---

# 43. 模块级测试要求

每个主要模块至少区分：

```text
Unit Test
Contract Test
Integration Test
E2E Test
```

原则：

```text
Memory 测试不要求启动 React
Quality 测试不要求启动 MCP
LLM Router 测试不要求写生产数据库
MCP schema 测试不负责故事质量
Blueprint generation 测试使用明确 fixture
```

废弃 historical 不再作为隐式测试 fixture。

---

# 44. V4 完成定义

## Agent Ready

外部 Agent 能通过 MCP 完成：

```text
创建项目/作品
→ 设定
→ 人物
→ 人物弧
→ 世界
→ 故事弧
→ 章节大纲
→ 场景大纲
→ Quality
→ Repair
→ Verify
→ 导出 Story Blueprint
```

无需操作浏览器。

---

## Quality Closed Loop

不是：

```text
Generate → Save
```

而是：

```text
Generate → Evaluate → Repair → Verify → Revision Save
```

---

## Memory

生成任意 Story Blueprint 节点时能够正确检索：

- 相关人物
- 相关人物弧
- 最近剧情状态
- Canon
- StoryState
- 未完成伏笔
- setup/payoff
- 作者偏好

不需要加载废弃 historical 或完整正文。

---

## Blueprint Editor

作者能够：

```text
直接编辑节点
查看 Diff
恢复 Revision
接受/拒绝 AI 修改
查看 Quality Issue
定向 Repair
```

---

## Export

最终结果：

- 只属于当前目标作品
- Story Blueprint 结构完整
- 不带旧 historical
- 不带废弃正文
- 不带内部调试字段
- 可追溯
- 可以交给其他 Agent / Writer / Screenplay Tool 继续处理

---

# 45. V4 最重要的四个边界

## 1. LLM 不是数据库

## 2. MCP 不是业务层

## 3. Quality 是正式业务能力

## 4. Story Blueprint 是核心创作产物

正文生成如果未来重新加入，应作为：

```text
下游能力 / Plugin / External Agent Workflow
```

而不是重新侵入 V4 Core。

---

# 46. 尚未完全冻结、但不阻塞 V4-01 的决策

V4-00 中以下问题仍可后续定案：

```text
novel/runs 的长期保留策略
novel/pipelines 中哪些旧能力最终保留
novel/learning 的最终产品定位
是否把“多作品”作为长期 UI 产品能力
```

但 V4-01 必须先满足一个最低不变量：

```text
任何 artifact、state、export、cache 不得通过全局硬编码路径隐式混入其他作品/历史数据。
```

即使最终 UI 只支持一个 active novel，底层也不得依赖“磁盘上只有一个作品”这一假设。

---

# 47. V4 最终目标

NovelForge V4 最终应成为：

```text
Story Blueprint Runtime
+
Story State Engine
+
Long-term Story Memory
+
LLM Orchestrator
+
Narrative Quality Engine
+
Targeted Repair Engine
+
Blueprint Editor
+
MCP Server
+
Plugin Platform
```

它的主要价值不是替作者把小说正文全部写完，而是：

```text
把一个故事从创意
逐步推演成结构清晰、因果成立、人物连续、场景有效、伏笔可追踪、可以直接继续创作的高质量故事蓝图。
```
