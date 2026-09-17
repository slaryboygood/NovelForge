# 章节上下文包结构

旧版人工上下文包可参考此结构。NovelForge 自动流程优先使用 Pydantic 生成的 `ChapterContextPack` JSON。

```yaml
chapter: 1
chapter_id: chapter_001
source_title: ""
arc: ""
time: unknown
location: []
pov: []
chapter_goal: ""
reader_hook: ""
external_conflict: []
internal_conflict: []
must_happen: []
must_not_happen: []
computing_concept:
  name: ""
  dramatization: ""
  misconception_to_avoid: ""
silicon_grind:
  question_before_answer: ""
  answer_or_system_pressure: ""
  protagonist_reframes: ""
  judgment_after_feedback: ""
daoist_motion:
  pattern: ""
  embodied_action: ""
character_change: {}
state_changes_expected: []
foreshadowing:
  plant: []
  advance: []
  resolve: []
ending_hook: ""
continuity_risks: []
author_decisions_needed: []
```

字段值要短、明确、可执行。ContextPack 是生产任务书，不是正文。
