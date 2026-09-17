# NovelForge Agent Instructions

## Product state（当前正式状态）

```text
NovelForge V3 Final = RELEASED / FROZEN（Functional Closure）
release tag         = novelforge-product-v3-final
history shape       = 单一 root commit（main = v4 = V3 Final root）
历史 release        = novelforge-product-v3.0 / novelforge-product-v2.0 / story-engine-v2.0
                      已归档：historical / archived / not an active Git ref
                      完整历史见外部 bundle NovelForge_pre_V4_full_history.bundle
```

规则：

- 不修改、不移动唯一活动 release tag `novelforge-product-v3-final`；
- 旧 release（V3.0 / V2.0 / Story Engine V2）只作为 metadata：不得要求活动仓库能
  resolve 它们（冻结机制见 `docs/FROZEN_EVIDENCE_MANIFEST.json` 与
  `tests/test_v2_frozen_guard.py`）；
- 新需求 / 新功能不进入 V3 Final：进入 V4（从 `v4` 分支开始，先写版本计划再开工）；
- V2/V3 的 frozen truth（Canon / StoryState / legacy 源 / 已冻结的 Contract / Gate）保持只读；
- 真实作者数据（story engine authoring / 内容包 / forge chain / workspace 产物）保持
  gitignored，不进入版本控制。

> 本文件是 NovelForge 仓库级长期执行规则。
>
> **适用范围：所有 Codex 会话、所有新任务、所有子任务。**
>
> 只要 Codex 在本仓库内工作，就必须在每次新会话 / 新任务开始时先读取并遵守本文件，
> 不得因为上下文切换、开启新对话、进入新 milestone 或更换执行阶段而忽略这些规则。
>
> 若用户当前任务与本文件冲突：
>
> 1. 用户当前明确指令优先；
> 2. frozen truth / contract / gate / approval boundary 不得被隐式绕过；
> 3. 如必须突破 frozen boundary，必须显式报告并停止相关 production mutation。
>
> 本文件应放置在仓库根目录 `AGENTS.md`，并作为 Codex 的仓库级执行约束长期维护。


## Documentation

When implementing or modifying code involving third-party libraries,
use Context7 to check the latest official documentation before coding.

Do not guess APIs when documentation can be retrieved.

---

## 0. 每次会话启动规则（强制）

每次新的 Codex 对话、任务或工作恢复时，必须先完成以下 bootstrap：

1. 读取仓库根目录 `AGENTS.md`。
2. 读取与当前任务直接相关的文档（见 §17）：产品入口 `README.md`、架构 `docs/ARCHITECTURE.md`、
   数据模型 `docs/DATA_MODEL.md`、变更记录 `docs/CHANGELOG.md`；新版本工作再读该版本的计划。
3. 检查 `git status`、当前分支、最近提交、`git tag`（确认 release tag 未被改动）。
4. 搜索已有实现，确认是否已经存在相同或相近能力。
5. 明确当前任务属于：
   - 产品功能实现；
   - 缺陷修复 / regression；
   - architecture / refactor；
   - 测试与验收；
   - documentation only；
   - analysis-only（只读诊断）。
6. 明确当前任务允许修改的边界，以及必须保持不变的 frozen boundary。
7. 以磁盘真实状态与测试结果为准，不依赖聊天摘要或历史报告里的执行状态。

默认原则：

```text
READ AGENTS.md FIRST
DISK STATE WINS
SEARCH BEFORE IMPLEMENT
UNDERSTAND BOUNDARY BEFORE MUTATION
```

不得因为“之前已经读过 AGENTS.md”而跳过。

---

## 1. 项目目标

NovelForge 正在实现一套“游戏化小说设计与创作流程”。

核心思想不是传统表单，而是类似游戏技能树：

选择 → 解锁 → 展开 → 改选 → 复核 → 剧情影响 → 大纲生成。

设计需要支持不同题材，不得只针对《硅基升维》写死逻辑。

---

## 2. 总体工作原则

1. 先阅读现有实现和文档，再修改代码。
2. 不重复实现已经完成的功能。
3. 每次聚焦一个明确的**执行目标 / 工作包**，但在当前目标没有真实外部阻塞时，不要因为完成一个小步骤就停止整个会话。
4. 一个目标必须经过：
   - 实现；
   - 主动结构自检；
   - 定向测试；
   - 全量回归测试；
   - 必要时浏览器实际验证；
   - 更新实施计划 / milestone / audit。
5. 测试通过之前，不得把目标标记为完成。
6. 发现历史问题时可以修复；如果问题与当前 subsystem / 当前目标正确性直接相关，应优先在当前任务内修掉；不要借机大规模重构无关代码。
7. 优先复用现有：
   - session
   - catalog
   - adventure
   - outline
   - version
   - export
   - overlay
   - readiness
   - backlog
   - queue
   - lineage
   - graph
   - reconciliation
   机制，不建立平行体系。
8. 不为了测试通过而削弱业务规则。
9. 不把配置直接等价为角色已经拥有的知识、物资、装备或能力。
10. 已发生剧情与未来规划必须严格区分。
11. 不修改历史小说正文和既有正式数据，除非任务明确要求。
12. 不主动提交 Git，除非用户明确要求；如果当前用户任务已经明确要求“完成并提交”，则按任务要求提交。
13. 不为了“最小改动”保留明显会立刻导致下一阶段返工的错误抽象。
14. 不为了“结构更漂亮”突破 frozen truth / contract / gate / approval boundary。
15. 能在当前 subsystem 内安全完成的局部结构优化，默认在当前任务内完成，不再机械拆成 00A / 00B / 00C 小任务。

---

## 3. 受控自治结构优化模式

从现在开始，NovelForge 默认采用：

```text
CONTROLLED AUTONOMOUS REFACTORING
```

目标是减少：

```text
实现
→ 汇报
→ 人工发现结构问题
→ 新任务修结构
→ 再验证
```

改为：

```text
实现
→ 主动结构审计
→ 必要的安全重构
→ 验证
→ 一次性交付
```

### 3.1 默认允许主动优化的情况

如果在当前任务中发现以下问题，Codex 可以在**同一个任务 / commit** 内主动优化：

- 重复逻辑；
- 重复 data model；
- artifact identity 与 semantic identity 混淆；
- 同一概念存在多个来源但没有 canonical identity；
- 同一状态存在多个不一致计算入口；
- 多个 run executor / validator / report generator 大量复制；
- 明显可以抽成共享组件的重复 pipeline；
- 冗余 adapter / compatibility wrapper；
- 当前 subsystem 内明显错误的模块边界；
- 高耦合但可局部安全拆分；
- 分析结果存在 alias / duplicate / double-count 风险；
- 测试暴露的结构性问题；
- 当前实现会明显导致下一 milestone 重复返工；
- 当前分析结果即将被用于 production execution，但结构还没有 canonicalize。

原则：

```text
如果结构问题是当前任务正确完成所必需，
或者现在不修会让下一阶段建立在错误抽象上，
就在当前任务内解决。
```

### 3.2 默认允许主动修改的范围

可以主动优化：

- `src/` 内部实现；
- analysis / orchestration 层；
- helper / utility；
- 内部 data model；
- canonicalization layer；
- deduplication layer；
- dependency graph；
- validator；
- reconciliation；
- report generator；
- run executor 公共逻辑；
- tests；
- 内部命名；
- 非 frozen planning / roadmap。

前提：

```text
外部行为正确
已有兼容性保持
测试通过
production invariants 不被破坏
```

### 3.3 不允许自行改变的 Frozen Boundary

以下内容不能因为“架构更优雅”而自行改变：

- Canon；
- StoryState；
- legacy source；
- 570 source Chapter IR；
- Historical Foundation；
- frozen Repair Contract；
- frozen Gate；
- Truth precedence；
- Approval boundary；
- 已冻结的 Overlay primary taxonomy；
- 已冻结的 Readiness semantics；
- Author decision policy；
- 已冻结 production truth / lineage；
- 已经明确冻结的 M11/P15 capability boundary。

如果确实发现 frozen boundary 无法表达真实场景：

```text
不要偷偷修改
→ 标记 ARCHITECTURE_EXCEPTION_REQUIRED
→ 停止相关 production mutation
→ 输出 evidence 与影响
```

普通代码结构问题不属于 architecture exception。

---

## 4. 每个任务必须做结构自检

### 4.1 实现前

快速检查：

- 当前功能是否已有类似实现？
- 是否存在重复 canonical identity？
- 是否存在两个 artifact 表示同一 semantic object？
- 是否会新增第三套相同计算逻辑？
- 当前设计是否会造成下一 milestone 重复返工？
- 是否有现成 graph / queue / ledger / resolver / reconciler 可以复用？
- 当前任务是否会直接产出 production execution recommendation？
- 如果会，identity / dedup / coverage / double-count 是否已经验证？

### 4.2 实现后

再次检查：

- 是否产生新的重复代码？
- 是否产生新的重复 truth source？
- 是否出现 artifact identity 与 semantic identity 混淆？
- 是否产生多个 owner 表示同一个 semantic requirement？
- 是否有 alias 被错误计为多个 root / item？
- 是否有 shared dependency 被重复计入 unlock impact？
- 是否出现临时兼容层可以安全收掉？
- 是否应该抽成共享组件？
- 当前输出能否安全作为下一阶段输入？

这些检查默认属于当前任务，不应机械拆成独立 milestone。

---

## 5. Canonical Identity 原则

长期 invariant：

```text
ARTIFACT_IDENTITY_IS_NOT_SEMANTIC_IDENTITY
```

当多个 artifact 指向同一业务对象，例如：

- Backlog item；
- CDQ item；
- Overlay requirement；
- Resolution record；
- Dependency node；
- Author action；
- Manual item；
- Entity item；

必须优先建立：

```text
canonical semantic identity
```

允许：

```text
ONE_SEMANTIC_ROOT_MAY_HAVE_MULTIPLE_ARTIFACT_REFS
```

不得因为 artifact 数增加，就错误增加：

- root count；
- blocker count；
- dependency count；
- unlock impact；
- execution item count；
- lane priority。

如果 equivalence 有歧义：

```text
AMBIGUOUS_DO_NOT_MERGE
```

不能为了减少 root 数强行合并。

---

## 6. Analysis → Production 前强制审计

任何 analysis artifact 将直接决定下一步 production execution 时，必须在**当前任务内**自动完成：

- identity canonicalization；
- alias reconciliation；
- deduplication；
- coverage；
- multi-root semantics；
- dependency traversal；
- cycle / SCC；
- stale artifact；
- zero-target artifact；
- orphan artifact；
- ownership consistency；
- double-count protection；
- immediate unlock / conditional unlock 区分；
- lane ranking revalidation。

规则：

```text
未经 canonicalization 的分析结果
不得直接驱动 production execution
```

如果发现明显问题：

```text
先修分析层
→ 重新计算
→ 再给 production recommendation
```

普通 canonicalization / deduplication 不再默认新增 00A / 00B milestone。

---

## 7. Root Blocker / Blocker Resolution 长期规则

长期 invariant：

```text
DERIVED_BLOCKER_COUNT_IS_NOT_EXECUTION_ITEM_COUNT
ROOT_BLOCKER_FIRST
ROOT_BLOCKER_MUST_BE_EVIDENCE_BACKED
AUTHOR_DECISION_IS_BATCHED
NO_ALIAS_DOUBLE_COUNT
NO_DIRECT_BACKLOG_DRAIN_BEFORE_ROOT_CAUSE_GRAPH
```

含义：

1. derived blocker occurrence 不能直接换算为 execution item。
2. 必须先找真实 root blocker。
3. 一个 root 必须有 evidence。
4. Author decision 尽量聚合为 decision package。
5. alias / artifact manifestation 不能重复计算。
6. 不允许因为 backlog 中已有几十个 item 就机械逐条 drain。
7. multi-root target 必须保留 multi-root 语义。
8. immediate unlock 只计算单独解决当前 root 真正能释放的 target。
9. conditional unlock 与 immediate unlock 必须分开。
10. lane 执行顺序由真实 unlock impact / truth risk / approval dependency / dependency depth 决定，不按固定编号硬编码。

---

## 8. 不机械复制 Run Executor

如果连续多个 production run 出现大量高度重复的：

```text
m11_run08.py
m11_run09.py
m11_run10.py
m11_run11.py
...
```

Codex 必须主动评估是否应抽象为：

```text
generic production-run executor
+
run-specific declarative configuration
```

只要满足：

- 历史 artifact 仍可复现；
- frozen semantics 不变；
- compatibility 保持；
- regression tests PASS；

即可在当前 subsystem 内主动重构。

不要无限复制：

```text
executor + test + report logic
```

同理适用于：

- closeout；
- gate；
- snapshot；
- reconciliation；
- queue validation；
- graph analysis。

---

## 9. Architecture Debt Queue

如果结构问题：

- 不是当前任务正确性的阻塞项；
- 修改风险较大；
- 涉及跨 subsystem；
- 需要独立 approval；
- 会影响 frozen architecture；

则不要硬塞进当前 commit。

记录到：

```text
ARCHITECTURE_DEBT.json
```

至少包含：

```text
debt_id
location
problem
impact
recommended_fix
urgency
blocking_future_phase
safe_to_defer
```

只有：

```text
当前不修会让下一阶段建立在错误结构上
```

的 debt，才要求当前任务立即修。

---

## 10. 重构预算与 Scope 控制

默认原则：

```text
直接任务 = 主目标
局部安全重构 = 同任务完成
跨系统重构 = Architecture Debt
Frozen architecture change = 禁止自动进行
```

如果重构影响已经超过当前 subsystem：

```text
停止扩大 scope
记录 debt
继续完成当前主任务
```

“受控自治优化”不是无限重构许可。

---

## 11. 自动架构审计触发条件

以下情况必须主动做 architecture audit：

- 进入新 milestone；
- 结束一个 phase；
- 同类型逻辑复制 >= 3 次；
- 同一 semantic object 出现 >= 2 个 identity system；
- 新增 dependency graph；
- 新增 queue / ledger / overlay；
- 出现大量 compatibility code；
- repeated reconciliation logic；
- 一个 analysis 结果将直接决定 production execution 顺序；
- blocker lane 即将开始；
- M11 → M12 这种阶段切换。

audit 默认在当前任务内完成，不自动新增独立 milestone。

---

## 12. 已发布产品的工作方式

`NovelForge Product V3.0` 已经 RELEASED / FROZEN。这里的规则针对**已发布代码**：

```text
小步修改
→ 定向测试
→ 相关回归
→ 需要时真实浏览器验证
→ 一次提交
```

允许在同一个工作包内连续完成多个安全步骤（不要拆成无意义的 00A / 00B / 00C），
但每一步都必须可验证，并且不得削弱既有 gate。

禁止：

```text
为了赶进度绕过验证
把不是本次任务的改动混进提交
修改 release tag / release commit
在没有版本计划的情况下堆新功能
```

### 12.1 不应停止等待用户确认的情况

以下情况默认继续：

- 当前 subsystem 内的局部结构优化；
- canonicalization；
- deduplication；
- validator 加固；
- alias reconciliation；
- analysis 修正；
- 测试修复；
- 文档 / roadmap 同步；
- 同一工作包内下一个无争议步骤；
- 已有计划中明确的下一个安全步骤。

### 12.2 必须停止的情况

只有以下情况才应停下来等待用户 / 外部输入：

1. 需要作者做真实剧情决定；
2. 会新增真实历史事件且需要 Author Content Approval；
3. 需要修改 Canon / StoryState / legacy / source Chapter IR；
4. 需要改变 frozen Contract / Gate / approval boundary；
5. 出现真实 architecture exception；
6. API / 权限 / 外部依赖阻塞；
7. 当前环境明确无法继续；
8. 测试持续失败且原因无法在当前 subsystem 内安全修复；
9. recommendation 发生重大变化，继续执行将进入不同风险 lane；
10. 系统即将强制终止当前执行。

否则不要因为：

- 已完成一个阶段；
- 已完成 3～5 个小目标；
- 已经运行较长时间；
- 已产生阶段总结；
- 下一个目标较大；
- 想让用户确认一下；

而停止。

---

## 13. 任务粒度

```text
一次一个明确的工作包（work package），
工作包内部允许包含多个连续、依赖明确、安全可验证的步骤。
```

只有当风险边界发生变化（触碰 frozen truth / 需要作者决定 / 需要改变 contract 或 gate）时，
才把工作包拆开并停下来报告。

---

## 14. 小说设计原则

整个设计系统逐渐形成以下设计树：

故事定位
→ 阅读体验
→ 世界背景
→ 社会秩序
→ 地域与生活
→ 主角身份
→ 当前危机
→ 人物经历
→ 性格
→ 欲望
→ 恐惧
→ 错误信念
→ 人物关系
→ 势力
→ 能力
→ 资源
→ 信息
→ 冲突
→ 开篇
→ 主线
→ 支线
→ 转折
→ 伏笔
→ 高潮
→ 结局
→ 叙事方式
→ 章节大纲。

设计思想类似游戏技能树：

- 前置条件；
- 推荐原因；
- 条件解锁；
- 分支选择；
- 返回改选；
- 下游待复核；
- 不强迫一次填写全部内容。

允许：

快速起步 → 按需展开 → 深度设计。

---

## 15. 数据原则

配置不是事实。

例如：

选择“学习过剑术”
≠ 当前一定拥有剑。

选择“知道某秘密”
≠ 剧情角色已经获得该情报。

选择“富裕家庭”
≠ 当前旅途中自动获得无限金钱。

未来规划也不能倒灌为已经发生的剧情事实。

长期保持：

```text
PLANNING != OCCURRED TRUTH
CONFIG != POSSESSION
DESIGN INTENT != CANON FACT
```

---

## 16. M11 / Repair / Blocker 特别规则

> **历史边界（2026-09-17 起）**：M11–M18 是 V2 时代的里程碑，已经随
> `novelforge-product-v2.0` 冻结（该 tag 现已归档：historical / archived /
> not an active Git ref；其 commit `56cda829…` 由外部 bundle 承载）。
> 它们的验收测试依赖本机历史数据，
> **V4-01 起这批历史验收测试已随废弃资产删除**（作者决策 A/B；
> marker 保留给 V4 里程碑验收复用，见 `pytest.ini`）。
> 本节规则仍然有效：**任何情况下都不得自行修改** 已冻结的 Repair Contract / Gate /
> truth boundary，即使相关代码已经归档为只读历史路径。

如果当前工作涉及 M11：

### 16.1 Frozen architecture

不得自动修改：

- frozen Repair Contract；
- `REPAIR_GATE_V1`；
- Truth Boundary；
- P15 closeout invariants；
- confirmed approval boundary。

### 16.2 P15

长期执行：

```text
P15_EXECUTOR_READ_ONLY_AFTER_CLOSEOUT
```

P15 executor 不得：

- claim `M11_RUN_*` production item；
- repair blocker item；
- promote blocker item；
- rewrite production ownership。

### 16.3 FIELD_REBIND

除非真实自然 target 完整满足 frozen SAFE_AUTO gate，否则：

```text
FIELD_REBIND capability = NOT_PROVEN
```

不得：

- 制造样本；
- 降低 risk；
- 绕过 state-binding conflict；
- 为 capability matrix 强行 promotion。

### 16.4 M12

不得因为：

```text
AUTO_SAFE_SWEEP_COMPLETE
```

就认为：

```text
M11 COMPLETE
M12 ENTRY ALLOWED
```

必须满足 frozen M12 entry criteria。

---

## 17. 主要文档

产品文档集合（当前版本）：

```text
README.md                                       产品入口：是什么 / 怎么装 / 怎么跑 / 怎么测
AGENTS.md                                       仓库级长期规则（本文件）
docs/ARCHITECTURE.md                            架构 SSOT（Domain / Application / ViewModel / UI）
docs/DATA_MODEL.md                              数据模型与 truth 分层
docs/STORY_BUILDER_USER_GUIDE.md                使用指南
docs/NEW_NOVEL_GUIDE.md                         新建小说指南
docs/NOVELFORGE_REAL_NOVEL_PRODUCTION_GUIDE.md  真实长篇生产指南
docs/CONTENT_PACK.md / GENRE_TEMPLATE.md        内容包与题材模板规范
docs/LEGACY_COMPAT.md                           兼容与 legacy 边界
docs/CANON_DEFENSE_COVERAGE_MATRIX.md           Canon 防冲突矩阵（由测试校验）
docs/CHANGELOG.md                               Release history（V3.0 / V2.0 / 更早）
```

Release / 验收 artifact：

```text
docs/V3_FULL_PRODUCT_ACCEPTANCE.json            V3.0 最终验收结果
docs/V3_VISUAL_ASSET_REQUIREMENTS.json          视觉资源契约（由 contract test 校验）
docs/NOVELFORGE_PRODUCT_V2_RELEASE.md           V2 release 记录（frozen）
```

历史开发过程（M11–M18、W1–W6、Story Engine 早期阶段）保存在 **Git history**，
不在仓库里保留副本；需要时用 `git log` / `git show <commit>:<path>` 查阅。

新版本工作：

```text
先创建该版本的计划（例如 V3.1_PLAN.md），再开工；
不要把已经发布版本的验收 artifact 当成进行中的计划。
```

如果文档与代码冲突：

```text
代码实际行为 + 测试结果
用于判断当前实现状态

产品目标
以设计方案 + 当前主实施计划为准
```

发现冲突时先分析原因；如果属于当前 subsystem 且可安全修复，可在当前任务内修复，不必机械等待下一轮。

---

## 18. 主要代码区域

Story Builder：

`src/novelforge/story_builder/`

Story Engine：

`src/novelforge/story_engine/`

API：

`src/novelforge/api/story_builder_routes.py`

配置：

`novel/config/story_builder/step_catalogs.yaml`

Web UI：

`ui/src/`

测试：

`tests/`

修改之前先搜索相关实现，不假设文件职责。

---

## 19. 验收要求

每个工作包至少验证与当前任务相关的：

- 保存；
- 刷新恢复；
- 上游改选；
- 下游复核；
- 条件限制；
- 不相关节点不受污染；
- 旧存档兼容；
- API；
- UI；
- 大纲/剧情联动；
- canonical identity；
- deduplication；
- ownership；
- queue / ledger conservation；
- dependency graph；
- production digest；
- truth boundary；
- targeted tests；
- full regression。

如果涉及 UI 交互，应尽量进行实际浏览器验证。

如果涉及主动重构，必须：

```text
targeted tests PASS
full pytest PASS
validate_project PASS
```

并验证相关 production state：

```text
before == after
```

除非当前任务明确允许预期 production mutation。

---

## 20. 不为了测试通过削弱规则

禁止：

- 删除关键 assertion 只为让测试通过；
- 把精确检查改成模糊检查以掩盖真实错误；
- 修改 frozen digest 期望来迁就错误 mutation；
- 把 architecture exception 当普通 downgrade；
- 把 author decision 自动选择掉；
- 用 derived blocker count 冒充真实 execution item；
- 用 artifact 数冒充 semantic root 数；
- 忽略 orphan / duplicate / uncovered；
- 为赶进度绕过 gate。

如果旧测试与真实新状态冲突：

先判断：

```text
测试是否表达历史 timepoint
还是表达永久 invariant
```

只允许对历史 timepoint 做兼容性更新，不得削弱永久 invariant。

---

## 21. 版本计划规则

1. V3 Final 已冻结（Functional Closure）：不改功能、不重排 roadmap，
   只修缺陷或做安全的内部整理；剩余质量问题全部进入 V4。
2. 新需求先写新的版本计划（V4 计划），再按计划实现；V4 从 `v4` 分支开始。
3. 计划必须反映真实状态，不得为了文档好看提前标记完成。
4. 小型内部重构 / canonicalization / dedup 不新增版本号。
5. 只有独立 phase gate、需要作者 approval、高风险 migration、frozen architecture change
   或独立外部依赖，才值得单独拆出一个版本阶段。
6. 版本计划完成后，同步更新 `docs/CHANGELOG.md` 与相关 acceptance artifact。

---

## 22. 工作汇报格式

完成一个工作包后，只报告：

- 完成了什么；
- 修改的关键文件；
- 主动做了哪些结构优化；
- 为什么这些结构优化属于当前任务；
- 测试结果；
- 浏览器验证结果（如适用）；
- production / truth / frozen boundary 是否变化；
- 发现的问题；
- Architecture Debt（如有）；
- 实施计划状态；
- 唯一下一接续点（仅当当前会话确实必须停止）。

不要长篇复述整个项目。

---

## 23. 发布后变更规则

对已发布的 V3.0 代码：

```text
同一工作包内可以连续完成多个安全步骤，但每个步骤都必须可验证；
遇到 frozen boundary / 作者决定 / 需要改 contract 或 gate 时，停下来报告。
```

必须停止并报告的情况：

1. 需要作者做真实剧情决定；
2. 需要修改 Canon / StoryState / legacy 源 / source Chapter IR；
3. 需要改变 frozen Contract / Gate / approval boundary；
4. 需要移动或修改任何 release tag / release commit；
5. 出现真实 architecture exception；
6. API / 权限 / 依赖等外部条件阻塞；
7. 当前环境明确无法继续；
8. 测试持续失败且无法在当前 subsystem 内安全修复。

不得因为“已经改了不少”“下一步比较大”“想让用户确认一下”而停下。

---

## 24. 数据与仓库卫生

```text
真实作者数据不进版本控制
测试必须使用 isolated / temporary root
生成物（ui/dist、缓存、截图、运行产物）保持 gitignored
release tag 只增不改
```

- 作者数据（`novel/authoring/story_engine/**`、内容包 `*_pack.json`、forge chain、
  `workspace/**`）一律 gitignored，由运行环境生成；
- 测试默认不得读取开发机上的作者数据：需要历史数据的 V2 里程碑验收
  V4 里程碑验收改用最小 deterministic fixture（不依赖本机历史数据）；
- 仓库根目录不保留临时文件、备份、审计截图或一次性迁移脚本。

---

## 25. 最终目标

Codex 的职责不是：

```text
只完成当前测试要求的最小补丁
```

而是：

```text
在不突破 frozen boundary 的前提下，
交付一个可以继续向前开发的健康结构。
```

长期优化目标：

```text
减少重复实现
减少人工反馈回路
减少错误抽象进入下一阶段
减少无意义的 00A / 00B / 00C
保持 truth / contract / gate 稳定
提高每次 Codex 会话的有效推进距离
```
