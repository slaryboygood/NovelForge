---
name: novelforge-v4.0.1.studio.open-story-studio
description: 启动并打开 NovelForge V4.0.1 Story Studio（后端 + 已构建前端），确认产品面可用。
---

# open-story-studio

- **Skill ID**: `novelforge-v4.0.1.studio.open-story-studio`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `studio`
- **Product owner**: `scripts/start_novelforge_ui.py` + `ui/src/studio/StudioApp.tsx`

## Purpose

用一条命令起「后端 + 已构建前端」，得到可操作的 Story Studio。

## Use when

- 需要人工（或浏览器门禁）验证产品面。
- 需要对照 UI 行为确认 REST 语义。

## Do not use when

- 只做机器调用 → 直接用 REST 或 MCP（不需要起 UI）。
- 需要重建前端类型检查 / 构建 → 见 `Verification`。

## Preconditions

```text
· Python 3.11 venv 已装依赖（scripts/bootstrap_dev.ps1）
· Node 18+（首次 --rebuild-ui 时需要 ui/node_modules）
```

## Required inputs

| 输入 | 必填 | 说明 |
| --- | --- | --- |
| `--port` | 否 | 默认端口由启动脚本决定（README 示例 8000） |
| `--root` | 否 | 项目根（默认当前仓库根） |
| `--rebuild-ui` | 否 | 首次 / 前端改动后构建 `ui/dist` |

## Authoritative interfaces

```text
UI           http://127.0.0.1:<port>/ → Story Studio Landing（#/studio）
REST         GET /（返回前端）、GET /api/health
Application  —
MCP          N/A
```

## Procedure

```text
1 .venv\Scripts\python.exe scripts/start_novelforge_ui.py --rebuild-ui
2 open http://127.0.0.1:<port>/
3 expect: Landing → 作品卡列表（或空态「新建作品」）
4 expect: 无 console error、无重定向循环
5 next：inspect-overview（选作品后）或 create-novel（空态）
```

## Expected result

Landing 渲染成功；`GET /api/health` 正常；`GET /api/story-builder/novels` 返回列表。

## Verification

```text
· GET /api/health 正常
· 浏览器标签标题 / 一级导航文案与 V4_UI_CONTRACT §3 一致
· 前端门禁：npm.cmd --prefix ui test（vitest）与 npm.cmd run build --prefix ui
· 浏览器 golden：node tests/browser_v4_studio_golden.cjs（需要 stub 模型 server）
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 首页空白 | `ui/dist` 未构建 | 加 `--rebuild-ui` |
| 端口占用 | 已有实例 | 换 `--port` |
| 生成报 `GENERATION_UNAVAILABLE` | 未启用 provider（默认行为） | 见 `ai/configure-llm-provider` 或视为预期 |

## Safety / invariants

```text
默认不启用任何模型 provider（不会悄悄产生真实 API 花费）
UI 只展示后端真相，不推导结论
旧产品面（V2/V3）不再被加载 —— 不要尝试恢复
```

## Side effects

构建 `ui/dist`（gitignored）、启动本地 HTTP 服务、可能创建测试用 workspace 根。

## Related skills

`navigate-studio-workspace`、`inspect-overview`、`handle-legacy-url`

## Source references

```text
scripts/start_novelforge_ui.py
ui/src/main.tsx、ui/src/App.tsx、ui/src/studio/StudioApp.tsx
docs/v4/V4_UI_CONTRACT.md
tests/browser_v4_studio_golden.cjs
```
