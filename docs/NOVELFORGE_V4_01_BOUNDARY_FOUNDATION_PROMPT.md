# NovelForge V4-01 — Boundary Foundation & Legacy Cleanup

你现在开始 NovelForge V4 的第二个正式阶段：

```text
V4-01 Boundary Foundation & Legacy Cleanup
```

V4-00 Architecture 已完成并 PASS。

本阶段不是继续设计，也不是开始接 LLM。

目标是：

```text
把 V4-00 已经确定的架构边界真正落到代码结构上，
删除作者明确判定为废弃的旧资产，
消除历史数据/路径污染，
建立后续模块可以独立分支开发的稳定地基。
```

---

# 1. 开始前先读取

必须读取：

```text
docs/v4/V4_00_ARCHITECTURE_REPORT.md
docs/v4/V4_ARCHITECTURE.md
docs/v4/V4_MODULE_CLASSIFICATION.md
docs/v4/V4_MIGRATION_PLAN.md
docs/v4/V4_DELETION_PLAN.md
docs/v4/V4_ARCHITECTURE_RISKS.md
docs/v4/V4_LLM_CONTRACT.md
docs/v4/V4_MEMORY_ARCHITECTURE.md
docs/v4/V4_QUALITY_CONTRACT.md
docs/v4/V4_MCP_SPEC.md
docs/v4/adr/*
NOVELFORGE_V4_MASTER_PLAN.md
```

如果 `V4_MODULE_BOUNDARIES.md` / `V4_BRANCH_STRATEGY.md` 已存在，也必须读取。

---

# 2. 最新作者决策 —— 高于 V4-00 中的旧假设

以下决策已经冻结。

## 2.1 删除旧正文

```text
novel/final/*.md
```

作者确认这些正文已经没用。

要求：

```text
DELETE
NO MIGRATION
NO ChapterRevision import
NO compatibility preservation
```

先检查依赖，再删除文件及只为它们服务的代码/测试/路径。

禁止为了“以后可能有用”保留一份新的 legacy copy。

---

## 2.2 删除 570 章 historical

作者确认 570 章 historical 是废弃产物。

要求：

```text
DELETE
NO IMPORT
NO ARCHIVE NOVEL
NO PRODUCT FIXTURE
```

删除：

- historical 内容
- 自动扫描 historical 的运行时代码
- 指向该废弃作品的 hardcoded path
- 只服务该数据的 export / inspector / writer compatibility

如果测试依赖 historical，大型历史数据必须替换为最小 deterministic fixture。

---

## 2.3 V4 产品目标已经改变

V4 的最终目标不是完整小说正文。

核心产物是：

```text
Story Blueprint / 小说故事大纲
```

形态接近电影剧本开发阶段的结构化故事规划：

```text
Premise
Characters
Character Arcs
World
Story Arc
Act / Volume / Arc
Chapter Cards
Scene Cards
Causal Chain
Setup / Payoff
Timeline
Story State Transitions
Quality Evidence
Revision
```

因此本阶段如果发现 Architecture / ADR 中仍把：

```text
Writer
Full Draft
ChapterRevision for prose
novel/final
```

作为 V4 核心 source of truth，应先更新文档。

不要在 V4-01 建立新的正文 canonical store。

---

# 3. Git 分支

由于远端存在 `origin/v4`，不要创建：

```text
v4/01-...
```

使用：

```text
v4-01-boundary-foundation
```

从当前已接受的 V4-00 commit / main 集成基线创建。

不得移动：

```text
novelforge-product-v3-final
```

tag。

---

# 4. 第一任务：同步 Architecture Decision

在修改业务代码前，先做一个文档提交。

至少更新：

```text
V4_ARCHITECTURE.md
V4_MIGRATION_PLAN.md
V4_DELETION_PLAN.md
V4_MODULE_CLASSIFICATION.md
V4_QUALITY_CONTRACT.md
V4_MCP_SPEC.md
```

根据实际内容决定是否更新其他文件。

ADR 要求：

1. 检查 ADR-003 是否仍以 Canonical Writer Store / prose 为核心。
2. 如果是，标记为：

```text
Superseded
```

并新增一个 ADR：

```text
Story Blueprint Is The Primary Creative Artifact
```

3. 更新 ADR-007 或对应 ownership ADR：

```text
novel/final = DELETE
historical 570 chapters = DELETE
```

4. 不要伪造已决策内容。仍未决定的问题保持 Proposed/Open。

建议第一提交：

```text
docs(v4): align architecture with story blueprint product decision
```

---

# 5. 第二任务：删除明确废弃资产

定位并删除：

```text
novel/final/*.md
```

以及 V4-00 报告中的 570 章 historical 实际目录。

删除前必须列出：

```text
exact path
tracked/untracked
file count
code references
test references
config references
```

然后移除所有产品运行时依赖。

注意：

```text
不要备份到 legacy/
不要复制到 fixtures/
不要打包进 archive/
```

这些资产已经被作者明确判定无用。

测试需要的数据请重新制作最小 fixture，而不是继续依赖真实 historical。

---

# 6. 第三任务：消除废弃资产硬编码

V4-00 已发现类似：

```text
RECON_DIR
PLANNING_INDEX
canon/wasteland_001.sqlite
writer_integration.CANON_DB
inspector.CANON_DB
historical_ir.HISTORY_DIR
```

逐个验证当前代码。

原则：

```text
如果只服务已删除数据 → DELETE
如果是通用能力但路径写死 → REWRITE / parameterize
如果 frozen boundary 不能修改 → 新建 adapter 隔离
```

不得保留：

```text
“如果找不到当前数据就退回 wasteland/history”
```

这种 fallback。

---

# 7. 第四任务：建立 Path / Ownership Boundary

实现统一路径解析能力。

目标不是一次性支持复杂多作品 UI，而是建立硬性不变量：

```text
任何 artifact/state/export/cache
都不能通过全局硬编码路径
隐式读取其他作品或历史资产。
```

建议建立或完善：

```text
persistence/paths.py
```

或者 V4_MODULE_BOUNDARIES 指定的等价模块。

路径 API 必须显式接收足够 ownership context，例如：

```text
project_id
novel_id
artifact kind
```

禁止：

```text
GLOBAL_CURRENT_NOVEL_PATH
默认 wasteland_001
扫描磁盘后猜当前作品
```

不要在这一阶段顺便实现完整 multi-novel 产品。

---

# 8. 第五任务：Application Service Boundary

V4-00 已发现：

```text
api/story_builder_routes.py
```

承担大量业务编排。

V4-01 只做“边界抽离”，不要大改业务算法。

目标：

```text
Route / UI Adapter
      ↓
Application Service
      ↓
existing story_builder / story_engine capabilities
```

优先抽出稳定入口骨架。

不要求本阶段把 1,545 行 route 一次性清空。

禁止 Big Bang Rewrite。

应选择：

```text
低风险、边界清楚、测试充分
```

的第一批 orchestration 迁出 route。

---

# 9. 第六任务：JourneyProjection 单一入口

V4-00 已确认存在两套状态推导。

建立：

```text
JourneyService / JourneyProjection
```

作为唯一 canonical projection。

UI / API / 后续 MCP 必须消费同一结果。

原则：

```text
不要同时重写所有 UI
```

可以先建立 service 和 adapter，然后逐个入口切换。

本阶段结束时不得再新增第三套 journey/progress 计算。

---

# 10. 第七任务：Revision Primitive

建立最小、通用 revision primitive。

注意：

```text
Revision ≠ prose ChapterRevision
```

V4 未来的核心 revision 服务于：

```text
Story Blueprint
Story State
AI Repair
Editor Change
Agent Mutation
```

建议 primitive 至少定义：

```text
revision
expected_revision
revision conflict
parent revision
operation id
```

不要在 V4-01 实现完整 Blueprint Editor 历史系统。

只建立后续模块可以复用的基础 contract。

---

# 11. 第八任务：Legacy Boundary

V4-00 发现约 40+ frozen 历史模块。

不要为了“整理目录”大规模移动 frozen 文件。

使用：

```text
Frozen V3 Module
        ↑
Legacy Adapter
        ↑
V4 Service
```

可以创建：

```text
legacy/
    adapters/
    manifest / registry
```

或 Architecture 指定的等价结构。

但：

```text
legacy/ 只能隔离仍需要兼容的 frozen code
```

不要把已经明确 DELETE 的 `novel/final` 和 570 章 historical 搬进去。

---

# 12. 第九任务：模块目录真正成为维护边界

根据 V4-00 的 Module Boundaries 落地：

```text
Public Contract
Internal implementation
Module tests
Allowed dependency
Forbidden dependency
```

如果 V4_MODULE_BOUNDARIES.md 尚不存在，本阶段必须补齐。

每个新模块目录禁止出现：

```text
万能 service.py
万能 utils.py
跨模块 private import
```

`core/` 保持小。

---

# 13. 第十任务：新增 Isolation Tests

新增长期保留的隔离测试。

建议：

```text
tests/v4/isolation/
```

至少覆盖：

### A. No Historical Fallback

在 historical 不存在时：

```text
应用正常启动/核心测试正常运行
```

不得尝试读取：

```text
wasteland_001
historical
旧 570 章目录
```

### B. No Final Prose Dependency

删除 `novel/final/*.md` 后：

```text
pytest
validate_project
core API tests
```

不得失败。

### C. Ownership Isolation

构造两个最小 project/novel fixture：

```text
A
B
```

对 A 执行：

```text
read state
journey
export-related read
```

结果中不得出现 B 数据。

这不是承诺完整 multi-novel UI，而是验证底层 ownership 不依赖全局路径。

### D. No Implicit Disk Discovery

核心业务路径不能因为某个目录存在就自动把它绑定为当前作品。

---

# 14. V4-01 禁止事项

本阶段禁止：

```text
❌ 接 OpenAI / DeepSeek 新 API
❌ 实现 Model Router
❌ 实现 Memory V4
❌ 实现完整 Story Blueprint generation
❌ 实现 Quality Loop V4
❌ 实现 MCP Server
❌ 重做 UI
❌ 生成完整小说正文
❌ 新建 prose canonical writer store
❌ 大规模移动 frozen V3 模块
❌ 顺手重构所有 story_engine
❌ Big Bang database migration
```

---

# 15. 关于旧正文相关代码

由于产品目标已经变成 Story Blueprint：

遇到旧代码时按下面分类。

```text
只服务完整正文生成
    → 优先 DELETE / COMPATIBILITY_ONLY

同时服务大纲和正文
    → 拆出 Story Blueprint 可复用部分

属于稳定 Story Engine 能力
    → KEEP

属于硬编码创作 prose
    → REPLACE_BY_LLM 或 DELETE（后续阶段）
```

本阶段不要为了删除正文目标而一次性删除所有生成代码。

只删除：

```text
证据明确
范围清楚
有测试覆盖
```

的废弃路径。

---

# 16. 数据安全与删除验证

这次允许删除大量 tracked legacy data，但必须留下证据。

最终报告列出：

```text
deleted paths
deleted file count
deleted tracked bytes
references removed
fixtures added
```

同时证明：

```text
没有删除仍被 active V3/V4 tests 使用的 source code
没有移动 V3 final tag
没有污染 main
```

---

# 17. 测试与验收

至少执行：

```text
pytest -q
python validate_project.py
frozen guard / frozen boundary tests
UI/backend relevant tests
```

如果项目已有更正式的 acceptance scripts，全部执行。

必须对比：

```text
V4-00 baseline
vs
V4-01 result
```

V4-00 baseline：

```text
892 passed / 687 deselected / 0 failed
validate_project.py PASS
```

如果测试数量因为删除废弃 historical fixtures 发生变化，必须逐项解释，不能只报告新的数字。

---

# 18. Git 提交建议

建议保持 4~7 个有意义提交，例如：

```text
docs(v4): align architecture with story blueprint product decision
chore(v4): remove obsolete final and historical assets
refactor(v4): parameterize persistence ownership paths
refactor(v4): establish application service boundary
refactor(v4): centralize journey projection
feat(v4): add revision primitives and legacy adapters
test(v4): add ownership and legacy isolation coverage
```

不要创建大量碎片提交。

---

# 19. V4-01 Definition of Done

只有同时满足以下条件才 PASS。

## Product Direction

```text
[ ] Architecture 不再把完整小说正文当作 V4 核心交付物
[ ] Story Blueprint 被定义为 primary creative artifact
[ ] Writer 概念已在架构层重定义为 Blueprint Editor / Story Studio
```

## Legacy Cleanup

```text
[ ] novel/final/*.md 已删除
[ ] 570 章 historical 已删除
[ ] 无自动 historical fallback
[ ] 无 wasteland hardcoded product fallback
[ ] 无测试隐式依赖真实 historical
```

## Boundaries

```text
[ ] Application Service boundary 已落地第一批
[ ] JourneyProjection 有唯一 service 入口
[ ] path / ownership 不依赖隐式全局作品
[ ] revision primitive 已建立
[ ] legacy adapter boundary 已建立
[ ] frozen code 未被大规模搬迁
```

## Modularity

```text
[ ] module public/internal boundary 明确
[ ] 新增代码没有形成跨模块 private import
[ ] core 没有变成 utils dumping ground
[ ] 后续模块可以使用独立 flat task branch
```

## Tests

```text
[ ] pytest 通过
[ ] validate_project PASS
[ ] frozen guard PASS
[ ] no historical fallback test PASS
[ ] no final prose dependency test PASS
[ ] ownership isolation test PASS
```

---

# 20. 最终报告

完成后输出：

```text
V4-01 BOUNDARY FOUNDATION RESULT
```

必须包含：

```text
1. Architecture decisions updated
2. ADR changes
3. Deleted legacy assets
4. Hardcoded historical references removed
5. Application service boundary changes
6. JourneyProjection changes
7. Path / ownership changes
8. Revision primitive
9. Legacy boundary
10. Module boundary changes
11. Isolation tests added
12. Full test results
13. Frozen boundary result
14. Files created
15. Files modified
16. Files deleted
17. Git branch
18. Git commits
19. Known remaining risks
20. V4-02 readiness
```

最后明确：

```text
V4-01 = PASS
```

或：

```text
V4-01 = BLOCKED
```

如果 BLOCKED，只列真实 blocker。

---

# 最重要的执行原则

V4-01 不追求“看起来像全新架构”。

它追求：

```text
删除明确无用的历史负担
+
消灭隐式数据污染
+
建立稳定模块边界
+
保持现有有效内核正常运行
+
为 V4-02 之后的模块化并行开发建立可靠地基
```
