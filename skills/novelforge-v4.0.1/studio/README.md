# Module: `studio` — Story Studio（唯一产品面）

```text
Module purpose     V4 唯一 current 产品界面：进入、导航、总览、旧 URL 回落
Authoritative owner ui/src/studio/**（+ ui/src/api/studio.ts 作为唯一 HTTP 入口）
Owned skills       open-story-studio / navigate-studio-workspace / inspect-overview /
                   handle-legacy-url
Truth ownership    无。Studio 只显示后端返回的真相，不推导质量 / 接受状态 / 交付资格
Public interfaces  hash 路由 #/studio[/n/<novelId>[/<view>[/<id>]]]；REST 只经 studioApi
Dependencies       REST /api/story-builder/{novels,studio,editor,delivery,agent}
Forbidden          在组件里直接 fetch、前端重算质量 / 进度 / 交付资格、恢复 V2/V3 界面
Related modules    所有其它模块（作为消费方）
```

## 视图与意图

| View | 标签 | 意图 | 主要后端 |
| --- | --- | --- | --- |
| `overview` | 总览 | 这本作品做到哪里 / 下一步 | `GET /studio/overview` |
| `creation` | 创造 | 前提 / 主题 / 核心冲突 | `POST /studio/generate` + Editor |
| `world` | 世界 | 规则 / 地点 / 势力 / 资源 | Generation + Editor |
| `characters` | 人物 | 人物卡与人物弧 | Generation + Editor |
| `story` | 故事 | 故事弧 / 结构单元 / 章节 | Generation + Editor |
| `scenes` | 场景 | 每场戏为什么存在 | Generation + Editor |
| `quality` | 检查 | 质量问题与定向修复 | `GET/POST /studio/quality*` |
| `delivery` | 交付 | 选择 / 预检 / 下载 | `/delivery` + `/studio/delivery/formats` |
| `plugins` | 插件 | 扩展能力的只读状态 | `GET /studio/plugins` |
| `agent` | Agent | 给目标，先看计划再执行 | `/agent/*` |

## 不变量

```text
· Story Studio 是唯一 current 产品面（ADR-032）；V2/V3 界面已随 post-release cleanup 移除
· UI 不实现阶段推进 / 质量判定 / 交付资格规则（ADR-033）
· 已冻结的一级导航文案由门禁测试保护，不随实现细节漂移
```
