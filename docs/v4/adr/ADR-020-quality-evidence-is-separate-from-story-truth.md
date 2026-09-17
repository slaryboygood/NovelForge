# ADR-020 — Quality Evidence Is Separate From Story Truth

```
Status    : Accepted（V4-05 实施完成）
Date      : 2026-09-17
Context   : V4-05 Quality Closed Loop & Targeted Repair
Related   : ADR-016（Blueprint node graph）；ADR-018（gate-based quality）；
            ADR-014（memory is derived）；V4_QUALITY_CONTRACT.md §45–§46
```

## Context

质量结论需要保存：为什么判定、看了哪些节点、依据哪条 Canon、哪个 evaluator、哪个版本。
最省事的做法是把它塞进 Blueprint 节点：

```text
node.quality = { issues: [...], evidence: [...], history: [...] }
```

这条路的直接问题：

```text
单个节点的 quality evidence 可以达到几十 KB；
节点 revision 是 append-only → 每次评估都会产生新 revision；
于是"评估"变成了"写 blueprint" → 评估不再只读，也会互相覆盖。
```

## Decision

1. **Quality Store 是 quality truth，独立存储**：

   ```text
   novel/authoring/story_engine/quality/<novel_id>/
   ├── reports/<report_id>.json
   ├── issues/<issue_id>.json
   ├── repair_history/<plan_id>.json
   └── MANIFEST.json
   ```

   路径必须经 `persistence.paths`（新增 `quality_dir` 等），quality 不得自行拼路径。
2. **Evaluator 是只读的**：不得修改 Blueprint / Canon / StoryState，不得调用 Repair。
3. **Blueprint 节点的 `quality_status` 只是投影**：由 Application Service 或显式
   lifecycle function 从 Quality Store 投影得到，节点不承载 evidence 明细。
4. **evidence 是一等对象**：`QualityEvidence(evidence_id / kind / source_ids / node_ids /
   revision / excerpt / comparison / metric / explanation)`，不允许只有"感觉不合理"。
5. **provenance 保留审计信息但不保存 prompt 原文**（沿用 V4-02 §60）：
   `request_id / contract_id / contract_version / context_digest / source_ids /
   model / provider`。

## Consequences

正面：

* 评估不产生 Blueprint revision（只读语义成立），不会因"评估"制造版本噪声；
* 质量明细可以无限增长而不污染 canonical artifact；
* 删除 quality 目录不影响 story truth（与 memory 派生层同样的可重建性）。

代价：

* 需要一次投影步骤才能让 UI 看到节点级状态（V4-10 消费 `project_quality_status`）；
* 跨 store 的一致性需要显式验证（`MANIFEST.json` 记录 issue / report 计数）。

## Alternatives considered

| 方案 | 为什么不选 |
| --- | --- |
| evidence 写进节点 payload | 评估变成写操作；节点体积与 revision 噪声失控 |
| 只存最终 PASS/FAIL，不留 evidence | 无法回答"为什么判定"，修复与 MCP 都失去输入（§59） |
| 与 Blueprint 共用 store | quality truth 与 story truth 混淆；删除/重建语义不同 |

## Evidence

```text
src/novelforge/persistence/paths.py          quality_dir / quality_*_dir / quality_manifest_path
src/novelforge/quality/store.py              QualityStore（report / issue / repair history / manifest）
src/novelforge/quality/contracts.py          QualityEvidence（kind / source_ids / comparison / metric）
src/novelforge/quality/service.py            project_quality_status（投影，不写回节点）
tests/quality/test_quality_service.py        节点 quality_status 保持 unevaluated（evaluator 只读）
tests/v4/isolation/test_quality_boundaries.py quality 不自行拼路径 / 不写 Canon / StoryState
```

