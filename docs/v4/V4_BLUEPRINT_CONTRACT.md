# NovelForge V4 — Story Blueprint Contract（schema SSOT）

> 状态：**V4-04 实施完成**
> 定位：本文件是 **Story Blueprint schema 的唯一 SSOT**（任务书 §58）。
> 代码实现：`src/novelforge/blueprint/`（模型 / repository / validation / lifecycle）
> 与 `src/novelforge/generation/`（版本化生成 contract）。

---

## 1. Blueprint 是什么 / 不是什么

```text
是：canonical creative artifact（可保存 / 可引用 / 可追踪 / 可局部重生成 / 可验证 / 可修订）
是：一组可独立 revision 的节点图（ADR-016）
不是：正文（prose 非 V4 Core，ADR-011）
不是：Memory（Memory 是派生层，ADR-014）
不是：事实（生成结果是 proposal，ADR-017）
```

---

## 2. 节点类型（12 类）

```text
premise         前提：premise / central_conflict / protagonist_goal / stakes /
                dramatic_question / story_promise / genre / tone / constraints
theme           主题：theme / statement / counter_theme / motifs
world           世界约束：rules / locations / factions / resources /
                technology_or_magic / social_constraints / conflict_sources /
                story_relevant_history
character       人物（是什么）：name / role / kind / goal / motivation / need / fear /
                misbelief / strength / flaw / conflict_source / relationships /
                story_function / constraints
character_arc   人物弧（如何变化）：character_id / start_state / internal_conflict /
                external_pressure / key_turns / midpoint_change / crisis /
                climax_choice / end_state / linked_chapters / linked_scenes
story_arc       故事弧：initial_state / inciting_incident / progressive_complications /
                major_turns / midpoint / crisis / climax / resolution
structural_unit 结构单元：unit_type(act|volume|arc) / title / goal / conflict / turn /
                outcome / child_units
chapter         Chapter Card：title / goal / pov / characters / location / conflict /
                turn / outcome / hook / setup / payoff / state_change_intent
scene           Scene Card：chapter_id / pov / location / time / scene_purpose /
                character_goals / conflict / escalation / turn / outcome /
                information_reveal / character_change / relationship_change /
                setup / payoff / state_transition_intent / next_hook / story_function
causal_link     因果链：source_node / target_node / relation / reason
setup           伏笔：content / expected_payoff / status(open|partially_paid|paid|abandoned)
payoff          回收：resolves_setup_ids / result / status(planned|paid|abandoned)
```

枚举：

```text
story_function  = advance_plot | reveal_information | escalate_conflict |
                  character_change | relationship_change | setup | payoff |
                  decision | reversal | transition
causal relation = causes | enables | blocks | reveals | motivates | pays_off
transition kind = knowledge | relationship | resource | location | promise |
                  identity | flag | progression
```

payload 全部是 **strict pydantic 模型**（`extra="forbid"`）：模型输出多一个字段就会被拒绝。

---

## 3. 节点结构

```json
{
  "node_id": "ch_001",
  "novel_id": "novel_alpha",
  "node_type": "chapter",
  "parent_id": "act_01",
  "revision": 2,
  "parent_revision": 1,
  "status": "proposed",
  "sequence": 1,
  "source_ids": ["canon:FACT_x@3", "story_state:character.hero@2"],
  "context_digest": "…",
  "created_at": "…",
  "updated_at": "…",
  "generation_contract": "blueprint.chapter.v1",
  "generation_contract_version": 1,
  "provenance": {"context_blocks": ["required.canon", "…"], "model": "…",
                 "provider": "…", "parent_revision": 1, "preserve": []},
  "quality_status": "unevaluated",
  "schema_version": 1,
  "payload": { }
}
```

`quality_status` 字段已存在但 **V4-04 不实现 Quality Loop**（属 V4-05）。

---

## 4. 节点 ID 规则（系统分配，模型不得自造）

```text
premise / theme / world / story_arc         → 单例固定 id
character                                   → char_<NN>_<slug|digest6>
character_arc                               → arc_<character_id>
structural_unit                             → act_NN / vol_NN / arc_NN（按 unit_type）
chapter                                     → ch_NNN
scene                                       → sc_<chapter_index:03d>_<sequence:02d>
causal_link                                 → cl_NNN（确定性生成）
setup / payoff                              → setup_NNN / payoff_NNN（确定性生成）
```

名称 → slug 时：ASCII 名取 slug；纯非 ASCII 名（如中文）取 `sha1(name)[:6]`，
避免所有角色都退化成同一个占位 id（有测试）。

---

## 5. 生成结果的地位

```text
status 默认 "proposed"；允许 proposed → draft → accepted → superseded（accepted 不可回退）
accept() 必须显式调用（V4-04 只提供 API；UI/Agent 审批属后续阶段）
AI 重新生成不覆盖 accepted 历史：它产生新 revision（旧 revision 永久可读）
state_transition_intent 只是**计划**；不写 StoryState / Canon（ADR-017）
```

---

## 6. 存储（canonical store）

```text
novel/authoring/story_engine/blueprint/<novel_id>/
├── index.json        current revision / children 顺序 / idempotency 记录 / schema_version
├── MANIFEST.json     novel_id / node_count / updated_at / schema_version
└── nodes/<node_id>/r%06d.json    每个 revision 一个文件（append-only）
```

路径解析只能经 `persistence.paths`（`blueprint_dir` / `blueprint_node_dir` /
`blueprint_node_path` / `blueprint_index_path` / `blueprint_manifest_path`）。

`BlueprintRepository` 方法：

```text
get_current / get_revision / require_current / list_revisions
list_children（按 sequence 排序）/ list_by_type / all_nodes / index_snapshot
save_revision(node, expected_revision, idempotency_key)   ← 唯一写入口
set_status(node_id, status, expected_revision)
find_by_idempotency(key)
```

---

## 7. Revision 与幂等

```text
· 每个节点 append-only：新写入 = 新 revision（≥1），parent_revision 指向上一版
· 写入携带 expected_revision；不匹配 → RevisionConflict（core.revision）
· 生成在调用模型**之前**先检查 expected_revision（避免跑完才发现冲突）
· idempotency_key 命中时直接返回既有 revision，且不再调用模型
```

---

## 8. 校验（V4-04 范围）

```text
schema      payload 严格模型（额外字段 / 缺失必填 / 非法枚举 → 拒绝，不落盘）
structural  parent 类型白名单 / 必填 parent / sequence 正数与唯一
ownership   节点与父节点必须同属一个 novel_id（跨作品写 → 拒绝）
reference   character_id / chapter_id / characters[] / causal 端点 / resolves_setup_ids
            / transition intent 的 kind 与 scope
graph       全图校验：ownership / 重复 id / 父子 / sequence / 未回收 setup 列表
```

**不做**（V4-05）：人物一致性评分、节奏评估、语义重复检测、因果评估、repair planner。

---

## 9. 生成 Contract（版本化）

```text
blueprint.premise.v1 / blueprint.theme.v1 / blueprint.world.v1 /
blueprint.character.v1 / blueprint.character_arc.v1 / blueprint.story_arc.v1 /
blueprint.structural_unit.v1 / blueprint.chapter.v1 / blueprint.scene.v1
+ 确定性（非 LLM）：causal_link / setup / payoff（由 Scene/Chapter Card 推导）
```

每个 contract 声明：输入要求、输出 schema（= 上表 payload 模型）、context policy、
model capability、generation mode（structured_json）、timeout、retry、structured output policy。

上下文政策（§44–§45）示例：

| 任务 | capability | token budget | 上下文类型 |
| --- | --- | --- | --- |
| premise | creative + structured_output | 700 | canon, story_state |
| world | creative + structured_output | 900 | canon, story_state |
| character | creative + structured_output | 700 | canon |
| character_arc | creative + structured_output | 800 | canon, episodic |
| story_arc | creative + structured_output + large_context | 1400 | canon, story_state, episodic |
| chapter | creative + structured_output | 900 | canon, story_state, episodic |
| scene | creative + structured_output | 800 | canon, story_state, episodic |

---

## 10. 与既有 IR 的关系（ADAPT，不重写）

```text
ChapterSemanticIR   Scene/Chapter Card 的字段与其一致（purpose/goal/conflict/turn/outcome/
                    setup/payoff），可作为编译目标
StoryPlanningIR     StoryArc / StructuralUnit 与 Spine/Arc/Chapter 概念对齐
OutlinePackage      Chapter Card 可编译成 OutlineItem（不新建平行大纲模型）
ContentPack         世界/人物提案仍可过既有 schema 校验
Canon / StoryState  只作为上下文（经 Memory），生成结果不写入
```

