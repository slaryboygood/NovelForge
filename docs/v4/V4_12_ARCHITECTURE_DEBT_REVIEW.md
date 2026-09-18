# NovelForge V4-12 — Architecture Debt Review

> 状态：**V4-12 Final Acceptance**
> 方法：逐项核对 `V4_ARCHITECTURE_RISKS.md`、`V4_DELETION_PLAN.md`、
> V4-00→V4-11 各阶段报告的 Remaining Risks / DEFER / Compatibility-only 条目。
> 分类：`BLOCKER` / `ACCEPTED_RISK` / `DEFERRED` / `COMPATIBILITY_LIMITATION` / `CLEANUP_ELIGIBLE`

## 1. 按分类汇总

```text
BLOCKER                     0
ACCEPTED_RISK               2
DEFERRED                    8
COMPATIBILITY_LIMITATION    4
CLEANUP_ELIGIBLE            2
```

## 2. ACCEPTED_RISK

| 项 | 现状 | 依据 |
| --- | --- | --- |
| Trusted in-process plugin 无 OS sandbox（R-12） | **MITIGATED / NOT ELIMINATED**：默认不执行未批准插件、权限声明、最小权限上下文、Core 不可覆盖、owner 可卸载、失败隔离、错误净化；但 in-process Python 仍可 `import os` / 开文件 / 建 socket | `V4_PLUGIN_CONTRACT.md` §6、ADR-030、R-12 章节；进程级隔离明确 DEFER |
| 历史 V3/V2 acceptance 数据根缺失 | V2/V3 frozen guards PASS、legacy entry smoke PASS、frozen semantics 未改；历史套件本环境 NOT RUN（两次确认，无伪造数据） | `V4_12_FINAL_ACCEPTANCE_REPORT.md` §27、`tests/test_v2_frozen_guard.py`、`tests/test_v3_frozen_guard.py` |

## 3. DEFERRED

| 项 | 状态 | 后续触发条件 |
| --- | --- | --- |
| MCP agent tools（`agent_plan/start/status/...`） | 明确 DEFER（V4-11 §63、§102） | `AgentService` 已稳定（V4-11 PASS）；需要机器端编排时按同一 facade 暴露 |
| 插件 AI / network Host capability | 仅声明 permission（`ai.invoke` / `network.request`） | 需要真实 Host 中介能力时，经 Gateway 提供窄接口 |
| Plugin marketplace / 远程安装 / 自动升级 | 明确不做 | 需要时应先有 operator boundary 与签名模型 |
| Hot reload / runtime unload plugin | DEFER（逻辑 disable + 重启） | 需要零停机升级时 |
| Prose / 正文写作核心 | 非 V4 Core（ADR-011） | 产品定位变化时（README §Non-goals 已声明） |
| EPUB 核心 exporter | 非 V4 首批 exporter（JSON/Markdown/DOCX/nfpack） | 需要时以插件 exporter 形式提供 |
| Agent 编排元数据归档（audit 上限 1000；session/checkpoint 单文件） | DEFER（V4-12 §22 明确不在本阶段设计 archival subsystem） | 长期会话出现实际增长压力时 |
| Large-project delivery streaming | DEFER | 大型作品出现内存/时间压力时（当前按 snapshot 一次性编译） |

## 4. COMPATIBILITY_LIMITATION

| 项 | 现状 | 移除条件 |
| --- | --- | --- |
| V3 工作台（`ui/src/v3/**` + `/v3/*` 投影） | 保留为显式兼容入口（`?ui=v3`） | 作者确认 V3 投影无消费者 |
| V2 creator 面板（`ui/src/*.tsx` + ~90 legacy 端点） | 保留为显式兼容入口（`?ui=v2`） | V2 面板退出 + legacy 浏览器门禁退出 |
| Legacy writer（`writer_integration.py` + `/writer/*`） | 保留 compatibility（V4 不提供正文编辑器） | 作者确认正文 writer 路径无真实消费者 |
| Legacy export 后端端点（outline / package / writer-bundle） | 保留 compatibility；V4 交付走 `/delivery` | V4-10 UI 切换已完成；条件变为"legacy 浏览器门禁退出" |

## 5. CLEANUP_ELIGIBLE

| 项 | 内容 | 建议 |
| --- | --- | --- |
| `ui/src/v3/export-flow.css` / 旧 export 面板样式 | Studio 交付页已替代其产品路径 | 随 V3 入口退出时一并清理（当前仍被 V3 兼容面引用） |
| Delivery 路由中的 `_export_service` helper 之外的重复构造残留 | V4-10 已收敛为唯一构造点 | 已清理完毕；无剩余 action（保留为"已验证无残留"） |

## 6. 逐项核对结论

```text
R-01 Big Bang Rewrite        → 未发生（V4 分阶段 + 边界守卫）        PASS
R-02 Over-abstraction        → 受 00A/00B 合并规则与 Debt Queue 约束  PASS
R-03 LLM coupling            → 唯一 Gateway + 守卫                   PASS
R-04 Provider coupling       → 配置驱动 provider adapter             PASS
R-05 Prompt sprawl           → contract 版本化（blueprint.*/agent.plan.v1）PASS
R-06 Context explosion       → ContextBuilder 预算 + 唯一性           PASS
R-07 Memory corruption       → 派生 + 可重建 + 跨作品隔离             PASS
R-08 Canon drift             → Canon/StoryState 哈希不变（Layer B）    PASS
R-09 Revision race           → expected_revision + 冲突不覆盖（Layer B）PASS
R-10 Agent duplicate writes  → step id + idempotency + checkpoint     PASS
R-11 Historical data leakage → V4-01 删除 + ownership 参数化           PASS
R-12 Plugin privilege        → MITIGATED / NOT ELIMINATED             ACCEPTED_RISK
R-13 Quality cost explosion  → deterministic first + budget           PASS
R-14 Infinite repair loop    → max_repair_rounds + verifier           PASS
R-15 Writer overwrite        → 正文非 canonical artifact              PASS
R-16 Export contamination    → revision-pinned delivery + 扫描        PASS
R-17 Schema version drift    → 版本独立 + owner 明确                  PASS
R-18 MCP contract instability→ 契约冻结 + 48 项 mcp 测试              PASS

Architecture Debt: 无 BLOCKER；两项 ACCEPTED_RISK、八项 DEFERRED、
四项 COMPATIBILITY_LIMITATION 均有明确触发条件与责任人（后续阶段）。
```
