---
name: novelforge-v4.0.1.delivery.validate-delivery
description: 交付预检（0 落盘）：在真正交付前确认 accepted / 质量 / 完整性条件是否满足。
---

# validate-delivery

- **Skill ID**: `novelforge-v4.0.1.delivery.validate-delivery`
- **Version**: 1（baseline `V4.0.1`）
- **Capability Module**: `delivery`
- **Product owner**: `src/novelforge/delivery/validation.py::DeliveryValidator`

## Purpose

用同一套 validator 提前回答"现在能不能交付"，避免生成到一半才失败。

## Use when

- 交付前的必做步骤。
- 想知道差什么才能交付（blocking_reason / issues）。

## Do not use when

- 只关心质量本身 → `inspect-quality-report`。

## Preconditions

```text
Blueprint 有节点；若 selection_mode=accepted 则至少有一个 accepted 节点
```

## Required inputs

| 输入 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- |
| `novel_id` | 是 | — | 目标作品 |
| `selection_mode` | 否 | `accepted` | 交付选择模式 |
| `profile` | 否 | `author` | reader / author / machine / audit |
| `formats` | 否 | `["json","markdown"]` | 目标格式 |
| `require_accepted` / `require_quality_pass` | 否 | true | policy 开关 |
| `allow_unevaluated` / `allow_stale_quality` | 否 | false | 放宽项（要显式） |

## Authoritative interfaces

```text
UI           「交付」→ 预检
REST         POST /api/story-builder/delivery（"dry_run": true）
Application  ExportService.delivery_selection(...) + DeliveryService.validate(selection)
MCP          tool validate_delivery
```

## Procedure

```text
1 confirm novel_id 与格式清单：GET /studio/delivery/formats
2 POST /delivery {novel_id, selection_mode:"accepted", profile:"author",
  formats:[…], dry_run:true}
3 读 validation.{ok, phase, blocking_reason, issues[], selected_revisions, quality_summary}
4 读未被选中的节点：**顶层没有 excluded[]**，看 `validation.quality_summary.excluded`
   （计数）；要逐节点原因用 `GET /delivery/snapshots` 里同一次 selection 的 `excluded[]`
   （node_id / node_type / reason，例如 NO_REVISION / not_accepted）
5 需要放宽时先向作者说明（require_* / allow_* 都是显式决定）
6 next：ok → create-delivery-snapshot / deliver-blueprint；不 ok → 回到 quality / editor
```

## Expected result

```json
{"status":"validated","ok":true,
 "validation":{"ok":true,"phase":"preflight","issues":[]},
 "selected_revisions":{"ch_001":5},
 "manifest":null,"idempotent":false}
```

## Verification

```text
· dry_run 下 0 落盘（delivery snapshots 数量不变）
· validation.phase == "preflight"，且 ok=false 时 blocking_reason 非空
· 与 Q9（Delivery Readiness）结论不冲突（Q9 blocker → preflight 必须拦住）
```

实测补充（V4.0.1 dogfood）：

```text
· `require_accepted` / `require_quality_pass` / `allow_*` 只能放宽"政策类"检查。
  DELIVERY_Q9_BLOCKER / DELIVERY_REJECTED_REVISION / DELIVERY_PLACEHOLDER_CONTENT
  等仍会拦；不要以为把开关全关掉就一定能交付。
· 这些检查读的是 Quality Store 里的历史 issue，**不按 issue.status 过滤**：
  即使底层问题已修好、最新报告该 gate 已 passed、issue 已被 verify 标为 resolved，
  preflight 仍可能继续报同一个 blocker（已知产品问题，见 dogfood report）。
  当前唯一可用绕过口径是把受影响节点排除在 selection 之外（explicit_revisions）。
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `DELIVERY_VALIDATION_FAILED` | 未 accepted / 质量未通过 / 有 blocker | 先 accept 或修质量 |
| 所有节点都在 excluded | 用了默认 accepted 但一个都没接受 | `accept-revision` |
| 格式不支持 | formats 含未知 / 未注册格式 | 用 `/studio/delivery/formats` 的 `format_ids` |

## Safety / invariants

```text
preflight 不落盘、不写 revision、不调用模型
不因客户端方便把默认 selection_mode 改成 current（ADR-028 语义）
quality pass ≠ accepted：两个条件独立（ADR-025）
```

## Side effects

无（dry run）。

## Related skills

`create-delivery-snapshot`、`deliver-blueprint`、`novelforge-v4.0.1.editor.accept-revision`

## Source references

```text
src/novelforge/delivery/validation.py、selection.py
src/novelforge/api/delivery_routes.py
tests/delivery/test_validation.py、tests/delivery/test_selection.py
docs/v4/V4_DELIVERY_CONTRACT.md §6
```
