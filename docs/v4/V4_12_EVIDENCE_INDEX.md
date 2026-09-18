# NovelForge V4-12 — Acceptance Evidence Index

> 状态：**V4-12 Final Acceptance**　用途：不需要翻阅几十份报告即可定位证据。
> 所有数字为 **V4-12 final run**（见 §Full regression / Frontend / Browser）。

## 1. 计划与契约（SSOT）

```text
docs/NOVELFORGE_V4_MASTER_PLAN.md            V4 总体计划
docs/v4/V4_ARCHITECTURE.md                   架构 SSOT（含依赖矩阵）
docs/v4/V4_MODULE_BOUNDARIES.md              模块边界 SSOT（§3.1–§3.17）
docs/v4/V4_DATA_MODEL.md                     数据模型 / truth 分层
docs/v4/V4_BLUEPRINT_CONTRACT.md             Blueprint 契约
docs/v4/V4_LLM_CONTRACT.md                   LLM 契约（设计稿形态；ADR-012 为正式决策）
docs/v4/V4_MEMORY_ARCHITECTURE.md            Memory 架构（设计稿形态；ADR-014/015）
docs/v4/V4_QUALITY_CONTRACT.md               Quality 契约（Q0–Q9）
docs/v4/V4_REPAIR_CONTRACT.md                Repair 契约
docs/v4/V4_EDITOR_CONTRACT.md                Editor 契约
docs/v4/V4_DELIVERY_CONTRACT.md              Delivery 契约
docs/v4/V4_MCP_CONTRACT.md                   MCP 契约
docs/v4/V4_PLUGIN_CONTRACT.md                Plugin 契约
docs/v4/V4_UI_CONTRACT.md                    Story Studio UI 契约
docs/v4/V4_AGENT_CONTRACT.md                 Agent 契约
docs/v4/V4_12_ACCEPTANCE_MATRIX.md           最终验收矩阵（18 维度）
docs/v4/V4_12_ARCHITECTURE_DEBT_REVIEW.md    架构债复审
docs/v4/V4_12_FINAL_ACCEPTANCE_REPORT.md     最终验收报告（48 节）
```

## 2. ADR

```text
docs/v4/adr/README.md                        索引（ADR-001 … ADR-036）
ADR-001…028  V4-00→V4-08：canonical service / gateway / memory / blueprint / quality /
             repair / editor revision / delivery / MCP
ADR-029…031  V4-09 Plugin：extension points / trusted in-process / Core 不可覆盖
ADR-032…033  V4-10 UI：Story Studio 主产品面 / UI 不推导业务真相
ADR-034…036  V4-11 Agent：编排不拥有业务逻辑 / 有界自治 / 可审计可恢复
```

## 3. 阶段报告

```text
docs/v4/V4_00_ARCHITECTURE_REPORT.md          V4-00 Architecture = PASS
docs/v4/V4_01_BOUNDARY_FOUNDATION_REPORT.md   V4-01 = PASS
docs/v4/V4_02_LLM_GATEWAY_REPORT.md           V4-02 = PASS
docs/v4/V4_03_STORY_MEMORY_REPORT.md          V4-03 = PASS
docs/v4/V4_04_BLUEPRINT_GENERATION_REPORT.md  V4-04 = PASS
docs/v4/V4_05_QUALITY_CLOSED_LOOP_REPORT.md   V4-05 = PASS
docs/v4/V4_06_BLUEPRINT_EDITOR_REPORT.md      V4-06 = PASS
docs/v4/V4_07_DELIVERY_REPORT.md              V4-07 = PASS
docs/v4/V4_08_MCP_SERVER_REPORT.md            V4-08 = PASS
docs/v4/V4_09_PLUGIN_PLATFORM_REPORT.md       V4-09 = PASS
docs/v4/V4_10_STORY_STUDIO_REPORT.md          V4-10 = PASS
docs/v4/V4_11_AGENT_MODE_REPORT.md            V4-11 = PASS
docs/v4/V4_12_FINAL_ACCEPTANCE_REPORT.md      V4-12 = PASS
```

## 4. 验收测试（V4-12）

```text
tests/acceptance/test_final_contracts.py      Layer A（9）：SSOT / 版本 / public contract /
                                              无总分 / provider 边界 / 循环依赖
tests/acceptance/test_final_integration.py    Layer B（11）：Golden Project / e2e 作者控制权 /
                                              revision / 并发 / 幂等 / memory / context / Canon
tests/acceptance/test_final_release.py        Layer C（8）：跨作品隔离 / 交付可复现与安全 /
                                              MCP baseline / 错误契约 / 仓库卫生
命令：pytest -q tests/acceptance → 28 passed
```

## 5. 回归证据

```text
Python full regression       pytest -q                → 见最终报告 §30（passed / skipped / failed / duration）
Acceptance                   pytest -q tests/acceptance → 28 passed
Frozen guards                tests/test_v2_frozen_guard.py + tests/test_v3_frozen_guard.py → 12 passed（§33）
validate_project             python scripts/validate_project.py → PASS（§34）
Frontend                     npm test → 60 passed (8 files) ； npm run build → PASS（§31）
Browser                      Story Studio golden / Agent / Legacy entry → PASS（§32）
                               （real Edge + stub model，0 real network model calls）
Dry run / clean venv         git archive HEAD + clean venv smoke → 见最终报告 §35
```

## 6. 浏览器与视觉证据

```text
tests/browser_v4_studio_golden.cjs    Story Studio golden（含 Markdown/DOCX/nfpack 真实下载）
tests/browser_v4_11_agent.cjs         Agent（plan → start → approval → complete + 取消文案）
tests/browser_v4_legacy_entry.cjs     默认→Studio，?ui=v3→V3，?ui=v2→V2
workspace/studio_ui_review/**         截图（landing / overview / creation / characters /
                                      story / scenes / quality / delivery / plugins / agent /
                                      四视口）
workspace/studio_ui_review/downloads/ V4-12 final run 的真实交付物
```

## 7. Golden Project

```text
tests/acceptance/acceptance_support.py::golden_project
  premise / theme / world / 3 characters / character arcs / story arc /
  2 structural units / 4 chapters / 8+ scenes / setup+payoff / causal links
  完全隔离在 tmp_path（不接触作者数据）
```

## 8. 风险与债务

```text
docs/v4/V4_ARCHITECTURE_RISKS.md        R-01…R-18（含 R-10 / R-12 / R-16 的 V4 后状态）
docs/v4/V4_12_ARCHITECTURE_DEBT_REVIEW.md  分类复审（ACCEPTED_RISK 2 / DEFERRED 8 /
                                          COMPATIBILITY_LIMITATION 4 / CLEANUP 2 / BLOCKER 0）
docs/v4/V4_DELETION_PLAN.md             删除项与移除条件
```

## 9. Release Candidate

```text
branch        v4-12-final-acceptance
release candidate commit
              cc974ed8ac3adc3a6dcb79a5a460b3390130b5d1
              docs(v4): finalize v4-12 acceptance report and evidence
results       pytest -q                        1707 passed / 7 skipped / 0 failed / 818.48s
              pytest -q tests/acceptance         28 passed（Layer A 9 / B 11 / C 8）
              frozen guards                      12 passed
              npm test                           60 passed（8 files）
              npm run build                      PASS
              browser gates                      Story Studio / Agent / Legacy entry = PASS
              validate_project                   PASS
final report  docs/v4/V4_12_FINAL_ACCEPTANCE_REPORT.md（48 节，V4-12 = PASS）
V3 frozen tag novelforge-product-v3-final = f21464713e4786410e5550a7ad5504692cc644dd（未移动）
recommended   Release version tag: v4.0.0
              Optional frozen product baseline tag: novelforge-product-v4-final
              （V4-12 不创建 / 不 push 任何 tag）
```
