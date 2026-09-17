# V4-04 STRUCTURED STORY BLUEPRINT GENERATION RESULT

> 阶段：**V4-04 Structured Story Blueprint Generation**
> 分支：`v4-04-blueprint-generation`（integration branch，单 Agent 顺序执行）
> 基线：`v4-03-memory-integration`（V4-03 PASS，1074 passed / 7 skipped）
> 结论：**V4-04 = PASS**

---

## 1. Existing generation inventory

完整盘点见 [`V4_04_GENERATION_INVENTORY.md`](V4_04_GENERATION_INVENTORY.md)。要点：

| 模块 | 结论 |
| --- | --- |
| `story_engine/creative.py` | ADAPT：结构契约保留；`TONE_RULES` / `SELLING_POINT_TEMPLATES` 等转 compatibility；LLM 路径迁 Gateway |
| `story_engine/settings_gen.py` | ADAPT：schema / id / 校验保留；`RULE_TEMPLATES` / `content_pack_draft` 固定骨架转 compatibility |
| `story_engine/outline_forge.py` | ADAPT：四级大纲模型与门禁 KEEP；`NARRATIVE_BEATS` / 「（第 N 次）」标题兜底由新路径取代 |
| `story_builder/ai_recommendations.py` | ADAPT：「AI 只能补充」的合并校验 KEEP；provider 迁 Gateway |
| `story_engine/journey.py` | REPLACE_BY_LLM（后续阶段）：三原型与固定场景文本登记 compatibility |
| `ChapterSemanticIR` / `StoryPlanningIR` / `ContentPack` / `OutlinePackage` | **ADAPT/KEEP**：Blueprint 作为它们的更高层聚合，不重新发明字段 |

---

## 2. Blueprint contract

新增 [`V4_BLUEPRINT_CONTRACT.md`](V4_BLUEPRINT_CONTRACT.md) 作为 **schema SSOT**：
节点类型（12 类）、payload 字段、ID 规则、节点结构、存储布局、revision/幂等、
校验范围、生成 contract、与既有 IR 的 ADAPT 关系。

---

## 3. Blueprint node model

```text
node_id / novel_id / node_type / parent_id / revision / parent_revision /
status / sequence / source_ids / context_digest / created_at / updated_at /
generation_contract(+version) / provenance / quality_status / schema_version / payload
```

* 12 类 payload 全部是 **strict pydantic 模型**（多字段/缺字段/非法枚举都会被拒绝）。
* `status` 默认 `"proposed"`（ADR-017）；`quality_status` 预留（V4-05）。
* 节点 ID 由**系统**分配（§47）：`char_NN_<slug|digest6>` / `arc_<char>` / `act_NN` /
  `ch_NNN` / `sc_NNN_NN` / `setup_NNN` / `cl_NNN`；纯中文名用 6 位摘要，避免占位 id 冲突。

---

## 4. Repository / persistence

```text
novel/authoring/story_engine/blueprint/<novel_id>/
├── index.json          current revision / children 顺序 / idempotency / schema_version
├── MANIFEST.json       novel_id / node_count / updated_at / schema_version
└── nodes/<node_id>/r%06d.json      append-only revision
```

* 路径经 `persistence.paths`（新增 `blueprint_dir` / `blueprint_node_dir` /
  `blueprint_node_path` / `blueprint_index_path` / `blueprint_manifest_path`）。
* `BlueprintRepository`：`get_current` / `get_revision` / `list_revisions` /
  `list_children`（按 sequence）/ `list_by_type` / `all_nodes` / `save_revision`
  （唯一写入口）/ `set_status` / `find_by_idempotency`。
* 原子写（tmp + replace）；索引与 manifest 每次写入同步。

---

## 5. Premise generation

`blueprint.premise.v1`（capability: creative + structured_output；budget 700）→
`PremisePayload`：premise / central_conflict / protagonist_goal / stakes /
dramatic_question / story_promise / genre / tone / constraints。

Theme 单独建模（`blueprint.theme.v1` → `ThemePayload`），不重复塞进 premise（§17）。

## 6. World generation

`blueprint.world.v1` → `WorldPayload`（rules / locations / factions / resources /
technology_or_magic / social_constraints / conflict_sources / story_relevant_history）。
prompt 明确要求「只生成对故事有用的约束，不写百科、不发明与 Canon 冲突的事实」；
结果默认 proposal，**不升级 Canon**（§20）。

## 7. Character generation

`blueprint.character.v1` → `CharacterPayload`（identity/role/kind/goal/motivation/need/
fear/misbelief/strength/flaw/conflict_source/relationships/story_function/constraints）。
prompt 明确**禁止固定原型文案**（§18）。

## 8. Character arc generation

Character 与 CharacterArc 分离：`blueprint.character_arc.v1` → `CharacterArcPayload`
（start_state / internal_conflict / external_pressure / key_turns / midpoint_change /
crisis / climax_choice / end_state / linked_chapters / linked_scenes）。
父节点必须是 character；`character_id` 由系统覆盖写入（模型不得自造）。

## 9. Story arc

`blueprint.story_arc.v1` → `StoryArcPayload`（initial_state / inciting_incident /
progressive_complications / major_turns / midpoint / crisis / climax / resolution），
与 `StoryPlanningIR` 的 Spine/Arc 概念对齐（ADAPT）。

## 10. Structural units

不硬编码「必须三幕 / 四卷」：`blueprint.structural_unit.v1` → `StructuralUnitPayload`
（`unit_type = act | volume | arc` + goal / conflict / turn / outcome / child_units）。
层级由任务输入决定；ID 由系统按类型分配（`act_01` / `vol_01` / `arc_01`）。

## 11. Chapter cards

`blueprint.chapter.v1` → `ChapterCardPayload`（title / goal / pov / characters /
location / conflict / turn / outcome / hook / setup / payoff / state_change_intent）。
标题是**创意字段**，prompt 要求「必须是内容，不得使用字段标签或模板占位」；
不再使用「第 N 章：模板正文」生成新内容（§23）。

## 12. Scene cards

`blueprint.scene.v1` → `SceneCardPayload`（scene_purpose / character_goals / conflict /
escalation / turn / outcome / information_reveal / character_change /
relationship_change / setup / payoff / state_transition_intent / next_hook /
story_function）。prompt 强制回答「如果删掉这一场，故事损失什么？」（§24）；
`story_function` 是结构化枚举（10 个取值，可多选，§25）——V4-05 的直接依据。
**不生成正文**（§55）。

## 13. Causal links

`generation/tasks/links.py` 从 Scene/Chapter Card **确定性**推导 `CausalLink`
（relation ∈ causes / enables / blocks / reveals / motivates / pays_off），
规则写死且可解释（上一场 outcome → causes；下一场 payoff → pays_off；
上一场 setup → enables）。无需额外 LLM 调用，天然可重建。

## 14. Setup / payoff

同样确定性：把 setup/payoff 文本提升为结构化 `Setup` / `Payoff` 节点
（`status` ∈ open / partially_paid / paid / abandoned），并按 payoff 绑定情况
回填 setup 状态；`validate_graph` 输出 `unpaid_setups` 列表供 V4-05 使用（§27）。

## 15. Planned state transitions

Chapter / Scene Card 可声明 `state_change_intent` / `state_transition_intent`
（kind ∈ knowledge / relationship / resource / location / promise / identity / flag /
progression）。校验只检查 `kind` 与 scope 归属，**不写 StoryState**（§28）——
promotion 属于未来 execution 层（ADR-017）。

## 16. LLM Gateway integration

```text
generation → novelforge.ai（LLMGateway）唯一入口
每个任务一个版本化 contract（blueprint.<task>.v1，含 output_model = Blueprint payload）
模型只填内容；id / parent / revision / provenance 由系统决定
provider 不可用 → GenerationUnavailableError（明确失败，不生成硬编码创意）
```

## 17. Context Builder integration

```text
spec.context_request() → ContextRequest（每个任务声明 context policy / token budget /
capability，§44–§45）→ ContextBuilder.build() → ContextBundle
   ↓ 渲染为 contract 的 {task_input} / {context}
LLMGateway
```

* generation **不**直接查 Canon / StoryState / 索引（守卫测试断言 generation 包内
  不出现 `CanonRepository` / `StoryStateRepository` / `MemoryIndex` 等标识符）。
* ContextBundle 的 digest 与 block 顺序进入节点 `context_digest` 与 `provenance`；
  上下文来源进入 `source_ids`。
* 有测试断言：Canon 文本与作者偏好确实出现在送给模型的 prompt 里。

## 18. Legacy provider migration

四处鸭子类型 provider（`creative` / `settings_gen` / `ai_recommendations` /
`outline_forge`）不再各自拼 HTTP：

```text
ai/legacy_support.GatewayStructuredProvider
  实现完全相同的 generate_structured(...) -> (meta, draft) 形状
  内部经 LLMGateway（contract = legacy.<stage>.v1，可带 output_model 做 schema 校验）
default_structured_provider()：只有配置了 enabled provider 才返回它，否则 None
  → 未配置模型时保持 V3 确定性行为（行为不变，测试全绿）
```

四个模块在函数内惰性 import `novelforge.ai`（边界守卫白名单，只减不增）；
`legacy/manifest.py` 登记 `story_engine.creative.settings_generation` 与移除条件。

## 19. Hardcoded creativity cleanup

按 §41 逐项分类（详见 inventory §3）：业务约束（`GENRE_KEYWORDS`、schema/enum、
`FIELD_LABEL_BLACKLIST`）→ **KEEP**；创意表与固定标题模板 → **REPLACE_BY_LLM /
compatibility**，并登记移除条件。

**本阶段的范围决定（如实说明）**：没有删除 V3 的确定性创意表，因为它们是
未配置模型时 V3 产品面（UI + 浏览器门禁 + 900+ 测试）的默认行为；
删除属于 V4-05/V4-10 的产品决策。V4-04 的实质进展是：① 新路径（blueprint +
generation）成为结构化创作路径；② 四处 legacy provider 已收编到 Gateway；
③ 每张表都有 removal condition。

## 20. Revision / idempotency

```text
append-only revision（nodes/<node_id>/r%06d.json）
expected_revision 不符 → RevisionConflict（core.revision），且**在调用模型之前**检查
idempotency_key 命中 → 直接返回既有 revision，不再次调用模型
局部重生成（regenerate）只动目标节点；其他节点字节不变（有测试）
```

## 21. Validation

```text
schema     严格 payload（额外字段 / 缺失必填 / 非法枚举 → 拒绝且不落盘）
structural parent 类型白名单 / 必填 parent / sequence 正数与唯一
ownership  节点与父节点同属一个 novel_id（跨作品写 → 拒绝）
reference  character_id / chapter_id / characters[] / causal 端点 / resolves_setup_ids /
           transition kind 与 scope
graph      ownership / 重复 id / 父子 / sequence / unpaid_setups
```

## 22. Ownership isolation

* repository 按 `novel_id` 解析路径；跨作品写入抛 `BlueprintOwnershipError`。
* `validate_graph(novel_id=…)` 报告 `OWNERSHIP_MISMATCH`。
* `tests/v4/isolation/test_generation_boundaries.py`：两本作品各自生成节点，
  互相读不到对方节点，且不能用 A 的 repository 保存 B 的节点。

## 23. Module boundary verification

新增守卫（`tests/v4/isolation/test_generation_boundaries.py` + `test_module_boundaries.py`）：

```text
generation 不 import api / ai.providers / fastapi / mcp / HTTP client
generation 只依赖 ai / memory / blueprint / core / persistence / domain
generation 不自行做 memory retrieval（禁用标识符检查）
generation / blueprint 不自行拼 artifact 路径（AST 字符串字面量检查）
domain / ai / memory / blueprint / core / persistence 不得 import generation
blueprint 不得 import ai / generation / memory
api 层不得直接 import generation（必须经 application.services）
```

---

## 24. Tests

```text
pytest -q                          1141 passed / 7 skipped / 0 failed（394s）
tests/generation/**                  57 passed（全部离线、零真实模型）
tests/v4/**                          60 passed（含 10 个 generation/blueprint 守卫）
tests/memory/**                      61 passed（未受影响）
tests/ai/**                          90 passed（新增 Gateway 桥后仍全绿）
python scripts/validate_project.py   PASS
tests/test_v2_frozen_guard.py        6 passed
tests/test_v3_frozen_guard.py        6 passed
```

tests/generation 覆盖（§49 清单）：

```text
contracts        payload 严格性 / 节点字段 / id 规则 / 状态流转 / roundtrip
repository       save/read/revisions/children/idempotency/状态流转/ownership/manifest
service          结果 envelope / evidence / revision conflict（模型调用前检查）/
                 局部重生成 / 幂等（不重复调用模型）/ accept / 跨作品拒绝 / 未知任务
pipeline         golden 蓝图（premise→…→6 节点→links）：parent-child / sequence /
                 story_function / state intent / causal / setup-payoff / 全图校验 /
                 provenance / 重建等价
validation       非法 payload 不落盘 / 未知角色引用 / scene 父缺失 / 无父节点 /
                 跨作品 ownership / parent 类型不符
context          context digest 进节点 / Canon + 偏好进入 prompt / Canon 未被写 /
                 上下文确定性 / capability 声明
legacy migration 四模块无 HTTP / 使用 Gateway 桥 / 鸭子接口形状 / output_model 校验 /
                 默认 None（未配置模型）/ 注入可用
```

### 24.1 测试数量变化解释（V4-03 → V4-04）

| 类别 | 变化 | 原因 |
| --- | --- | --- |
| `tests/generation/**` | **+57** | 本阶段新增（contracts / repository / service / pipeline / validation / context / legacy migration） |
| `tests/v4/isolation/**` | **+10** | 新增 generation/blueprint 边界守卫（6）+ 跨作品隔离（1）+ module boundary 扩展（2）+ 路由守卫 |
| 既有测试 | ±0 | legacy 模块默认行为未变（未配置 provider → 确定性路径），全部原测试继续通过 |

---

## 25. Frozen boundary

```text
novelforge-product-v3-final tag        未移动（annotated tag f214647 → f02ca8c）
novel/authoring frozen digest          未变化（guard PASS）
frozen Repair Contract / REPAIR_GATE_V1 未修改
StoryState / Canon 语义                 未修改（生成只读上下文；有 fingerprint 测试）
story_engine/memory.py                 未改名（V4-03 决定）
```

---

## 26. Files created

```text
src/novelforge/blueprint/{__init__,contracts,errors,lifecycle,repository,validation}.py
src/novelforge/generation/{__init__,contracts,errors,service}.py
src/novelforge/generation/tasks/{__init__,premise,world,characters,story,chapter,scene,links}.py
src/novelforge/application/services/blueprint.py
tests/generation/{gen_support,test_blueprint_contracts,test_blueprint_repository,
                  test_generation_service,test_generation_pipeline,
                  test_generation_validation,test_context_integration,
                  test_generation_legacy_migration}.py
tests/v4/isolation/test_generation_boundaries.py
docs/v4/V4_BLUEPRINT_CONTRACT.md
docs/v4/V4_04_GENERATION_INVENTORY.md
docs/v4/V4_04_BLUEPRINT_GENERATION_REPORT.md（本文件）
docs/v4/adr/ADR-016-story-blueprint-is-a-revisioned-node-graph.md
docs/v4/adr/ADR-017-generated-content-is-proposal-until-promoted.md
```

## 27. Files modified

```text
src/novelforge/persistence/paths.py           新增 blueprint 路径解析（唯一来源）
src/novelforge/persistence/__init__.py        导出上述函数
src/novelforge/ai/legacy_support.py           GatewayStructuredProvider + default factory
src/novelforge/ai/__init__.py                 导出上述 Public Contract
src/novelforge/story_engine/creative.py       默认 provider → Gateway 桥
src/novelforge/story_engine/settings_gen.py   同上
src/novelforge/story_engine/outline_forge.py  同上
src/novelforge/story_builder/ai_recommendations.py 同上
src/novelforge/legacy/manifest.py             登记 V3 规则式生成器（移除条件）
src/novelforge/application/services/__init__.py 导出 BlueprintService
tests/v4/isolation/test_module_boundaries.py  扩展 generation 边界与 allowlist
docs/v4/{V4_MODULE_BOUNDARIES,V4_BRANCH_STRATEGY,V4_ARCHITECTURE,V4_MIGRATION_PLAN,
          V4_DELETION_PLAN,V4_MEMORY_ARCHITECTURE,V4_QUALITY_CONTRACT}.md
docs/v4/adr/README.md
```

## 28. Files deleted

```text
无（V3 规则式生成器按 §41/§42 范围决定转为 compatibility，并登记移除条件）。
```

---

## 29. Git branches

```text
v4-04-blueprint-generation（integration branch，单 Agent 顺序执行）
```

## 30. Git commits

```text
（1）docs(v4): freeze story blueprint generation contracts
（2）feat(blueprint): add node model and canonical repository
（3）feat(generation): add contracts, tasks and blueprint service
（4）refactor(ai): route legacy structured providers through gateway
（5）test(generation): add blueprint generation coverage
（6）test(v4): enforce generation module boundaries
（7）docs(v4): record v4-04 result
```

---

## 31. Remaining risks

| 风险 | 状态 | 说明 |
| --- | --- | --- |
| V3 确定性创意表仍在（creative / settings_gen / outline_forge / journey） | 已登记 | 未配置模型时的默认行为；删除需 V4-05/V4-10 + 作者确认（`legacy/manifest.py` 有 removal condition） |
| Blueprint 尚无 Quality 结论 | 设计如此 | `quality_status` 默认 `unevaluated`；V4-05 消费 |
| 生成质量取决于模型与 prompt | 已知 | V4-04 只保证结构/引用/所有权正确；语义质量由 V4-05 门禁与 repair 处理 |
| 逐级生成调用次数较多（13 次/样例） | 已知 | 换取可控性与可修订性；V4-05 可基于节点做局部修复而不是全量重生成 |
| `structural_unit` / `chapter` 存在默认父节点推断 | 已知 | 只在唯一层级时推断（unit→story_arc，chapter→第一个 unit）；多层结构必须显式传 parent_id |
| 派生序列（setup/payoff）使用 1000+ 偏移 | 已文档化 | 避免与叙事子节点 sequence 冲突；导出/UI 需按 node_type 分组展示 |
| Context Builder 的 blueprint 上下文源尚未填充 | 计划内 | `blueprint_node` 已是合法 source_type；V4-05/V4-06 会把 accepted 节点写入 Memory 供后续检索 |
| MCP / REST / UI 尚未暴露生成能力 | 设计如此（§53–§54） | 只提供 `application.services.BlueprintService`；V4-08/V4-10 消费 |
| `journey.py` 三原型文本 | 未动（§41 登记） | 属 Scene/正文边界，V4-06 之后处理 |

---

## 32. V4-05 readiness

```text
[x] Story Blueprint canonical store（节点 + revision + index + manifest）
[x] 12 类节点、parent-child、sequence、schema_version
[x] 逐级生成（premise → … → scene）+ 确定性 links（causal / setup / payoff）
[x] 局部重生成 + expected_revision（模型调用前检查）+ idempotency_key
[x] 结构 / 引用 / ownership 校验；未回收 setup 列表可被 Quality 直接消费
[x] 所有生成经 LLMGateway；四处 legacy provider 已收编；无 HTTP 直连
[x] 每个任务经 ContextBuilder；provenance / context_digest / source_ids 齐全
[x] 生成结果是 proposal（不写 Canon / StoryState），accept() 提供显式接受点
[x] 默认测试套件 1141 passed / 7 skipped / 0 failed；frozen guards PASS
```

Quality 可以开始（V4-05）：**Quality Loop**（Q0–Q9 / evaluator / repair planner /
targeted repair / re-evaluate），直接消费 `BlueprintNode` + `unpaid_setups` +
`story_function` + `quality_status`，并按节点 scope 做定向修复。

---

# V4-04 = PASS

