---
name: silicon-state-tracker
description: 在章节通过后抽取并更新《硅基升维》的故事状态，追踪时间、人物、知识、能力、物品、伏笔、谜题和世界规则变化。
---

# 硅基状态追踪器

在《硅基升维》的章节完成、返修或定稿后，使用此 Skill。

## 核心规则

长篇小说最容易失败在状态漂移。每章结束后，必须先抽取“发生了什么变化”，再规划下一章。

## 输入

- 定稿或当前最新版章节正文
- 当前章节的 `ChapterContextPack`
- 相关 Bible 和时间线文件
- `novel/state_updates/` 中已有的状态更新

## 输出

输出结构化 `StateDelta`，或写入 `novel/state_updates/chapter_XXX_state.json`：

```json
{
  "chapter": "chapter_XXX",
  "time_advanced": "",
  "locations_changed": [],
  "new_facts": [],
  "character_changes": [],
  "relationship_changes": [],
  "abilities_changed": [],
  "items_changed": [],
  "organizations_changed": [],
  "world_rules_confirmed": [],
  "world_rules_changed": [],
  "secrets_revealed": [],
  "knowledge_state_changes": [],
  "foreshadowing_planted": [],
  "foreshadowing_advanced": [],
  "foreshadowing_resolved": [],
  "unresolved_mysteries": [],
  "continuity_risks_for_next_chapter": []
}
```

## 追踪优先级（Novel Reboot v2）

- **等级与成长**（必须追踪）：主角与队友的等级、职业、技能点、技能获取、转职进度——每次升级都要反映到 `novel/state/current_state.yaml`。
- **装备与物品**（必须追踪）：品级、部位、强化等级、持有者、绑定状态；成长装备（裂变剑）的阶段变化。
- **任务状态**（必须追踪）：主线/支线/隐藏任务进度、Boss 首杀记录、掉落清单、地图解锁。
- `knowledge_state` 极其重要：记录谁知道、谁怀疑、谁误解、谁仍不知道某个秘密。
- 追踪能力边界，而不只是能力名称。新能力必须有约束、代价和失败模式（如吞噬的腐化值）。
- 追踪物品归属和损坏状态。装备、灵核碎片、万芯残片不能在场景之间瞬移。
- 追踪知识概念覆盖，避免重复讲同一个知识点而没有升级。

## 更新正典

如果章节已定稿，可以更新：

- `novel/config/outline/master_timeline.yaml`
- `novel/state/current_state.yaml`
- 相关人物、地点、物品、等级/装备记录

如果章节仍是草稿，只写状态更新，并标记 `status: draft`。

## 边界

- 不发明正文或已批准 ContextPack 中没有的后续变化。
- 如果某个变化是暗示但不明确，记录到 `continuity_risks_for_next_chapter` 或 `author_decisions_needed`。
