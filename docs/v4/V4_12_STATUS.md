# NovelForge V4-12 — Final Acceptance 状态（进行中）

> 状态：**IN PROGRESS（未完成，下一步明确）**　分支：`v4-12-final-acceptance`
> 已完成：三层 acceptance 测试套件 + 一处真实隔离缺陷修复（见下）。
> 未完成：full pytest 基线记录、前端 / 浏览器回归重跑、4 份必需文档、README 更新。

## 已完成（有证据）

```text
tests/acceptance/**（28 tests，全部 PASS）
  Layer A test_final_contracts.py（9）
    SSOT 存在性 + 旧稿降级 + 版本独立性 + public contract + Q0–Q9 无漂移 +
    无权威总分 + provider 边界扫描 + ContextBuilder/Gateway 唯一性 +
    V4 文档无过时表述 + 模块循环依赖扫描（plugins/host.py 为已登记 composition 例外）
  Layer B test_final_integration.py（11）
    Golden Project 形状（§12）+ 端到端作者控制权（§14–§15）+ revision append-only（§16）+
    restore 新 revision（§16）+ 并发冲突不覆盖（§17）+ Agent revision/approval stale（§17）+
    幂等（generation / editor / agent step，§18）+ memory 派生可重建（§21）+
    ContextBuilder 使用（§22）+ Canon/StoryState 不可变（§20）
  Layer C test_final_release.py（8）
    跨作品隔离（memory / plugin state / agent runtime / blueprint，§19）+
    MCP 不跨作品读取 + 交付可复现与无 secret（§30–§32）+ stale/unaccepted 交付被阻止 +
    MCP core baseline（23 tools / 13 resources）+ 插件增量与 disable 恢复 +
    错误契约稳定（§53）+ 仓库卫生与 .gitignore（§77–§78）

真实缺陷修复（V4-12 发现）
  agent 持久化路径原为 novel 无关目录 → 不同作品的 session 会互相可见（违反 §19）。
  修复：persistence.paths.agent_dir 改为 `.../agent/<novel_id>/`；
  session_novel_id 改为按 `<novel_id>/sessions/<session_id>.json` 反查。
  证据：tests/acceptance/test_final_release.py::test_cross_novel_isolation_everywhere
```

## 下一步（按顺序，完成即可 PASS）

```text
1. pytest -q（§68 必跑）→ 记录 passed / skipped / failed / duration
2. npm test + npm run build（§72）→ 记录
3. 浏览器回归（§73–§75）：browser_v4_studio_golden / browser_v4_11_agent /
   browser_v4_legacy_entry（用 scripts/studio_ui_test_server.py）
4. docs/v4/V4_12_ACCEPTANCE_MATRIX.md（§4，覆盖 18 个维度）+ V4_12_EVIDENCE_INDEX.md（§93）
   + V4_12_ARCHITECTURE_DEBT_REVIEW.md（§58–§60）+ V4_12_FINAL_ACCEPTANCE_REPORT.md（§95 的 48 节）
5. README 更新为真实 V4 定位（§62；保留 V3 release history + mcp 依赖区间说明 §63）
6. Release dry run（§65：无 Python packaging 配置 → 前端 build + git archive 干跑）+
   clean-venv smoke（§66，成本过高则记录原因）
7. commit；输出 release candidate commit + 建议 tag（**不创建 / 不 push tag**，§80–§81、§101）
```

## 已知残余（§59–§60、§83）

```text
trusted in-process plugin 无沙箱（ACCEPTED_RISK，R-12 MITIGATED / NOT ELIMINATED）
历史 V3/V2 acceptance 数据根缺失（NOT RUN，非 blocker —— frozen guards PASS 即可）
MCP agent tools / 插件 AI·网络能力 / prose / EPUB / 插件市场 / 热重载（DEFERRED）
Agent 编排元数据增长（DEFERRED，audit 上限 1000 条）
```
