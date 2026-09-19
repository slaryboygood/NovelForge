# NovelForge V4.0.1 — Skill Usability Matrix（Dogfood 结果）

> 由 `docs/v4/V4_0_1_SKILL_DOGFOOD_REPORT.md` 的同一次 dogfood 会话产出。
> 列含义：
> `Executed` = executed / simulated / review-only / blocked；
> `Discoverable` = 从 `SKILL_CATALOG.md` 能否找到入口（yes / ambiguous-idle）；
> `Sufficient` = 只靠该 skill 能否知道「需要什么参数 / 前置条件」；
> `Correct` = 文档与实测行为是否一致；
> `Verification works` = 文档给的验证步骤是否真的能执行。

## 汇总

```text
skills reviewed             77 / 77
executed (真实调用成功)      63
simulated (Application/API 直调或受控 fixture)  9
review-only (文档 / 边界类，无需 mutation)      2
blocked (环境 / 产品缺陷阻塞) 3
```

| Skill | Executed | Discoverable | Sufficient | Correct | Verification works | Result |
| ----- | -------- | ------------ | ---------- | ------- | ------------------ | ------ |
| `project.create-novel` | executed | yes | yes | yes | yes | PASS |
| `project.inspect-novels` | executed | yes | yes | yes | yes | PASS |
| `project.rename-novel` | executed | yes | yes | yes | yes | PASS |
| `project.archive-novel` | executed | yes | yes | yes | yes | PASS |
| `studio.open-story-studio` | executed | yes | no | no | yes | FIXED（无 `--root`；隔离根要走 test server） |
| `studio.navigate-studio-workspace` | simulated | yes | yes | yes | yes | PASS（深链接由 golden gate 覆盖） |
| `studio.inspect-overview` | executed | yes | yes | yes | yes | PASS |
| `studio.handle-legacy-url` | simulated | yes | yes | yes | yes | PASS（legacy gate 覆盖） |
| `blueprint.inspect-blueprint` | executed | yes | yes | yes | yes | PASS |
| `blueprint.inspect-node` | executed | yes | yes | yes | yes | PASS |
| `blueprint.inspect-revisions` | executed | yes | yes | yes | yes | PASS |
| `blueprint.inspect-scene-cards` | executed | yes | yes | yes | yes | PASS |
| `blueprint.understand-blueprint-model` | review-only | yes | yes | yes | n/a | PASS |
| `generation.generate-premise` | executed | yes | yes | yes | yes | PASS |
| `generation.generate-theme` | executed | yes | partial | partial | yes | FIXED（parent 会触发 Q0 sequence；code 语义补充） |
| `generation.generate-world` | executed | yes | partial | partial | yes | FIXED（同上） |
| `generation.generate-character` | executed | yes | yes | yes | yes | PASS（index 语义实测正确） |
| `generation.generate-character-arc` | executed | yes | no | no | yes | FIXED（必填 `character_id` 未写） |
| `generation.generate-story-arc` | executed | yes | partial | partial | yes | FIXED（同上） |
| `generation.generate-structural-unit` | executed | yes | partial | no | yes | FIXED（node_id 实为 `act_01`） |
| `generation.generate-chapter-plan` | executed | yes | yes | partial | yes | FIXED（父节点示例 id 错误） |
| `generation.generate-scene-plan` | executed | yes | yes | partial | yes | FIXED（node_id 补零形式） |
| `memory.inspect-derived-memory` | executed | yes | no | no | yes | FIXED（`MemoryQuery(text=…)` 不存在） |
| `memory.build-generation-context` | executed | yes | yes | yes | partial | PASS（digest 复现需要相同 request 参数，文档未强调） |
| `memory.understand-truth-precedence` | review-only | yes | yes | yes | n/a | PASS |
| `quality.evaluate-blueprint` | executed | yes | yes | yes | yes | PASS |
| `quality.inspect-quality-report` | executed | yes | partial | no | yes | FIXED（summary / blockers 口径） |
| `quality.list-quality-issues` | executed | yes | yes | yes | yes | PASS |
| `quality.understand-quality-gates` | simulated | yes | yes | yes | yes | PASS（gate 语义与实测一致） |
| `repair.plan-repair` | executed | yes | yes | yes | yes | PASS（0 mutation 实测） |
| `repair.apply-repair` | executed | yes | yes | yes | yes | PASS（新 revision + verify 诚实报 partial） |
| `repair.verify-repair` | executed | yes | yes | yes | yes | PASS |
| `repair.understand-repair-contract` | simulated | yes | yes | yes | yes | PASS（preserve / allow_change 实测生效） |
| `editor.patch-node` | executed | yes | yes | yes | yes | PASS |
| `editor.rewrite-node` | executed | yes | yes | yes | yes | PASS（越界字段被拒，实测） |
| `editor.accept-revision` | executed | yes | yes | partial | yes | FIXED（重复 accept 不是 idempotent） |
| `editor.reject-revision` | executed | yes | yes | yes | yes | PASS |
| `editor.restore-revision` | executed | yes | yes | yes | yes | PASS（diff 验证 payload 一致） |
| `editor.diff-revisions` | executed | yes | yes | yes | yes | PASS |
| `delivery.validate-delivery` | executed | yes | partial | partial | yes | FIXED（无顶层 excluded；policy 不能放宽全部 blocker） |
| `delivery.create-delivery-snapshot` | executed | yes | yes | yes | yes | PASS |
| `delivery.deliver-blueprint` | executed | yes | partial | partial | yes | PARTIAL（默认 policy 被历史 issue 卡住；explicit_revisions 成功） |
| `delivery.inspect-delivery-manifest` | executed | yes | yes | yes | yes | PASS（checksum 与下载一致） |
| `delivery.download-delivery-artifact` | executed | yes | yes | yes | yes | PASS（4 格式 bytes / MIME / 文件名正确） |
| `delivery.list-delivery-snapshots` | executed | yes | yes | yes | yes | PASS |
| `canon.inspect-canon-truth` | executed | yes | yes | yes | yes | PASS（空 Canon 返回空列表） |
| `canon.inspect-canon-graph` | executed | yes | yes | yes | yes | PASS |
| `canon.validate-canon-integrity` | executed | yes | yes | yes | yes | PASS |
| `canon.validate-planning-against-canon` | executed | yes | no | no | yes | FIXED（novel_id 为 query；chapter schema 未写） |
| `canon.rebuild-canon` | executed | yes | partial | no | yes | FIXED（novel_id 为 query） |
| `story-state.understand-story-state-boundary` | simulated | yes | yes | yes | yes | PASS |
| `story-state.inspect-story-state` | executed | yes | yes | partial | yes | PASS（字段名 `timeline.current_time`，文档列得不全） |
| `plugins.inspect-plugins` | executed | yes | yes | yes | yes | PASS |
| `plugins.inspect-plugin-contributions` | executed | yes | partial | partial | yes | FIXED（声明 vs 已注册贡献） |
| `plugins.approve-plugin` | executed | yes | yes | yes | yes | PASS |
| `plugins.enable-plugin` | executed | yes | yes | yes | yes | PASS（原子注册实测） |
| `plugins.disable-plugin` | executed | yes | yes | yes | yes | PASS（精确卸载实测） |
| `agent.plan-agent-goal` | executed | yes | yes | partial | yes | FIXED（字段名 requires_approval / status=planning） |
| `agent.start-agent-session` | executed | yes | yes | partial | yes | FIXED（响应字段与文档不一致；repair 可能 skipped） |
| `agent.inspect-agent-session` | executed | yes | partial | no | yes | FIXED（返回 {session,runs,checkpoint,audit}） |
| `agent.approve-agent-run` | executed | yes | yes | no | yes | BLOCKED（approve → session failed；已写进 skill 警告） |
| `agent.resume-agent-session` | executed | yes | yes | yes | yes | PASS（failed session 拒绝 resume；body 需 session_id） |
| `agent.cancel-agent-session` | executed | yes | yes | yes | yes | PASS（语义文案与门禁一致） |
| `mcp.start-mcp-server` | blocked | yes | no | no | yes | BLOCKED（stdio 入口崩溃；需 PYTHONPATH=src） |
| `mcp.discover-mcp-surface` | executed | yes | yes | yes | yes | PASS（23 tools / 13 resources 实测一致） |
| `mcp.read-mcp-resource` | executed | yes | yes | yes | yes | PASS（11 个 resource 读取成功，含 artifact manifest） |
| `mcp.call-mcp-tool` | executed | yes | yes | partial | yes | PARTIAL（ok=false 时 errors 可能为空） |
| `mcp.understand-mcp-boundary` | simulated | yes | yes | yes | yes | PASS |
| `ai.configure-llm-provider` | simulated | yes | yes | yes | yes | PASS（未写真实 secret；仅校验配置结构） |
| `ai.inspect-llm-provider-config` | executed | yes | yes | yes | yes | PASS（enabled 为空 = 默认不启用） |
| `ai.run-without-provider` | executed | yes | yes | yes | yes | PASS（422 GENERATION_UNAVAILABLE + 0 mutation） |
| `ai.understand-llm-gateway-boundary` | review-only | yes | yes | yes | n/a | PASS |
| `workflows.create-new-story-blueprint` | executed | yes | partial | partial | yes | PARTIAL（GAP-002 场景缺 setup/payoff；sequence 陷阱已记录） |
| `workflows.review-and-repair-blueprint` | executed | yes | yes | yes | yes | PARTIAL（stub 无法真正修复 → verify 报 partial，属预期） |
| `workflows.prepare-final-delivery` | executed | yes | partial | partial | yes | PARTIAL（需 explicit_revisions 才能完成交付） |
| `workflows.operate-with-agent` | executed | yes | yes | partial | yes | BLOCKED（protected approval 路径失败） |
| `workflows.use-novelforge-through-mcp` | executed | yes | partial | partial | yes | BLOCKED for stdio / PASS for in-process |

## Skill Discovery Test（§38）

| 自然语言目标 | 入口 skill | 跳数 | 歧义 |
| --- | --- | --- | --- |
| 「我要生成一个角色」 | `generation.generate-character` | 1 | 无 |
| 「这个故事为什么交付不了？」 | `delivery.validate-delivery`（blocking_reason）→ 必要时 `quality.inspect-quality-report` | 1–2 | 低（两个入口互补，不是重复） |
| 「我要修复一个质量问题」 | `repair.plan-repair` | 1 | 无 |
| 「我要恢复旧 revision」 | `editor.restore-revision` | 1 | 无 |
| 「我要导出 DOCX」 | `delivery.deliver-blueprint` → `download-delivery-artifact` | 1–2 | 低（交付与下载是两步） |
| 「我要检查 Canon 冲突」 | `canon.validate-canon-integrity` 或 `quality.evaluate-blueprint`（Q2） | 1 | **有歧义**：Canon 自洽 vs 蓝图↔Canon 对照，catalog 未区分 |
| 「我要让 Agent 帮我规划下一步」 | `agent.plan-agent-goal` | 1 | 无 |

结论：catalog → module README → skill 的 1–2 跳路径对多数目标足够；
唯一真实歧义是 Canon 相关目标（建议在 catalog / DEPENDENCY_MAP 增加一句分流说明）。
