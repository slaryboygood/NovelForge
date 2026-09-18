# NovelForge V4-12 — Final Acceptance Matrix

> 状态：**V4-12 Final Acceptance**（与 `V4_12_FINAL_ACCEPTANCE_REPORT.md` 同时生效）
> 说明：本矩阵是**重新验证**，不是"前面 PASS 所以最终 PASS"。每个维度给出真实证据与门禁。
> Status 取值：`PASS` / `NOT RUN` / `ACCEPTED_RISK` / `DEFERRED` / `BLOCKED`

| Dimension | Requirement | SSOT | Evidence | Gate/Test | Status | Release Blocker |
| --- | --- | --- | --- | --- | --- | --- |
| 1 Architecture | Story Studio / REST / MCP → Application Services → domain；插件经 extension point；Agent 经 narrow ports | `V4_ARCHITECTURE.md`、`V4_MODULE_BOUNDARIES.md` | §63 依赖图；`tests/v4/isolation/**`（含 agent/plugin/mcp boundaries）；验收 Layer A 循环依赖扫描 | `pytest -q tests/v4`、`tests/acceptance/test_final_contracts.py::test_no_dependency_cycles_between_v4_modules` | PASS | 否 |
| 2 Module Boundaries | 每个模块 Public Contract 精简；业务模块不反向依赖上层；UI 只经 HTTP | `V4_MODULE_BOUNDARIES.md` §3.1–§3.17 | boundary guards 19 个文件；`__all__` 审计（AI surface 已记录） | `tests/v4/isolation/**`、`test_public_contracts_do_not_expose_internals` | PASS | 否 |
| 3 Truth Model | Canon/StoryState 权威；Blueprint canonical creative artifact；Memory 派生；Quality 证据；Delivery 选定快照；Plugin/Agent 为 metadata | `V4_DATA_MODEL.md`、各 Contract | Layer B：Canon/StoryState 哈希在流水线前后一致；memory 删除重建后 truth 不变 | `test_canon_and_storystate_unchanged_by_pipeline`、`test_memory_is_derived_and_rebuildable` | PASS | 否 |
| 4 Blueprint | revisioned node graph；append-only；restore 产生新 revision；结构/引用校验 | `V4_BLUEPRINT_CONTRACT.md` | Layer B revision-chain / restore 测试；`tests/generation`、`tests/editor` | `test_revision_chain_is_append_only`、`test_restore_creates_new_revision_and_keeps_history` | PASS | 否 |
| 5 LLM | 唯一 Gateway；路由 / 结构化输出 / retry / usage / trace / secret redaction / cache | `V4_LLM_CONTRACT.md`、ADR-012/013 | `tests/ai`（90 项，full regression 内）；Gateway 唯一性扫描 | `tests/ai`、`test_single_context_builder_and_single_gateway`、`test_provider_boundary_has_no_direct_vendor_calls` | PASS | 否 |
| 6 Memory | 派生 / 可重建；stale 不进默认 retrieval；经 ContextBuilder 选上下文 | `V4_MEMORY_ARCHITECTURE.md`、ADR-014/015 | Layer B memory rebuild；`tests/memory`；ContextBuilder 唯一 | `test_memory_is_derived_and_rebuildable`、`tests/memory` | PASS | 否 |
| 7 Generation | 结构化生成；proposal 而非 accepted；provenance / contract 版本 | `V4_BLUEPRINT_CONTRACT.md`、ADR-010/017 | Layer B e2e（生成 → proposed）；`tests/generation`；generation index 回归 | `test_end_to_end_workflow_preserves_author_control`、`tests/studio/test_studio_generate_contract.py` | PASS | 否 |
| 8 Quality | Q0–Q9 gate-based；无权威总分；issue evidence；needs_human_review 保留 | `V4_QUALITY_CONTRACT.md`、`V4_REPAIR_CONTRACT.md`、ADR-018/020 | Layer A gate 名称 + 无总分扫描；`tests/quality`（122 项） | `test_gate_names_and_no_global_score_persist`、`tests/quality` | PASS | 否 |
| 9 Repair | 最小范围 + preserve + 新 revision + verifier 确认才算解决 | `V4_REPAIR_CONTRACT.md`、ADR-019 | `tests/quality/repair/**`；Agent repair 复用既有闭环；needs_human_review 端口级测试 | `tests/quality`、`test_agent_human_review.py` | PASS | 否 |
| 10 Editor | patch / rewrite / diff / accept / reject / restore / 冲突 | `V4_EDITOR_CONTRACT.md`、ADR-021/022/023 | Layer B e2e + 冲突测试；`tests/editor`（110 项） | `test_end_to_end_workflow_preserves_author_control`、`test_concurrency_conflict_does_not_overwrite` | PASS | 否 |
| 11 Delivery | accepted revision 选择 + 质量证据 revision 匹配 + stale 拒绝 + snapshot pinning + manifest/checksum + 原子发布 + 无 secret/跨作品污染 | `V4_DELIVERY_CONTRACT.md`、ADR-024/025/026 | Layer C 可复现/无 secret/stale 阻止；`tests/delivery`；浏览器真实下载（V4-12 final run） | `test_delivery_is_reproducible_and_secure`、`test_delivery_blocks_stale_or_unaccepted`、`tests/browser_v4_studio_golden.cjs` | PASS | 否 |
| 12 MCP | 官方 SDK 契约；23 tools / 13 resources 基线；命名空间增量；错误/安全/隔离 | `V4_MCP_CONTRACT.md`、ADR-027/028 | Layer C baseline + 插件增量 + 跨作品拒绝；`tests/mcp`（48 项） | `test_mcp_core_baseline_and_plugin_increment`、`test_mcp_cannot_read_other_novel`、`tests/mcp` | PASS | 否 |
| 13 Plugins | discover ≠ load；显式批准；权限；原子注册；Core 不可覆盖；disable 卸载；失败隔离；trust 声明诚实 | `V4_PLUGIN_CONTRACT.md`、ADR-029/030/031 | `tests/plugins`（87 项）+ 边界守卫；Layer C 插件增量 | `tests/plugins`、`tests/v4/isolation/test_plugin_boundaries.py` | PASS | 否 |
| 14 Story Studio | 默认产品面；无业务真相推导；golden 流程 + 四视口 | `V4_UI_CONTRACT.md`、ADR-032/033 | 浏览器 golden（V4-12 final run）+ 前端 60 tests + 组件/错误/状态语义冻结 | `tests/browser_v4_studio_golden.cjs`、`npm test` | PASS | 否 |
| 15 Agent | bounded / revision-aware / idempotent / checkpoint / resume / approval；默认不自动接受、不自动交付 | `V4_AGENT_CONTRACT.md`、ADR-034/035/036 | `tests/agent`（35 项）+ 浏览器 Agent gate；Layer B/C agent 断言 | `tests/agent`、`tests/browser_v4_11_agent.cjs` | PASS | 否 |
| 16 Isolation | Novel A 不能读写导出 Novel B；覆盖 Blueprint/Memory/Quality/Editor/Delivery/MCP/Plugin/Agent | `V4_DATA_MODEL.md`、各 Contract | Layer C 跨作品隔离（含 **V4-12 修复的 agent session 泄漏**） | `test_cross_novel_isolation_everywhere`、`tests/v4/isolation/test_ownership_isolation.py` | PASS | 否 |
| 17 Security | 无 secret 泄漏；无路径逃逸；无 traceback；权限边界诚实 | `V4_LLM_CONTRACT.md` §secret、`V4_PLUGIN_CONTRACT.md` §6、`V4_AGENT_CONTRACT.md` §4 | Layer C secret/path/hygiene；`tests/plugins/test_plugin_security.py`；`tests/mcp` 安全用例 | `test_repository_has_no_runtime_or_secret_artifacts_tracked`、`tests/plugins/test_plugin_security.py` | PASS | 否 |
| 18 Compatibility / Frozen Boundary | V3/V2 显式入口可用；frozen guards PASS；V3 tag 未移动；历史验收如实 NOT RUN | `V4_BRANCH_STRATEGY.md`、`docs/FROZEN_EVIDENCE_MANIFEST.json` | 兼容入口 smoke gate；V2/V3 frozen guard；tag 校验 | `tests/browser_v4_legacy_entry.cjs`、`tests/test_v2_frozen_guard.py`、`tests/test_v3_frozen_guard.py` | PASS | 否 |
| 18b Historical V3/V2 acceptance | 依赖作者 acceptance data root 的历史套件 | 同上 | 数据根在本 workspace 不存在（V4-10/V4-12 两次确认） | 未运行 | NOT RUN | 否（前提：frozen guards + legacy entry PASS） |

## 汇总

```text
PASS             18 / 18 维度
NOT RUN          1（Historical V3/V2 acceptance，数据根缺失，非 blocker）
ACCEPTED_RISK    trusted in-process plugin 无 OS sandbox（R-12 MITIGATED / NOT ELIMINATED）
DEFERRED         MCP agent tools / 插件 AI·网络能力 / prose / EPUB / marketplace / hot reload /
                 Agent 编排元数据归档 / large-project streaming
BLOCKED          0
Release blocker  NONE
```
