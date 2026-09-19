---
name: novelforge-v4.0.1.studio.navigate-studio-workspace
description: 在 Story Studio 里定位到指定作品与工作区（hash 深链接），确保刷新后位置不丢。
---

# navigate-studio-workspace

- **Skill ID**: `novelforge-v4.0.1.studio.navigate-studio-workspace`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `studio`
- **Product owner**: `ui/src/studio/nav.ts`

## Purpose

用 stable hash 路由把用户（或验证脚本）直接送到某个视图 / 实体，不依赖点击路径。

## Use when

- 要把某本作品 + 某个工作区（甚至某个节点 / issue / snapshot）直接打开。
- 写浏览器验证脚本时要构造 URL。

## Do not use when

- 只需要数据（不打开 UI）→ 直接调用 REST。

## Preconditions

```text
Story Studio 已启动；novel_id 已确认存在（inspect-novels）
```

## Required inputs

| 输入 | 必填 | 说明 |
| --- | --- | --- |
| `novel_id` | 是 | 目标作品 |
| `view` | 否 | 缺省 `overview` |
| `entity_id` | 否 | 可深链接实体（见下表） |

## Authoritative interfaces

```text
UI           #/studio                              Landing
             #/studio/n/<novelId>                  Overview
             #/studio/n/<novelId>/<view>[/<id>]    工作区（可深链接）
REST         —（路由只决定 UI 位置；数据仍走 REST）
Application  —
MCP          N/A
```

可深链接实体（`ENTITY_VIEWS`）：`characters→character`、`story→chapter`、
`scenes→scene`、`quality→issue`、`delivery→snapshot`。

## Procedure

```text
1 确认 novel_id：inspect-novels
2 构造 hash：#/studio/n/<novelId>/<view>[/<entityId>]
3 打开后确认 URL 片段未被重写（除旧 URL 归一化外）
4 刷新页面：位置保持不变（深链接语义）
5 无法识别的 view → 解析为 overview（不报错、不 404）
```

## Expected result

对应工作区渲染，且左侧导航高亮与该 view 一致。

## Verification

```text
· locator 能命中该 view 的标题（例如「场景」页场景卡）
· reload 后仍在该 view / 实体
· ui/src/studio/nav.test.ts 覆盖 parseStudioRoute / studioHash 往返
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 打开后跳回 Landing | novel_id 为空或 hash 非 `studio/n/…` 形状 | 检查 hash 拼装 |
| 打开的 view 变成总览 | view 字符串不在允许集合 | 用 `docs/v4/V4_UI_CONTRACT.md` §3 的 view 名 |
| 实体没高亮 | entity id 未 URL-encode | 使用 `encodeURIComponent` |

## Safety / invariants

```text
只有一套产品路由；不要添加 V3 / V2 的视图分支
不在前端推导"当前阶段"或"下一步"（由 /studio/overview 提供）
```

## Side effects

无（仅浏览器地址变化）。

## Related skills

`open-story-studio`、`inspect-overview`、`handle-legacy-url`

## Source references

```text
ui/src/studio/nav.ts、ui/src/studio/nav.test.ts
ui/src/studio/StudioApp.tsx
docs/v4/V4_UI_CONTRACT.md §3.1
```
