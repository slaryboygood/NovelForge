# V4-05 QUALITY CLOSED LOOP RESULT

> 阶段：**V4-05 Quality Closed Loop & Targeted Repair**
> 分支：`v4-05-quality-loop`（integration branch，单 Agent 顺序执行）
> 基线：`v4-04-blueprint-generation`（V4-04 PASS，1141 passed / 7 skipped / 0 failed）
> 结论：**V4-05 = PASS**

---

## 1. Existing quality inventory

完整盘点见 [`V4_05_QUALITY_INVENTORY.md`](V4_05_QUALITY_INVENTORY.md)。要点：

| 既有能力 | 处置 |
| --- | --- |
| `blueprint/validation.py`（V4-04 schema / parent / 引用 / ownership / sequence） | **ADAPT（直接复用）** → Q0 + Q1 |
| `blueprint/repository.py`（revision / index / manifest / idempotency 一致性） | **ADAPT（直接复用）** → Q1 |
| `canon/validator.py` / `canon/graph.py` / `canon/prose.py` | **ADAPT** → Q2 / Q3 的 deterministic 层（经 memory 检索，不直连数据库） |
| `chapter_ir/validator.py` / `evidence.py` / `state.py` / `function_policy.py` / `verifier.py` | **ADAPT** → Q0 / Q1 / Q2 / Q6 / Q7 的形态来源 |
| `planning/{validator,graph_validator,spine_analysis,health,narrative_analysis,conflict_escalation}.py` | **ADAPT** → Q4 / Q5 / Q7 的判定语义 |
| `outline_forge.py`（标题唯一性 / 字段标签黑名单 / 来源一致性） | **ADAPT** → Q6 / Q8 |
| `story_builder/v3_projection.py`（导出就绪度 6 步） | **ADAPT** → Q9 的语义来源 |
| `story_engine/settings_check.py` / `story_builder/inspector.py` | **ADAPT** → Q1 / 修复诊断参考 |
| `canon/mutation.py`、`planning/health.py` | **KEEP**（不是产品 Gate：自测与三态健康度） |
| `story_engine/repair.py`（M11 frozen）、`historical_ir.py`、`reconstruction.py` | **FROZEN / COMPATIBILITY**（不进入 V4 质量路径，不复用实现） |
| 只服务已删除历史数据的 validator / report 入口 | **DELETE（登记）**：V4-01 已随数据删除 |

结论：**没有重写任何成熟的 deterministic 校验**；V4-05 新建的是"统一对象 + Gate 装配 + 闭环"。

---

## 2. Public Quality contracts

`src/novelforge/quality/__init__.py`（精简导出，§6 / §79）：

```text
QualityService / quality_service      唯一评估入口（deterministic first）
QualityScope / QualityEvidence        作用域与一等证据
QualityIssue / QualityGateResult      结构化问题与逐 gate 结果
QualityReport / QualityPolicy         report 与生产策略
QualityStatus / SEVERITIES / decide_status
EvaluatorRegistry / EvaluatorSpec     注册表（不硬编码 if gate == ...）
CODE_REGISTRY / code_spec / codes_for_gate / is_registered
QualityStore                          quality truth
RepairPlanner / RepairExecutor / RepairVerifier / RepairBlastRadius /
RepairContract / RepairStep / RepairPlan / RepairResult / VerificationResult
QualityError 家族
```

不导出 evaluator 内部实现（守卫测试断言）。

---

## 3. Issue code registry

```text
src/novelforge/quality/codes.py  →  ISSUE_CODES / CODE_REGISTRY（48 个 code）
分布：Q0=4  Q1=8  Q2=2  Q3=4  Q4=3  Q5=6  Q6=5  Q7=5  Q8=4  Q9=7
每个 code 固定声明：gate / severity / repairable / preserve / allow_change / description
```

**LLM 不能自由生成 issue code**：`make_issue` 对未注册 code 抛 `QualityPolicyError`；
critic 的候选 code 只有通过 `make_issue` 才能变成 issue（有测试）。

---

## 4. Evidence model

```text
QualityEvidence = evidence_id / kind / source_ids / node_ids / revision /
                  excerpt / comparison / metric / explanation
```

* `QualityIssue.__post_init__` **拒绝没有 evidence 的 issue**（不允许无证据判定）。
* evidence 记录 revision；**issue identity 与 revision 无关**（同一问题跨 revision 保持
  同一 `issue_id`）——否则 verifier 会把"没修好"误判成"已解决 + 新问题"。
* provenance 保存 `request_id / contract_id / contract_version / context_digest / model /
  provider / source_ids`，**不保存完整 prompt**（沿用 V4-02 §60）。

---

## 5. Quality policies

```text
required_gates / blocking_severities / max_repair_rounds / enable_llm_evaluators /
cost_limit / token_limit / stop_on_blocker / gate_thresholds / max_issues_per_gate
```

默认值：`required_gates = Q0/Q1/Q2/Q3/Q5/Q6/Q7/Q8`、
`blocking_severities = (blocker, major)`、`max_repair_rounds = 3`、
`enable_llm_evaluators = False`、`stop_on_blocker = True`。
生产策略只来自 policy，evaluator 不自行解释 severity。

---

## 6. Q0 Schema

```text
ADAPT blueprint.validate_node（schema / parent 类型 / 引用完整性 / transition intent）
+ validate_graph 的 sequence 部分（SEQUENCE_DUPLICATE / SEQUENCE_INVALID）
映射：SCHEMA_INVALID / REFERENCE_BROKEN / PARENT_TYPE_INVALID / SEQUENCE_INVALID
Q0 不承担 Q1 的 ownership / provenance 判定（映射表不含这些 code，有测试）
```

## 7. Q1 Integrity

```text
ownership（foreign node → OWNERSHIP_MISMATCH, blocker）
duplicate node id / revision 链连续性 / parent_revision 一致性
index ↔ 节点文件一致性（INDEX_INCONSISTENT）
provenance（source_ids + generation_contract 缺失 → PROVENANCE_INVALID）
必需节点类型（MISSING_REQUIRED_NODE）
idempotency 记录一致性（IDEMPOTENCY_INCONSISTENT）
```

## 8. Q2 Canon

```text
deterministic：从 MemoryService 检索 Canon 事实（evaluator 不直接扫数据库），
               识别「显式禁制 / 死亡状态」并对照蓝图文本 →
               CANON_CONTRADICTION / CANON_CHARACTER_IDENTITY_CONFLICT（blocker）
llm_assisted：quality.canon.critic.v1（capability=critic，默认关闭）；
              候选 code 必须来自 registry；只提 candidate，scope / preserve 由 Planner 决定
```

## 9. Q3 Continuity

```text
时间单调（第 N 天倒退）、地点跳转缺少过渡、信息在揭示前被使用（knowledge leak）、
关系变化缺少结构支撑 → CONTINUITY_TIME_CONFLICT / LOCATION_CONFLICT /
KNOWLEDGE_LEAK / RELATIONSHIP_CONFLICT
scope 内 ≥2 场才判定（单场不猜）
```

## 10. Q4 Character

```text
关键决定缺少动机 / 压力 → CHARACTER_MOTIVATION_GAP
人物弧在当前场景集合中没有推进证据 → CHARACTER_ARC_STALL
关键转折在场景 outcome/turn/character_change 中找不到支撑 →
CHARACTER_ARC_UNSUPPORTED_TURN
不使用"像不像好角色"这类模糊 prompt；evidence 必须指向结构字段
```

## 11. Q5 Causality

```text
因果图（CausalLink 边集）上的结构化检测：
  CAUSAL_GAP（无入边且无 escalation+conflict）
  ORPHAN_EVENT（无入边无出边且无 setup/payoff）
  CIRCULAR_DEPENDENCY（环；不可自动修）
  UNSUPPORTED_PAYOFF（resolves_setup_ids 为空）
  UNMOTIVATED_DECISION（decision 场景且此前没有目标）
  DEAD_BRANCH（setup 既无 payoff 绑定也不在后续场景出现）
```

## 12. Q6 Semantic

```text
normalized 精确 + token Jaccard + char n-gram Jaccard（_internal/similarity.py）
  SCENE_SEMANTIC_REPETITION（相邻场景 ≥2 个结构字段重复）
  CHAPTER_GOAL_REPETITION / TITLE_SEMANTIC_REPETITION / CONFLICT_PATTERN_REPETITION
  HOLLOW_NODE（结构字段总长度不足）
**不使用 LocalHashEmbedding**（守卫测试断言模块内不出现 embedding 标识符）
```

## 13. Q7 Narrative

```text
SCENE_NO_NARRATIVE_FUNCTION（story_function 为空 / 只有 transition /
                            声称 advance_plot 但 outcome 为空）
PACING_STAGNATION（连续 ≥3 场没有升级功能与 escalation 文本）
CLIMAX_UNPREPARED / RESOLUTION_INCOMPLETE（依赖 StoryArc 结构）
SETUP_PAYOFF_DISTRIBUTION_SKEW（图级，identity 与请求 scope 无关）
```

## 14. Q8 Blueprint Style

```text
BLUEPRINT_VAGUE_CONTENT（"关系进一步发展"这类不可执行表达）
BLUEPRINT_FIELD_LABEL_TEXT（字段标签 / 内部枚举进入作者可见文本）
BLUEPRINT_PLACEHOLDER_TEXT（未命名 / 待定 / TODO）
BLUEPRINT_TITLE_TOO_SIMILAR（措辞模板化，含"加后缀"型重复）
只评 Blueprint clarity / specificity，不评小说文笔（§1）
```

## 15. Q9 Delivery Readiness

```text
DELIVERY_MISSING_REQUIRED_NODE / DELIVERY_MISSING_CHAPTER_OR_SCENE /
DELIVERY_UNPAID_SETUP / DELIVERY_ORPHAN_NODE / DELIVERY_PLACEHOLDER /
DELIVERY_CROSS_NOVEL_CONTAMINATION / DELIVERY_UNRESOLVED_BLOCKER（来自 prior_issues）
对象是**整个 Blueprint**（不是本次请求的 scope）；不实现导出（V4-07）
```

## 16. Deterministic / hybrid / LLM matrix

见 [`V4_QUALITY_CONTRACT.md`](V4_QUALITY_CONTRACT.md) §3.3（冻结矩阵）。摘要：

```text
Q0 deterministic   Q1 deterministic   Q2 hybrid（+ critic，默认关闭）
Q3 hybrid          Q4 hybrid          Q5 hybrid
Q6 hybrid（无 embedding）  Q7 deterministic evidence（+ 可选 LLM）
Q8 hybrid          Q9 mostly deterministic
LLM 只在 policy 显式开启时运行；capability = critic；全部经 novelforge.ai
```

执行顺序：deterministic first；上游 blocker 时下游 gate 标记 `skipped`（可配置）。

---

## 17. Quality Store

```text
novel/authoring/story_engine/quality/<novel_id>/
├── reports/<report_id>.json
├── issues/<issue_id>.json
├── repair_history/<plan_id>.json
└── MANIFEST.json
路径全部经 persistence.paths（quality_dir / quality_*_dir / quality_manifest_path）
```

Quality Store 是 **quality truth**，不是 story truth：删除它不影响 Canon / StoryState /
Blueprint（ADR-020）。

## 18. Blueprint quality projection

```text
QualityService.project_quality_status(node_ids=...) → {node_id: status}
blocker → blocked；major → failed；minor/info → passed_with_issues；无 issue → passed
evaluator 只读：节点 quality_status 保持 unevaluated 直到 Application 层显式投影
（有测试断言评估后节点仍为 unevaluated）
```

## 19. Repair Contract

见 [`V4_REPAIR_CONTRACT.md`](V4_REPAIR_CONTRACT.md)。`RepairContract` 固定
`issue_ids / scope / node_ids / preserve / allow_change / must_resolve / constraints /
max_scope / strategy`；`preserve` 包含 `node_id` / `source_ids` / `canon` 与结构 identity
字段（scene→chapter_id、chapter→characters、character_arc→character_id、
causal_link→source/target、payoff→resolves_setup_ids）。

## 20. Repair Planner

```text
合并同一节点的 issue → 一个 step（must_resolve 保留全部 issue id）
最小 scope：只碰问题节点；结构节点（setup / payoff / causal_link）回落到宿主场景
无法定位唯一最小节点（多节点 scope）→ needs_human_review（不猜）
allow_change 必须是真实 payload 字段；preserve ∩ allow_change 交集 → conflict（上报）
不可自动修的 code（ownership / 因果环）→ needs_human_review（strict → RepairNotAllowedError）
plan_id 确定性（同一输入 → 同一 plan_id → 稳定幂等键）
```

## 21. Blast Radius

```text
changed（direct） + dependent（child_of_changed / same_chapter_scene /
causal_endpoint_changed / resolves_changed_setup / attached_to_changed_node /
arc_links_changed_node） + gates（baseline Q0/Q1/Q9 ∪ issue gate ∪ 节点类型 gate ∪ policy required）
```

## 22. Targeted Repair

```text
repair → generation.regenerate(task, node_id, expected_revision, preserve, task_input, key)
repair 不实现自己的 LLM 生成；generation 不反向依赖 quality（守卫测试）
新 revision 落盘后逐字段比对 preserve → 违反即 REPAIR_PRESERVE_VIOLATION（blocked step）
失败不吞：异常进入 blocked_steps（error / message / fields）
```

## 23. Verification

```text
重新评估 blast radius scope + （blast gates ∪ policy.required_gates）
→ original / resolved / remaining / new（new = 与 before_report 全量比较）
→ status ∈ resolved / partial / unresolved / regression
→ issue 状态同步回 Quality Store（resolved / open），但不修改 Blueprint
```

## 24. Closed Loop

```text
ReviewService.evaluate_and_repair()：
evaluate → plan → execute → verify →（passed | repaired | needs_human_review）
QualityLoopService 是唯一闭环实现；ReviewService 只是入口（§56）
needs_human_review 场景：轮次耗尽 / contract 冲突 / 无法定位 scope / 预算耗尽 /
                        本轮没有解决任何 issue
```

## 25. Revision / idempotency

```text
· 任何修复都产生新 revision（append-only）；accepted 节点不被静默覆盖
  （accepted r2 → repair 产生 proposed r3，r2 仍为 accepted 且永久可读）
· expected_revision 冲突在**任何模型调用之前**发现（预检全部步骤）→ RevisionConflict
· 同一 idempotency_key 重放 → idempotent_replay（不产生第二个 revision，不再调用模型）
```

## 26. Usage / budget

```text
usage = {evaluation, repair, verification, total} × {input_tokens, output_tokens, cost, calls}
Q2 critic 调用记录 usage（context.record_usage）；repair 汇总每次 generation 的 usage
policy.token_limit / cost_limit 触顶 → 停止自动 repair → needs_human_review（有测试）
estimated_cost 只在 provider 配置了价格时非 null（不猜价格）
```

## 27. Ownership isolation

```text
QualityService 必须显式 novel_id；scope.novel_id 不符 → QualityScopeError
Planner 拒绝跨作品 issue；Executor 拒绝跨作品 plan；Verifier 拒绝跨作品 report
两本同名同 node_id 的作品：A 的评估不读 B 的 blueprint，B 的 quality store 仍为空（有测试）
```

## 28. Legacy validator migration

```text
ADAPT   blueprint.validation / repository（Q0 + Q1）、canon + planning + chapter_ir 语义
        （Q2–Q7 的判定与 evidence 形态）、outline_forge 标题与字段标签门禁（Q6/Q8）、
        v3_projection 交付就绪度语义（Q9）
KEEP    canon/mutation.py（fault injection 自测）、planning/health.py（三态健康度）
FROZEN  story_engine/repair.py（M11）、historical_ir / reconstruction（不进质量路径）
```

未删除任何 V3 模块；删除条件已随 V4-01 的资产删除登记（属后续阶段）。

## 29. Module boundary verification

`tests/v4/isolation/test_quality_boundaries.py`（9 个永久守卫）：

```text
quality 不 import api / application / ai.providers / fastapi / mcp / HTTP client
quality 不自行拼 artifact 路径（AST 字符串字面量检查：novel/ workspace/ authoring/）
quality 只经 persistence.paths 取路径
evaluator / service 不依赖 generation（allowlist = quality/repair/executor.py）
domain / ai / memory / blueprint / generation / core / persistence 不得 import quality
generation 绝不 import quality / repair
quality 不写 Canon / StoryState（标识符守卫）
Public Contract 精简（不导出 evaluator 内部模块）
quality 顶层不 import generation / api / application
```

---

## 30. Tests

```text
pytest -q                                1272 passed / 7 skipped / 0 failed（443s）
tests/quality/**                          122 passed（含 repair/ 34 个）
tests/v4/**                                69 passed（含 9 个 quality 边界守卫）
tests/generation/**                        57 passed（未受影响）
tests/memory/**                            61 passed（未受影响）
tests/ai/**                                90 passed（未受影响）
python scripts/validate_project.py         PASS
tests/test_v2_frozen_guard.py              PASS
tests/test_v3_frozen_guard.py              PASS（12 passed 合计）
```

### 30.1 测试数量变化解释（V4-04 → V4-05）

| 类别 | 变化 | 原因 |
| --- | --- | --- |
| `tests/quality/**` | **+122** | 本阶段新增：contracts/registry（13）、Q0–Q9 gate（52）、service（7）、repair planner/blast/executor/verifier/loop（34）、fixture（不计入） |
| `tests/v4/isolation/**` | **+9** | 新增 quality 模块边界守卫 |
| 既有测试 | ±0 | 未修改任何既有模块的外部行为（persistence 仅新增函数；application 仅新增服务） |

§63 golden closed loop 覆盖：semantic repetition、no narrative function、causal gap、
unmotivated decision、motivation gap、orphan event、vague content、knowledge leak、
canon contradiction（9 个 issue 一次闭环全部解决，report → passed）。

---

## 31. Frozen boundary

```text
novelforge-product-v3-final tag          未移动（`git tag` 仍只有该 tag）
novel/authoring frozen digest            未变化（V2/V3 frozen guard PASS）
frozen Repair Contract / REPAIR_GATE_V1  未修改、未被引用（V4 repair 是独立实现）
story_engine/repair.py                   未修改（CHALLENGE-03 边界保持）
Canon / StoryState 语义                   未修改：evaluator 只读，repair 只写 Blueprint proposal
quality 路径                              新增（novel/authoring/story_engine/quality/**，gitignored 运行数据）
```

---

## 32. Files created

```text
src/novelforge/quality/__init__.py
src/novelforge/quality/{contracts,codes,errors,registry,aggregation,service,store}.py
src/novelforge/quality/_internal/{__init__,similarity}.py
src/novelforge/quality/evaluators/{__init__,base,schema_gate,integrity_gate,canon_gate,
                                   continuity_gate,character_gate,causality_gate,
                                   semantic_gate,narrative_gate,style_gate,delivery_gate}.py
src/novelforge/quality/repair/{__init__,contracts,blast_radius,planner,executor,verifier}.py
src/novelforge/application/services/review.py
tests/quality/{conftest,quality_support,test_quality_contracts,test_quality_registry,
               test_schema_gate,test_integrity_gate,test_canon_gate,test_continuity_gate,
               test_character_gate,test_causality_gate,test_semantic_gate,
               test_narrative_gate,test_style_gate,test_delivery_gate,
               test_quality_service}.py
tests/quality/repair/{test_planner,test_blast_radius,test_executor,test_verifier,test_loop}.py
tests/v4/isolation/test_quality_boundaries.py
docs/v4/V4_05_QUALITY_INVENTORY.md
docs/v4/V4_REPAIR_CONTRACT.md
docs/v4/V4_05_QUALITY_CLOSED_LOOP_REPORT.md（本文件）
docs/v4/adr/ADR-018-quality-is-gate-based-not-score-based.md
docs/v4/adr/ADR-019-repair-is-minimal-scope-and-revisioned.md
docs/v4/adr/ADR-020-quality-evidence-is-separate-from-story-truth.md
```

## 33. Files modified

```text
src/novelforge/persistence/paths.py           新增 quality_dir / quality_*_dir / quality_manifest_path
                                               + ARTIFACT_KINDS += "quality"
src/novelforge/persistence/__init__.py        导出上述函数
src/novelforge/application/services/__init__.py  导出 ReviewService / QualityLoopService / RepairOutcome
docs/v4/V4_QUALITY_CONTRACT.md                冻结状态 + §3.3 矩阵 + code registry + evidence + store + policy
docs/v4/V4_BLUEPRINT_CONTRACT.md              §3.1 quality_status 投影语义
docs/v4/V4_MODULE_BOUNDARIES.md               §3.11 / §3.12 + 模块表 + 依赖矩阵 + 明文禁令 + 守卫清单
docs/v4/V4_ARCHITECTURE.md                    §1.3 / §1.10 / §4.1 / §5（Quality 边界）
docs/v4/V4_ARCHITECTURE_RISKS.md              R-13 / R-14 关闭说明
docs/v4/V4_BRANCH_STRATEGY.md                 V4-05 分支行 + 分支声明
docs/v4/adr/README.md                         ADR-018/019/020 登记
```

## 34. Files deleted

```text
无（未删除任何 V3 模块；legacy creative 表按 §70 保持 compatibility）
```

---

## 35. Git branches

```text
v4-05-quality-loop（integration branch，单 Agent 顺序执行）
未创建 v4-05a…f 子分支（§3：单 Agent 时使用一个 integration branch 即可）
```

## 36. Git commits

```text
（1）docs(v4): freeze quality and repair contracts
（2）feat(quality): add quality issue evidence and gate registry
（3）feat(quality): add deterministic quality gates
（4）feat(quality): add semantic, narrative and style evaluators
（5）feat(repair): add repair planning and blast radius
（6）feat(repair): add targeted repair and verification
（7）feat(application): add quality loop service
（8）test(quality): add quality and repair coverage
（9）test(v4): enforce quality module boundaries
（10）docs(v4): record v4-05 result
```

---

## 37. Remaining risks

| 风险 | 状态 | 说明 |
| --- | --- | --- |
| Q3 / Q6 / Q7 / Q8 只有 deterministic 层，没有 critic evaluator | 已知（契约已留出） | `enable_llm_evaluators` 与 `EvaluatorSpec.kind=hybrid` 已就位；扩展属后续阶段，不阻塞 V4-06 |
| 少数问题无法自动修复（未回收 setup / 因果环 / ownership） | 设计如此 | 明确进入 `needs_human_review`，不做含糊的半修复 |
| `quality_status` 投影尚未写入节点 | 计划内 | 本阶段只提供投影函数；写回属 Blueprint Editor / lifecycle（V4-06） |
| deterministic 相似度阈值（0.6 / 0.75 / 0.8）是固定值 | 已知 | 进 policy 的 `gate_thresholds` 已有字段，标定属后续调优 |
| Q9 只是 readiness，不是交付门禁 | 设计如此 | 真正的 package / DOCX / nfpack 与 export gate 属 V4-07 |
| 评估成本在启用 critic 后上升 | 已缓解 | deterministic first + stop_on_blocker + revision 缓存 + 预算闸门 |

---

## 38. V4-06 readiness

```text
[x] Quality 是独立模块；repair 是明确子模块；Public Contract 精简
[x] Q0–Q9 全部实现并注册；issue code / severity / status 固定语义
[x] deterministic first；hybrid 只在需要时用 LLM；全部 LLM 经 Gateway；上下文经 ContextBuilder
[x] evidence 是一等对象；provenance 完整；不保存 prompt 原文
[x] revision-aware 增量评估；ownership 隔离；质量结果独立存储
[x] RepairContract / preserve / allow_change / minimal scope / blast radius / dry_run
[x] expected_revision 冲突 0 次模型调用；幂等键不产生第二个 revision
[x] 修复产生新 revision；accepted 节点不被静默覆盖；preserve 违反被上报
[x] verifier 重新评估受影响 gate，报告 resolved / remaining / new / regression
[x] max_repair_rounds + needs_human_review + usage / budget
[x] Evaluate → Plan → Repair → Verify 闭环可用；计划外节点 byte-for-byte 不变
[x] 默认套件 1272 passed / 7 skipped / 0 failed；validate_project PASS；frozen guards PASS
```

V4-06（Blueprint Editor）可以直接消费：

```text
ReviewService.evaluate / list_issues / plan_repair(dry_run) / repair_issue / verify_repair
QualityReport + QualityIssue（含 evidence / repair_contract）
RepairPlan（改哪些节点 / 允许改什么 / 复核哪些 gate / 预计多少次模型调用）
VerificationResult（before/after revision + resolved/remaining/new）
```

---

# V4-05 = PASS
