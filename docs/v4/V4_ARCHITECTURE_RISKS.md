# NovelForge V4 — Architecture Risk Register

> 状态：**V4-00 Architecture — 只识别，不处理**；已按 **V4-01 作者决策**更新受影响条目
> 每条风险必须有 `Evidence`（代码 / 数据事实）。没有证据的担忧不进入本表。
> Probability / Impact 采用 `H / M / L`（High / Medium / Low）。

### 0.1 V4-01 风险状态更新

| 风险 | V4-00 | V4-01 状态 |
| --- | --- | --- |
| R-11 Historical data leakage | H / H（已发生） | **已修复**：路径按 `novel_id` 参数化；历史数据与历史分区从产品导出 / inspector / writer 移除；跨作品隔离测试落地 |
| R-16 Export contamination | H / H（已发生） | **部分修复**：导出不再含历史分区与单作品硬编码；Q9 Delivery Validator 留待 V4-07 |
| R-15 Writer overwrite | M / H | **风险对象改变**：正文不再是 canonical artifact（ADR-011）；风险转为「Blueprint Editor 覆盖作者接受的节点」，缓解手段不变（append-only revision + proposed 状态） |
| R-05 Prompt sprawl / R-03 LLM coupling | H / H | 未变化（V4-02 处理） |

---

## 0. 风险总表

| # | Risk | Prob. | Impact | Owner Layer |
| --- | --- | --- | --- | --- |
| R-01 | Big Bang Rewrite | M | **H** | 全局 / 计划层 |
| R-02 | Over-abstraction | **H** | M | 全局 / 架构层 |
| R-03 | LLM coupling | M | **H** | `ai` / `generation` |
| R-04 | Provider coupling | M | M | `ai.providers` |
| R-05 | Prompt sprawl | **H** | M | `ai.contracts` / `generation` |
| R-06 | Context explosion | M | M | `memory.context_builder` |
| R-07 | Memory corruption | M | **H** | `memory` |
| R-08 | Canon drift | M | **H** | `domain.canon` / `quality` |
| R-09 | Revision race | M | **H** | `persistence` / `application` |
| R-10 | Agent duplicate writes | **H** | **H** | `interfaces.mcp` / `application` |
| R-11 | Historical data leakage | **H**（已发生） | **H** | `persistence` / `legacy` |
| R-12 | Plugin privilege escalation | M | **H** | `plugins` |
| R-13 | Quality cost explosion | M | M | `quality` / `ai.usage` |
| R-14 | Quality infinite repair loop | M | **H** | `quality.repair` |
| R-15 | Writer overwrite | M | **H** | `application.services.writer` |
| R-16 | Export contamination | **H**（已发生） | **H** | `services.export` |
| R-17 | Schema version drift | M | M | `core.revision` / `persistence` |
| R-18 | MCP contract instability | M | M | `interfaces.mcp` |

---

## 1. 逐条风险

### R-01 Big Bang Rewrite

```text
Probability : M
Impact      : H（同时破坏 frozen boundary 与 892 个测试建立的回归网）

Evidence
  · Master Plan §30 列出 13 个阶段；其中 V4-01 "Core Cleanup" 若按计划新建 domain/，
    会形成两套领域模型（见 V4_ARCHITECTURE.md CHALLENGE-01）
  · 现有 40+ 冻结模块不可删除，任何"推倒重来"都会撞上 frozen 证据
  · 892 passed / 687 deselected 的测试网是围绕现有模块路径建立的

Mitigation
  · V4_MIGRATION_PLAN.md §1：Strangler + Adapter-first + 单点切换 + 每阶段可回滚
  · 每阶段保持 pytest 全绿 + validate_project PASS + production state before == after
  · 冻结模块只换命名空间，不改语义

Owner Layer : 全局（V4 版本计划）
Detection   : 每阶段 acceptance（pytest / validate_project / frozen guard）
```

### R-02 Over-abstraction

```text
Probability : H（当前最主要的风险：Master Plan 提议 13 个顶层目录）
Impact      : M（拖慢交付、增加空洞层，但不破坏正确性）

Evidence
  · Master Plan 提议 memory/ / plugins/ / observability/ / repair/ / persistence/migrations/
    等新层，而 V3 已用 5 个模块（creative / settings_gen / outline_forge / journey / writer）
    完成了当前全部生成能力
  · 当前没有任何 trace / metrics / cost 基础设施（observability 无存量）
  · 当前持久化为 JSON + 单 SQLite，引入 migrations/ 框架没有对应需求
  · 插件真实需求只有 4 类（V4_PLUGIN_SPEC.md §1.1）

Mitigation
  · V4_ARCHITECTURE.md §3.2 列出"暂时不建"的抽象与重启条件
  · V4_PLUGIN_SPEC.md §3.2 把 8 类插件缩减为先做 3 类
  · 每层必须有 owner 与真实消费者才允许创建

Owner Layer : 架构层
Detection   : 阶段评审必问"如果没有这层，哪个具体用例会失败？"
```

### R-03 LLM coupling

```text
Probability : M
Impact      : H（模型耦合会让换 provider / 换模型 / 成本控制全部失效）

Evidence
  · story_engine/spec/llm.py 把 DEFAULT_MODEL = "deepseek-chat" 与
    DEFAULT_ENDPOINT = "https://api.deepseek.com/chat/completions" 写成模块常量
  · 三处业务模块（creative / settings_gen / ai_recommendations）直接用 provider 鸭子类型
  · 无 usage / cost / trace 记录

Mitigation
  · V4_LLM_CONTRACT.md §3：所有调用经 llm.generate(contract, context, model_policy)
  · §11.1：provider 不允许依赖 domain / application / persistence
  · 源码守卫：业务模块不得出现 urllib / requests / httpx / openai / anthropic

Owner Layer : ai / generation
Detection   : import 边界守卫测试 + provider 单测离线化
```

### R-04 Provider coupling

```text
Probability : M
Impact      : M

Evidence
  · 目前只有一个 provider 实现，用 urllib 手写 HTTP（无 SDK 抽象）
  · 环境变量只有 DEEPSEEK_API_KEY / ARK_API_KEY（.env.example）

Mitigation
  · ai/providers/base.py 定义 LLMProvider 协议；deepseek 只是其中一个实现
  · ModelRouter 按任务选模型；业务层不出现厂商名
  · 配置只出现 provider_id，不出现端点常量

Owner Layer : ai.providers
Detection   : 换 provider 演练（用假 provider 跑通全部 contract）
```

### R-05 Prompt sprawl

```text
Probability : H（prompt 已经散落在业务模块里）
Impact      : M（不可审计、不可版本化、不可复用）

Evidence
  · creative.CreativeIdeaProvider._prompt() 在业务模块内拼 prompt 字符串
  · settings_gen.SettingsProvider._prompt() 同上
  · spec/llm.py:SYSTEM_PROMPT 是模块级常量
  · 没有任何 prompt 版本号或 contract 注册表

Mitigation
  · prompt 归属 ai/contracts（id + version + template）
  · GenerationContract.prompt_template_id 是唯一入口
  · prompt 变更必须提升 contract version（质量变化可追溯）

Owner Layer : ai.contracts / generation
Detection   : 源码守卫：业务模块中不得出现长字符串 prompt 常量
```

### R-06 Context explosion

```text
Probability : M
Impact      : M（成本上升、注意力稀释、质量下降）

Evidence
  · WriterContextBuilder 已设 BLOCK_BUDGET = 40（items/block）+ 跨块去重
    —— 说明容量问题已经出现过
  · _state_block 把全部角色与地点塞进 items（无相关性筛选）
  · _canon_block 取 facts(novel_id)[:BLOCK_BUDGET]，是"前 N 条"而不是"相关 N 条"

Mitigation
  · V4_MEMORY_ARCHITECTURE.md §5：按章节引用做相关性筛选（不是取前 N 条）
  · 上下文预算显式化（token 上限），trace 记录 context_refs
  · 超预算时按相关性裁剪并记录被丢弃项

Owner Layer : memory.context_builder
Detection   : 每次调用记录 context token 数；超预算告警
```

### R-07 Memory corruption

```text
Probability : M
Impact      : H（派生记忆被当作事实，会产生难以定位的错误）

Evidence
  · 现有 story_engine/memory.py 与计划中的 V4 memory/ 同名不同义（命名冲突）
  · export_package 的 section 带 truth_layer，说明"事实 / 派生混用"是已知风险
  · V3 尚无任何可重建性测试（删除派生层不影响事实）

Mitigation
  · memory 层显式声明 derived + rebuildable（V4_MEMORY_ARCHITECTURE.md §1）
  · 「删除 memory 目录后事实不变」测试
  · 上下文冲突检测（检索结果与 truth 不一致时记录，不静默采用）

Owner Layer : memory
Detection   : rebuild 等价性测试 + 冲突计数
```

### R-08 Canon drift

```text
Probability : M
Impact      : H（破坏"已发生事实"的权威性，直接违背项目核心原则）

Evidence
  · 现有防线扎实：canon/validator.py（引用支持判定）、canon/graph.py、canon/prose.py、
    chapter_ir/evidence.py、chapter_ir/verifier.py
  · 风险来自 V4 新增能力：LLM 生成的正文 / 大纲若直接写入会绕过这些防线

Mitigation
  · 原则 1.1（LLM 不是数据库）+ 生成结果一律为 proposal
  · Quality Q2 / Q3 对每个生成产物强制运行
  · Canon 只允许 CanonService 提升事实（既有语义）

Owner Layer : domain.canon / quality
Detection   : Canon validator 通过率；drift 样本回归集
```

### R-09 Revision race

```text
Probability : M
Impact      : H（静默覆盖作者内容）

Evidence
  · 现在写入是"原子替换 + 单进程锁"（storage.py），无跨进程保护
  · 没有 expected_revision 协议；后写者无条件覆盖
  · Agent 接入后并发写概率显著上升

Mitigation
  · V4_ARCHITECTURE.md §7.3：写操作必须携带 expected_revision，不匹配返回 conflict
  · append-only revision（不覆盖）
  · 单进程限制显式写入文档；多进程需求出现时再评估锁

Owner Layer : persistence / application
Detection   : 并发写测试（两个 client 同时写同一章节 → 一个成功、一个 conflict）
```

### R-10 Agent duplicate writes

```text
Probability : H（Agent 重试是常态）
Impact      : H（重复章节 / 重复事实 / 重复导出）

Evidence
  · V3 没有任何 request_id / idempotency 机制（全仓 rg 无 idempotency）
  · MCP tool 的重试语义必须显式设计（V4_MCP_SPEC.md §4.1）

Mitigation
  · 所有写 tool 必须带 request_id + idempotency_key + expected_revision
  · 同一 idempotency_key 的重试不产生第二次副作用
  · Result Envelope 返回 revision_before / revision_after

Owner Layer : interfaces.mcp / application
Detection   : 幂等测试（同 key 重放 N 次 → 只产生一个 revision）
```

### R-11 Historical data leakage

```text
Probability : H（已经发生）
Impact      : H（导出物可信度受损；作者可能误以为别的作品数据是自己的）

Evidence（均已核对）
  · export_package.py：RECON_DIR / PLANNING_INDEX / canon 路径写死 wasteland_001
    → 任意作品导出都带 WASTELAND 的 spine / planning / canon 分区（= V3 缺陷 NR-002）
  · writer_integration.CANON_DB、inspector.CANON_DB、historical_ir.HISTORY_DIR 同类
  · historical_ir.py L527 / L927 读取 novel/final/chapter_XXXX_final.md（另一部手稿），
    仅靠 _has_wasteland_entities()（L1822）关键词启发式防串稿，
    并在 L580 明确注明"novel/final/*.md 属另一部手稿，不得当作本作 source"
  · writer_integration 读取 workspace/wasteland_001_exports/writer_v1 作为 legacy 草稿源

Mitigation
  · V4-01：所有路径按 novel_id 参数化；section 带 identity 校验
  · V4-07：ExportPlan.excluded 显式列出未归属数据；DeliveryValidator 把混入判为 blocker
  · legacy 数据只能通过 legacy 命名空间显式访问
  · 去掉关键词启发式判断，改为显式 ownership（novel_id 绑定）

Owner Layer : persistence / legacy / services.export
Detection   : 跨作品导出测试（novel A 导出中不得出现 novel B 的任何 id / 文本）
```

### R-12 Plugin privilege escalation

```text
Probability : M
Impact      : H（插件可绕过质量门或改写事实）

Evidence
  · 尚无插件机制，因此无现有防护
  · 现有扩展点是数据配置（无代码执行），当前风险为 0

Mitigation
  · V4_PLUGIN_SPEC.md §7（P1–P7）+ PluginHost 不暴露 repository / 文件句柄
  · capability 白名单 + 权限声明 + 作者显式启用
  · 插件不得改变 Quality Gate severity 与放行规则

Owner Layer : plugins
Detection   : 结构性测试（host 无 db() / write_file()）+ 未声明 capability 拒绝测试
```

### R-13 Quality cost explosion

```text
Probability : M
Impact      : M（长篇小说 × 多 Gate × 多次修复 = 成本失控）

Evidence
  · 计划中 Q0–Q9 共 10 层门禁；若每层都用 LLM 评估，一章可能触发多次模型调用
  · 当前无任何 usage / cost 记录（无法度量）
  · 真实规模：novel/authoring/outline/chapters/ 已有 120 个章节文件

Mitigation
  · deterministic 优先（V4_QUALITY_CONTRACT.md §3.1）：能用 identity / 守恒 / DAG 的绝不调模型
  · Budget 闸门 + 每次评估记录 usage
  · 评估结果缓存（同 revision + 同 contract version + 同模型）

Owner Layer : quality / ai.usage
Detection   : 每章平均 token / cost 报表；预算触顶事件计数
```

### R-14 Quality infinite repair loop

```text
Probability : M
Impact      : H（永不收敛，且可能反复改写同一字段）

Evidence
  · 计划循环为 Generate → Evaluate → Repair → Verify →（失败重试）
  · V3 的 settings_check 已有"允许数据层修补"的自愈逻辑，但没有次数上限概念
  · M11 的经验显示修复会分批次反复执行（m11_batch04 / m11_batch05 / micro_wave / p15o）

Mitigation
  · RepairContract.max_attempts（默认 2）+ 超限 → needs_author
  · issue_id 稳定（同一问题不新增 issue）
  · 每次修复产生 lineage（issue → plan → diff → verify）
  · 修复只允许动 allow_change_fields

Owner Layer : quality.repair
Detection   : 修复轮次直方图；同一 issue 重复出现次数告警
```

### R-15 Writer overwrite（V4-01：对象改为 Blueprint 节点）

```text
Probability : M
Impact      : H（丢失作者已接受的内容，不可接受）

Evidence
  · V3 当前没有正文编辑能力（WriterDraftService 只有 create / list / get / sync-facts，无 update / PATCH）
  · 一旦加入 AI 改写（无论是正文还是 Blueprint 节点），最自然的实现就是 in-place 覆盖 → 直接触发该风险
  · writer.py 已明确"AI 永远拿不到 StoryState 写入口"，说明团队对此敏感
  · V4-01 决策 C：canonical creative artifact 改为 StoryBlueprint，因此本风险的主要载体
    从"正文"变为"作者已接受 Blueprint 节点"（ADR-011）

Mitigation
  · append-only Blueprint 节点 revision；AI 结果默认 status = proposed
  · 作者 accept 后才成为 canonical；旧 revision 永久可读
  · 原则 1.8（AI 修改绝不静默覆盖作者文本）

Owner Layer : application.services.writer
Detection   : 修订历史完整性测试（每次写入产生新 revision，旧节点内容不变）
```

### R-16 Export contamination

```text
Probability : H（已经发生 = NR-002 / NR-003 / NR-004）
Impact      : H（交付物可信度）

Evidence
  · 导出包含与当前作品无关的 V2 分区（NR-002）
  · Markdown 角色行带机器枚举 (player)/(npc)，分区标题中英混排（NR-003）
  · 导出面板正文显示 export_id（NR-004）
  · export_package.serialize_export() 直接把 manifest.export_id 写进 markdown

Mitigation
  · V4_EXPORT_SPEC.md §2（ExportPlan.excluded）+ §4（DeliveryValidator）
  · 内部 metadata 与用户可见正文分离（§3.1）
  · 文本扫描测试（无 export_id / player / npc / sqlite）

Owner Layer : services.export
Detection   : 导出物文本扫描 + 跨作品数据检查（自动化）
```

### R-17 Schema version drift

```text
Probability : M
Impact      : M（旧数据读不了，或静默补齐导致语义漂移）

Evidence
  · StoryState 已有 schema_version + upgrade_story_state_payload（storage.py）
  · Blueprint / Outline / Planning 各自有版本字段，语义不统一
  · 计划引入 revision 后，若不复用既有机制会产生第二套版本语义

Mitigation
  · V4_ARCHITECTURE.md CHALLENGE-06：暂不引入 migrations/，先统一 revision + schema_version 语义
  · 读取时显式升级并记录（不静默丢弃字段）
  · 每个 artifact 带 format_version

Owner Layer : core.revision / persistence
Detection   : 旧数据读取回归（既有存档必须仍可打开）
```

### R-18 MCP contract instability

```text
Probability : M
Impact      : M（Agent 依赖的 tool / resource 形状变化会破坏外部集成）

Evidence
  · MCP 尚不存在，但 V4 计划把它作为对外接口
  · 现有 REST 契约形状复杂（envelope 不统一，部分端点直接返回 DTO）
  · V3 期间已发生过契约演进（NF-005 journey 投影统一）

Mitigation
  · Result Envelope 统一（V4_MCP_SPEC.md §5）
  · tool / resource 版本化（contract version + deprecated 标注）
  · 先内部稳定（V4-01…V4-07），再暴露 MCP（V4-08）

Owner Layer : interfaces.mcp
Detection   : MCP contract golden test（schema 快照 + 变更评审）
```

---

## 2. 优先级（按「必须先解决」排序）

```text
第一优先级（阻塞 V4 成立）
  R-11 Historical data leakage   → 不解决则所有 ownership 承诺失效（V4-01 / V4-07）
  R-16 Export contamination      → 作者可感知的交付质量（V4-07）
  R-15 Writer overwrite          → 一旦有正文编辑就必须先有 revision（V4-06）
  R-09 / R-10 并发与幂等          → Agent 接入前置条件（V4-06 / V4-08）

第二优先级（影响质量与成本）
  R-03 / R-04 / R-05 LLM 边界与 prompt 治理（V4-02）
  R-08 Canon drift / R-14 修复循环（V4-05）
  R-06 Context explosion / R-13 成本（V4-03 / V4-05）

第三优先级（防过度设计）
  R-02 Over-abstraction
  R-12 Plugin 权限（V4-09）
  R-18 MCP 契约稳定性（V4-08）
```

---

## 3. 检测手段汇总（可机械执行的部分）

```text
源码守卫（pytest）
  · 业务模块不 import provider HTTP client
  · api 路由不 import domain 模块
  · domain 不 import fastapi / mcp / docx 序列化器
  · legacy 模块不被新写路径 import

数据守卫
  · 跨作品导出检查（novel A 导出不含 novel B 的 id）
  · 删除 memory 目录后事实不变
  · 写入必须产生新 revision（append-only）

契约守卫
  · MCP tool 实现行数 ≤ 3
  · Result Envelope schema golden test
  · Quality Gate 映射表与实际注册一致

成本守卫
  · 每章 token / cost 报表
  · 修复轮次直方图
  · Budget 触顶事件计数
```
