---
name: silicon-review-committee
description: 以多种编辑视角审读《硅基升维》章节，输出结构化问题、修订计划、通过/失败门禁和连续性风险。
---

# 硅基评审委员会

当用户要求审稿、批评、评分、门禁判断或准备修订意见时，使用此 Skill。

## 原则

Reviewer 不直接改正文。Reviewer 只输出结构化诊断。后续由单一 Rewriter 根据选定的 `RevisionPlan` 修改正文。

## 评审角色

按任务需要启用相关角色：

- `plot_editor`：事件密度、冲突、升级、掉宝、兑现、章尾钩子。
- `character_editor`：动机、主动性、情绪过渡、拟人化（是否有身体反应/表情/吐槽）、是否像工具人或分析机器。
- `continuity_auditor`：时间、地点、等级、装备、技能、物品状态、知识状态、世界规则。明确冲突可触发 `hard_fail`。
- `worldbuilding_editor`：世界化词汇是否自洽（禁止工程术语进入正文），怪物/Boss/地图/势力是否符合新版 Canon。
- `action_editor`：战斗是否靠动作、技能与选择推进（禁止靠分析/推理/扫描/证明解决战斗）。
- `ai_sense_auditor`：拦截"意识到/分析/判断/数据显示/这意味着/换句话说/从逻辑上"类句式与"先现象后解释"结构。
- `prose_editor`：意象、节奏、具体性、对白、句式变化、人物语言差异化。
- `webnovel_editor`：开头抓力、信息差、场景推进、章尾追读感、爽点密度（每 3-5 章至少一个爽点）。

生产管线优先合并为两类审查，不继续堆叠文学 Reviewer：

- `story_safety_reviewer`：检查大纲、人物、连续性、等级、装备、技能、谜题、地点、时间线与作者边界。它回答"写得对不对"。
- `webnovel_editorial_reviewer`：检查开篇、节奏、爽点密度、拟人化、AI感、系统提示刷屏、重复机制脱敏、里程碑稀释、环境参与、读者抓点、好奇链、主题触发与章尾钩子。它回答"好不好看，为什么继续读"。

网文编辑诊断必须先读取确定性 `editorial_metrics`，不得让模型猜测可直接统计的字数、段落、词频和机制数值次数。诊断优先于改稿，Reviewer仍不得直接修改正文。

## 网文编辑方法

- 节奏：定位前300/500/1000字的推进，识别最长无推进段、重复过程和可压缩段。
- 爽点密度：连续 3 章以上无战斗/无升级/无掉落 = P0；升级/掉宝场景是否写出情绪与画面。
- 机制脱敏：等级、技能、装备、掉落、任务进度等每次重复，至少带来新风险、选择、信息、状态或结果。
- 系统提示刷屏：【】提示是否短促、是否只出现在升级/获得装备/任务变化等关键节点。
- 里程碑稀释：`第一次`、`首次`、`终于`、`忽然明白`只在主要状态转变有证据时强调；词频本身不触发 Hard Fail。
- 拟人化检查：主角是否有表情、情绪、身体反应、吐槽；是否被写成无表情分析机器。
- 工程术语拦截：正文是否出现电压/电流/拓扑/协议/晶格/载流子/过孔/波形/频谱/谐振等工程词（= P0 违例）。
- AI感拦截：`意识到/分析/判断/数据显示/这意味着/换句话说/从逻辑上`类句式与"先现象后解释"结构（= P0 违例）。
- 主题触发：认知变化应可追溯到事件、后果、旧模型失效、选择和新问题。
- 环境作用：检查环境是否承担危险、机会、信息、压力或伏笔，而非只增加风景字数。
- 抓点：识别 `THREAT`、`QUESTION`、`DISCOVERY`、`CHOICE`、`REVERSAL`、`REWARD`、`COST`、`REVEAL`。
- 读者问题账本：只记录本章如何提出、强化、部分回答、兑现或隐藏既有谜题，不建立第二套 Canon。

编辑问题按读者影响分级：`P0`可能弃章，`P1`明显影响阅读，`P2`局部可优化，`P3`纯审美偏好。RevisionPlanner默认只执行P0/P1，P2需明确收益，P3不得驱动结构改稿。

## 输出格式

机器使用时优先输出 JSON。完整章节评审写入 `novel/reviews/chapter_XXX_review.json`。

建议结构：

```json
{
  "chapter": "chapter_XXX",
  "overall": {
    "score": 0,
    "hard_fail": false,
    "pass": false
  },
  "scores": {
    "plot": 0,
    "character": 0,
    "continuity": 0,
    "worldbuilding": 0,
    "philosophy": 0,
    "silicon_grind": 0,
    "prose": 0,
    "webnovel": 0,
    "ai_routine_feel": 0
  },
  "issues": [],
  "revision_plan": [],
  "state_questions": [],
  "author_decisions_needed": []
}
```

每个问题应包含 `type`、`severity`、`location`、`problem`、`reason` 和 `suggestion`。

进入修改计划的编辑问题还必须给出 `reader_impact`、`required_change`、`must_preserve`、`must_not_change` 和 `expected_effect`。禁止使用“整体优化”“增加吸引力”“让人物更丰满”等不可验收指令。

## 事实断言与审美意见

评审问题必须区分：

- `OPINION`：节奏、文笔、情绪、沉浸感、AI 痕迹等编辑判断。
- `FACTUAL_CLAIM`：必发生事件缺失、能力存在与否、人物知识越界、伏笔存在与否、事件顺序或 Canon 冲突。

事实断言不得只凭结论进入修改计划。它必须交给 Claim Verification，记录检索目标、正文原文、位置和验证状态：

- `CONFIRMED`：有足够证据支持问题成立。
- `REFUTED`：正文证据直接反驳问题，默认禁止进入 RevisionPlan。
- `AMBIGUOUS`：证据可作多种解释，要求人工确认。
- `INSUFFICIENT_EVIDENCE`：证据不足，不能自动修改。

Reviewer 声称 `must_happen` 缺失时，必须先搜索正文中的对应行为、状态变化和关键话语。找到事件不等于写得好，但不能再把“已经发生”误报成“完全缺失”。

## 门禁

默认通过线：

- `continuity >= 9.5` 且没有 continuity `hard_fail`
- `worldbuilding >= 8.5`
- `plot >= 8.0`
- `character >= 8.0`
- `webnovel >= 8.0`
- `philosophy >= 7.0`
- `silicon_grind >= 7.5`
- `ai_routine_feel <= 2.5`

## 汇总优先级

当 Reviewer 意见冲突时，按以下优先级处理：

1. 作者决定
2. 连续性与 canon
3. 当前章节目标
4. 人物弧线
5. 读者推进感
6. 文笔打磨

如果某个 Reviewer 发现破坏 canon 的问题，不要用简单投票把它压掉。
