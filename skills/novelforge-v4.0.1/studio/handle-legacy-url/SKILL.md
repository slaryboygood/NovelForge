---
name: novelforge-v4.0.1.studio.handle-legacy-url
description: 处理 V2/V3 旧 URL（?ui=v3 / #/v3… / ?ui=v2 / #/story-builder…），一次性归一化回 Story Studio。
---

# handle-legacy-url

- **Skill ID**: `novelforge-v4.0.1.studio.handle-legacy-url`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `studio`
- **Product owner**: `ui/src/App.tsx`

## Purpose

旧书签不会 404，也不会出现第二套产品 UI：一次性归一化到 Story Studio。

## Use when

- 用户带着旧链接进来。
- 写浏览器验证（`tests/browser_v4_legacy_entry.cjs`）。

## Do not use when

- 想恢复旧界面 → **不可能**：V2/V3 产品面已在 post-release cleanup 中删除。
- 想找旧功能 → 见 `docs/v4/V4_POST_RELEASE_CLEANUP_REPORT.md` §96b–§96h。

## Preconditions

```text
Story Studio 已启动
```

## Required inputs

| 输入 | 必填 | 说明 |
| --- | --- | --- |
| 旧 URL 形状 | 是 | `?ui=v3` / `#/v3…` / `?ui=v2` / `#/story-builder…` |

## Authoritative interfaces

```text
UI           ui/src/App.tsx（归一化入口）
REST         GET /（同一入口）
Application  —
MCP          N/A
```

## Procedure

```text
1 用旧形状打开 URL（例如 /?ui=v3#/v3/novels）
2 期望：URL 被归一化，页面 = Story Studio（Landing 或 #/studio/n/<id>）
3 期望：0 page error、0 重定向循环
4 若旧 URL 带具体作品 / 视图信息且能安全映射 → 落到对应 Studio 位置，否则落到 Landing
5 next：navigate-studio-workspace
```

## Expected result

Story Studio 正常渲染；浏览器历史里没有循环跳转。

## Verification

```text
· node tests/browser_v4_legacy_entry.cjs（0 page error / 0 循环）
· 页面里不存在 V2/V3 专属控件
· 旧端点（`/api/story-builder/v3/**` 等）已不存在（404），且 UI 不依赖它们
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 白屏 | 归一化后没有可渲染视图 | 检查 `ui/dist` 是否最新构建 |
| 旧接口 404 被前端当作致命错误 | 前端残留旧调用 | 这是缺陷：记录到 `V4_0_1_SKILL_GAPS.md`，不要在前端加回退 |

## Safety / invariants

```text
不重建 V2/V3 路由、视图或数据投影
旧 URL 只做"进得来"，不承诺旧功能
frozen：不得因为兼容旧 URL 触碰 Canon / StoryState / legacy 源
```

## Side effects

可能重写浏览器地址与 history 状态（一次性）。

## Related skills

`open-story-studio`、`navigate-studio-workspace`

## Source references

```text
ui/src/App.tsx
tests/browser_v4_legacy_entry.cjs
docs/v4/V4_POST_RELEASE_CLEANUP_REPORT.md §9、§96b–§96h
```
