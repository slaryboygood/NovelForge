# Module: `blueprint` — Story Blueprint（canonical 节点图）

```text
Module purpose     Story Blueprint 的节点模型与 canonical store（append-only revision）
Authoritative owner src/novelforge/blueprint/{contracts,repository,lifecycle,validation}.py
Owned skills       inspect-blueprint / inspect-node / inspect-revisions / inspect-scene-cards /
                   understand-blueprint-model
Truth ownership    Blueprint 是"计划真相"（planning truth）；不是 Canon / StoryState（已发生事实）
Public interfaces  REST /studio/blueprint、/editor/nodes/*；MCP blueprint resources；
                   UI 世界 / 人物 / 故事 / 场景页
Dependencies       core（ids / digest / revision）、persistence.paths
Forbidden          直接改节点 revision 文件、绕过 repository 写 status、把 Blueprint 当 Canon
Related modules    generation（写入 proposal）、editor（作者编辑）、quality（只读评估）、
                   delivery（只读编译）
```

## 节点类型与父层级（唯一 SSOT）

| 节点类型 | id 前缀 | 允许的父类型 | 说明 |
| --- | --- | --- | --- |
| `premise` | `premise` | 无 | 故事前提（单例） |
| `theme` | `theme` | 无 | 主题（单例） |
| `world` | `world` | premise / 无 | 世界规则 / 地点 / 势力 / 资源 |
| `character` | `char` | premise / world / 无 | 人物卡 |
| `character_arc` | `arc` | character | 人物弧 |
| `story_arc` | `story_arc` | premise / 无 | 故事弧 |
| `structural_unit` | `unit` | story_arc / structural_unit | 结构单元（幕 / 部 / 篇） |
| `chapter` | `ch` | structural_unit / story_arc | 章节卡 |
| `scene` | `sc` | chapter | 场景卡（必须声明 `chapter_id`） |
| `setup` | `setup` | chapter / scene / structural_unit | 埋设 |
| `payoff` | `payoff` | chapter / scene / structural_unit | 回收 |
| `causal_link` | `cl` | story_arc / structural_unit / chapter / scene / 无 | 因果关系 |

## 状态语义（两组状态互相独立，禁止混淆）

```text
status（生命周期，Blueprint owner）        proposed → draft → accepted → superseded
quality_status（Quality Store 投影）        unevaluated / passed / passed_with_issues / failed / blocked

quality passed ≠ status accepted（ADR-022）；review 决定（accepted / rejected）属于
Editor metadata，不改变 lifecycle enum。
```

## 不变量

```text
APPEND_ONLY_REVISION：任何修改都产生新 revision，历史永不删除
SYSTEM_ASSIGNED_NODE_ID：节点 id 由系统按前缀规则分配，模型不得自造
PLANNING != OCCURRED TRUTH：Blueprint 不写 Canon / StoryState
STRUCTURAL_IDENTITY 只能经 move_node / 系统分配改变（patch / rewrite 一律拒绝）
```
