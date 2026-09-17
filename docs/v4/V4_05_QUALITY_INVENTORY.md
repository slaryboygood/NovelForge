# V4-05 — Existing Quality Inventory

> 阶段：**V4-05 Quality Closed Loop & Targeted Repair**
> 目的：在写任何新 Evaluator 之前，把 V3 / V4 现有质量能力盘清楚（任务书 §5、§69）。
> 原则：**成熟 deterministic 校验优先 ADAPT，不重写。**

---

## 1. 现有 validator / finding 总表

| Existing Module | Current Check | Input | Output Shape | Deterministic? | V4 Action | Target Gate |
| --- | --- | --- | --- | --- | --- | --- |
| `story_engine/settings_check.py` | 内容包可运行性：起点地点 / 行动可达 / 事件可触发 / 成长与伏笔引用 | ContentPack | `CheckFinding(code/severity/message/hint/target)` + `SettingsCheckReport` | 是 | **ADAPT** → Q1（内容包完整性）；保留原实现，由 adapter 转 `QualityIssue` | Q1 |
| `story_engine/canon/validator.py` | Canon 引用必须真的支持被声明的事实 | CanonFact + source refs | `SourceRefFinding` / `SourceRefReport` | 是 | **ADAPT** → Q2（deterministic 层） | Q2 |
| `story_engine/canon/graph.py` | Canon 依赖图：时序 / 因果校验 | CanonGraph | verdict + issues | 是 | **ADAPT** → Q3（deterministic 层） | Q3 |
| `story_engine/canon/prose.py` | writer-visible 叙事完整性（C12 blind spots） | Canon 事实 | `ProseFinding` / `AuditProseReport` | 是 | **ADAPT** → Q2/Q3（writer-visible 字段校验） | Q2 / Q3 |
| `story_engine/canon/mutation.py` | fault injection / mutation test（防线的自测） | 合成变更 | `MutationSuiteReport` | 是 | **KEEP**（属测试基础设施，不是产品 Gate） | — |
| `story_engine/chapter_ir/validator.py` | 章节 IR 四层合并校验（结构 + evidence + typed state + writer-visible） | ChapterSemanticIR | `IRReport` | 是 | **ADAPT** → Q0/Q1（IR 形态的 Schema/Integrity） | Q0 / Q1 |
| `story_engine/chapter_ir/evidence.py` | Writer-visible 字段必须由 IR 事实支撑 | IR | `EvidenceFinding` / `EvidenceReport` | 是 | **ADAPT** → Q2（evidence 支撑） | Q2 |
| `story_engine/chapter_ir/state.py` | Typed State Registry 校验 | IR | `StateFinding` | 是 | **ADAPT** → Q1 | Q1 |
| `story_engine/chapter_ir/function_policy.py` | 章节功能决定 required / optional / N/A 字段 | IR | `FunctionFinding` | 是 | **ADAPT** → Q7（功能完整性） | Q7 |
| `story_engine/chapter_ir/verifier.py` | 语义验证（抓 schema 过但语义错的 IR）；无 LLM 时 Null | IR + 可选 LLM verdict | `Verdict`（AGREE/DISAGREE/AMBIGUOUS） | 混合 | **ADAPT** → Q6/Q7 的 hybrid 层 | Q6 / Q7 |
| `story_engine/chapter_ir/semantic_judge.py` | LLM 语义裁判（optional，ambiguous only） | IR | `JudgeVerdict` | LLM（可选） | **ADAPT** → Q6 hybrid 的 critic 接入点 | Q6 |
| `story_engine/planning/validator.py` | Planning IR 结构 / 语义校验 | StoryPlanningIR | findings | 是 | **ADAPT** → Q0/Q5 | Q0 / Q5 |
| `story_engine/planning/graph_validator.py` | 图级 + 跨图一致性 | Planning graphs | findings | 是 | **ADAPT** → Q5（因果/依赖） | Q5 |
| `story_engine/planning/spine_analysis.py` | Spine DAG 硬门 + requirement closure + coverage | StorySpine | findings | 是 | **ADAPT** → Q5 | Q5 |
| `story_engine/planning/health.py` | 长线规划健康度（三态，不给假精确总分） | Planning IR | `PlanningHealthReport` | 是 | **ADAPT** → Q7（结构健康） | Q7 |
| `story_engine/planning/chapter_ir_store.py` | Chapter IR artifact 完整性报告 | store | `ChapterIRIntegrityReport` | 是 | **ADAPT** → Q1 | Q1 |
| `story_engine/planning/narrative_analysis.py` | Progression / Information / Foreshadow 长期一致性 | Planning IR | `AnalysisReport` | 是 | **ADAPT** → Q4/Q7 | Q4 / Q7 |
| `story_engine/planning/conflict_escalation.py` | 冲突升级是否有理由与结构支撑 | Planning IR | findings | 是 | **ADAPT** → Q7 | Q7 |
| `story_engine/planning/plot_pressure.py` / `plot_synthesis.py` | 压力 / 机会清单与 PlotNode 合成 | Planning IR | 派生分析 | 是 | **ADAPT** → Q7（pacing 证据来源） | Q7 |
| `story_engine/outline_forge.py` | 章节质量门禁：标题唯一性 / 字段标签黑名单 / 来源一致性（stale） | OutlinePackage | `QualityFinding` / `OutlineQualityReport` | 是 | **ADAPT** → Q8（风格/模板化）与 Q6（标题重复） | Q6 / Q8 |
| `story_builder/v3_projection.py` | 导出就绪度 6 步（内容包 / 起点事实 / 自检 / 大纲确认 / 章纲就绪 / 写作草稿） | 各层投影 | readiness steps | 是 | **ADAPT** → Q9（delivery readiness） | Q9 |
| `story_builder/inspector.py::repair_diagnosis` | 修复中心诊断（settings findings + outline quality → 建议动作） | pack / outline | issues with proposed_action | 是 | **ADAPT** → 作为 V4 Repair 的**诊断来源**（decision 参考），不复制其动作模型 | — |
| `story_engine/repair.py`（M11，frozen） | 570 章历史内容修复（REPAIR_BATCH / contract / gate） | Historical IR | `RepairFinding` | 是 | **FROZEN / 不复用**（任务书 §78：与 V4 Repair 不是同一能力） | — |
| `story_engine/historical_ir.py` / `reconstruction.py` | 历史 IR / 重建（数据已删除） | 历史证据 | reports | 是 | **COMPATIBILITY**（只读源码保留，不进入 V4 质量路径） | — |
| `story_engine/planning/outline_batch.py` | 批量推进的 review findings | session | `BatchReviewFinding` | 是 | **ADAPT** → Q1（批处理完整性，低优先） | Q1 |
| `blueprint/validation.py`（V4-04） | Blueprint 节点 schema / parent / 引用 / ownership / sequence | BlueprintNode | issues + graph report | 是 | **ADAPT（直接复用）** → Q0 + Q1 | Q0 / Q1 |
| `blueprint/repository.py`（V4-04） | revision / index / manifest / idempotency 一致性 | Blueprint store | 结构化返回 | 是 | **ADAPT（直接复用）** → Q1 | Q1 |

---

## 2. 现状问题（为什么需要统一契约）

```text
1. finding 形状不统一：CheckFinding / SourceRefFinding / ProseFinding / EvidenceFinding /
   StateFinding / FunctionFinding / Verdict / QualityFinding / IRReport …
   → UI / 导出 / 修复无法用同一语义消费（V4-00 已记录）
2. severity 语义不一致：error/warning（settings_check）vs severity 字符串（outline_forge）
   vs verdict 三态（verifier）
3. 没有统一 issue code：同一类问题在不同模块里叫不同名字
4. 没有 evidence 一等对象：多数 finding 只有 message 文本
5. 没有 revision / provenance：无法回答「这条判断基于哪个 revision、哪个 evaluator」
6. 修复只有"建议动作"字符串（inspector），没有 preserve / allow_change 契约
```

---

## 3. V4-05 的处置策略

```text
ADAPT（不重写）
  · Q0 / Q1 直接复用 blueprint.validation + repository 一致性检查
  · Q2 / Q3 / Q5 / Q7 复用 canon / planning / chapter_ir 的 deterministic 校验，
    经 adapter 转成统一 QualityIssue
  · Q8 / Q6 复用 outline_forge 的标题与字段标签门禁
  · Q9 复用 v3_projection 的导出就绪度语义（Blueprint 版本）
KEEP（不是产品 Gate）
  · canon/mutation.py（fault injection 自测）、planning/health（三态健康度）
COMPATIBILITY / FROZEN（不进入 V4 质量路径）
  · story_engine/repair.py（M11 frozen）、historical_ir.py、reconstruction.py
DELETE（登记，不在本阶段删除）
  · 只服务已删除历史数据的 validator / 报告入口（V4-01 已随数据删除）
```

---

## 4. 与 V4-04 的边界

```text
V4-04 已实现（generation validation，属于 Q0/Q1 的一部分）：
  strict payload schema / parent 类型 / sequence / ownership / 引用完整性

V4-05 新增（Quality Gate 本体）：
  Q2 Canon / Q3 Continuity / Q4 Character / Q5 Causality / Q6 Semantic /
  Q7 Narrative / Q8 Blueprint Style / Q9 Delivery Readiness
  + EvaluatorRegistry / QualityStore / QualityPolicy / Repair Planner / Executor / Verifier
  + Application 层闭环编排

分界原则：**结构与引用正确 ≠ 故事质量**。V4-04 保证前者，V4-05 负责后者。
```

