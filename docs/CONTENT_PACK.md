# 内容包格式说明（T16-03）

> **2026-09 更新**：内容包（`novel/config/story_engine/*.json`）与它的 loader
> （`settings_gen` / `settings_check` / `wizard`）已随 V2 Story Builder 后端退休；
> `novel/config` 现在只剩 `ai/providers.json`。本文件保留为历史格式说明。
> 当前 canonical creative artifact 是 **Story Blueprint**
> （`docs/v4/V4_BLUEPRINT_CONTRACT.md`），题材默认值来自 `story_engine/templates.py`
> （`apply_template`）。

内容包描述“这本小说有什么”，不包含引擎逻辑。引擎按通用结构消费它，新增题材只需新增数据。

## 文件位置

- 单包：`novel/config/story_engine/<pack_id>.json`
- 合集：`novel/config/story_engine/genre_packs.json`（`{"packs": [ ... ]}`，可放多份题材包）
- 运行态选择：`NovelProfile.content_pack_id` → `AdventureEngine` 按小说实例加载；未设置时回退默认包 `journey_v1`。

## 顶层字段

| 字段 | 说明 |
|---|---|
| `pack_id` / `title` / `genre` | 标识与展示信息；`genre` 只是字符串标签，引擎不据此分支 |
| `initial_flags` / `initial_resources` | 旅程起点（声明式，引擎不写默认值） |
| `text` | 场景文本：`place_fallbacks`、`opening_profiles`、`crisis_*`、`hero_memories`、`companion_lines`、`opponent_pressure`、`scene_titles`、`scene_texts`、`followup_titles`、`followup_texts` |
| `choice_sets` | 每个场景（`rev0`…`revN`、`followup`）的可选行动规则：`action_id`、`order`、`when_patterns`、`unless_patterns` |
| `actions` | 通用 Action：`requirements`、`costs`、`immediate_effects`、`risks`、`delayed_effects`、`visibility`、`data.cost_text` / `data.result` |
| `events` | EventCard：`trigger`、`available_actions`、`consequences`、`priority`、`cooldown`、`once_only` |
| `events[].scope` | `scene`（默认，主角场景事件）或 `world`（世界事件，主角可不参与） |
| `events[].knowledge_id` / `reader_visible` | 世界事件产生的知识 id 与读者可见性；**默认不交给任何角色**，需通过合法来源（亲眼见到、被告知）才能成为角色知识 |
| `recompute` | 从选择历史重算计数器（`counters` / `floors`）、知识（`knowledge_choices`）、结局标记（`arc_finished_choices`） |
| `choice_aliases` | Action id → 对外 choice id（兼容既有前端与存档） |

## 校验规则

- action id、event id 唯一；事件引用的行动必须存在。
- 条件与效果只能使用通用结构（见 `story_engine/conditions.py`、`effects.py`）。
- 模板与内容包都不会创建库存、知识或能力；这些只能由效果写入 StoryState。
- 世界事件（`scope = "world"`）只改变世界状态（地点、势力、flag）并登记未认领知识；
  主角资源与知识不会被世界事件自动修改。

## 常用校验命令

```powershell
.venv\Scripts\python.exe -m pytest tests/test_story_engine_content.py tests/test_story_engine_cross_genre.py -q
```
