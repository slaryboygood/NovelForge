# 兼容边界（Legacy Compatibility）

本文件是**兼容性 SSOT**：说明旧数据、旧接口与旧行为在当前产品里如何被对待。
历史开发过程见 Git history；版本历史见 `docs/CHANGELOG.md`。

## 已冻结的版本边界

```text
V3 Final（活动）
  tag            novelforge-product-v3-final
  history shape  单一 root commit（main = v4 = V3 Final root）
  状态           RELEASED / FROZEN（Functional Closure）

Product V3.0 / Product V2.0 / Story Engine V2（已归档）
  tags           novelforge-product-v3.0
                 novelforge-product-v2.0
                 story-engine-v2.0
                 状态：historical / archived / not an active Git ref
  commits        20d03cfa78b458e18e385fdaf58a04e3f2bde1c3
                 56cda829d812d95f65cb282e0c85328792f6d9cd
                 fbe99cd2092cb03a4f8ffa480b453ab9e33aa53d
                 （仅作历史 metadata；活动仓库不要求可寻址）
  完整历史       NovelForge_pre_V4_full_history.bundle（外部冷备，已通过恢复验证）
```

不可修改：

- 唯一活动 release tag `novelforge-product-v3-final` 指向的 commit 与 tag message；
- 已冻结的 truth：Canon、StoryState 基线、legacy 源、source Chapter IR、
  Historical Foundation、Repair Contract、`REPAIR_GATE_V1`、approval boundary；
- `novel/authoring` 中已跟踪的作者数据不得漂移 —— 由加密摘要 manifest 校验
  （`docs/FROZEN_EVIDENCE_MANIFEST.json`）。

冻结机制已从「Git tag / historical commit must remain resolvable」迁移为
「tracked frozen evidence + cryptographic digest manifest」；旧 tag 与旧 commit
不得作为活动寻址依赖。

守卫：`tests/test_v2_frozen_guard.py`（冻结证据摘要 + 单一 root + 历史 ref 语义，默认运行）、
`tests/test_v3_frozen_guard.py`（route_lab 只读放宽边界，默认运行）。
> **V4-01 更新**：字节级 M11–M18 frozen-digest 验收所依赖的 570 章 historical 数据由作者判定为
> 废弃并已删除，对应测试随之移除（`pytest -m historical_acceptance` 目前为空；
> marker 保留给 V4 里程碑验收复用）。frozen-boundary 规则本身保持不变。

## 旧存档兼容（仍然只读支持）

| 存档 | 位置 | 处理方式 |
|---|---|---|
| 构筑会话 / 蓝图 / 大纲 | `novel/authoring/story_builder/` | 格式未变；缺少新字段时由默认值补齐（`design_choices`、`needs_review_steps` 等） |
| 旧旅程（rules_version 1/2） | `novel/authoring/story_builder/adventures/*.json` | 继续按旧规则读取；不会被转成 StoryState；必要时可用 `from_legacy_adventure` 只读转换 |
| 引擎状态 | `novel/authoring/story_engine/state/` | JSON 带 `schema_version`，读取时由 `upgrade_story_state_payload` 补齐分节；版本高于当前引擎时拒绝读取 |

行为约定：

- 新旅程（有内容包）→ `rules_version = 3`，由 StoryState 驱动；Adventure 文件降级为镜像投影。
- `legacy` 字段原样保留无法映射的旧数据（trust、debt、history 等），不猜测语义。
- 旧数据只读兼容：不被新引擎接管、不被重写。

## V3 里的 legacy bridge（为什么还在）

V3 工作台（`ui/src/v3/`）覆盖浏览、检查、目标与推演；**完整编辑**仍通过既有面板提供，
经由两个入口进入同一套 domain 与同一批 API：

```text
#/story-builder?...     高级工具（世界 / 角色 / 剧情 / 导演 / 路线实验室 / 大纲锻造 / Canon 检查 / 修复中心）
?ui=v2                  旧入口 / 书签 / 旧验收脚本
```

规则：

- 一级导航不做成开发者菜单；高级工具是 Contextual / Advanced 入口；
- bridge 只做跳转，不产生第二套业务规则或第二套状态；
- 旧面板依赖的接口（`/api/story-builder/*`）属于兼容层，语义变更需单独评估。

## 兼容层接口与只读放宽

```text
route_lab.list_branches：pack is None → 合法空结果
  （只读列表放宽：没有内容包 = 这本书还没开始推演，不是错误；
    浏览器因此不再把预期空态记为 404）
  边界：fork / compare / merge / freeze 与 runtime/start 仍然要求内容包
  证据：tests/test_v3_frozen_guard.py
```

## 本地数据与仓库边界

```text
作者数据（不进版本控制，运行时生成）
  novel/authoring/story_engine/**（Canon / StoryState / profile / planning）
  novel/config/story_engine/*_pack.json（内容包）
  novel/authoring/story_builder/outlines/*/ol_forge_*（锻造链）
  workspace/**（导出 / 修复 / 验收证据与生产文档）
```

这些路径已在 `.gitignore` 中排除；删除或重写它们不属于兼容性问题，但**不得提交进仓库**。
