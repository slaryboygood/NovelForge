---
name: silicon-novel-bible
description: 维护《硅基升维》（Novel Reboot v2）的故事圣经，把新版大纲、世界规则、人物、势力、升级体系、伏笔和作者决定整理成长篇写作资产。
---

# 硅基小说圣经（Novel Reboot v2）

当用户要求整理、扩写、规范化、审计或更新《硅基升维》的项目圣经时，使用此 Skill。

## 项目契约

- 新版定位：**硅基拟人世界 + MMO 游戏式升级 + 打怪掉宝 + 地图推进 + 小白爽文 + 长篇连载**（作者 2026-08-26 指令，Novel Reboot v2）。
- 新版 Canon 是唯一有效 Canon：SSOT 层级见 `novel/config/outline/master.yaml`（宪法最高解释权）。
- 作者决定高于一切。修改 canon、主线篇章、结局或主题前，先检查 `novel/config/human/author_decisions.yaml`。
- 旧版内容（旧角色/旧设定/旧地图/旧术语）一律不得进入新版 Bible；旧专名黑名单见 `novel/config/legacy_worldview_denylist.yaml`。
- Bible 更新要结构化、便于 diff。事实优先用 YAML，文风和创作指导优先用 Markdown。
- 对不确定或推断内容标记 `status: inferred` 或 `status: needs_author_decision`，不要把猜测静默固化为 canon。

## 需要维护的区域（Novel Reboot v2 路径）

- `novel/config/bible/premise.md`：前提、目标读者、作品承诺（先爽再故事最后思想）。
- `novel/config/bible/worldview.yaml`：世界本质、灵核、腐化信号、世界化词汇表、regions/iron_rules/life_tiers。
- `novel/config/bible/world_rules.yaml`：灵能/等级/职业/装备/掉落/任务/腐化/地图规则。
- `novel/config/bible/style_guide.md`：小白爽文语言、反 AI 感清单、系统提示限制、人物语言差异化。
- `novel/config/bible/forbidden_patterns.md`：旧叙事方式黑名单。
- `novel/config/bible/philosophy.yaml`：主题如何藏在事件与选择里。
- `novel/config/characters/`：主角卡与队伍弧光。
- `novel/config/progression/`：等级/职业/技能/装备/掉落。
- `novel/config/factions/factions.yaml`：势力。
- `novel/config/maps/maps.yaml`：地图体系。
- `novel/config/monsters/`：怪物与 Boss 图鉴。
- `novel/config/outline/`：master_story/master_timeline/volumes/chapters。

## 工作流

1. 读取相关 SSOT 文件；宏观意图优先从 `novel/config/outline/master_story.yaml` 开始。
2. 判断任务属于 canon 抽取、canon 更新、矛盾审计还是结构扩展。
3. 只更新必要的最小 Bible 文件。
4. 同时保留剧情功能和学习功能：每个区域、Boss、技能都应推进故事、情绪和游戏式成长。
5. 结束时简短说明改了什么、还有什么需要作者决定。

## 红线

- 正文方向禁止工程术语（电压/电流/拓扑/协议/晶格/载流子/过孔/波形等）；技术概念必须世界化。
- 全面拟人化：主要角色是人形硅基生命，有表情、情绪、身体反应与个性语言。
- 禁止把哲学/文明命题作为剧情驱动；思想只能藏在事件与选择里。

## 边界

- 不用此 Skill 写完整章节正文；正文交给 `silicon-scene-writer`。
- 不在这里运行评审委员会；评审交给 `silicon-review-committee`。
- 除非用户明确要求编辑 Word 文档，否则不覆盖源 `.docx` 文件。
