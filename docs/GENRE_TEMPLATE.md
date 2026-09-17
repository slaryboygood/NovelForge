# Genre Template 开发说明（T16-04）

Genre Template 是题材的默认目录，不是小说事实，也不改写核心算法。

## 结构

`story_engine/templates.py` 中的 `GenreTemplate`：

| 字段 | 说明 |
|---|---|
| `template_id` / `name` / `genre` | 标识与展示 |
| `concepts` | 六个通用概念的题材映射：progression / resource / faction / identity / ability / location |
| `resource_catalog` / `ability_catalog` / `factions` | 默认目录项（`ResourceDefinition` / `Ability` / `Faction`），只描述“是什么” |
| `rules` / `notes` | 推荐规则与作者提示 |

## 应用方式

```python
profile = apply_template(profile, "xianxia")   # 只补默认目录，作者已有条目优先
profile.model_dump()["world_profile"]["concepts"]  # 概念映射落在 Novel Profile
```

- 模板不写 `StoryState`：不会产生库存、能力、知识或已发生事件。
- 默认条目带 `data.source = template_id`，便于区分作者内容与模板内容。
- `template_id=""` 表示无模板/自定义题材；未知模板抛 `GenreTemplateError`。

## 新增一个题材

1. 在 `templates.py` 里加一份 `GenreTemplate` 数据并注册进 `TEMPLATES`；
2. 如需可玩的旅程，再按 `docs/CONTENT_PACK.md` 加一份内容包；
3. 不需要修改任何引擎代码，也不会出现 `if genre == ...` 分支（有源码守卫测试拦截）。

## 校验

```powershell
.venv\Scripts\python.exe -m pytest tests/test_story_engine_templates.py -q
```
