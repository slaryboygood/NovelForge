# ADR-032 Story Studio Is The Primary V4 Product Surface

> 状态：**Accepted**（V4-10 实施完成）
> 日期：2026-09-18
> 阶段：V4-10 Story Studio UI
> 相关：ADR-011（Story Blueprint 是主产物）、ADR-027（MCP 是 adapter）、
> `docs/v4/V4_UI_CONTRACT.md`、`docs/v4/V4_10_UI_INVENTORY.md`

## 背景

V4-01→V4-09 已经落地 Blueprint / Quality / Editor / Delivery / MCP / Plugin 六套能力，
但它们此前只通过 V3 工作台（`ui/src/v3/**`）与 V2 面板（`ui/src/*.tsx`）间接暴露：
V3 界面围绕「阶段 + 目标」组织，V2 面板围绕「会话 + 大纲」组织，两者都不是
Story Blueprint 的产品模型。

同时存在三个产品面的进入方式冲突：默认 URL 曾经指向 V3；V2 依赖 `?ui=v2`。

## 决策

```text
Story Studio（ui/src/studio/**）是 V4 的默认产品面；
V3 / V2 是**显式兼容入口**，不再是默认。
```

```text
/                     → Story Studio（默认）
?ui=v3 / #/v3...      → V3 工作台（兼容）
?ui=v2 / #/story-builder?... → V2 面板（兼容）
```

规则：

1. Story Studio 直接表达 Story Blueprint 产品模型（创造 / 世界 / 人物 / 故事 / 场景 / 检查 + 交付 / 插件）。
2. 兼容入口必须是**显式参数或显式 hash**；默认 URL 不得渲染 V3/V2 外壳
   （由 `tests/browser_v4_legacy_entry.cjs` 验证）。
3. 旧界面与旧后端端点**保留**，直到其真实消费者退出（见 ADR-007 / V4_DELETION_PLAN）。
4. 兼容入口只允许改「启动参数」，不允许改旧验收断言与业务期待。

## 备选方案

| 方案 | 否决理由 |
| --- | --- |
| 保留 V3 为默认、Studio 放在 `#/studio` | 主产品面仍是「阶段 + 大纲」模型，与 Blueprint 产品模型不一致 |
| 直接删除 V3/V2 界面 | 仍有真实兼容消费者（高级工具 / 旧验收 / 正文与 outline 产品面），删除条件未满足 |
| 让 V3/V2 与 Studio 并行且都默认 | 无法判断作者看到的是哪个产品模型；深链接语义冲突 |

## 后果

```text
正面
  · 作者第一次打开就是 Story Blueprint 工作流（ADR-119 验收问题得到回答）
  · 兼容面显式化：不会「莫名其妙进了旧界面」
  · 旧后端与旧验收未被削弱，历史证据仍可复现
负面 / 约束
  · V3/V2 门禁必须带入口参数（已同步：8 个 V3 + 4 个 V2 脚本）
  · V3/V2 的深度联调需要作者验收数据根（本环境缺失，见最终报告 §26）
```

## 验证

```text
tests/browser_v4_legacy_entry.cjs      默认→Studio；?ui=v3→V3；?ui=v2→V2；无页面错误
tests/browser_v4_studio_golden.cjs     Story Studio 主流程 + 4 视口
tests/browser_v3_*.cjs / browser_creator_*.cjs  入口已显式化（断言未改）
```
