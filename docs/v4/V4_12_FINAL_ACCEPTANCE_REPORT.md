# V4-12 FINAL ACCEPTANCE REPORT

> 阶段：**V4-12 Final Acceptance & Release Readiness**　状态：**PASS**
> 日期：2026-09-18　分支：`v4-12-final-acceptance`
> 契约：[V4_12_ACCEPTANCE_MATRIX.md](V4_12_ACCEPTANCE_MATRIX.md)　证据索引：[V4_12_EVIDENCE_INDEX.md](V4_12_EVIDENCE_INDEX.md)
> 债务复审：[V4_12_ARCHITECTURE_DEBT_REVIEW.md](V4_12_ARCHITECTURE_DEBT_REVIEW.md)
> 状态文件：[V4_12_STATUS.md](V4_12_STATUS.md)（已被本报告取代）

## 1. Acceptance scope

V4-12 **不是功能开发阶段**，只用真实证据回答一个问题：NovelForge V4 是否已经成为
完整、稳定、可验证、作者可掌控的 Story Blueprint 产品（任务书 §67）。

范围：Layer A 契约完整性 / Layer B 跨模块集成 / Layer C 发布验收；完整 Python 回归、
前端回归、浏览器回归、frozen guards、`validate_project`、发布 dry run 与干净环境 smoke；
文档（本报告 / 验收矩阵 / 证据索引 / 债务复审 / README）。**未新增任何产品能力**。

本阶段禁止项（任务书 §1）全部保持未触及：MCP agent tools、Plugin AI / network host
capability、Prose Writer、EPUB、Marketplace、Hot reload、新 Blueprint node、新 Quality
gate、新 Agent action、新 UI workspace。

## 2. Baseline

```text
branch              v4-12-final-acceptance
HEAD                c08c13b（V4-12 工作起点）→ 见 §41 release candidate commit
date                2026-09-18
V3 frozen tag       novelforge-product-v3-final = f21464713e4786410e5550a7ad5504692cc644dd（未移动）
working tree        提交前：仅本次验收文档改动；提交后 clean（§36、§41）
V4-00 → V4-11       全部 PASS
V4-12 acceptance    Layer A/B/C = 28 passed（65.75s）
```

## 3. Contract integrity

验收套件总览（任务书 §47）：

```text
tests/acceptance                      28 passed
  Layer A test_final_contracts.py      9  Contract Integrity
  Layer B test_final_integration.py   11  Cross-module Integration
  Layer C test_final_release.py        8  Release Acceptance
```

`tests/acceptance/test_final_contracts.py`（9 项，全部 PASS）：

```text
test_all_v4_ssot_documents_exist_and_are_current
  Blueprint / Quality / Repair / Editor / Delivery / MCP / Plugin / UI / Agent 契约存在且声明自身
test_no_conflicting_ssot_for_the_same_capability
  旧设计稿已降级并指向契约（V4_MCP_SPEC / V4_EXPORT_SPEC / V4_PLUGIN_SPEC）
test_schema_and_interface_versions_are_independent
  版本互不混用：schema 版本、REST 版本、MCP 版本、plugin API 版本各自独立递增
test_public_contracts_do_not_expose_internals
  public contract 精简；内部实现不出现在 __all__ / AI surface
test_gate_names_and_no_global_score_persist
  唯一 gate 名称集合 Q0–Q9；无权威总分字段持久化
test_provider_boundary_has_no_direct_vendor_calls
  业务模块不得直接调用 vendor SDK（必须经 LLM Gateway）
test_single_context_builder_and_single_gateway
  唯一 ContextBuilder + 唯一 LLM Gateway
test_v4_docs_do_not_claim_stale_product_truth
  V4 文档无过时产品定位表述（四类：旧主入口 / 正文权威 / 总分 / 自动接受），最新 revision
  不自动成为 accepted
test_no_dependency_cycles_between_v4_modules
  V4 模块无循环依赖（唯一已登记例外：plugins/host.py = composition root，V4_MODULE_BOUNDARIES §3.16）
```

## 4. Architecture

唯一依赖方向：

```text
Story Studio / REST / MCP  →  Application Services  →  domain capabilities
Plugin → approved contribution → Host Adapter → Registry → existing pipeline
Agent  → narrow Ports → Application-backed adapters → existing capabilities
```

由 `tests/v4/isolation/**`（19 个守卫文件）与验收 Layer A 的模块图扫描分别独立证明；
`plugins/host.py` 是唯一（已登记）同时接触 application 与 interfaces 的 composition root。

## 5. Module boundaries

`V4_MODULE_BOUNDARIES.md` §3.1–§3.17 与守卫一一对应；验收重新确认：

```text
core/domain ✗ interfaces/application/plugins/agent/UI
blueprint ✗ generation/quality/editor/UI        generation ✗ quality/editor/UI
quality ✗ editor/UI                             editor ✗ 反向依赖
delivery 只读 story truth                       interfaces → application facade
plugins → extension points only                 agent → narrow ports only
UI → HTTP only
```

## 6. Truth model

```text
Canon / StoryState  = authoritative truth（唯一事实来源；V4 全流程不得改写）
Blueprint           = canonical creative artifact（revisioned，可编辑，可回滚）
Memory              = derived（可丢弃、可重建；不是 truth）
Quality             = evidence（gate 结果 + issue evidence；不是 truth 也不是总分）
Delivery            = selected snapshot（选定 revision 的不可变快照）
Plugin state        = extension metadata（不属于 story truth）
Agent state         = orchestration metadata（不属于 story truth）
```

证据：`test_canon_and_storystate_unchanged_by_pipeline`（Layer B）、
`test_memory_is_derived_and_rebuildable`（Layer B）、`V4_DATA_MODEL.md`。

## 7. Blueprint

```text
有序节点图：premise / theme / world / character / character-arc / story-arc /
            unit / chapter / scene / setup / payoff / causal-link
append-only revision chain + expected_revision 乐观并发 + restore 产生新 revision
结构 / 引用校验（悬空引用、孤立节点、ordinal 冲突在生成与编辑两侧都校验）
```

证据：Layer B `test_revision_chain_is_append_only`、
`test_restore_creates_new_revision_and_keeps_history`、`test_golden_project_covers_all_core_concepts`；
`tests/generation/**`、`tests/editor/**`；`V4_BLUEPRINT_CONTRACT.md`。

## 8. LLM Gateway

```text
唯一模型入口 src/novelforge/ai/**（contract / router / provider / structured output /
retry / timeout / usage / trace / cache / secret boundary）
默认 0 provider 启用（novel/config/ai/providers.json 全部 enabled=false）
→ 未配置模型时产品行为是"不调用模型"，source 恒为 rule、notes 含 AI_UNAVAILABLE
api_key 只经环境变量 / 配置边界，不写入 trace / log / cache key / API 响应
```

证据：`test_single_context_builder_and_single_gateway`、
`test_provider_boundary_has_no_direct_vendor_calls`（Layer A）；`tests/ai/**`（full regression 内）；
`V4_LLM_CONTRACT.md`、ADR-012 / ADR-013。

## 9. Memory

```text
Memory = 派生检索层：可由已接受 artifact 完全重建；stale 条目不进入默认 retrieval；
上下文装配只能经 ContextBuilder（唯一上下文选择系统，带预算）
```

证据：Layer B `test_memory_is_derived_and_rebuildable`（删除后重建，story truth 不变）、
`test_generation_uses_context_builder`；`tests/memory/**`；`V4_MEMORY_ARCHITECTURE.md`、ADR-014 / ADR-015。

## 10. Generation

```text
逐级结构化生成（premise → world → character → arc → unit → chapter → scene）
AI 产出永远是 proposal（proposed），不自动进入 accepted
每个 generation 记录 provenance（contract 版本 / 输入引用 / provider 或 rule）
```

证据：Layer B `test_end_to_end_workflow_preserves_author_control`（生成 → proposed → 作者 accept）；
`tests/generation/**`、`tests/studio/test_studio_generate_contract.py`；`V4_BLUEPRINT_CONTRACT.md`、ADR-010 / ADR-017。

## 11. Quality Q0–Q9

```
Q0 Schema
Q1 Integrity
Q2 Canon
Q3 Continuity
Q4 Character / Motivation
Q5 Causality
Q6 Semantic / Repetition
Q7 Structure / Pacing
Q8 Setup-Payoff / Narrative Function
Q9 Delivery Readiness
```

```text
gate-based，无权威总分；每个 issue 带 evidence（node / field / 依据）；
needs_human_review 保留在结果中，不被自动消解
```

证据：Layer A `test_gate_names_and_no_global_score_persist`；`tests/quality/**`（full regression 内）；
`V4_QUALITY_CONTRACT.md`、ADR-018 / ADR-020。

## 12. Repair

```text
最小范围修复 + preserve 规则 + 产生新 revision（不改写既有 revision）
verifier 重新检查后才算 resolved；不可安全自动修复 → 需要作者决定（needs_human_review）
max_repair_rounds 有界，避免无限修复循环
```

证据：`tests/quality/repair/**`；Agent 修复复用同一闭环（V4-11）；`V4_REPAIR_CONTRACT.md`、ADR-019；
债务复审 R-14（Infinite repair loop）复核 PASS。

## 13. Editor

```text
字段级 patch / AI 改写（proposal）/ deterministic diff / accept / reject / restore
revision 冲突检测（expected_revision 不匹配 → 409，不静默覆盖）
```

证据：Layer B `test_end_to_end_workflow_preserves_author_control`、
`test_concurrency_conflict_does_not_overwrite`；`tests/editor/**`；`V4_EDITOR_CONTRACT.md`、ADR-021 / ADR-022 / ADR-023。

## 14. Revision integrity

```text
历史只增不改：append-only revision chain
restore = 用历史版本内容产生**新** revision（历史保持不变）
latest revision 不自动成为 accepted；accepted 由作者显式动作决定
```

证据：Layer B `test_revision_chain_is_append_only`、
`test_restore_creates_new_revision_and_keeps_history`。

## 15. Concurrency

```text
两人 / 两个客户端同时改同一节点 → 第二个写入收到冲突（409），
第一份写入不被覆盖；前端展示冲突而不是自动合并
Agent 遇到 revision 变化 → 暂停并等待作者，0 mutation
```

证据：Layer B `test_concurrency_conflict_does_not_overwrite`、
`test_agent_revision_conflict_pauses_with_zero_mutation`；浏览器 golden 冲突截图
（`workspace/v4_12_ui_review/06-conflict.png`）。债务复审 R-09 复核 PASS。

## 16. Idempotency

```text
generation：同一 idempotency key 只产生一次副作用
editor：重复提交同一 patch 不产生额外 revision
agent step：同一 step 重放不重复写入（step id + checkpoint）
```

证据：Layer B `test_idempotency_single_side_effect_per_key`、
`test_agent_step_replay_is_idempotent`。债务复审 R-10 复核 PASS。

## 17. Delivery

```text
preflight（质量证据 revision 必须匹配选定 revision）
→ snapshot（revision pinning）
→ manifest + checksum
→ 原子发布
格式：JSON / Markdown / DOCX / nfpack（+ 插件 exporter 注册的格式）
stale（选定 revision 已被更新的质量证据覆盖）或未 accepted 的交付被拒绝
交付物经 secret scan，不导出 .env / Authorization / 私有绝对路径
```

证据：Layer C `test_delivery_is_reproducible_and_secure`、
`test_delivery_blocks_stale_or_unaccepted`；浏览器真实下载（§32）；`tests/delivery/**`；
`V4_DELIVERY_CONTRACT.md`、ADR-024 / ADR-025 / ADR-026。

## 18. MCP

```text
官方 MCP Python SDK 薄适配层（stdio transport；不自造协议解析）
core baseline：23 tools / 13 resources（V4-08 冻结基线）
插件可追加命名空间化的 tool / resource；disable 后增量精确回退
显式 novel scope：MCP 不能读取其它作品
错误契约稳定（结构化错误，不泄漏 traceback）
```

证据：Layer C `test_mcp_core_baseline_and_plugin_increment`、`test_mcp_cannot_read_other_novel`；
`tests/mcp/**`；`V4_MCP_CONTRACT.md`、ADR-027 / ADR-028。债务复审 R-18 复核 PASS。

## 19. Plugins

```text
discover ≠ load（发现不等于加载）
manifest → compatibility check → 显式批准 → permission 声明 → contribution → adapter
原子注册（失败不留下半成品）；Core 注册不可覆盖
disable 精确卸载（含其 tool / resource / exporter 增量）
失败隔离；错误净化；trust 声明诚实（trusted in-process）
```

证据：`tests/plugins/**` + `tests/v4/isolation/test_plugin_boundaries.py`；
Layer C 插件增量；`V4_PLUGIN_CONTRACT.md`、ADR-029 / ADR-030 / ADR-031。
风险分类见 §28 / §29（R-12 = MITIGATED / NOT ELIMINATED）。

## 20. Story Studio

```text
V4 默认产品面（打开 / 即 Studio）
工作区：创造 / 世界 / 人物 / 故事 / 场景 / 检查 / 交付 / 插件 / Agent
UI 只展示后端返回的真相：不推导质量、不接受状态、不决定交付资格
```

证据：浏览器 golden 全流程 PASS（§32，含真实下载）；前端 60 tests PASS（§31）；
四视口截图（390 / 1024 / 1280 / 1440）；`V4_UI_CONTRACT.md`、ADR-032 / ADR-033。

## 21. Agent

```text
目标 → 计划预览（0 mutation）→ 有界执行 → 需要时审批 → 继续 → 完成
默认不自动接受、默认不交付；protected action 必须作者批准
新 AI 节点保持 proposed；检查点可恢复；预算有界
```

证据：`tests/agent/**`；浏览器 Agent gate PASS（§32）；Layer B/C agent 断言；
`V4_AGENT_CONTRACT.md`、ADR-034 / ADR-035 / ADR-036。

## 22. Cross-novel isolation

```text
Novel A 不能读 / 写 / 导出 Novel B 的：Blueprint、Memory、Quality、Editor revision、
Delivery snapshot、MCP 视图、Plugin state、Agent runtime（session / run / checkpoint / audit）
```

证据：Layer C `test_cross_novel_isolation_everywhere`、`test_mcp_cannot_read_other_novel`；
`tests/v4/isolation/test_ownership_isolation.py`。

**本阶段真实缺陷（§48）**：Agent runtime 原先 novel 无关 → 跨作品 session 可见；
V4-12 修复并有回归测试覆盖。

## 23. Canon / StoryState immutability

```text
完整流水线（生成 → 质量 → 修复 → 编辑 → 交付）前后：
Canon digest 不变；StoryState digest 不变
```

证据：Layer B `test_canon_and_storystate_unchanged_by_pipeline`。

## 24. Security / secret scan

```text
no secret leakage       交付物 / 日志 / trace / MCP 响应不含 api key
no cross-novel leakage  §22
no path traversal       作品 / 插件 / 交付路径不接受越界输入
no raw traceback        错误经净化后返回结构化错误
```

证据：Layer C `test_delivery_is_reproducible_and_secure`、
`test_repository_has_no_runtime_or_secret_artifacts_tracked`；
`tests/plugins/test_plugin_security.py`；`tests/mcp/**` 安全用例。

## 25. Error contracts

```text
HTTP 状态码 + 错误体形状稳定（409 冲突 / 400 校验 / 404 不存在 / 403 未批准 …）
错误体不含 traceback / 绝对路径 / provider 原文
```

证据：Layer C `test_error_contracts_are_stable_and_safe`；前端 `errors.test.ts`（11 项）。

## 26. Compatibility

```text
默认入口            → Story Studio
?ui=v3  / #/v3…     → V3 工作台（显式兼容入口）
?ui=v2              → V2 / Story Builder 面板（显式兼容入口）
legacy REST 端点    保留（V3 投影 / writer / legacy export），不进入 V4 主路径
```

证据：浏览器 Legacy Entry gate PASS（§32）；`tests/v4/isolation/**`；
`V4_BRANCH_STRATEGY.md`、`V4_DELETION_PLAN.md`。

## 27. Legacy status / Historical acceptance

```text
Historical V3/V2 acceptance:
NOT RUN — required author acceptance data root unavailable.
```

```text
原因：历史验收依赖作者本机 acceptance data root（本 workspace 不存在；
      V4-10 与 V4-12 两次确认）。未伪造数据、未修改断言、未把 NOT RUN 写成 PASS。
不构成 V4-12 blocker，前提（已满足）：
  V2 frozen guard PASS、V3 frozen guard PASS（§33）
  legacy entry smoke PASS（§32）
  frozen semantics 未修改（§37）
```

历史里程碑验收（V2 M11–M18 / wasteland / 570 章 historical）的测试与数据已在 V4-01 随
废弃资产一并删除（作者决策 A/B）；`historical_acceptance` marker 仍注册在 `pytest.ini`，
留给 V4 后续里程碑验收复用（届时以新的最小 deterministic fixture 支撑）。

## 28. Architecture risks

`V4_ARCHITECTURE_RISKS.md` R-01…R-18 逐项复核（详见债务复审 §6）：

```text
R-01 Big Bang Rewrite         → 未发生（分阶段 + 边界守卫）        PASS
R-02 Over-abstraction         → 受合并规则与 Debt Queue 约束        PASS
R-03 LLM coupling             → 唯一 Gateway + 守卫                 PASS
R-04 Provider coupling        → 配置驱动 provider adapter           PASS
R-05 Prompt sprawl            → contract 版本化                    PASS
R-06 Context explosion        → ContextBuilder 预算 + 唯一性        PASS
R-07 Memory corruption        → 派生 + 可重建 + 跨作品隔离          PASS
R-08 Canon drift              → Canon/StoryState 哈希不变           PASS
R-09 Revision race            → expected_revision + 冲突不覆盖      PASS
R-10 Agent duplicate writes   → step id + idempotency + checkpoint  PASS
R-11 Historical data leakage  → V4-01 删除 + ownership 参数化       PASS
R-12 Plugin privilege         → MITIGATED / NOT ELIMINATED          ACCEPTED_RISK
R-13 Quality cost explosion   → deterministic first + budget        PASS
R-14 Infinite repair loop     → max_repair_rounds + verifier        PASS
R-15 Writer overwrite         → 正文非 canonical artifact           PASS
R-16 Export contamination     → revision-pinned delivery + 扫描     PASS
R-17 Schema version drift     → 版本独立 + owner 明确               PASS
R-18 MCP contract instability → 契约冻结 + mcp 测试                 PASS
```

## 29. Architecture debt

`V4_12_ARCHITECTURE_DEBT_REVIEW.md` 分类汇总：

```text
BLOCKER                     0
ACCEPTED_RISK               2   （trusted in-process plugin 无 OS sandbox；历史验收数据根缺失）
DEFERRED                    8   （MCP agent tools / 插件 AI·网络 capability / marketplace /
                                 hot reload / prose / EPUB / Agent 元数据归档 / 大项目交付流式化）
COMPATIBILITY_LIMITATION    4   （V3 工作台投影 / V2 面板 / legacy writer / legacy export 端点）
CLEANUP_ELIGIBLE            2   （V3 export-flow 样式随 V3 入口退出清理；delivery helper 已收敛无残留）
```

```text
Architecture Debt: 无 BLOCKER；每项 ACCEPTED_RISK / DEFERRED / COMPATIBILITY_LIMITATION
都有明确触发条件与后续责任人（阶段）。
```

## 30. Full Python regression

```text
command   .venv\Scripts\python.exe -m pytest -q
result    1707 passed, 7 skipped, 0 failed
duration  818.48s (13:38)
```

这是 V4 final Python baseline（任务书 §43）。0 failed；skip 为环境 / 平台条件跳过
（见 §38），未通过削弱断言、删除测试或扩大 skip 取得。

`-m historical_acceptance` 的历史套件不属于本次运行范围（§27）。

## 31. Frontend regression

```text
npm.cmd test        60 passed (8 files, 7.69s)
                    src/studio/design/parents.test.ts      9
                    src/studio/design/errors.test.ts      11
                    src/api/studio.test.ts                10
                    src/studio/workspaces/agent.test.tsx   1
                    src/studio/workspaces/plugins.test.tsx 4
                    src/studio/workspaces/delivery.test.tsx 4
                    src/studio/components.test.tsx        18
                    src/studio/nav.test.ts                 3
npm.cmd run build   PASS（tsc -b + vite build，2.41s，98 modules）
```

## 32. Browser regression

```text
Story Studio      PASS
Agent             PASS
Legacy Entry      PASS
```

```text
环境     real Edge Chromium（project-pinned Playwright）
模型     stub model
网络     0 real network model calls
服务     scripts/studio_ui_test_server.py
错误     0 uncaught page errors
```

Story Studio 覆盖（§8）：Create → Generate → Edit → Diff → Accept → Conflict → Quality →
Repair preview → Delivery → Download → Plugin。

Delivery 真实下载（V4-12 final run，§9）：

```text
blueprint.md               5,557 bytes
blueprint.docx             3,845 bytes
novelforge-package.nfpack 20,707 bytes
```

Agent 覆盖（§10）：goal → plan preview（0 mutation）→ start → approval → continue → complete；
断言：preview 0 mutation、新 AI 节点保持 proposed、默认不自动接受、默认不交付、取消文案诚实。

Legacy Entry 覆盖（§11）：默认 → Story Studio；`?ui=v3` / `#/v3…` → V3；`?ui=v2` → V2；
no page errors、no redirect loop。

证据：`workspace/v4_12_ui_review/**`（22 张截图 + `downloads/` 三个真实交付物）。

## 33. Frozen guards

```text
tests/test_v2_frozen_guard.py     PASS
tests/test_v3_frozen_guard.py     PASS
合计                               12 passed
```

即使 `pytest -q`（§30）已覆盖，此处仍单列结果（任务书 §13）。

## 34. validate_project

```text
python scripts/validate_project.py
→ NovelForge story-builder: PASS
```

## 35. Release build / dry run

```text
1) Frontend production build（任务书 §31）
   npm.cmd run build → PASS（tsc -b + vite build）
   ui/dist = index.html + assets/**（98 modules）
   检查：无 test / spec / fixture 文件被打包；无 .env / 测试 secret

2) Git archive dry run（任务书 §32）
   git archive --format=zip HEAD（RC 提交 tree）→ 成功、非空
   bytes      6,948,831
   entries    1,724
   contains   README.md / src/novelforge（414）/ tests（304）/ docs/v4（87，含本报告）/
              requirements.txt / .env.example
   excludes   workspace/** / node_modules / ui/dist / .env（仅 .env.example，tracked 示例）/
              novel/authoring/story_engine/**（作者运行数据）
   archive 未被提交（临时目录生成后删除）

3) Python packaging（任务书 §30）
   未新增 pyproject.toml / setup.py / wheel build（仓库本无 Python packaging config）

4) Clean-environment smoke（任务书 §34/§35/§36）
   临时 clean venv → pip install -r requirements.txt（exit 0）→ import novelforge →
   create_app() → GET /api/health = 200 → 结束（未跑第二套完整回归）
   随后删除临时 venv

5) Requirements audit（任务书 §37）
   requirements.txt       fastapi / uvicorn / pydantic / httpx / PyYAML / networkx /
                          mcp>=1.9,<2 / sse-starlette<2 / starlette<0.47
   requirements-dev.txt   -r requirements.txt + pytest>=8.0
   ui/package.json        dev / build / preview / test / test:watch（真实存在；无 lint / typecheck script）
   ui/package-lock.json   存在且与 package.json 一致（npm ci 路径可用）
   无临时手工安装依赖遗漏；无意外 major upgrade
```

## 36. Git cleanliness

```text
git status → working tree clean（本报告与 V4-12 文档提交后）
git ls-files → 不含 .env / node_modules / ui/dist / workspace/** / agent runtime /
               plugin runtime / delivery runtime / 临时 archive
.gitignore 覆盖上述全部路径（Layer C test_gitignore_covers_v4_runtime_artifacts）
仓库根目录无临时文件 / 备份 / 一次性脚本
```

## 37. Frozen V3 tag

```text
novelforge-product-v3-final
→ f21464713e4786410e5550a7ad5504692cc644dd
→ 未移动、未重建、未推送

novel/authoring frozen digest        unchanged
story_engine/repair.py               unchanged
REPAIR_GATE_V1                       unchanged
Canon semantics                      unchanged
StoryState semantics                 unchanged
V4-12 未创建 / 未推送任何 tag、未创建 release、未合并分支（任务书 §52）
```

## 38. Known limitations

```text
1. Trusted in-process plugin 模型无 OS sandbox（R-12 = MITIGATED / NOT ELIMINATED）
   permission 治理的是 Host API 能力，不是进程级隔离
2. 历史 V3/V2 acceptance 套件本环境 NOT RUN（作者 acceptance data root 缺失，§27）
3. 默认不启用任何模型 provider → 开箱行为是本地确定性流程（source = rule）
4. 无 lint / typecheck npm script（package.json 只有真实存在的 scripts；未臆造）
5. npm audit 报告 2 条 vite / esbuild advisory（仅影响本地 dev server，不影响构建产物运行）
6. DeliveryStore 按单进程并发假设设计（多进程部署需外部协调，DEFERRED）
```

## 39. Deferred items

```text
MCP agent tools（agent_plan / start / status / …）
Plugin AI / network Host capability（当前只声明 permission）
Plugin marketplace / 远程安装 / 自动升级
Hot reload / runtime unload plugin
Prose / 正文写作核心（明确非 V4 Core）
EPUB 核心 exporter
Agent 编排元数据归档（audit 上限 1000；session / checkpoint 单文件）
Large-project delivery streaming
```

每项均记录在 `V4_12_ARCHITECTURE_DEBT_REVIEW.md` §3，含后续触发条件。

## 40. Release blockers

```text
Release blockers:
NONE
```

依据：full regression 0 failed（§30）、acceptance 28 passed（§3）、前端 60 passed + build PASS（§31）、
浏览器三门 PASS（§32）、frozen guards PASS（§33）、`validate_project` PASS（§34）、
working tree clean（§36）、V3 frozen tag 未移动（§37）、acceptance Layer A/B/C 无 BLOCKER（§29）。

## 41. Release candidate commit

```text
release candidate commit:
cc974ed8ac3adc3a6dcb79a5a460b3390130b5d1
message   docs(v4): finalize v4-12 acceptance report and evidence
branch    v4-12-final-acceptance
改后工作树 clean（§36）
```

V4-12 不创建 tag、不 push、不合并分支（任务书 §52）；只记录 RC commit 与推荐 tag（§42）。

## 42. Recommended V4 release tag

```text
Release version tag:              v4.0.0
Optional frozen product baseline: novelforge-product-v4-final
```

```text
依据：仓库既有语义化 release tag 形态（novelforge-product-v3.0 / v2.0 / story-engine-v2.0），
以及 V3 Final 的冻结产品基线形态（novelforge-product-v3-final）。
本阶段不创建、不推送（任务书 §52/§53）。
```

## 43. Files created

```text
tests/acceptance/conftest.py                      acceptance 测试路径隔离（sys.path）
tests/acceptance/acceptance_support.py            golden_project() / stub gateway / truth hashes
tests/acceptance/test_final_contracts.py          Layer A（9）
tests/acceptance/test_final_integration.py        Layer B（11）
tests/acceptance/test_final_release.py            Layer C（8）
docs/v4/V4_12_ACCEPTANCE_MATRIX.md                18 维度验收矩阵 + 18b NOT RUN
docs/v4/V4_12_EVIDENCE_INDEX.md                   证据索引
docs/v4/V4_12_ARCHITECTURE_DEBT_REVIEW.md         架构债分类复审
docs/v4/V4_12_FINAL_ACCEPTANCE_REPORT.md          本报告（48 节）
docs/v4/V4_12_STATUS.md                           V4-12 工作状态（已标记 superseded）
```

## 44. Files modified

```text
README.md                                         V4 定位重写（Story Blueprint Runtime + Story Studio）
src/novelforge/persistence/paths.py               隔离修复：agent_dir → agent/<novel_id>/
src/novelforge/application/services/agent.py      隔离修复：session_novel_id 按 <novel_id>/sessions 反查
docs/v4/V4_12_STATUS.md                           顶部标记 SUPERSEDED（任务书 §55）
docs/v4/V4_12_EVIDENCE_INDEX.md                   §9 回填 release candidate SHA 与最终数字
```

## 45. Files deleted

```text
git 层面：无（V4-12 未删除任何 tracked 文件）
本地（gitignored，非版本控制）：workspace/studio_ui_test_root* / agent_ui_root* /
  v4_12_ui_root / studio_ui_final / v4_12_clean_venv / 临时 pytest log / 临时 archive
保留（gitignored 证据）：workspace/v4_12_ui_review/**（截图 + downloads）、
  workspace/studio_ui_review/**、workspace/pilot_v2/**
```

## 46. Git branch

```text
v4-12-final-acceptance
```

## 47. Git commits

```text
6459a04  test(acceptance): add v4-12 contract integration and release gates
         （含隔离缺陷修复：persistence/paths.py + application/services/agent.py）
c08c13b  docs(v4): record v4-12 continuation point
cc974ed8ac3adc3a6dcb79a5a460b3390130b5d1
         docs(v4): finalize v4-12 acceptance report and evidence   ← release candidate commit
docs(v4): record v4-12 release candidate commit
         （收尾提交：把 RC SHA 与最终回归数字回填进本报告 §41/§35 与证据索引 §9；
           它是 V4-12 的最后一次提交，分支 tip 即此提交 —— 见 `git log --oneline -3`）
```

## 48. Final verdict

```text
V4-12 = PASS
```

NovelForge V4 开发阶段至此结束（任务书 §67）：现有 V4 已有足够证据作为 release candidate。
