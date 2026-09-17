# ADR-009 — Plugin DB Isolation

```
Status   : Proposed
Date     : 2026-09-17
Context  : V4-00 Architecture
Related  : V4_PLUGIN_SPEC.md；ADR-001；V4_ARCHITECTURE_RISKS.md R-12
```

## Context

V4 计划引入插件扩展点。当前全部扩展需求都由数据配置满足：

```text
novel/config/story_engine/*.json        题材模板 / 内容包
novel/config/story_builder/step_catalogs.yaml  十步目录
```

只有「导出格式 / 质量规则 / 模型 provider / 生成器」需要代码级扩展。
一旦允许插件访问核心存储，就会出现：绕过质量门、改写事实、破坏 frozen 证据、
静默覆盖其他插件能力等风险。

## Decision

1. 插件只能获得 `PluginHost`（只读资源 + service 调用 + capability 注册 + propose），
   **不得获得** repository、文件句柄、数据库连接或 gateway override。
2. 插件必须声明 capability 与 permission；未声明的能力注册被拒绝。
3. 插件不得改变 Quality Gate 的 severity 与放行规则（只能新增规则）。
4. 插件产生的 artifact 必须带 plugin_id + version + api_version。
5. V4-09 只实现 3 类（Exporter / Evaluator / ModelProvider），其余 Deferred。

## Consequences

正面：从结构上（而非仅评审上）保证插件无法修改核心数据。

代价：插件能力受限，某些「深度集成」类需求需要走核心代码变更流程。

## Alternatives considered

| 方案 | 为什么不选 |
| --- | --- |
| 给插件 repository 但靠 review 约束 | 无法机械验证；一次失误即可破坏 frozen 证据 |
| 在独立进程运行插件（沙箱） | 当前单进程文件存储模型下复杂度过高，收益不足 |
| 不做插件，全部走核心代码 | 会让导出格式 / provider 的扩展长期阻塞在核心发布节奏上 |

## Evidence

```text
docs/LEGACY_COMPAT.md                       bridge 只跳转、不产生第二套业务规则（同类边界先例）
src/novelforge/story_engine/canon/repository.py  「唯一允许写 SQL 的地方」
tests/test_v2_frozen_guard.py                frozen 证据守卫（插件绝不可触及）
docs/v4/V4_PLUGIN_SPEC.md §1.1               插件真实需求清单（4 类）
```

