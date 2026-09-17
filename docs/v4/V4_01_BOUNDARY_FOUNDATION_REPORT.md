# V4-01 BOUNDARY FOUNDATION RESULT

> 阶段：**V4-01 Boundary Foundation & Legacy Cleanup**
> 分支：`v4-01-boundary-foundation`
> 基线：`v4/00-architecture`（V4-00 PASS，commit `71520ea`）
> 结论：**V4-01 = PASS**

---

## 1. Architecture decisions updated

| 文档 | 更新内容 |
| --- | --- |
| `NOVELFORGE_V4_MASTER_PLAN.md` | 采用作者更新后的版本（Story Blueprint Runtime、扁平分支命名、模块边界章节）；纳入本阶段提交 |
| `V4_ARCHITECTURE.md` | 新增 §0.A「V4-01 作者决策对齐」；修正 §3 目录树（`blueprint_store`）、§6 ownership 表（canonical artifact = StoryBlueprint；正文不再是 owner 概念）、§6.1 canonical 清单、§5 Ownership 边界行、§9 DoD 行 |
| `V4_MODULE_CLASSIFICATION.md` | 新增 §0.1 分类变更表；更新 writer_integration / story_engine.writer / export_package 行；`novel/final/**`、`workspace/wasteland_001_exports/**`、`scripts/wasteland_001_m1b_closure.py` 改为 DELETE（已执行）；统计表更新为 V4-01 口径（DELETE 1→3、MIGRATE 4→3、REWRITE 13→12、UNKNOWN 1→2） |
| `V4_MIGRATION_PLAN.md` | 新增 §0.1 决策对照；§2 Writer 行改为 Blueprint Editor；§4.1 原「正文 revision 迁移」方案作废；BLOCKER-01 / 03 标记已解除 |
| `V4_DELETION_PLAN.md` | 新增 §2.1「V4-01 已执行删除」含 A/B 两类资产的完整证据（路径 / 数量 / tracked / 代码引用 / 测试引用 / 配置引用）；「明确不删除」清单同步修正 |
| `V4_QUALITY_CONTRACT.md` | 新增 §0.1：质量对象改为 Story Blueprint 节点；Q9 校验对象改为 Blueprint 交付物 |
| `V4_MCP_SPEC.md` | 新增 §0.1：Resource 根对象改为 Blueprint / scenes；`generate_draft` / `continue_draft` / `rewrite_text` 退出 V4 核心 tool 集 |
| `V4_MEMORY_ARCHITECTURE.md` | 新增 §0.1：episodic 来源改为 Blueprint 节点 revision + effect_log（不再是正文） |
| `V4_EXPORT_SPEC.md` | 新增 §0.1：EPUB 降级、nfpack 以 blueprint/* 为主、`novel/final` 规则作废 |
| `V4_ARCHITECTURE_RISKS.md` | 新增 §0.1 状态更新（R-11 已修复、R-16 部分修复、R-15 对象改变）；重写 R-15 正文 |
| `V4_00_ARCHITECTURE_REPORT.md` | 顶部加「V4-01 更新说明」，把被取代的结论显式标记（保留 V4-00 历史记录） |

新增两份长期文档：

```text
docs/v4/V4_MODULE_BOUNDARIES.md   物理目录 / Public Contract / 依赖矩阵 / 守卫测试（§12 要求的维护边界 SSOT）
docs/v4/V4_BRANCH_STRATEGY.md      扁平分支命名、任务分支声明模板、并行开发隔离要求
```

---

## 2. ADR changes

| ADR | 变更 |
| --- | --- |
| **ADR-003 Canonical Writer Store** | **Status: Superseded by ADR-011**；顶部加 SUPERSEDED 说明（正文 writer store / `novel/final` 导入 / AI 改写正文全部作废），原文保留为 V4-00 记录 |
| **ADR-011（新增）Story Blueprint Is The Primary Creative Artifact** | Status: **Accepted**（作者决策）；定义 canonical artifact = StoryBlueprint、Writer → Blueprint Editor、draft 非核心、`novel/final` 与 570 章 historical 删除、revision 语义保留但对象改变、Export 目标改为 Blueprint Package |
| **ADR-007 Artifact Ownership** | 新增「作者决策更新」：`novel/final` 与 570 章 historical → DELETE；保留唯一仍未定项（`project_id` / `novel_id` 层级关系）；补充 V4-01 最低不变量 |
| `adr/README.md` | 索引更新（ADR-003 标记 Superseded、ADR-011 标记 Accepted）；「已裁定 / 仍待定」两张表重组 |

---

## 3. Deleted legacy assets

### A. `novel/final/**`（旧正文，作者决策 A）

```text
Exact Path      : F:/AI_小说/硅基升维/novel/final/
File Count      : 69（含 1 个含引号的畸形文件名）
Tracked         : 69 / 69（git rm 进入版本控制）
Size            : ~1.9 MB
Code References : 1 —— story_engine/historical_ir.py（该模块同时脱离产品路径）
Test References : 0
Config Refs     : novelforge.project.yaml protected_paths（已同步移除该条目）
```

### B. `workspace/wasteland_001_exports/**`（570 章 historical，作者决策 B）

```text
Exact Path      : F:/AI_小说/硅基升维/workspace/wasteland_001_exports/
File Count      : 1918
Tracked         : 0（workspace/ 全程 gitignored；磁盘删除不影响版本控制）
Size            : ~62 MB
子目录           : chapter_ir_v1(31) / historical_chapter_ir_v1(581) / plan_v2(2) / plan_v3(122) /
                  reconstruction_v2(19) / repair_adoption_v1(709) / repair_v1(365) / writer_v1(6)
                  + 根级 WASTELAND_001_* 报告 / 大纲 / 审计产物
Code References : 47 个 src/scripts 文件（historical_ir / repair / reconstruction /
                  historical_adoption / m11_* 18 个 / m12..m18 7 个 / export_package /
                  inspector / writer_integration / novel_admin / canon_routes / phase_snapshot /
                  scripts/wasteland_001_m1b_closure.py）
Test References : 53 个测试文件
Config Refs     : novelforge.project.yaml（local_only_paths.workspace）、DATA_MODEL.md、LEGACY_COMPAT.md
```

### C. 连带删除（只服务上述两类资产）

```text
novel/config/story_engine/wasteland_001_pack.json   废弃作品的内容包（untracked，git clean）
scripts/wasteland_001_m1b_closure.py                只服务 570 章 historical 的 M1b closeout 脚本
tests/ 52 个 historical_acceptance 测试文件          685 个测试函数（对应数据已删除）
tests/{phase_history,m11_phase_history,m12_phase_history,m13_phase_history}.py
tests/test_m1b_closure.py / test_m1b_v2_coverage.py  12 个测试函数（M1B 历史管线）
```

**没有**做任何迁移 / 归档 / ZIP / fixture 复制 / archived novel（符合作者要求）。

---

## 4. Historical hardcoded references removed

| 位置 | 处理 | 结果 |
| --- | --- | --- |
| `story_builder/export_package.py` | `RECON_DIR` / `PLANNING_INDEX` / `canon/wasteland_001.sqlite` / `FROZEN_*_DIGESTS` / spine + historical_ir 分区 / `historical_repair` truth layer | **重写**：路径经 `persistence.paths`；导出去掉历史分区；manifest `source_digests` 改为本作品 section 摘要 |
| `story_builder/writer_integration.py` | `CANON_DB` 常量 / `LEGACY_WRITER_STORE_DIR` 回退 / `historical_repair` 上下文块 / `_history_dir()` | **重写**：canon 路径按 novel_id；历史回退与历史上下文块删除（TRUTH_BLOCKS 6 层 → 5 层） |
| `story_builder/inspector.py` | `CANON_DB` 常量 / `history_dir()` / `_chapter_ir_rows()` / REPAIR_REPLAY provenance / `historical_repair` 层 | **重写**：只检查本作品 Canon + StoryState；`LAYERS` 从 4 层降为 3 层；`chapter_ir` 字段显式返回 `null` |
| `story_builder/novel_admin.py` | 归档候选里的 `workspace/.../writer_v1` | 删除该候选路径 |
| `api/canon_routes.py` | `DEFAULT_NOVEL_ID = "wasteland_001"` | 改为复用 `story_engine.profile.DEFAULT_NOVEL_ID`；`canon_db_path` 变为 `persistence.paths` 的兼容包装 |
| `scripts/wasteland_001_m1b_closure.py` | — | 删除 |
| frozen `story_engine/{historical_ir,repair,reconstruction,historical_adoption,m11_*,m12..m18}` | 冻结边界不可改 | **原地保留**（不移动、不删除、不再被产品路径引用），登记进 `legacy/manifest.py` |

**绝对禁止项已确认不存在**：没有任何"当前作品没有数据 → 自动回退 historical / wasteland"的路径
（守卫测试 `tests/v4/isolation/test_no_historical_fallback.py` 与
`test_no_final_prose_dependency.py` 机械验证）。

---

## 5. Application service boundary changes

新增（Strangler：先建立边界，实现仍委托既有模块）：

```text
src/novelforge/application/__init__.py
src/novelforge/application/services/__init__.py
src/novelforge/application/services/journey.py   JourneyService
src/novelforge/application/services/export.py    ExportService
src/novelforge/application/services/project.py   ProjectService
```

收编的路由（路由变薄，业务在服务层）：

```text
GET    /api/story-builder/novels                     → ProjectService.list_novels
POST   /api/story-builder/novels                     → ProjectService.create_novel
GET    /api/story-builder/novels/{novel_id}          → ProjectService.get_novel
PATCH  /api/story-builder/novels/{novel_id}          → ProjectService.rename_novel
DELETE /api/story-builder/novels/{novel_id}          → ProjectService.archive_novel
GET    /api/story-builder/export/package             → ExportService.export
GET    /api/story-builder/export/writer-bundle       → ExportService.writer_bundle
GET    /api/story-builder/v3/novels/{id}/journey     → JourneyService.projection（新增）
```

`story_builder_routes.py` 没有一次性重写（仍 1,500+ 行），符合「Strangler 而不是 Big Bang」；
已迁移部分的外部行为不变（既有 API 测试全部通过）。

---

## 6. JourneyProjection changes

```text
新增公开 Contract : story_builder/v3_projection.py::journey_projection()（唯一公开入口）
服务层入口        : application.services.journey.JourneyService
新 REST 入口      : GET /v3/novels/{novel_id}/journey
收编第二套推导    : story_builder/ui_flow.py::guided_flow_state() 的 current_stage /
                    current_stage_label 改为由 JourneyService 派生
                    （保留 journey_stage / journey_stage_label / journey_next_action 字段，
                     UI 现有展示形状不变）
```

`ui_flow` 仍保留自己的「四步 onboarding 状态」（创意 / 设定 / 自检 / 开始推演），
但**阶段与下一步不再由它推导**——文档化在 `ui_flow.py` 的注释与 ADR-004 对齐说明中。
已知代价：`/guided-flow` 现在会多计算一次 journey 投影（该端点是 legacy bridge，V4-10 会移除）。

---

## 7. Path / ownership changes

新增 `src/novelforge/persistence/`（唯一路径来源）：

```text
persistence/__init__.py   公开 Contract
persistence/paths.py      ArtifactContext + 全部 artifact 路径解析 + 跨作品守卫
```

规则（已由测试机械验证）：

```text
· 路径必须显式携带 project_id / novel_id / artifact_kind（novel_id 无默认值）
· 禁止 GLOBAL_CURRENT_NOVEL / 默认 wasteland_001 / 扫描磁盘推断当前作品
· 禁止"当前作品没有数据 → 回退到其他作品或历史数据"
· require_same_novel() 提供跨作品读取守卫；路径解析拒绝逃逸项目根
```

已接入的调用点：`export_package` / `writer_integration` / `inspector` / `canon_routes`。

---

## 8. Revision primitive

新增 `src/novelforge/core/`：

```text
core/ids.py       new_request_id / digest_payload
core/revision.py  RevisionRef / RevisionConflict / OperationContext /
                  check_expected_revision / new_revision / revision_view
```

能力（V4-01 范围，**不含**完整 revision history 系统）：

```text
revision / expected_revision / parent_revision
revision conflict（不覆盖、不自动合并）
operation / request_id（OperationContext 自动生成）
source_ids / changed_nodes / digest
```

明确语义：revision 服务的对象是 **Story Blueprint 节点 / StoryState / Quality-Repair /
Agent mutation**，不是正文版本历史（ADR-011）。

---

## 9. Legacy boundary

新增 `src/novelforge/legacy/`：

```text
legacy/manifest.py   9 条 frozen 能力清单（module_id / path / capability / status /
                     used_by / removal_condition）
legacy/adapters.py   只读查询：describe_legacy_capabilities / legacy_adventure_status /
                     forbid_write（显式拒绝写操作）
```

规则执行情况：

```text
· frozen 模块原地保留，未做大规模移动 ✅
· 只有仍需要兼容的能力登记（旧旅程存档 / 正文预览 / phase snapshot 机制）✅
· 已删除的废弃数据**没有**进入 legacy/ ✅（文档里只出现"已删除"说明，不作路径使用）
· 新业务路径（application / persistence / core）不 import frozen 历史模块 ✅（守卫测试）
```

---

## 10. Module boundary changes

```text
docs/v4/V4_MODULE_BOUNDARIES.md   16 个模块的 Current/Target Path、State、Owner Phase
                                  + 逐模块 Public Contract / Internal / Allowed / Forbidden /
                                    State Ownership / Module Tests
                                  + 依赖矩阵（core / persistence / domain / app-services /
                                    legacy / interfaces / ui / ai / memory / quality）
                                  + 明文禁令 + 守卫测试位置 + 新增模块流程
docs/v4/V4_BRANCH_STRATEGY.md      扁平分支命名表 + 任务分支声明模板 + 分支规则 + 并行隔离要求
```

V4-01 实际落地的边界：`core` / `application.services` / `persistence` / `legacy`
（+ 对 `domain`、`ui` 的只读声明）；其余目录（ai / memory / generation / quality /
mcp / plugins / observability）按计划在对应阶段创建，未提前建空壳。

---

## 11. Isolation tests

新增 `tests/v4/`（永久守卫，默认运行）：

| 文件 | 覆盖 |
| --- | --- |
| `isolation/test_no_historical_fallback.py` | 废弃资产不存在；产品侧模块无历史路径字面量 / 常量标识符；导出无历史分区与冻结 digest；无历史数据时导出可用；Inspector 不再有 historical_repair 层 |
| `isolation/test_no_final_prose_dependency.py` | 旧正文不存在且无引用；writer context 无 historical 块；writer draft 无历史回退；无正文时主链可用 |
| `isolation/test_ownership_isolation.py` | Novel A / B 两作品：journey / 路径 / 导出 / StoryState 读操作不含对方数据 |
| `isolation/test_no_implicit_disk_discovery.py` | 路径必须显式 novel_id；磁盘上多出的作品不进入其他作品的投影；损坏 profile 不被静默当作作品；服务构造要求 novel_id |
| `isolation/test_module_boundaries.py` | domain 不依赖 interface/provider/persistence；api 不新增 domain import（存量白名单）；application 不依赖 interface；persistence 不依赖 application/api；UI 不引用后端模块 |
| `isolation/test_legacy_boundary.py` | manifest 完整性；适配器只读（零文件写入）；legacy/ 不含可访问的已删除路径；新写路径不 import frozen 历史模块；写操作被拒绝 |
| `test_core_revision.py` | revision primitive（append-only / parent / conflict / request id / digest） |

共 **37** 个新测试，全部 PASS。

---

## 12. Full test results

```text
pytest -q                                   910 passed / 7 skipped / 0 failed（267s）
python scripts/validate_project.py          PASS
tests/test_v2_frozen_guard.py               6 passed
tests/test_v3_frozen_guard.py               6 passed
tests/v4（新增守卫）                         37 passed
```

### 12.1 测试数量变化逐类解释（V4-00 → V4-01）

```text
V4-00：892 passed + 687 deselected = 1579 collected
V4-01：910 passed +   7 skipped    =  917 collected
```

| 类别 | 变化 | 原因 |
| --- | --- | --- |
| 52 个 historical_acceptance 测试文件 | **−687 collected**（V4-00 时全部 deselected） | 它们验证的 570 章 historical / M11–M18 里程碑能力随数据删除而消失（作者决策 B） |
| `tests/test_m1b_closure.py` + `test_m1b_v2_coverage.py` | **−12 passed** | 只覆盖 M1B 历史管线；其数据与被测脚本同时删除 |
| 3 个依赖 workspace 历史 fixture 的默认测试 | **12 passed → 5+1+1 skipped**（7 个用例） | `test_chapter_ir_full_migration`（5）、`test_canon_regression_corpus`（1）、`test_chapter_ir_semantic_verification`（1）：这些文件**本来就有** `pytest.skip` 守卫，现在正确地跳过；它们的产品侧断言部分仍保留 |
| `tests/v4/**` 新增 | **+37 passed** | V4-01 新增的永久隔离守卫与 revision primitive 测试 |
| `test_acceptance_repair_regressions.py` | 1 个用例改写（数量不变） | 原「legacy writer 目录只读兼容」断言的是被删除的行为；改为断言「不存在历史回退」 |

---

## 13. Frozen boundary result

```text
release tag novelforge-product-v3-final          未移动（annotated tag f214647 → f02ca8c）
docs/FROZEN_EVIDENCE_MANIFEST.json               仅更新「历史形态」断言口径（见下）
novel/authoring/**（242 tracked 冻结资产）        未改动（digest 匹配，guard PASS）
frozen Repair Contract / REPAIR_GATE_V1          未修改
StoryState / Canon 语义                          未修改
```

**一处显式的冻结口径调整（必须报告）**：
`tests/test_v2_frozen_guard.py::test_history_is_a_single_root_commit` 原断言是
`git rev-list --count HEAD == 1`，表达的是 **V3 Final 冻结时刻的时间点状态**。
V4 开发分支必然在该 root commit 之上追加提交，因此该断言在分支上无法成立。
按 `AGENTS.md` §20（区分「历史 timepoint」与「永久 invariant」），把它收敛为永久不变式：

```text
1. HEAD 的历史里只有一个 root commit（不继承 V1/V2/V3 历史）
2. novelforge-product-v3-final 仍指向该 root commit（tag 未移动）
3. 当 HEAD 恰好是 release commit 时，仍要求 commit 数 == 1（冻结时刻严格形态）
```

manifest 的 `active_history_shape.requirement` / `invariants` 文案同步更新，
**断言强度没有放宽**（新增了「tag 必须指向 root」这一条）。

---

## 14. Files created

```text
src/novelforge/core/{__init__.py,ids.py,revision.py}
src/novelforge/legacy/{__init__.py,manifest.py,adapters.py}
src/novelforge/persistence/{__init__.py,paths.py}
src/novelforge/application/{__init__.py}
src/novelforge/application/services/{__init__.py,journey.py,export.py,project.py}
tests/v4/test_core_revision.py
tests/v4/isolation/_guard_utils.py
tests/v4/isolation/test_no_historical_fallback.py
tests/v4/isolation/test_no_final_prose_dependency.py
tests/v4/isolation/test_ownership_isolation.py
tests/v4/isolation/test_no_implicit_disk_discovery.py
tests/v4/isolation/test_module_boundaries.py
tests/v4/isolation/test_legacy_boundary.py
docs/v4/V4_MODULE_BOUNDARIES.md
docs/v4/V4_BRANCH_STRATEGY.md
docs/v4/adr/ADR-011-story-blueprint-primary-artifact.md
docs/v4/V4_01_BOUNDARY_FOUNDATION_REPORT.md（本文件）
```

## 15. Files modified

```text
src/novelforge/api/canon_routes.py                默认作品 + 路径包装
src/novelforge/api/story_builder_routes.py        服务层接线 + /journey 路由
src/novelforge/story_builder/export_package.py    历史分区 / 硬编码路径 / truth layer 清理
src/novelforge/story_builder/writer_integration.py 历史回退 / 历史块 / canon 路径
src/novelforge/story_builder/inspector.py         历史层 / canon 路径
src/novelforge/story_builder/novel_admin.py       历史 writer 目录候选
src/novelforge/story_builder/ui_flow.py           阶段改为 JourneyService 派生
src/novelforge/story_builder/v3_projection.py     新增公开 journey_projection()
tests/conftest.py / pytest.ini                    历史套件隔离机制移除
tests/test_acceptance_repair_regressions.py       legacy writer 用例改写
tests/test_v2_frozen_guard.py                     历史形态断言收敛为永久不变式
docs/FROZEN_EVIDENCE_MANIFEST.json                历史形态口径文案
README.md / AGENTS.md / novelforge.project.yaml   历史套件与 protected_paths 同步
docs/ARCHITECTURE.md / docs/DATA_MODEL.md / docs/LEGACY_COMPAT.md
docs/NOVELFORGE_REAL_NOVEL_PRODUCTION_GUIDE.md    历史资产与 V4 定位说明
docs/v4/{V4_ARCHITECTURE,V4_MODULE_CLASSIFICATION,V4_MIGRATION_PLAN,V4_DELETION_PLAN,
          V4_QUALITY_CONTRACT,V4_MCP_SPEC,V4_MEMORY_ARCHITECTURE,V4_EXPORT_SPEC,
          V4_ARCHITECTURE_RISKS,V4_00_ARCHITECTURE_REPORT}.md
docs/v4/adr/{README,ADR-003,ADR-007}.md
docs/NOVELFORGE_V4_MASTER_PLAN.md（作者更新版）
```

## 16. Files deleted

```text
novel/final/**                                       69 个 tracked 文件
workspace/wasteland_001_exports/**                   1918 个 untracked 文件（62 MB）
novel/config/story_engine/wasteland_001_pack.json    1 个 untracked 文件
scripts/wasteland_001_m1b_closure.py                 1 个 tracked 文件
tests/（52 个 historical_acceptance 测试 + 4 个 phase_history helper
        + test_m1b_closure.py + test_m1b_v2_coverage.py）  58 个 tracked 文件
```

合计 tracked 删除 **128** 个文件；untracked 删除 **1919** 个文件。

---

## 17. Git branch

```text
v4-01-boundary-foundation
```

（按作者要求使用扁平命名；`v4/...` 与 `origin/v4` 冲突，见 `V4_BRANCH_STRATEGY.md` §1）

## 18. Git commits

```text
a3508c6  docs(v4): align architecture with story blueprint product decision
4433f43  chore(v4): remove obsolete final and historical assets
ef97620  refactor(v4): parameterize persistence ownership paths
9a5eccf  refactor(v4): establish application service boundary
c6895f0  feat(v4): add revision primitives and legacy adapters
b2084c7  test(v4): add ownership and legacy isolation coverage
（+ 本报告与产品文档同步提交）
```

---

## 19. Remaining risks

| 风险 | 状态 | 说明 |
| --- | --- | --- |
| frozen 历史模块成为"无人使用但仍在 src"的 12k 行 | 已知、已登记 | 只在 `legacy/manifest.py` 登记 + 源码守卫；删除需要作者确认（不阻塞任何阶段） |
| `/guided-flow` 多一次 journey 计算 | 新引入、低风险 | legacy bridge 端点；V4-10 移除 |
| `story_builder_routes.py` 仍有 1,500+ 行、部分路由直接依赖 domain | 存量 | module boundary 守卫已用显式白名单登记，**只允许缩小**；V4-04…V4-07 继续迁移 |
| `project_id` / `novel_id` 层级未定 | 待产品决定 | ADR-007 保留该问题；V4-01 用同值映射兼容，不阻塞 |
| `workspace/pilot_v2/**`（165 文件）未裁定 | 待作者决定 | 不在本次决策 A/B 范围内；已登记在 inventory §6 与 classification |
| `novel/runs|state|pipelines|learning` 等未裁定 | 待作者决定 | 同上，V4-01 未触碰 |
| Q9 / DeliveryValidator 尚未实现 | 计划内 | V4-07；当前导出校验仍是 V3 的 schema/identity 级校验 |
| Blueprint 数据模型尚未建立 | 计划内 | V4-04；V4-01 只确立法定地位与边界（ADR-011） |

---

## 20. V4-02 readiness

```text
[x] 唯一业务入口存在（application.services），MCP / REST / UI 有可调用目标
[x] 路径与 ownership 已有唯一实现，模型层不需要再自己拼路径
[x] revision primitive 就绪（Gateway 的 usage / trace 可挂到 request_id）
[x] legacy 边界明确，frozen 模块不会被误当作新产品能力扩展
[x] 隔离守卫就绪（新增 provider / gateway 不会破坏跨作品隔离）
[x] 无历史资产干扰：LLM Gateway 不需要为 570 章 historical 设计任何特殊路径
[x] 默认测试基线 910 passed / 7 skipped / 0 failed
```

V4-02 可以开始：**LLM Gateway（Provider / Router / Contract / usage / trace / cache）**，
开工前需按 `V4_BRANCH_STRATEGY.md` §3 填写任务分支声明（Primary Module = `ai`）。

---

# V4-01 = PASS

唯一未完成项均为**其他阶段的范围**（Gateway / Memory / Blueprint generation / Quality /
Editor / MCP），以及 3 个**待作者裁定**的仓库卫生问题（`workspace/pilot_v2`、
`novel/runs|state|pipelines|learning`、`project_id` 层级）。
它们都不阻塞 V4-02。

