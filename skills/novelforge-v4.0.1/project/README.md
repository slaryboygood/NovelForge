# Module: `project` — 作品生命周期

> 模块 Public Contract（Skill 视角）。技术 SSOT：`docs/v4/V4_MODULE_BOUNDARIES.md`。

```text
Module purpose     作品（novel）这一级对象的创建 / 列表 / 读取 / 重命名 / 归档
Authoritative owner application/services/project.py + application/services/novel_admin.py
Owned skills       create-novel / inspect-novels / rename-novel / archive-novel
Truth ownership    NovelProfile（作品档案）；本模块不拥有 Canon / StoryState / Blueprint 真相
Public interfaces  REST /api/story-builder/novels{,.../{novel_id}}；UI Studio Landing；
                   Application ProjectService；MCP 只有 novelforge://novels/{novel_id} 只读摘要
Dependencies       persistence.paths（档案路径唯一入口）、story_engine.profile、story_engine.templates
Forbidden         直接读写 profiles 文件、绕过 ProjectService、隐式当前作品推断
Related modules    studio（入口）、blueprint / canon / story-state（下游只读真相）
```

## 不变量

```text
· 每个调用显式携带 novel_id（除 list_novels）；禁止"磁盘上有别的作品就混进来"
· novel_id 必须匹配 ^[A-Za-z0-9][A-Za-z0-9_-]{2,95}$
· rename 只改作者可见 title，不改任何事实
· delete = 整体归档（可恢复、不留孤儿）；它不是"永久删除"
```

## 覆盖

| Use case | Skill | 接口 |
| --- | --- | --- |
| 新建作品 | `create-novel` | UI / REST / Application |
| 列出 / 查看作品 | `inspect-novels` | UI / REST / Application / MCP（摘要） |
| 重命名 | `rename-novel` | REST / Application |
| 归档（删除） | `archive-novel` | UI（二次确认）/ REST / Application |
