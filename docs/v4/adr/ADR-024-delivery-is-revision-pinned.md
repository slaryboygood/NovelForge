# ADR-024 — Delivery Is Revision-Pinned

```
Status    : Accepted（V4-07 实施完成）
Date      : 2026-09-18
Context   : V4-07 Delivery, Export & NovelForge Package
Related   : ADR-006（revision model）；ADR-021（editor mutations are append-only）；
            ADR-023（restore creates a new revision）；V4_DELIVERY_CONTRACT.md §7–§9
```

## Context

导出最直觉的实现是"边遍历边读当前文件"：

```text
读 Premise r2 → 读 Character r3 → （期间别人改了 Character）→ 读 Scene r7
```

这样同一份交付物里可能一半是新内容、一半是旧内容，而且无法回答"这份交付物
究竟用了哪些 revision"。V4-06 又引入了编辑与 AI 改写 → 导出期间发生新 revision 是常态。

## Decision

1. **交付必须先解析一次 revision 选择，形成 `DeliverySnapshot`**
   （node_id → revision；accepted / explicit_revisions / current 三种模式）。
2. **snapshot 之后的全部读取都使用钉住的 revision**（compiler / exporters / manifest）。
   导出过程中产生的新 revision **不影响**本次交付。
3. **snapshot 不产生 Blueprint revision**（它是 release snapshot，不是新版本）。
4. manifest 显式记录 `selected_revisions`；snapshot 与 manifest 都落盘，可事后解释。
5. 正式发布默认模式是 `accepted`（取 status == accepted 的最新 revision），
   不是"编号最大的 revision"（§9）。

## Consequences

正面：

* 交付物可以自证来源（哪一本、哪些 revision、谁接受的）；
* 并发编辑不会污染正在生成的交付物；
* 复查/复现只需 snapshot + policy + exporter version。

代价：

* 需要多一次 resolve 步骤与 snapshot 落盘（成本很小，收益是可解释性）；
* 交付期间的编辑不会反映到本次交付（这是期望行为，需要 UI 提示）。

## Alternatives considered

| 方案 | 为什么不选 |
| --- | --- |
| 边遍历边读当前 revision | 交付物内部不一致；无法解释来源（§23–§24） |
| 为导出给所有节点创建新 revision | 污染 canonical 历史；违反 ADR-021 |
| 只记录"当前时间点"而不记录 revision | 无法验证质量结论是否针对这些 revision（§12） |

## Evidence

```text
src/novelforge/delivery/selection.py     RevisionSelector（accepted / explicit / current）
src/novelforge/delivery/service.py       _build_snapshot / compiler.compile(snapshot.node_revisions)
src/novelforge/delivery/store.py         snapshots/<snapshot_id>.json
tests/delivery/test_delivery_service.py  snapshot 稳定性、并发不改变、不产生 revision
tests/delivery/test_selection.py         proposed / rejected 不进入交付
```

