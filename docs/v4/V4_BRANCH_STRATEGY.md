# NovelForge V4 — Branch Strategy

> 状态：**V4-01 Boundary Foundation**
> 依据：`docs/NOVELFORGE_V4_MASTER_PLAN.md` §12–13、§42、§43；`docs/v4/V4_MODULE_BOUNDARIES.md`

---

## 1. 为什么不用 `v4/...` 层级分支

```text
远端已存在 origin/v4（V4 集成分支，当前与 main 同一 commit）。
Git ref 不能同时存在 refs/heads/v4 与 refs/heads/v4/<name>（文件 / 目录冲突）。

→ V4 全部阶段使用扁平命名：v4-NN-<module>-<topic>
```

历史事实：V4-00 期间曾创建 `v4/00-architecture`（当时通过删除本地 `v4` 引用实现，
`origin/v4` 未受影响）。V4-01 起统一使用扁平命名。

---

## 2. 分支命名表

| 阶段 | 主模块 | 分支 |
| --- | --- | --- |
| V4-01 | Boundary | `v4-01-boundary-foundation`（当前） |
| V4-02 | LLM | `v4-02-llm-gateway` |
| V4-03 | Memory | `v4-03-memory-canon`、`v4-03-memory-context-builder` |
| V4-04 | Blueprint | `v4-04-blueprint-generation` |
| V4-05 | Quality | `v4-05-quality-causality`、`v4-05-quality-continuity`、`v4-05-repair` |
| V4-06 | Editor | `v4-06-blueprint-editor` |
| V4-07 | Delivery | `v4-07-delivery` |
| V4-08 | MCP | `v4-08-mcp-resources`、`v4-08-mcp-tools` |
| V4-09 | Plugins | `v4-09-plugins` |
| V4-10 | UI | `v4-10-ui` |
| V4-11 | Agent | `v4-11-agent` |

跨模块集成使用短生命周期分支：

```text
v4-int-memory-blueprint
v4-int-quality-repair
v4-int-mcp-services
```

---

## 3. 每个任务分支开始前必须声明

```text
Primary Module        主模块（一个）
Primary Paths         主要维护路径
Allowed Shared Paths  允许同时触碰的共享路径（越少越好）
Forbidden Paths       明确禁止触碰的路径（含 frozen truth）
Required Contracts    依赖 / 需要修改的 Contract
Expected Tests        预期新增或运行的测试
```

模板：

```text
Module   : ai
Primary  : src/novelforge/ai/**
Shared   : docs/v4/V4_LLM_CONTRACT.md
Forbidden: src/novelforge/story_engine/canon/**, tests/test_v2_frozen_guard.py,
           docs/FROZEN_EVIDENCE_MANIFEST.json, novel/authoring/**
Contracts: GenerationContract / ModelPolicy（新增）
Tests    : tests/test_ai_gateway.py, tests/test_ai_provider_offline.py
```

---

## 4. 分支规则

```text
1. 一个分支主要维护一个模块；跨模块必须先改 Contract（单独 commit）
2. 禁止一个分支"顺手"改多个模块内部实现
3. 分支基于 main（或已合入的 V4 集成分支）；基线必须包含 V4-01 边界
4. 分支不得修改：
     refs/tags/novelforge-product-v3-final
     docs/FROZEN_EVIDENCE_MANIFEST.json（除非作者明确要求）
     novel/authoring/**（frozen tracked data）
5. 每个分支结束必须通过：
     pytest（默认套件）
     scripts/validate_project.py
     tests/v4/isolation/**（V4-01 起的永久隔离测试）
     V2 Frozen Guard
6. 不合入 main 之前不得删除其他分支；不 force-push 共享分支
```

---

## 5. 并行开发的最小隔离要求

```text
模块测试不得依赖：
  · 其他模块的内部实现
  · 真实 historical / 旧正文资产（V4-01 起已删除）
  · 本机作者数据（novel/authoring/**、workspace/**）

每个模块的测试根：tests/<module>/
共享 fixture：tests/fixtures/（必须最小、显式归属、可重复生成）
跨模块 E2E：tests/e2e/（单独标记，不阻塞单模块开发）
```

---

## 6. 提交信息约定

```text
docs(v4):     V4 文档 / ADR / 边界声明
chore(v4):    资产删除、仓库卫生
refactor(v4): 边界迁移、参数化、收编（不改变外部行为）
feat(v4):     新能力（带 Contract + 测试）
test(v4):     测试与守卫
fix(v4):      缺陷修复
```

每个提交都必须保持：`pytest` 默认套件可运行、无 frozen boundary 变更。

