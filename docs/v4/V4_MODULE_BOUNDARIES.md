# NovelForge V4 — Module Boundaries（维护边界 SSOT）

> 状态：**V4-01 Boundary Foundation**
> 依据：`docs/NOVELFORGE_V4_MASTER_PLAN.md` §8–13、§43；`docs/v4/V4_ARCHITECTURE.md` §3–§4
> 定位：本文件是**物理目录与依赖边界的最终依据**。任何新模块、目录改名、跨模块导入都要先改这里，
> 再改代码（Master Plan §13：先 Contract，再适配）。

---

## 1. 一个模块的定义

```text
一个主要能力
  = 一个明确模块
  = 一个独立目录
  = 一组公开 Contract（`__init__.py` 或 `contract.py` 显式导出）
  = 一组独立测试（tests/<module>/ 或 tests/test_<module>_*.py）
  = 可由独立任务分支维护（见 V4_BRANCH_STRATEGY.md）
```

每个模块必须在本文件声明六项：

```text
Public Contract     可被其他模块依赖的符号
Internal            仅模块内可见（外部禁止 import）
Allowed Dependencies
Forbidden Dependencies
State Ownership     该模块拥有 / 不拥有什么状态
Module Tests
```

---

## 2. 模块清单（V4-01 快照）

`State` 含义：`EXISTS`（V3 已有，建立边界即可）/ `NEW`（V4-01 新建）/ `DEFERRED`（后续阶段）。

| Module | Module ID | Current Path | Target Path | State | Owner Phase |
| --- | --- | --- | --- | --- | --- |
| Core Primitives | `core` | `src/novelforge/models.py` | `src/novelforge/core/` | NEW（`revision` / `ids` / `errors`） | V4-01 |
| Application Services | `app-services` | `src/novelforge/story_builder/` | `src/novelforge/application/services/` | NEW（骨架 + 3 个服务） | V4-01 → V4-11 |
| Persistence | `persistence` | 散落于各模块的 `Path(...)` | `src/novelforge/persistence/` | NEW（`paths.py`） | V4-01 |
| Legacy Compatibility | `legacy` | `story_engine/m11_*.py` 等 | `src/novelforge/legacy/` | NEW（adapter + manifest） | V4-01 |
| Story Engine / Domain | `domain` | `src/novelforge/story_engine/` | 保持原位（不整体移动） | EXISTS | — |
| LLM Gateway | `ai` | `story_engine/spec/llm.py` | `src/novelforge/ai/` | DEFERRED | V4-02 |
| Story Memory | `memory` | 无（`story_engine/memory.py` 是知识事实，需改名） | `src/novelforge/memory/` | DEFERRED | V4-03 |
| Blueprint Generation | `blueprint-generation` | `story_engine/{creative,settings_gen,outline_forge,journey}.py` | `src/novelforge/generation/` | DEFERRED | V4-04 |
| Story Quality | `quality` | 9 处 validator / finding | `src/novelforge/quality/` | DEFERRED | V4-05 |
| Story Repair | `repair` | `story_engine/repair.py`（冻结历史用途） | `src/novelforge/quality/repair/` | DEFERRED | V4-05 |
| Blueprint Editor | `editor` | `story_builder/writer_integration.py` | `src/novelforge/editor/` | DEFERRED | V4-06 |
| Delivery / Export | `delivery` | `story_builder/export_package.py` | `application.services.export` | DEFERRED（V4-01 建 service 入口） | V4-07 |
| MCP Adapter | `mcp` | 无 | `src/novelforge/interfaces/mcp/` | DEFERRED | V4-08 |
| Plugin Platform | `plugins` | 无 | `src/novelforge/plugins/` | DEFERRED | V4-09 |
| Observability | `observability` | 无 | `src/novelforge/observability/` | DEFERRED | V4-02 → V4-07 |
| UI | `ui` | `ui/src/` | `ui/src/` | EXISTS | V4-10 |

> **V4-01 只落地 5 个边界**：`core` / `app-services` / `persistence` / `legacy` +
> 对 `domain`、`ui` 的只读边界声明。其余目录在对应阶段创建，避免"先建空壳"。

---

## 3. 逐模块边界声明

### 3.1 `core` — Core Primitives

```text
Public Contract
  core.ids       : new_id / slug / digest（语义稳定，无业务规则）
  core.errors    : NovelForgeError 基类 + 统一 error envelope
  core.revision  : RevisionRef / RevisionConflict / expected_revision 校验
Internal
  core/_internal/*
Allowed
  python stdlib, pydantic
Forbidden
  任何 story / canon / blueprint 业务规则
  任何 adapter（fastapi / mcp / provider / 文件系统）
State Ownership
  无（纯函数与数据类型）
Module Tests
  tests/test_core_revision.py、tests/test_core_ids.py
```

`core` 不是公共垃圾桶（Master Plan §11）。允许进入的条件：

```text
语义稳定 + 无模块所有权争议 + 不含故事业务规则 + 不依赖具体 Adapter
禁止：core/utils.py、core/helpers.py、core/manager.py
```

### 3.2 `app-services` — Application Services

```text
Public Contract
  application.services.journey : JourneyProjection（唯一进度 / 下一步投影）
  application.services.export  : ExportService（唯一导出出口）
  application.services.project : ProjectService（作品生命周期）
Internal
  application/_legacy_adapters/*（对既有 story_builder 的过渡包装）
Allowed
  domain(story_engine)、persistence、core、legacy（只读）
Forbidden
  interfaces(fastapi / mcp)、ai provider、直接文件路径常量、直接 SQL
State Ownership
  编排状态（会话 / 批次 / agent session），不拥有 story truth
Module Tests
  tests/test_service_journey.py、tests/test_service_export.py、tests/test_service_project.py
```

**边界规则**：接口层（`api/`、未来 `interfaces/mcp/`）只调用 `application.services`；
不得直接 import `story_engine.*`（V4-01 建立守卫测试，存量例外显式白名单）。

### 3.3 `persistence` — Persistence & Ownership

```text
Public Contract
  persistence.paths : ArtifactContext + 全部 artifact 路径解析（唯一来源）
Internal
  persistence/_backends/*
Allowed
  core, domain 模型定义, python stdlib
Forbidden
  interfaces / ai / ui；任何隐式"当前作品"
State Ownership
  物理存储（文件 / SQLite），不拥有业务语义
Module Tests
  tests/v4/isolation/test_ownership_isolation.py
  tests/v4/isolation/test_no_implicit_disk_discovery.py
```

硬规则：

```text
1. 路径解析必须显式携带 project_id / novel_id / artifact_kind
2. 禁止 GLOBAL_CURRENT_NOVEL、默认 wasteland_001、扫描磁盘猜当前作品
3. 禁止"当前作品无数据 → fallback 到其他作品 / 已删除历史数据"
4. 路径常量集中在 persistence.paths；其他模块不得自行拼路径
```

### 3.4 `domain` — Story Engine（原位保留）

```text
Public Contract
  story_engine.__init__ 已导出符号（state / actions / conditions / effects / resolver /
  events / foreshadow / progression / driver / director / canon / chapter_ir / planning /
  profile / templates / content ...）
Internal
  story_engine 内部未导出实现
Allowed
  python stdlib, pydantic, networkx, core
Forbidden
  fastapi, mcp, provider SDK / 任何 HTTP client, ui, persistence 反向依赖
State Ownership
  StoryState / Canon / ChapterIR / PlanningIR 的语义（不是物理存储）
Module Tests
  tests/test_story_engine_*.py、tests/test_story_planning_*.py、
  tests/test_canon_*.py、tests/test_chapter_ir_*.py
```

`domain` 在 V4-01 **不被移动**（Master Plan §40：不为目录整齐搬 frozen 代码）。

### 3.5 `legacy` — Legacy Compatibility Boundary

```text
Public Contract
  legacy.manifest : frozen module inventory（id / path / status / used_by / removal_condition）
  legacy.adapters : 对 frozen 能力的只读包装
Internal
  legacy/_vendor/*（未来真正迁入的 frozen 模块）
Allowed
  core, domain（只读调用）
Forbidden
  被新的写路径依赖；被 interfaces 直接暴露；持有可变业务状态
State Ownership
  无（只读视图）
Module Tests
  tests/v4/isolation/test_legacy_boundary.py
```

规则：

```text
1. frozen 模块在替换完成前原地保留，只通过 adapter 暴露
2. frozen 模块不得被新业务写路径 import（守卫测试）
3. 已删除的废弃数据（novel/final、570 章 historical）不进入 legacy/
4. 只有"仍需要兼容的能力"才进 legacy/；废弃能力直接删除
```

### 3.6 `ui`

```text
Public Contract      仅通过 HTTP API 消费后端能力（ui/src/v3/api.ts）
Allowed              REST API
Forbidden            直接推导业务事实、直接读写文件、复制后端质量 / 进度逻辑
State Ownership      纯展示状态（含 localStorage 设计态参考位）
Module Tests         tests/browser_*.cjs
```

---

## 4. 依赖矩阵（V4-01 生效部分）

`✓` 允许 / `✗` 禁止 / `△` 仅经显式 Contract。

| ↓依赖 / 被依赖→ | core | persistence | domain | app-services | legacy | interfaces | ui | ai | memory | quality |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `core` | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| `persistence` | ✓ | ✓ | ✓ | ✗ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ |
| `domain` | ✓ | ✗ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| `app-services` | ✓ | ✓ | ✓ | ✓ | △ | ✗ | ✗ | ✓ | ✓ | ✓ |
| `legacy` | ✓ | ✓ | ✓ | ✗ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ |
| `interfaces` | ✓ | ✗ | ✗ | ✓ | ✗ | ✓ | ✗ | ✗ | ✗ | ✗ |
| `ui` | ✗ | ✗ | ✗ | ✗ | ✗ | ✓(HTTP) | ✓ | ✗ | ✗ | ✗ |
| `ai` | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ | ✗ | ✗ |
| `memory` | ✓ | △ | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ | ✓ | ✗ |
| `quality` | ✓ | △ | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ | ✓ | ✓ |

### 4.1 明文禁令

```text
domain       → 不允许 import fastapi / mcp / httpx / urllib / openai / anthropic
domain       → 不允许 import persistence（路径解析在 domain 之外）
interfaces   → 不允许 import domain（必须经 app-services）
persistence  → 不允许 import app-services / interfaces / ai
legacy       → 不允许被 app-services 之外的模块 import
ui           → 不允许 import 任何 Python 模块（只走 HTTP）
```

### 4.2 守卫测试

```text
tests/v4/isolation/test_module_boundaries.py
  · 扫描 src/ 的 import 图，断言上表禁例
  · 存量例外以显式白名单登记（V4-01 白名单 = 现状快照，后续只减不增）
```

---

## 5. 新增模块的申请流程

```text
1. 在本文件登记：Module / Path / Public Contract / Allowed / Forbidden / Tests
2. 先提交 Contract（单独 commit）
3. 再提交实现
4. 补模块测试（Unit / Contract / Integration / E2E 按需）
5. 跨模块变更按 Master Plan §13：先 Contract，再分别适配
```

---

## 6. 与 V4-00 目录提案的差异

| V4-00 提案 | V4-01 实际 | 原因 |
| --- | --- | --- |
| `application/services/*` 一次性搬迁 | 先建骨架 + 3 个服务（journey / export / project） | Strangler：1,545 行路由不一次性重写 |
| `domain/*` 重命名 | 保持 `story_engine/` 不动 | 不为目录整齐移动 frozen 代码（Master Plan §40） |
| `generation/*`（6 模块） | 推迟到 V4-04 | 生成能力尚未接 LLM，先不建空壳 |
| `quality/*`、`memory/*`、`ai/*` | 推迟到 V4-02 / V4-03 / V4-05 | 同上 |
| `legacy/*` 隔离区 | **V4-01 建立** | 需要明确表达"哪些 frozen 代码仍被兼容使用" |
| `persistence/paths.py` | **V4-01 建立** | ownership 是所有后续模块的前提 |

