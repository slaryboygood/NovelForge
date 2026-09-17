# NovelForge 真实长篇小说生产指南

适用版本：Story Engine V2（封版 `story-engine-v2.0` → `fbe99cd`；
该 tag 已归档：historical / archived / not an active Git ref，
完整历史见外部 bundle `NovelForge_pre_V4_full_history.bundle`）
依据：V2 真实小说生产试跑（CH001–CH030 / 123,177 字）
性质：**操作规则**，不是架构计划

---

## 0. 生产模式

```
Engine 提供事实与候选 → 作者选择 → Runtime 推进 → Director 调度
→ Writer 表现 → Validator → 每 10 章人工审读
```

**不是全自动写书。** 引擎决定事实，LLM 只负责表现，作者负责方向与选择。

---

## 1. 如何创建正式小说

```powershell
# 1) 启动（隔离数据根目录，避免污染其他项目）
.\.venv\Scripts\python.exe scripts/start_novelforge_ui.py --port 8000
```

在 UI 里：

1. 打开「世界面板」页签之前，先在顶部填「新小说编号」（如 `real_novel_001`）与内容包，点「新建小说」。
2. 选择「新故事起点」，点「开始构筑」，依次完成十步设定。
3. 完成后点「整合并查看故事蓝图」→「确认故事蓝图」。

命令行等价做法（生产脚本常用）：

```python
client.post("/api/story-builder/novels", json={"novel_id": "real_novel_001",
            "title": "正式小说", "content_pack_id": "real_pack_001"})
```

**规则**：`novel_id` 就是数据分区键；不要复用演示编号（`xianxia_demo` 等）。

---

## 2. NovelProfile / Content Pack 如何准备

数据文件位置：

| 文件 | 路径 |
| --- | --- |
| Novel Profile | `novel/authoring/story_engine/profiles/<novel_id>.json` |
| Content Pack | `novel/config/story_engine/<pack_id>.json` |

Novel Profile 里需要确认的字段：

- `content_pack_id`：指向本小说的内容包。
- `cast` / `factions` / `resource_catalog` / `ability_catalog`：起点世界清单。
- `director_weights`：导演倾向（可选项，留空用默认）。
- `future_plan`：未来阶段目标（**全小说级，不按分支分区**，见第 14 节）。

Content Pack 里需要确认的字段：

- `initial_flags` / `initial_resources` / `initial_locations` / `initial_current_location`
- `initial_characters`（目标 / 欲望 / 恐惧 / 底线）/ `initial_factions` / `initial_plots`
- `actions`（含 requirements / costs / immediate_effects / delayed_effects）
- `events`（含 trigger / scope / once_only / cooldown / consequences）
- `progressions` / `foreshadows` / `autonomous_rules`

**规则**：配置不等于事实。起点清单只是“可以有什么”，是否真的拥有由 StoryState 决定。

---

## 3. 如何初始化 StoryState

StoryState 在第一次 `runtime/tick` 或 `runtime/advance` 时按内容包声明落盘：

```
GET  /api/story-builder/runtime/state?novel_id=real_novel_001&branch_id=main
POST /api/story-builder/runtime/tick?novel_id=real_novel_001
     body: {"expected_revision": 0, "branch_id": "main"}
```

初始化后核对：

- `revision == 0`、`tick == 1`
- `summary.location` 等于内容包声明的起点
- `summary.characters` / `factions` / `plots` 与内容包一致

---

## 4. 如何运行一个章节

一个章节通常包含 **1～3 个 runtime turn**，直到形成完整叙事单位
（setup → decision → consequence → hook）。

每一轮：

```
1) GET  runtime/state  → 读取 revision / tick / 合法候选
2) 选择一个 available 的行动（作者决定，或按生产计划挑选）
3) POST runtime/advance（带 branch_id 与 expected_revision）
4) 检查返回的 effects / world_actions / world_events / plot_transitions / replan
5) 章节结束时把主线事实写回磁盘（advance 已自动保存）
```

**禁止**：跳过 `expected_revision`，或在被阻塞时手工改 StoryState。
如果行动不可用，换一个 available 的行动，或用 `runtime/tick` 推进世界。

---

## 5. 如何选择候选行动

候选来自 `runtime/state` 的 `candidates`：

- `available = true`：可以直接执行。
- `available = false`：附 `code` 与 `reason`（条件 / 成本 / 身份 / 地点 / 知识不足）。

选择原则：

1. 先看主线推进（`main_line` 相关事件与行动）。
2. 再看支线是否长期未动（`plot_transitions` 与支线进度）。
3. 避免连续多轮选同一类别（Director 的 `event_repetition` 会扣分，但作者也要有意识）。
4. 让 NPC 与世界的自主行动有发挥空间：必要时用 `runtime/tick` 让世界先动。

---

## 6. 如何保存章节

> **V4-01 更新**：V4 的 canonical 创作产物是 **Story Blueprint**（故事蓝图 / 大纲），
> 不是小说正文；仓库内旧的正文资产（`novel/final/**`）已由作者判定废弃并删除。
> 本节描述的是 V3 的正文型生产流程，保留作为历史参考。

1. （V3 流程）正文写在隔离目录：`workspace/<novel>/novel/final/chNNN_标题.md`。
2. StoryState 由 `runtime/advance` 自动原子写入，不需要手工保存。
3. 每章结束做一次**重载确认**：

```
GET runtime/state → revision 与刚推进后一致
```

4. 每章记录一份结构化日志（候选、选择、effects、Director、Writer 结果），便于 10 章审读。

---

## 7. 如何创建 branch 实验

```http
POST /api/story-builder/runtime/fork?novel_id=real_novel_001
body: {"source_branch": "main", "target_branch": "branch_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}
```

规则：

- 分支 id 必须是 `main` 或 `branch_` + 32 位十六进制（与既有 Adventure 分支命名一致）。
- fork 只做深拷贝，**不修改源分支**。
- 目标分支已存在时返回 409，不会覆盖。
- fork 之后所有 load / save / revision 校验都用 `branch_id`，例如：

```http
POST /api/story-builder/runtime/advance?novel_id=real_novel_001
body: {"action_id": "...", "branch_id": "branch_aaaa...", "expected_revision": 12}
```

存储位置：`novel/authoring/story_engine/state/<blueprint_id>/vXXXXXX.json`（main）
与 `vXXXXXX_branch_<32hex>.json`（分支）——**物理隔离**。

---

## 8. 如何切回 main

只需在所有 runtime 调用里把 `branch_id` 改回 `main`：

```
GET runtime/state?novel_id=real_novel_001&branch_id=main
```

分支推进不会影响 main 的 revision、tick、关系、资源、知识、支线与延迟后果（已有专项测试覆盖）。

---

## 9. 如何恢复 revision

当前提供两种可用路径（都不新建备份系统）：

1. **分支重放**：从较早状态 fork 出新分支，再按行动序列重放，得到等价事实。
2. **章节记录重放**：每章记录里的 `turns[].action` 就是权威行动序列；
   从初始状态重新推进同一序列即可还原主线（Pilot-03/04 实际用过，30 章全部可还原）。

注意：

- 不要直接编辑 `vXXXXXX.json`。
- 恢复实验一律在测试分支上做，不在 main 上做破坏性操作。

---

## 10. 每 10 章人工审读什么

1. 主线是否仍在推进（有没有被支线冲散）。
2. 三条以上跨 10 章的因果链是否成立（早期事件是否影响后期行为）。
3. 支线是否有堆积或长期失踪（活跃支线建议 ≤3）。
4. 伏笔是否还在生命周期里（open / reinforced / 该回收未回收）。
5. 关系是否跳变或长期不动（对照关系曲线）。
6. NPC 是否仍有独立目标，而不是只在主角需要时出现。
7. 世界事件是否真正影响后续剧情，而不是只留在记录里。
8. Writer 是否出现重复句式、重复钩子、人物声音趋同。
9. 长期人物事实是否出现矛盾（见第 13 节）。
10. `FuturePlan` 是否膨胀、重复阶段或留下已完成项。

---

## 11. 哪些内容可以改

- ✅ Content Pack：行动、事件、触发条件、成本、文本、成长树、伏笔定义、自主规则。
- ✅ Novel Profile：人物 / 势力 / 资源目录 / 能力目录 / 导演权重 / 未来阶段目标。
- ✅ 导演权重（`PUT /creator/director/weights`）。
- ✅ 尚未发生的计划与阶段（`future_plan`）。

改动内容包后，新事实只会从下一次推进开始生效；已经写入 StoryState 的事实不会被改写。

---

## 12. 哪些事实不能手工修改

**禁止直接编辑 StoryState 文件**，包括：

- 关系当前值、知识 `holders`、资源数量、能力与身份
- 已发生事件与 `effect_log`
- 支线状态与进度、延迟后果队列
- 伏笔运行时状态（`flags.foreshadows`）

需要改变就用合法的 `runtime/advance`（行动 / 事件 / 效果），或修正内容包让后续推进产生变化。

---

## 13. 如何处理 Writer proposed facts

Writer 的新增长期人物设定会以 `proposed_new_facts` 返回（年龄、身世、亲属、固定外貌、出生地、
过去经历、长期习惯、长期伤病、重要装备等），默认**不批准**：

1. 生产默认行为：不写回 StoryState；如与既有事实冲突，重写该章正文。
2. 确有必要时，才把它作为正式长期事实写入既有模型：
   - 角色属性 → 角色 `data`（如 `age` / `role` / 固定外貌字段）
   - 可被角色知道的信息 → `KnowledgeEntry(certainty="fact", holders=[...])`
3. **Writer 不能批准自己的提议**；批准动作必须由作者或生产脚本显式执行。

当前能力边界：模型若只在叙事里写长期事实而不声明，结构化校验无法抽取；
生产时靠每 10 章人工审读兜底。

---

## 14. 如何检查 FuturePlan / Plot / Foreshadow

| 对象 | 查看方式 | 注意 |
| --- | --- | --- |
| FuturePlan | Novel Profile 的 `future_plan`；`runtime/advance` 返回 `future_plan_changed` / `replan_reason` / old-new 摘要 | **全小说级，不按分支隔离** |
| PlotTrack | `GET /creator/plot` 与 `runtime/advance` 的 `plot_transitions` | 支线流转必须来自行动 / 事件 / 世界状态 |
| Foreshadow | `GET /creator/memory` 的 `foreshadows` / `open_foreshadows` | 状态来自 `flags.foreshadows`，回落内容包定义 |

**FuturePlan 的分支安全规则（重要）**：

- `future_plan` 存在 Novel Profile，不随 `branch_id` 分区。
- 分支实验只**读取**它；**不要**在分支运行时把重规划结果写回 Novel Profile，
  否则其它分支会看到被改写的未来规划。
- 只有 main 的正式生产才更新 `future_plan`；分支的重规划结果请单独保存到分支记录里。

---

## 15. 如何做生产备份

不需要额外备份系统，按下列最小做法即可：

1. **提交 Git**：`novel/authoring/story_engine/state/` 与 `novel/config/story_engine/` 纳入版本控制。
2. **章节记录**：每章保留一份结构化 JSON（`turns` 里的行动序列就是可重放来源）。
3. **重规划前记录**：`future_plan` 变更前保存 old 摘要（`runtime/advance` 已返回）。
4. **分支隔离**：任何实验先在 `runtime/fork` 出来的分支上做，不要在 main 上试错。
5. **恢复演练**：每 10 章做一次“fork → 重放 → 对比事实”的恢复演练（隔离目录内）。

---

## 16. 生产前检查清单

- [ ] `novel_id` 独立，未复用演示编号
- [ ] Content Pack 与 Novel Profile 已确认，起点清单完整
- [ ] `runtime/state` 显示 `revision=0`、起点地点正确
- [ ] 已确认 branch id 命名规则（`main` / `branch_<32hex>`）
- [ ] 分支实验只读 `future_plan`，不写回 Novel Profile
- [ ] 每章都有结构化记录与磁盘重载确认
- [ ] 每 10 章执行人工审读（第 10 节清单）
- [ ] Writer `proposed_new_facts` 有明确处理动作
- [ ] 全量测试通过（`pytest -q`、`validate_project`）
