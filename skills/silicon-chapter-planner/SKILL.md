---
name: silicon-chapter-planner
description: 在《硅基升维》（Novel Reboot v2：硅基拟人世界 + MMO 升级冒险爽文）正文写作前，基于新版 Canon、地图、怪物、等级、装备、人物状态、伏笔与任务体系生成章节任务书与章节上下文包。
---

# 硅基章节规划器（Novel Reboot v2）

在撰写或返修《硅基升维》某一章之前，使用此 Skill。

## 核心规则

不要只凭章节标题写正文。必须先产出章节级生产资料，明确这一章要完成什么、不能泄漏什么、继承什么状态、改变什么状态。

正式网文章节不能靠一句“写长一点”解决。Planner 必须先证明本章有足够叙事容量，再交给 Writer。

**新版方向（必须遵守）**：这是一部硅基拟人世界 + MMO 升级冒险爽文。规划必须围绕：任务→冲突→战斗→奖励→新发现→升级→更强敌人的循环；每 3-5 章一个爽点；主角是人形硅基生命（有表情、情绪、吐槽）；打怪、掉宝、升级、开图、收队友是剧情主轴。

**规划红线**：
- 禁止工程术语进入正文方向（电压/电流/拓扑/协议/晶格/载流子/过孔/波形等）；全部使用世界化词汇（灵能/灵核/记忆仓/能量仓/怪物名/职业名）。
- 禁止“先现象后旁白解释”结构；禁止角色坐下讨论抽象哲学。
- 禁止连续多章无战斗、无升级、无掉落；系统提示【】只用于升级/获得装备/任务变化等关键节点且要短。
- 不得规划主角靠“分析/扫描/推理/证明”解决战斗——战斗靠动作、技能与选择。

## 输入（新版 SSOT 路径）

只读取当前章节真正需要的资料：

- `novel/config/spec/novel_constitution.json`（宪法：最高解释权）
- `novel/config/bible/*`（premise/worldview/world_rules/style_guide/forbidden_patterns/philosophy）
- `novel/config/outline/master_story.yaml` + `master_timeline.yaml`（总主线/时间线）
- `novel/config/outline/volumes/*.yaml`（卷纲）
- `novel/config/outline/chapters/*.yaml`（120 章精细章纲——优先遵循）
- `novel/config/characters/*`（主角卡/队伍弧光）
- `novel/config/progression/*`（等级/职业/技能/装备/掉落）
- `novel/config/maps/maps.yaml`（地图）
- `novel/config/monsters/*`（怪物/Boss 图鉴）
- `novel/config/factions/factions.yaml`（势力）
- `novel/state/current_state.yaml`（当前状态）
- `novel/config/human/author_decisions.yaml`

Planner 可以读取以上 SSOT；Writer 不可以绕过 Context Builder 直接读取这些资料。

## 输出

输出给 NovelForge 的结构化 `ChapterPlan` 或章节上下文资料，至少包含：

- `chapter_id` / `source_title` / `timeline` / `location` / `pov`
- `chapter_purpose`（本章目标，单一主推进）
- `opening_state`（承接上一章地点/状态/动作）
- `must_happen` / `must_not_happen`
- `conflicts`（外部冲突必须有战斗或对抗；禁止只有内部思辨）
- `information.reveal` / `information.hide`
- `character_arc`（本章人物变化）
- `foreshadowing`（伏笔 plant/advance/resolve）
- `emotional_curve`
- `ending_hook`（章尾钩子，必须存在）

正式章节还必须包含：

- `chapter_length`
  - `length_class`: `STANDARD` / `KEY` / `CLIMAX`
  - `STANDARD`: 3800 / 4500 / 5000（Novel Reboot v2 校准）
  - `KEY`: 4200 / 5000 / 5500
  - `CLIMAX`: 4500 / 5500 / 6000
- `scenes`: 3 个以上场景计划（每个含 scene_id/purpose/entering_state/event/conflict/character_action/choice/reveal/hide/state_change/exit_state/estimated_chars）

如果现有大纲无法自然支撑所选 `length_class` 的最低正文汉字数，返回：

```text
PLAN_CAPACITY_FAIL
```

并指出薄弱项：场景数量、具体事件、冲突压力、主角选择、信息变化、状态变化或章尾钩子。

## 规划品味（Novel Reboot v2）

- 章节要有事件与战斗。知识型章节也需要压力、发现、代价或不可逆状态变化；情报通过任务、遭遇与打脸呈现，不通过讨论。
- 每章至少包含一个可执行的“爽点种子”：升级、掉宝、技能觉醒、打脸、开图、收队友、Boss 首杀中的一项或多项。
- 主角必须主动：测试、误读、重释或重新占有答案，而不是被动接收。
- 怪物与 Boss 要视觉化：外形、动作、机制、阶段、弱点、掉落。
- 升级与装备变化要可被动作证明（上一章打不过的怪，这一章一刀清场）。
- 人物语言差异化写入规划：主角嘴硬吐槽、队友各有口头习惯、反派有压迫感台词。
- ContextPack 要足够精确，能交给 Writer 执行；但不能细到变成正文。
- 正式开篇章通常适合 4 到 6 个有意义的场景。
- 叙事密度比裸字数重要。不要制造空走路、重复惊叹或抽象哲学来填长度。

## 边界

- 不写成稿正文。
- 不在没有作者确认时解决重大结局选择。
- 不用擅自降低已选 `length_class` 的方式掩盖计划容量不足。
- 不引用旧版 Canon（旧角色/旧设定/旧地图/旧术语一律不得出现在计划中）。
