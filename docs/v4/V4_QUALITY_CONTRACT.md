# NovelForge V4 — Quality Contract

> 状态：**V4-05 冻结（Quality Closed Loop 已实施）**，V4-00 设计稿 + V4-01 作者决策 + V4-05 实现事实
> 依据：`docs/v4/V4_ARCHITECTURE.md` §1.3、§4、§5；CHALLENGE-08；
>      `ADR-018`（gate-based）/ `ADR-019`（minimal-scope repair）/ `ADR-020`（evidence 独立存储）
> 原则：**Quality 是业务能力，不是测试脚本。**
> 实现位置：`src/novelforge/quality/**`（evaluator）、`src/novelforge/quality/repair/**`、
>          `src/novelforge/application/services/review.py`（闭环编排）

### 0.2 V4-05 实施落地（冻结）

```text
Quality 模块        src/novelforge/quality/{contracts,codes,registry,aggregation,service,store}.py
Evaluator（Q0–Q9）  src/novelforge/quality/evaluators/*.py（10 个 gate 模块 + base）
Repair 子模块       src/novelforge/quality/repair/{contracts,blast_radius,planner,executor,verifier}.py
Application         application.services.ReviewService / QualityLoopService（§55–§56）
Store               novel/authoring/story_engine/quality/<novel_id>/{reports,issues,repair_history}
```

已冻结语义（不得由 evaluator 自行解释）：

```text
severity    info / minor / major / blocker（含义见 §6）
status      unevaluated / evaluating / passed / failed / blocked / needs_human_review
issue code  只能来自 quality/codes.py 的 CODE_REGISTRY（LLM 不得自造 code）
判定        decide_status = Gate + Severity + Policy（绝不使用平均分，ADR-018）
```

详见 `V4_REPAIR_CONTRACT.md`（修复契约 SSOT）与
`V4_05_QUALITY_CLOSED_LOOP_REPORT.md`（本阶段实施结果）。

### 0.0 V4-04 衔接（generation validation vs Quality Gate）

```text
V4-04 已实现的是 **generation validation**（属于 Q0/Q1 的一部分）：
  schema（严格 payload 模型）/ structural（parent 类型、sequence）/
  ownership（同 novel_id）/ reference integrity（character / chapter / causal 端点 /
  setup-payoff 绑定）

V4-05 才实现 Quality Gate 本体：Q2 Canon / Q3 Continuity / Q4 Character / Q5 Causality /
Q6 Semantic Repetition / Q7 Narrative / Q8 Style / Q9 Delivery，
以及 Repair Planner / Targeted Repair / Re-evaluate。

节点上的 `quality_status` 字段已存在（默认 "unevaluated"），V4-05 直接消费它。
```

### 0.1 V4-01 对齐

```text
质量对象 = Story Blueprint 节点（Premise / Character Arc / Scene Card / Setup-Payoff / ...）
不再以"小说正文的文学质量"为质量目标（正文非 V4 Core，ADR-011）。
Q9 Delivery 校验对象 = Story Blueprint 交付物（结构完整性 / 内部字段泄漏 / 跨作品混入 /
                      setup 无 payoff / Scene 缺 purpose-conflict-turn-outcome）。
```

与原文档的差异：原文 §5 的示例 issue 使用 chapter 字段；V4-04 起
质量契约的 scope 以 Blueprint 节点为主（chapter / scene 作为子作用域保留）。

---

## 1. 现状：质量能力已经存在，但是分散的

| 能力 | 位置 | 类型 | 覆盖 |
| --- | --- | --- | --- |
| 内容包可运行性自检 | `story_engine/settings_check.py`（`CheckFinding` / `SettingsCheckReport`） | deterministic | 起点地点 / 行动可达性 / 事件可触发 / 成长与伏笔引用完整性 |
| 结构 + 语义 schema gate | `canon/gate.py`、`canon/schemas.py` | deterministic | planner / LLM 输出的严格 shape |
| Canon 引用校验 | `canon/validator.py`（`SourceReferenceValidator`） | deterministic | 引用必须真的支持被声明的事实 |
| 时序 / 因果校验 | `canon/graph.py` | deterministic | 时间优先级、依赖图 |
| 章节 IR 四层校验 | `chapter_ir/validator.py` + `evidence.py` + `state.py` | deterministic | 结构 / evidence / typed state / writer-visible |
| 语义 verifier | `chapter_ir/verifier.py`（`FixtureSemanticVerifier`，无 LLM 时 `NullVerifier`） | hybrid | 抓「schema 与 validator 都过、但语义错」的 IR |
| prose 完整性防线 | `canon/prose.py` | deterministic | writer-visible 叙事完整性（C11 人工审核暴露的 blind spots） |
| Planning IR 校验 | `planning/validator.py`、`planning/graph_validator.py`、`planning/spine_analysis.py` | deterministic | 图级 + 跨图一致性、DAG 硬门、requirement closure |
| 大纲标题质量 | `outline_forge.py`（`FIELD_LABEL_BLACKLIST`、`ChapterTitleLedger`、来源一致性） | deterministic | 标题唯一性 / 字段标签不得进入标题 |
| 交付就绪度 | `v3_projection`（导出就绪度 6 步） | deterministic | 内容包 / 起点事实 / 自检 / 大纲确认 / 章纲就绪 / 写作草稿 |

**问题不是「没有质量」，而是「没有统一对象」**：以上各处的结论形态互不相同
（`CheckFinding` / `GraphFinding` / `Verdict` / `notes` / `findings`），
UI、导出、修复流程无法用同一套语义消费。

---

## 2. 核心契约对象

```python
class QualityIssue:
    issue_id: str                    # 稳定 id（用于 repair 追踪与去重）
    code: str                        # 例如 CHAPTER_SEMANTIC_REPETITION
    gate: str                        # Q0…Q9
    severity: Severity               # blocker | major | minor | info
    status: QualityStatus            # open | repairing | repaired | verified | accepted_risk | ignored
    scope: Scope                     # novel / volume / arc / chapter / scene / field / delivery
    reason: str                      # 作者可读的一句话
    evidence: list[QualityEvidence]
    repair_contract: RepairContract | None
    detected_at: str
    detected_by: str                 # evaluator id（deterministic / llm / hybrid）
    source_revision: int

class QualityEvidence:
    kind: str                        # fact | state | chapter_ir | outline | text_span | rule
    ref: str                         # 例如 "canon:FACT_00042@3" / "ch_018@2#paragraph_4"
    quote: str = ""                  # 可选原文片段
    rule_id: str = ""                # deterministic 规则编号
    note: str = ""

class Scope:
    novel_id: str
    project_id: str = ""
    revision: int = 0
    chapter_ids: list[str] = []
    scene_ids: list[str] = []
    field_paths: list[str] = []      # 例如 "ch_019.goal"

class Severity:   # blocker / major / minor / info
    ...

class QualityStatus:
    ...

class RepairContract:
    preserve_fields: tuple[str, ...]   # 绝对不可改（canon / characters / source_ids …）
    allow_change_fields: tuple[str, ...]  # 只允许改这些（title / goal / conflict / turn …）
    max_attempts: int = 2
    strategy: str                      # targeted | regenerate_scope | manual_only
    requires_author: bool = False      # 需要作者决定时必须为 True

class QualityResult:
    result_id: str
    scope: Scope
    status: str                        # passed | passed_with_issues | failed | needs_author
    issues: list[QualityIssue]
    gates_run: list[str]
    usage: dict                        # tokens / cost（若涉及 LLM 评估）
    source_revision: int
```

### 2.1 与既有对象的映射

| 既有对象 | V4 处理 |
| --- | --- |
| `settings_check.CheckFinding`（`code` / `severity` / `message` / `hint` / `target`） | 作为 `QualityIssue` 的一种 evaluator 输出适配（保留原语义，不重写） |
| `planning.findings.GraphFinding` | 同上 |
| `chapter_ir.verifier` 的 `Verdict` | 映射为 `QualityIssue.status` + `evidence` |
| `outline_forge` 的标题 findings | 同上 |
| `v3_projection` 的导出就绪度 | 映射为 Q9 的前置检查项 |

**规则：适配而不是重写。** 既有 deterministic 实现在 V4 继续是唯一实现，
`QualityIssue` 只是统一外壳（`AGENTS.md` §20：不得为通过测试削弱规则）。

---

## 3. 质量门 Q0–Q9

> 下表是 **V4-00 的设计意图**；V4-05 的实现事实见 §3.3 冻结矩阵。

| Gate | 名称 | 内容 | 实现类型 | 现有实现来源 |
| --- | --- | --- | --- | --- |
| **Q0** | Schema | 结构是否有效 | **deterministic** | `chapter_ir/schemas.py`、`canon/gate.py`、`planning/schemas.py`、`content.validate_pack_draft` |
| **Q1** | Safety / Integrity | 数据是否损坏（引用完整性、守恒、无孤儿） | **deterministic** | `settings_check`、`canon/validator.py`、`planning/graph_validator.py`、`canon/prose.py` |
| **Q2** | Canon | 是否违反已确认事实 | **deterministic 优先 + LLM 辅助** | `canon/validator.py`（引用支持判定）、`canon/graph.py`；LLM 仅处理「表述不同但语义相同」的边界案例 |
| **Q3** | Continuity | 前后是否矛盾 | **隐藏 deterministic + LLM** | `canon/graph.py`（时序/因果）、`memory.episodic` 对比；LLM 负责跨章语义矛盾 |
| **Q4** | Character | 人物行为是否合理 | **LLM-assisted + deterministic 前置** | deterministic：角色知识/资源/身份约束（`characters.py`、`conditions.py`、`chapter_ir/state.py`）；LLM 判定「有约束但仍不合理」 |
| **Q5** | Causality | 事件是否存在因果 | **deterministic 优先** | `planning/spine_analysis.py`（DAG 硬门 + requirement closure）、`canon/graph.py` |
| **Q6** | Semantic | 重复、模板化、空洞 | **hybrid（LLM 主力）** | deterministic：字面重复 / 唯一性（`ChapterTitleLedger`、digest 去重）；LLM：语义重复判定 |
| **Q7** | Narrative | 节奏、冲突、转折、悬念 | **LLM-assisted** | V3 无实现（`planning/plot_pressure.py` 提供结构化输入） |
| **Q8** | Style | 文风、语言、可读性 | **LLM-assisted + 作者偏好** | V3 无实现；V4 依赖 `memory.author_preferences` |
| **Q9** | Delivery | 最终导出物是否可以交付 | **deterministic 主力 + LLM 辅助** | `v3_projection` 导出就绪度；V4 新增 `DeliveryValidator`（见 `V4_EXPORT_SPEC.md` §4） |

### 3.1 判定「deterministic vs LLM」的原则

```text
能用结构化 identity / 引用 / 守恒 / DAG 判定的  → deterministic（不得交给 LLM 猜）
需要理解「意思是否相同 / 行为是否合理」        → LLM-assisted（必须有 evidence）
需要作者价值判断（是否可接受）                → requires_author = true（不得自动决定）
```

这条原则与既有代码一致：`canon/validator.py` 的注释明确写
「第一层永远是 deterministic：用结构化 identity 判断，不让 LLM 猜『像不像』」。

### 3.2 critic 与 creative 必须分离

```text
生成模型（creative）≠ 评估模型（critic）
```

理由：同一模型评估自己的输出会产生系统性偏差。
V4 的 `ModelRouter` 必须支持为 Q3–Q8 指定独立模型（见 `V4_LLM_CONTRACT.md` §4.3）。

### 3.3 V4-05 冻结矩阵（deterministic / hybrid / LLM）

| Gate | 实现类型（实现事实） | Evaluator | 主要 issue codes | LLM 使用条件 |
| --- | --- | --- | --- | --- |
| **Q0** Schema | **deterministic** | `quality.schema.v1` | `SCHEMA_INVALID` / `REFERENCE_BROKEN` / `PARENT_TYPE_INVALID` / `SEQUENCE_INVALID` | 不用（ADAPT `blueprint.validate_node` + `validate_graph` 的 sequence 部分） |
| **Q1** Integrity | **deterministic** | `quality.integrity.v1` | `OWNERSHIP_MISMATCH` / `DUPLICATE_NODE_ID` / `REVISION_CHAIN_BROKEN` / `PROVENANCE_INVALID` / `MISSING_REQUIRED_NODE` / `INDEX_INCONSISTENT` / `IDEMPOTENCY_INCONSISTENT` | 不用（结构化身份 + 守恒） |
| **Q2** Canon | **hybrid** | `quality.canon.v1`（deterministic）+ `quality.canon.critic.v1`（llm_assisted） | `CANON_CONTRADICTION` / `CANON_CHARACTER_IDENTITY_CONFLICT` | critic 只在 `QualityPolicy.enable_llm_evaluators=True` 时运行；capability = `critic`；critic 只能提 candidate（code 必须在 registry 内） |
| **Q3** Continuity | **hybrid**（当前 deterministic 层已覆盖时间/地点/信息/关系；语义层留给 critic 扩展） | `quality.continuity.v1` | `CONTINUITY_TIME_CONFLICT` / `CONTINUITY_LOCATION_CONFLICT` / `CONTINUITY_KNOWLEDGE_LEAK` / `CONTINUITY_RELATIONSHIP_CONFLICT` | 结构化可判 → deterministic；跨章语义矛盾留给后续 critic 扩展 |
| **Q4** Character | **hybrid**（动机 / 人物弧 / 转折均为结构化字段判定） | `quality.character.v1` | `CHARACTER_MOTIVATION_GAP` / `CHARACTER_ARC_STALL` / `CHARACTER_ARC_UNSUPPORTED_TURN` | 不用模糊 prompt；必须给结构字段 evidence |
| **Q5** Causality | **hybrid**（因果图 deterministic） | `quality.causality.v1` | `CAUSAL_GAP` / `ORPHAN_EVENT` / `CIRCULAR_DEPENDENCY` / `UNSUPPORTED_PAYOFF` / `UNMOTIVATED_DECISION` / `DEAD_BRANCH` | 图的入/出边与 escalation/conflict 可机械判定 |
| **Q6** Semantic | **hybrid**（normalized 精确 + token/char-ngram 相似度）；**不使用 embedding** | `quality.semantic.v1` | `SCENE_SEMANTIC_REPETITION` / `CHAPTER_GOAL_REPETITION` / `TITLE_SEMANTIC_REPETITION` / `CONFLICT_PATTERN_REPETITION` / `HOLLOW_NODE` | 第三层语义比较（critic）属于可选扩展；`LocalHashEmbedding` 不得用于真实质量判定 |
| **Q7** Narrative | **deterministic evidence**（LLM-assisted 为可选扩展） | `quality.narrative.v1` | `SCENE_NO_NARRATIVE_FUNCTION` / `PACING_STAGNATION` / `CLIMAX_UNPREPARED` / `RESOLUTION_INCOMPLETE` / `SETUP_PAYOFF_DISTRIBUTION_SKEW` | 直接消费 `SceneCard.story_function` 与 `StoryArc` 结构字段 |
| **Q8** Style | **hybrid**（当前 deterministic） | `quality.style.v1` | `BLUEPRINT_VAGUE_CONTENT` / `BLUEPRINT_FIELD_LABEL_TEXT` / `BLUEPRINT_PLACEHOLDER_TEXT` / `BLUEPRINT_TITLE_TOO_SIMILAR` | 只评 Blueprint clarity / specificity / consistency，**不评小说文笔** |
| **Q9** Delivery | **mostly deterministic** | `quality.delivery.v1` | `DELIVERY_MISSING_REQUIRED_NODE` / `DELIVERY_UNPAID_SETUP` / `DELIVERY_MISSING_CHAPTER_OR_SCENE` / `DELIVERY_ORPHAN_NODE` / `DELIVERY_PLACEHOLDER` / `DELIVERY_CROSS_NOVEL_CONTAMINATION` / `DELIVERY_UNRESOLVED_BLOCKER` | 只做 delivery readiness，不实现导出（V4-07） |

执行顺序（§42）：**deterministic first**。`QualityPolicy.stop_on_blocker=True` 时，
Q0/Q1 出现 blocker 会跳过下游 gate（标记 `skipped` 并给出原因），不浪费 critic 预算。

### 3.4 Issue Code Registry（§28）

```text
src/novelforge/quality/codes.py  →  CODE_REGISTRY（code → gate / severity / repairable /
                                   preserve / allow_change / description）
LLM 只能选择 registry 中已有的 code；构造未注册 code 的 issue 会被拒绝
（QualityPolicyError），这是 §54「模型不能自由生成 issue code」的机械保证。
```

### 3.5 Evidence 模型（§27）

```text
QualityEvidence = evidence_id / kind / source_ids / node_ids / revision /
                  excerpt / comparison / metric / explanation
```

`kind ∈ {node_field, comparison, metric, graph, retrieval}`；
`comparison` / `metric` 保存结构化对照（相似度、run length、字符数等）——
这些是 **diagnostic**，不参与 PASS / FAIL（ADR-018）。
`revision` 记录 evidence 来自哪个 revision；**issue identity 与 revision 无关**
（同一问题跨 revision 保持同一 `issue_id`，否则 verifier 会把"没修好"误判成
"已解决 + 新问题"）。

### 3.6 Quality Store 与节点投影

```text
novel/authoring/story_engine/quality/<novel_id>/
├── reports/<report_id>.json
├── issues/<issue_id>.json
├── repair_history/<plan_id>.json
└── MANIFEST.json
```

节点上的 `quality_status` 只是该 store 的**投影**（`QualityService.project_quality_status`），
evaluator 不写回节点（ADR-020）。投影值：`passed` / `passed_with_issues` / `failed` / `blocked`。

### 3.7 Quality Policy（§40）

```text
required_gates          哪些 gate 必须评估过才允许判 passed（默认 Q0/Q1/Q2/Q3/Q5/Q6/Q7/Q8）
blocking_severities     哪些 severity 阻止通过（默认 blocker + major）
max_repair_rounds       闭环最大轮次（默认 3）
enable_llm_evaluators   是否允许 hybrid/LLM evaluator 参与（默认 False）
cost_limit / token_limit 预算（触顶 → 停止自动 repair）
stop_on_blocker         上游 blocker 是否跳过下游 gate（默认 True）
gate_thresholds/max_issues_per_gate  可配置阈值与 issue 上限
```

生产策略只来自 policy，不写死在 evaluator 里。

---

## 4. 质量循环（谁发现 / 谁计划 / 谁执行 / 谁验证）

```text
Generate（generation/* → proposal）
   ↓
QualityService.evaluate(scope)          ← **谁发现问题**：QualityService（按 Gate 依次执行）
   ↓
QualityResult
   ├─ passed / passed_with_issues → 交给 persistence 落盘（新 revision）
   └─ failed
        ↓
   RepairPlanner.plan(issues)          ← **谁计划修复**：quality/repair/planner.py
        │  产出 RepairContract（preserve / allow_change / strategy / requires_author）
        ↓
   RepairExecutor.apply(plan)          ← **谁执行**：quality/repair/executor.py
        │  只改 allow_change_fields；scope 外内容不动（禁止整本重生成）
        ↓
   RepairVerifier.verify(result)       ← **谁验证**：quality/repair/verifier.py
        │  重新跑受影响 Gate + 回归跑 Q0–Q3
        ↓
   PASS → 落盘新 revision（记录 repair lineage）
   FAIL → 重试（max_attempts）→ 超限 → needs_author（停，不静默接受）
```

### 4.1 不可违反的循环约束

```text
1. 修复只允许动 RepairContract.allow_change_fields
2. Canon / 人物 id / 已确认世界规则 / source_ids 永远在 preserve_fields
3. 修复不得产生新的 Canon 事实（只能产生 proposal 或修改 planned 层字段）
4. 修复次数有上限（默认 2）；超限必须报告作者
5. 每次修复产生 lineage：issue_id → plan → applied diff → verify result
```

### 4.2 与冻结 M11 Repair 的边界

| | M11 Repair（frozen） | V4 quality/repair（新） |
| --- | --- | --- |
| 对象 | 570 章历史内容修复 | 当前创作的生成质量 |
| Gate | `REPAIR_GATE_V1`（frozen） | Q0–Q9（V4 定义） |
| 输入 | Historical IR + overlay + CDQ | 生成产物 + QualityIssue |
| 写权限 | 已 closeout，只读 | 只写 allow_change_fields |

**两者不得共用实现、不得互相 promote**（`AGENTS.md` §16、`V4_ARCHITECTURE.md` CHALLENGE-03）。

---

## 5. 质量对象示例（NF-003）

```json
{
  "issue_id": "QI_ch019_title_semantic_repeat",
  "code": "CHAPTER_SEMANTIC_REPETITION",
  "gate": "Q6",
  "severity": "major",
  "status": "open",
  "scope": {
    "novel_id": "novel_project",
    "chapter_ids": ["ch_018", "ch_019"],
    "field_paths": ["ch_019.title", "ch_019.goal"]
  },
  "reason": "连续两章承担相同叙事动作，标题仅靠「第 N 次」区分",
  "evidence": [
    {"kind": "outline", "ref": "ch_018@3#title", "quote": "试探：查清核心记录"},
    {"kind": "outline", "ref": "ch_019@3#title", "quote": "试探：查清核心记录（第 2 次）"}
  ],
  "repair_contract": {
    "preserve_fields": ["canon", "characters", "source_ids", "chapter_index"],
    "allow_change_fields": ["title", "goal", "conflict", "turn", "hook"],
    "max_attempts": 2,
    "strategy": "targeted",
    "requires_author": false
  },
  "detected_by": "deterministic:outline_forge.title_ledger + llm:critic.semantic_repetition",
  "source_revision": 3
}
```

这条示例直接对应 V3 的 NF-003 缺陷（`outline_forge.ChapterTitleLedger.allocate()` 的
`f"{base}（第 {count} 次）"` 兜底），并且给出了 V4 的修复边界。

---

## 6. 严重级别与放行规则

| Severity | 含义 | 是否阻止落盘 | 是否阻止导出 |
| --- | --- | --- | --- |
| `blocker` | 破坏事实 / 结构 / 交付完整性（例如 Canon 冲突、缺章、串入其他作品数据） | 是 | 是 |
| `major` | 明显质量问题（例如语义重复、人物行为不合理、字段标签进入正文） | 默认否（记入 revision 的 quality status） | 是（或需作者显式接受） |
| `minor` | 可读性 / 一致性问题 | 否 | 否 |
| `info` | 提示 | 否 | 否 |

放行规则必须写入配置（每部作品可覆盖），并且**不允许 UI 单方面降级 severity**
（防止「为了交付把 blocker 改 minor」）。

> 现状对照：V3 的风险模型是 INFO / WARNING / BLOCKING（`v3_projection`），
> 只有真正阻止继续的问题才升级为 BLOCKING。V4 的 `blocker/major/minor/info` 是它的超集，
> 迁移时保持 WARNING→major、BLOCKING→blocker 的对应关系。

---

## 7. 成本与爆炸防护

```text
每次 evaluate 记录 tokens / cost（QualityResult.usage）
repair 循环受 max_attempts 限制
同一 issue 的重复修复必须命中同一 issue_id（避免无限新增 issue）
达到 Novel / Daily Budget → 停止并上报（不允许「为了通过质量无限重试」）
```

详见 `V4_ARCHITECTURE_RISKS.md` 的 `Quality cost explosion` 与
`Quality infinite repair loop`。

---

## 8. 与 UI / MCP 的关系

```text
UI   → 消费 QualityResult（已存在于 Review workspace 的形态可复用）
MCP  → novelforge.evaluate / list_quality_issues / repair_issue / verify_repair
       （见 V4_MCP_SPEC.md §6）
Export → 交付前必须拿到 status != failed 的 QualityResult（Q9）
```

---

## 9. 验收判据（V4-05）

```text
[x] 存在统一 QualityIssue / QualityEvidence / Scope / RepairContract / QualityReport
[x] 既有 deterministic validator 被 ADAPT 进对应 Gate（Q0 = blueprint.validate_node +
    validate_graph 的 sequence 部分；Memory 检索经 ContextBuilder / MemoryService）
[x] Q0–Q9 每个 Gate 显式声明实现类型与 evidence 形态（§3.3 冻结矩阵）
[x] 修复只动 allow_change 字段（preserve 违反 → REPAIR_PRESERVE_VIOLATION 上报）
[x] 修复次数 / token / cost 受限，超限进入 needs_human_review（有测试）
[x] 每次 evaluate / repair / verify 记录 usage 与 lineage（quality store repair_history）
[x] Q9 给出 delivery readiness 结论（真正的导出与门禁在 V4-07）
[x] M11 frozen repair contract / gate 未被引用或修改（守卫测试 + 边界测试）
[x] quality 模块边界由永久守卫测试机械验证（tests/v4/isolation/test_quality_boundaries.py）
```

## 10. 开放项（不属于 V4-05）

```text
· Q3/Q6/Q7/Q8 的 critic 扩展（LLM-assisted 层）：契约已留出（enable_llm_evaluators），
  当前只有 Q2 具备 critic evaluator；扩展属后续阶段。
· 质量结果的 UI 呈现 / Diff / accept-reject：V4-06 + V4-10。
· 质量结论进入导出交付物：V4-07。
· 让 quality 参与 REST / MCP：V4-08（只经 application.services.ReviewService）。
```
