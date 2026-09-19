# Module: `story-state` — StoryState / NovelContext（已发生事实的 runtime 状态）

```text
Module purpose     已发生事实的 runtime 状态 + 作品档案上下文（只读消费）
Authoritative owner src/novelforge/story_engine/{state,storage,context,profile,entities,templates}.py
Owned skills       understand-story-state-boundary / inspect-story-state
Truth ownership    StoryState 是 happened facts 的 runtime truth；V4 生成不写它
Public interfaces  Python API（resolve_novel_context / StoryStateRepository）；
                   UI / REST / MCP = N/A（无产品级入口，见 GAP-008）
Dependencies       persistence.paths（state / profiles 路径）、novelforge.models
Forbidden          用 Blueprint 或 Memory 覆盖 StoryState、手工改 state 文件、
                   把 planned 内容写进 state
Related modules    memory（只读投影）、canon（身份 / 规划关系）、generation（上下文只读）
```

## 关键事实

```text
· StoryState 字段：timeline（current_time / tick）、location、characters、identities、
  resources、relationships、promises、plots、effect_log
· 读取入口：resolve_novel_context(project_root, novel_id) → NovelContext(.state, .persisted, …)
· State 持久化：story/{blueprint_id}/v{version}[_{branch}].json（StoryStateRepository，原子写）
· V4 生成链只读 StoryState；写入发生在作者 / 引擎侧流程，不属于本 Skill Library 范围
```
