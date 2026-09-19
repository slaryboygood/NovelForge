# Module: `generation` — 逐级结构化生成

```text
Module purpose     Story Blueprint 的逐级生成（AI 产出 = proposal，等待作者接受）
Authoritative owner src/novelforge/generation/{service,tasks,rewrite}.py
Owned skills       generate-premise / generate-theme / generate-world / generate-character /
                   generate-character-arc / generate-story-arc / generate-structural-unit /
                   generate-chapter-plan / generate-scene-plan
Truth ownership    写 Blueprint（planning truth）；不写 Canon / StoryState；不写质量结论
Public interfaces  UI「创造 / 世界 / 人物 / 故事 / 场景」；REST POST /studio/generate；
                   Application BlueprintService.generate_task / regenerate；MCP 9 个 generate_* tool
Dependencies       ai（LLM Gateway，唯一模型入口）、memory（ContextBuilder 唯一上下文入口）、
                   blueprint（repository / validation）、core（ids / revision）
Forbidden          绕过 Gateway 直连 provider、自己拼 prompt、把生成结果写进 Canon / StoryState、
                   让模型自造 node_id / chapter_id / character_id
Related modules    blueprint（输出目标）、quality（评估 proposal）、editor（作者改动）、
                   agent（AgentGenerationPort）
```

## 任务表（唯一 SSOT：`generation/service.py::default_registry`）

| task | node_type | LLM contract | 需要父节点 | 关键 task_input |
| --- | --- | --- | --- | --- |
| `premise` | premise | `blueprint.premise.v1` | 否 | `task`（可选指令） |
| `theme` | theme | `blueprint.theme.v1` | 否 | `task` |
| `world` | world | `blueprint.world.v1` | 否（可挂 premise） | `task` |
| `character` | character | `blueprint.character.v1` | 否（可挂 premise / world） | `index`（兄弟序号，决定 `char_<NN>_…`） |
| `character_arc` | character_arc | `blueprint.character_arc.v1` | **是**（character） | 父节点决定 `character_id` |
| `story_arc` | story_arc | `blueprint.story_arc.v1` | 否（可挂 premise） | `task` |
| `structural_unit` | structural_unit | `blueprint.structural_unit.v1` | **是** | `unit_type`, `index` |
| `chapter` | chapter | `blueprint.chapter.v1` | **是** | `index`（`ch_<index>`） |
| `scene` | scene | `blueprint.scene.v1` | **是**（chapter） | `sequence`（`sc_<chapter_index>_<seq>`） |

## 不变量

```text
ONE_NODE_PER_CALL：不做"整本大纲一次生成"（DEFAULT_PIPELINE 逐级）
PROPOSAL_ONLY：新节点 status=proposed、quality_status=unevaluated；接受由 Editor 做
SYSTEM_ASSIGNED_ID：node_id / character_id / chapter_id 由系统分配，模型输出里的 id 被覆盖
CONTEXT_VIA_BUILDER：generation 不自己查 Canon / StoryState，一律经 ContextBuilder
EXPECTED_REVISION_BEFORE_MODEL：revision 冲突在调用模型之前就报错（0 model call）
```

## 当前边界（见 `docs/v4/V4_0_1_SKILL_GAPS.md`）

```text
GAP-001  POST /studio/generate 的 dry_run 字段未实现 —— 不要依赖它做"零副作用预览"
GAP-002  BlueprintService.build_links（setup / payoff / causal_link）没有 UI / REST / MCP 入口
          → 生成场景后 setup / payoff 可能为空，Q5 / Q7 / Q9 相关 issue 属预期
默认不启用任何 provider → 未配置模型时返回 GENERATION_UNAVAILABLE（422），不静默降级
```

补充（V4.0.1 dogfood 实测，仍属当前边界，不要当作新接口）：

```text
· 422 GENERATION_UNAVAILABLE 这个 code 同时被复用于"模型输出未通过 schema 校验"
  （message 写作"...生成失败：结构化输出未通过 schema 校验"）。它**不一定**表示
  provider 没配置：provider / stub 返回缺必填字段的内容时也会得到同一个 code。
· 给单例类型（theme / world / story_arc）传 parent_id（例如 parent_id="premise"）时，
  生成的节点 sequence=0；Q0 会把"非根节点 sequence=0"判为 SEQUENCE_INVALID（major，
  repairable=false），之后对该父节点再生成还可能直接 422 BLUEPRINT_VALIDATION_FAILED。
  当前安全做法是让这些单例节点留在根（不要传 parent_id），除非产品侧修正 sequence 赋值。
  （详见 docs/v4/V4_0_1_SKILL_DOGFOOD_REPORT.md；属产品问题，本目录不修 runtime。）
```
