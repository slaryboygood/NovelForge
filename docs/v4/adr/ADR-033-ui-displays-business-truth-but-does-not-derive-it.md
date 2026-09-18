# ADR-033 UI Displays Business Truth But Does Not Derive It

> 状态：**Accepted**（V4-10 实施完成）
> 日期：2026-09-18
> 阶段：V4-10 Story Studio UI
> 相关：ADR-001（canonical service layer）、ADR-018（质量是门禁）、ADR-027（MCP 是 adapter）、
> `docs/v4/V4_UI_CONTRACT.md`

## 背景

UI 是最容易「顺手实现一遍业务规则」的地方：前端算进度、前端判断 PASS、前端推断
accepted、前端决定交付是否可行、前端猜 repair scope。V3 已经出现过同类问题
（`ui_flow` 与 `journey_service` 两套 stage 公式 = NF-005）。

## 决策

```text
UI  →  HTTP API  →  Application Services  →  V4 modules
```

UI **只能**展示后端返回的真相，并调用后端动作。UI 不得：

```text
derive quality                  （不看 severity 自己判 PASS/FAIL）
derive acceptance               （不从 status/quality 推断作者已接受）
derive delivery eligibility     （必须读 preflight 结果）
derive repair scope             （必须读 plan_repair 输出）
derive story truth              （不拼 Canon / StoryState / revision）
read files / call Python / call MCP internally / import business modules
```

落地方式：

1. 单一 HTTP 客户端：`ui/src/api/studio.ts`（feature 组件禁止直接 `fetch`）。
2. 单一状态语义表：`ui/src/studio/design/status.ts`（`UI_STATUS_MAP`）。
3. 单一错误映射表：`ui/src/studio/design/errors.ts`（稳定 code → 作者语言）。
4. 父节点解析等结构性决策由 Host 契约给出（`StudioShell.generate` 先 `nodes.reload()`
   再按 generation task 契约解析；2+ 候选要求作者选择）。
5. 前端只做「显示派生」（格式化、分组、diff 高亮），不做业务派生。

## 备选方案

| 方案 | 否决理由 |
| --- | --- |
| 前端缓存 + 本地推导进度/下一步 | 会出现第二套公式（V3 已发生过） |
| 前端根据 issue severity 判断能否交付 | 交付资格属于 DeliveryService + policy |
| 前端自己算 repair 影响面 | 修复范围属于 RepairPlanner 契约 |
| UI 走 MCP 调自己的后端 | MCP 与 REST 是**平级 adapter**（ADR-027） |

## 后果

```text
正面
  · 后端契约是唯一真相；UI 可替换（Studio 与未来 UI 共用同一 API）
  · 错误语义稳定：同一 code 在所有页面同一文案
  · 状态语义统一：icon + text + shape，不只靠颜色
负面 / 约束
  · 每个新 UI 能力都需要一个明确的 REST/Application facade（不允许 UI 自己造）
  · 需要防止「顺手加个前端计算」——由 UI Contract 与本 ADR 约束
```

## 验证

```text
tests/v4/isolation/test_plugin_boundaries.py / test_mcp_boundaries.py（interfaces 不 import 业务）
ui/src/studio/design/errors.test.ts / status.test.tsx / nav.test.ts（语义冻结）
ui/src/api/studio.test.ts（wire contract：expected_revision / parent_id / index / dry_run）
tests/browser_v4_studio_golden.cjs（preflight / repair preview / conflict 全部来自后端）
```
