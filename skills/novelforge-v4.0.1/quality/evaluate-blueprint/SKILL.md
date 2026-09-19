---
name: novelforge-v4.0.1.quality.evaluate-blueprint
description: 对某本作品的 Blueprint 运行 Q0–Q9 质量门禁，得到 gate 结论、issue 与 evidence。
---

# evaluate-blueprint

- **Skill ID**: `novelforge-v4.0.1.quality.evaluate-blueprint`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `quality`
- **Product owner**: `src/novelforge/application/services/review.py::ReviewService.evaluate`

## Purpose

用统一契约发现结构 / 设定 / 叙事 / 因果 / 交付就绪度问题，并留下可追溯 evidence。
不做修复（修复见 repair 模块）。

## Use when

- 生成了一批节点之后。
- 准备交付之前的必做步骤。
- 修复之后再次评估（复核的一部分）。

## Do not use when

- 想直接修问题 → 先 `evaluate-blueprint`，再 `plan-repair`。
- 只想知道某个节点的 issue → `inspect-node` / `list-quality-issues?node_id`。

## Preconditions

```text
Blueprint 至少有 1 个节点（否则评估结果意义有限）
若需要 Q2 的 llm_assisted critic：必须显式启用（默认关闭）
```

## Required inputs

| 输入 | 必填 | 说明 |
| --- | --- | --- |
| `novel_id` | 是 | 目标作品 |
| `gates` | 否 | 子集（例如只跑 `["Q0","Q1"]`）；缺省按 policy 的 required gates |
| `node_ids` | 否 | 只评估指定节点 |

## Authoritative interfaces

```text
UI           「检查」→ 运行检查
REST         POST /api/story-builder/studio/quality/evaluate {"novel_id","gates","node_ids"}
Application  ReviewService.evaluate(scope) / EditorService.evaluate(node_id, gates)
MCP          tool evaluate_blueprint
```

## Procedure

```text
1 confirm novel_id 与当前 blueprint digest（inspect-overview）
2 POST /studio/quality/evaluate {novel_id, gates?:[…], node_ids?:[…]}
3 读 report.status（passed / failed / blocked / needs_human_review）与 report.gates[]
4 读 report.issues[]：code / gate / severity / scope / evidence[] / repairable
5 校验 report.node_revisions 与当前节点 revision 一致（评估针对哪些 revision）
6 next：有 issue → plan-repair（按 issue_ids）；无 blocker → 可以 accept / 交付
```

## Expected result

```json
{"report_id":"qr_…","novel_id":"novel_alpha","status":"failed",
 "gates":[{"gate":"Q6","status":"failed","issue_count":2,"blocker_count":0,
           "evaluator_ids":["quality.semantic.v1"],"duration_ms":12}],
 "issues":[{"issue_id":"qi_…","code":"SCENE_SEMANTIC_REPETITION","gate":"Q6",
            "severity":"major","repairable":true,"evidence":[…] }],
 "node_revisions":{"ch_003":2},"policy":{…}}
```

## Verification

```text
· 每个 issue.code 都在 issue code registry 内（未注册 code 必须报错）
· report.status 与 gate 结论自洽：有 blocker → blocked；有 major → failed
· report.node_revisions 覆盖本次评估范围，且与 inspect-node 的 revision 相同
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| Q2 只跑了 deterministic | `enable_llm_evaluators=false`（默认） | 需要 critic 时显式启用 policy |
| 422 `QUALITY_POLICY_INVALID` | gates 里有未知 gate | 只用 Q0–Q9 |
| issue 指向旧 revision | 评估后节点又被改过 | 重新评估，或按 revision 过滤 |

## Safety / invariants

```text
evaluator 只读：不改 Blueprint / Canon / StoryState
没有权威总分；不要向用户汇报"质量分 82"
插件 evaluator 只有被 policy 显式启用时才参与
```

## Side effects

写 Quality Store（report / issue / evidence 文件）；不改故事内容。

## Related skills

`inspect-quality-report`、`list-quality-issues`、`understand-quality-gates`、
`novelforge-v4.0.1.repair.plan-repair`

## Source references

```text
src/novelforge/application/services/review.py
src/novelforge/quality/service.py、registry.py、store.py
src/novelforge/api/studio_routes.py::quality_evaluate
tests/quality/test_quality_service.py
docs/v4/V4_QUALITY_CONTRACT.md
```
