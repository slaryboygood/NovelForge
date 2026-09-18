# ADR-025 — Accepted And Quality-Passed Are Independent Delivery Requirements

```
Status    : Accepted（V4-07 实施完成）
Date      : 2026-09-18
Context   : V4-07 Delivery, Export & NovelForge Package
Related   : ADR-018（quality is gate-based）；ADR-022（quality pass ≠ author accepted）；
            V4_DELIVERY_CONTRACT.md §4、§5
```

## Context

有了质量门与作者接受之后，交付侧最容易出现的两种偷懒：

```text
A. quality passed  →  认为可以交付（忽略作者还没接受）
B. 节点 accepted   →  认为质量一定没问题（沿用旧 quality_status 投影）
```

现实里这两种情况都会出现：作者可以接受一个"质量有 minor 提示"的版本；
一个 accepted 节点在上游 revision 变化后质量结论会失效。

## Decision

1. `DeliveryPolicy` 把两个要求**分别**声明：`require_accepted` 与
   `require_quality_pass`，默认都为 `True`，互不替代。
2. **质量真相取自 Quality Store**（issue + report），不是 `BlueprintNode.quality_status`
   投影（那只是 V4-05 的投影，可能过时）。
3. 质量结论必须**匹配被选 revision**：报告记录 `node_revisions[node] == R` 才算
   "R 被评估过"；否则 `DELIVERY_QUALITY_STALE`（有旧结论）或
   `DELIVERY_QUALITY_UNEVALUATED`（无结论），默认都是 blocker。
4. review 拒绝（editor metadata）单独形成 `DELIVERY_REJECTED_REVISION` blocker。
5. 交付**不修复**问题（§50）：发现 blocker 就返回 blocked，修复必须回到
   Quality / Editor 工作流。

## Consequences

正面：

* 交付物不会因为"分数通过"或"看起来已接受"而绕过任何一方；
* stale 质量可以被机械检出（编辑后必须重新评估）；
* 交付失败的返回是可行动的（稳定 code + 节点 + revision）。

代价：

* 需要报告记录所覆盖的 revision（V4-05 增加 `QualityReport.node_revisions`）；
* 每次编辑后重新评估成为交付前的常规动作（由 policy 决定是否强制）。

## Alternatives considered

| 方案 | 为什么不选 |
| --- | --- |
| 只信 `quality_status` 投影 | 投影可能过时（节点被编辑后仍是旧值）；无法证明针对哪个 revision |
| 只在交付时跑一遍质量 | 违反 §16（不做第二套 Quality Loop）；也会把交付变成昂贵的写操作 |
| 交付时自动修复 | 违反 §50 / §87；交付必须是只读且可解释 |

## Evidence

```text
src/novelforge/delivery/contracts.py      DeliveryPolicy（两个独立开关）
src/novelforge/delivery/selection.py      _quality_state（passed/failed/stale/unevaluated）
src/novelforge/delivery/validation.py     DELIVERY_QUALITY_* / DELIVERY_REJECTED_REVISION
tests/delivery/test_validation.py         accepted 与 quality 独立、stale、未评估、Q9 复用
tests/editor/test_accept_reject.py        quality pass ≠ accepted（V4-06 侧）
```

