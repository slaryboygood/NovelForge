# Module: `canon` — 受保护的真相边界（Canon）

```text
Module purpose     Canon 是"已确认事实 / 事件 / 实体 / 知识 / 伏笔 / 依赖关系"的可查询真相层
Authoritative owner src/novelforge/story_engine/canon/**（frozen 边界，V4 只读 + 一个受控 rebuild）
Owned skills       inspect-canon-truth / inspect-canon-graph / validate-canon-integrity /
                   validate-planning-against-canon / rebuild-canon
Truth ownership    Canon 拥有身份与规划关系；StoryState 仍是 happened facts 的 runtime truth
Public interfaces  REST /api/story-builder/canon/*（api 层直连 canonical 模块）；
                   MCP = N/A（当前没有 canon tool / resource）
Dependencies       persistence.paths（canon db 路径唯一入口）、story_engine.canon.*
Forbidden          直接编辑 Canon 文件 / SQL、用 Memory 覆盖 Canon、绕过 Canon 服务另建一套真相
Related modules    quality（Q2/Q3 读 Canon）、generation（上下文约束）、editor（不触碰 Canon）
```

## 边界要点

```text
· happened 事实不可改写：改事实只能"新事实 + SUPERSEDES 链"
· planned 事件可 promote 为 occurred（保留同一 event_id；不确定就不合并）
· 本模块没有任何"写入新剧情事实"的 Skill —— 那需要作者审批边界（AGENTS.md §12.2）
· rebuild-canon 是唯一 mutation，属 operator 显式操作，失败保留原 DB
· GAP-003：canon REST 路由绕过 Application Services（记录在 V4_0_1_SKILL_GAPS.md）
```
