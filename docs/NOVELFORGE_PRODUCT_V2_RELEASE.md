# NovelForge Product V2 — Release / Handoff

```text
product      = NovelForge Product V2
status       = RELEASED
freeze       = FROZEN（NOVELFORGE_PRODUCT_V2_FREEZE.json）
release_tag  = novelforge-product-v2.0
tag_status   = historical / archived / not an active Git ref
               （V3 Final 之后活动仓库只保留 novelforge-product-v3-final；
                 本 tag 的 commit 与字节级历史由外部 bundle
                 NovelForge_pre_V4_full_history.bundle 承载）
release_date = 2026-09-15
M0–M18       = COMPLETE
M18         = PRODUCT FINAL ACCEPTANCE = PASS
next_state   = PRODUCT_V2_COMPLETE（M19 未创建）
```

M18 最终验收 commit：`46d88e576e1278ee11cdd860164d9ad3d4f19547`；
release commit = `56cda829d812d95f65cb282e0c85328792f6d9cd`（当时由
`novelforge-product-v2.0` 指向；该 tag 现已归档为
historical / archived / not an active Git ref，仅作历史记录）。
除 release manifest / handoff 文档 / 历史标注外无产品代码或 truth 变更。

## What is released

一套通用的小说创作产品链：**创意 → 设定 → 设定自检 → 推演（StoryState）→ 路线试演 →
四级大纲 → 导出（Planning Export）→ Writer context / 草稿 / 事实提议**，
外加 2D 可视化、Canon 检查器、修复中心与跨题材复用（3 题材已验证）。

详细能力清单见 `workspace/wasteland_001_exports/repair_adoption_v1/m18/M18_PRODUCT_CAPABILITY_MATRIX.json`
（本地验收证据，不进版本控制）；V2 兼容边界见 `docs/LEGACY_COMPAT.md`。

## How to run

```powershell
.venv\Scripts\python.exe scripts/start_novelforge_ui.py --rebuild-ui
# 打开 http://127.0.0.1:8000/

# 隔离测试服务（不接触作者数据）
.venv\Scripts\python.exe scripts/creator_ui_test_server.py --port 8020 --root workspace/creator_ui_test
```

## How to test

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe scripts/validate_project.py
npm.cmd run build --prefix ui

# V2 里程碑验收（跨题材 E2E / M18 最终验收）需要本机历史数据，默认不运行：
.venv\Scripts\python.exe -m pytest -m historical_acceptance -q
```

## Release manifest

```text
workspace/wasteland_001_exports/repair_adoption_v1/m18/NOVELFORGE_PRODUCT_V2_RELEASE.json
```

manifest 为 deterministic（不含生成时间）：在同一个 commit 上重复生成字节一致。

```powershell
.venv\Scripts\python.exe -c "from pathlib import Path; from novelforge.story_engine.m18_final_acceptance import M18FinalAcceptanceService; M18FinalAcceptanceService(Path('.').resolve()).release_manifest()"
```

记录内容：product / status / freeze / release_tag / final_commit / release_date、
`m0_m18_complete`、final acceptance、verification（pytest · validate_project · UI build ·
browser acceptance · cross-genre E2E · crash-resume · capability matrix）、truth digests
（Canon / StoryState / legacy / source IR / Historical Foundation）、frozen digests
（Repair Contract / `REPAIR_GATE_V1`）、`blocking_debt = 0`、`non_blocking_debt`、`next_state`。

## Canonical author workflow

```text
1) 新建小说（选择内容包 / 题材模板）
2) 引导流：一句创意 → 方向候选 → 设定候选（可改写 / 换一批）→ 设定自检 → 开始推演
3) 创作者面板：世界 / 角色 / 剧情 / 成长 / 记忆 / 导演（全部来自 StoryState）
4) 产出：路线实验室（fork / 对比 / 合并 / 冻结）→ 大纲锻造（四级大纲）→ 大纲联动（版本 / 影响）
5) 可视化：设定总览 / 区域卡片 / 关系网 / 路线对比 / 大纲结构树 / 风格参考位
6) 检查与修复：Canon 检查器（只读 + 出处）；修复中心（诊断 → 预览 → 审批要求 → 执行 → 历史）
7) 导出 / 写作：Planning Export（json / markdown / docx）、Writer context / 草稿、
   事实提议（sync-facts，全部为 PROPOSED）
```

## Key architecture boundaries

```text
UI → API → Application → Domain（单向）
UI 不解析 Canon / 不判断 StoryState truth / 不读 repair artifact
Application 统一提供投影：ui_flow / inspector / export_package / writer_integration / cross_genre_e2e
引擎内不得出现题材分支（源码守卫：tests/test_story_engine_cross_genre.py、test_story_engine_templates.py）
```

## Frozen truth rules

```text
occurred（Canon / StoryState）唯一权威，不被 planning / export / writer 写入
historical repair（M11/M12 lineage）≠ Canon source
preview（writer 草稿 / 提议）≠ committed truth
export 只读投影 ≠ 事实写入
M11–M18 验收 artifact 与 phase snapshot（write-once + digest）为 frozen 输入，不得修改
```

当前 digest（release manifest 同步记录）：

```text
Canon 73836dada9d6bf8e / StoryState bbc67137eefb9c55 /
legacy cc144c76796d6a4c / source IR 2eaac16d66e39421 /
Contract 67559aa55442d69e / Gate e1eab4c33ae75b01
```

## Known non-blocking debt

| debt | classification | 说明 |
| --- | --- | --- |
| `COMPILER_CRASH_RESUME_INTERMITTENT` | HISTORICAL | 编译器 crash/resume 用例曾在 full suite 偶发失败，无法稳定复现；已有 3 轮循环 regression 兜底 |
| `M16_EXPORT_WRITER_NO_UI` | OPTIONAL | 导出 / Writer 目前只有 application / API 入口（repo 未要求 UI） |
| `LIVE_ANALYSIS_PHASE_SCOPED_DIR` | OPTIONAL | live analysis artifact 的 phase-scoped 目录化 |
| `REPAIR_CENTER_MORE_TYPES` | OPTIONAL | 修复中心目前只执行 settings/check 类兜底 |

`blocking_debt = 0`。

## Where future work starts

```text
NovelForge Product V2 已 frozen：不要在其上追加 M19，也不要直接扩 scope。

任何新产品需求：
  1) 作为独立 initiative / Product V3 planning 立项（独立文档与 roadmap）
  2) 独立 scope + 独立 acceptance criteria
  3) 不得修改 V2 的 frozen truth / acceptance artifact

已登记但未立项的候选（future candidates，非承诺）：
  W6 P2（3D / 图像 / 动画）、Export 与 Writer 的 UI 面板、更多 Repair Center 类型、
  长线章节生产能力扩展
```
