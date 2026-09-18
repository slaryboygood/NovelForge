# NovelForge V4-10 — Story Studio 阶段状态（过程记录）

> 状态：**SUPERSEDED —— 已被 `docs/v4/V4_10_STORY_STUDIO_REPORT.md` 取代**
> 当前唯一有效状态来源 = [V4_10_STORY_STUDIO_REPORT.md](V4_10_STORY_STUDIO_REPORT.md)（**V4-10 = PASS**）。
> 本文件保留为过程记录（记录 blocker 定位与修复路径），不再代表最新状态。
>
> 历史状态（已被取代）：`V4-10 = BLOCKED（进行中，未完成）`
> 分支：`v4-10-story-studio-ui`（integration）
> 契约：`docs/v4/V4_UI_CONTRACT.md`（已冻结）；盘点：`docs/v4/V4_10_UI_INVENTORY.md`
> 本文件是**接续点记录**；最终 41 节报告（`V4_10_STORY_STUDIO_REPORT.md`）在门禁全绿后写。

## 1. 已完成（有证据）

契约 / 盘点：

```text
docs/v4/V4_10_UI_INVENTORY.md   既有 UI → backend → V4 action 全量盘点（含 legacy 移除条件）
docs/v4/V4_UI_CONTRACT.md       IA / 路由深链接 / UI_STATUS_MAP / backend 映射 /
                                错误映射 / 视觉规则 / 插件信任语义（SSOT）
```

后端 facade（只经 application services）：

```text
src/novelforge/api/studio_routes.py    overview / blueprint / generate /
                                       quality(evaluate·repair·verify) /
                                       delivery/formats / plugins（只读）
src/novelforge/api/app.py              create_app(...)：注入 gateway / plugin_host /
                                       registry；UI 构建物来自仓库；legacy catalog 来自仓库
src/novelforge/api/delivery_routes.py  交付路由注入 exporter registry（插件格式可选择）
tests/studio/**                        11 项 REST facade 测试（含插件格式 / 错误码 / 无泄漏）
```

前端（Story Studio）：

```text
ui/src/studio/**       shell + 导航 + Overview + 创造/世界/人物/故事/场景工作区 +
                       节点抽屉（编辑 / AI 改写预览 / Diff / 历史 / 恢复 / 接受拒绝 /
                       冲突面板）+ Quality Center + 修复预览 + 交付 + 插件只读页
ui/src/api/studio.ts   唯一 HTTP 客户端与 DTO 来源
ui/src/studio/design/** UI_STATUS_MAP / 错误映射 / 字段词典（作者语言）
ui/src/App.tsx         Story Studio 为默认产品面；?ui=v3 / ?ui=v2 保留兼容
```

浏览器门禁环境（V4-07 缺口已解除）：

```text
playwright 已装（ui devDependency），用本机 Edge（chromium channel）可 headless 运行
scripts/studio_ui_test_server.py   隔离数据根 + stub 模型（零网络）+ fixture 插件
                                   + 干净作品（可交付）种子
tests/browser_v4_studio_golden.cjs 生成 / 编辑 / Diff / 接受 / 冲突 / 质量 / 修复预览 /
                                   交付下载（Markdown·DOCX·nfpack）/ 插件 / 四视口
```

已验证结果：

```text
ui build（tsc -b && vite build）            PASS
pytest -q tests/studio                    11 passed
pytest -q tests/delivery tests/editor    170 passed（registry 注入未破坏既有行为）
浏览器门禁                                部分通过：landing → 新建作品 → overview →
  premise/world/character/story_arc/structural_unit/chapter 生成 → 场景抽屉 →
  字段编辑 → 保存新版本 → Diff → 接受 → 冲突面板
  未通过点：生成 scene 后 scenes 工作区等待 node-card 超时
```

## 2. 唯一阻塞点（下一接续点）

```text
现象：gate 在 scenes 工作区等待 [data-testid^="node-card-"] 超时。
定位：POST /studio/generate {task: "scene"} 未成功 —— scene 需要 chapter 父节点，
      前台用 shell 里的 blueprintNodes 解析父节点；chapter 生成后若 nodes 尚未刷新，
      parent_id 为空 → 后端 BLUEPRINT_VALIDATION_FAILED。
下一步（按顺序）：
  1. StudioShell.generate：需要父节点的任务在解析父节点前先 await nodes.reload()，
     或在 scene 生成时显式传 chapter id。
  2. 重跑 gate，继续完成 quality / repair 执行 / delivery 下载 / 四视口断言。
  3. V3 门禁入口同步为 ?ui=v3（V3 现在是兼容入口）。
  4. 写 V4_10_STORY_STUDIO_REPORT.md（41 节）+ 更新 V4_MODULE_BOUNDARIES /
     V4_DELETION_PLAN / V4_ARCHITECTURE_RISKS + ADR-032·033 + 视觉对照截图。
```

## 3. 明确的偏差与风险（必须写进最终报告）

| 项 | 事实 | 处理 |
| --- | --- | --- |
| `UI标准.*` | 仓库根目录不存在该参考图（V3 验收已记录裁定：视觉基准 = 产品 Design System + 6 个默认美术 + 四视口渲染） | 已在 UI Contract §2 记录采用 / 调整项；作者若补图，只需替换 tokens 与卡片样式 |
| V3 工作台 | 不再是默认入口（Studio 为默认）；V3 门禁脚本需改用 `?ui=v3` | 待续（§2 第 3 步） |
| 前端单元测试框架 | 项目原本没有 unit/component 运行器（只有 dev/build/preview） | 需补 vitest + @testing-library/react 并新增组件测试 |
| 插件 enable/disable | V4-09 未开放 operator 边界 → 插件页只读 | 已按任务书 §53 选择方案 A |
