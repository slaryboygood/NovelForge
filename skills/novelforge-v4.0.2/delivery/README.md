# Module: `delivery` — revision-pinned 交付（V4.0.2）

> 本文件覆盖（override）`skills/novelforge-v4.0.1/delivery/README.md` 的继承版本。
> 只在 **issue 生命周期语义** 上有差异（PB-1 修复）；其余内容与 V4.0.1 相同。

```text
Module purpose     把（已钉住 revision 的）Blueprint 编译为可复现、可验证的交付物
Authoritative owner src/novelforge/delivery/{service,selection,validation,compiler,manifest,store,exporters}.py
Owned skills       validate-delivery / create-delivery-snapshot / deliver-blueprint /
                   inspect-delivery-manifest / download-delivery-artifact / list-delivery-snapshots
Truth ownership    交付快照 / manifest / artifact（只读消费 Blueprint + Quality + Editor metadata）
Public interfaces  UI「交付」；REST /delivery*、/studio/delivery/formats；
                   Application ExportService；MCP tools validate_delivery /
                   create_delivery_snapshot / deliver_blueprint + delivery resources
Dependencies       blueprint（只读）、quality store（只读）、editor metadata（只读）、core、persistence
Forbidden          调用 LLM、改 Blueprint / Canon / StoryState、修 issue、自行拼路径、
                   导出未钉住 revision 的状态
Related modules    quality（Q9 preflight 输入）、editor（review 元数据）
```

## 事实表

| 项 | 值 |
| --- | --- |
| selection modes | `accepted`（默认）/ `explicit_revisions` / `current` |
| profiles | `reader` / `author`（默认）/ `machine` / `audit` |
| formats（Core） | `json` / `markdown` / `docx` / `nfpack`（插件可追加） |
| schema 版本 | `DELIVERY_SCHEMA_VERSION = 1`、`PACKAGE_VERSION = 1` |
| 默认 policy | `require_accepted=true`、`require_quality_pass=true`、`allow_unevaluated=false`、`allow_stale_quality=false` |

## issue 生命周期语义（V4.0.2 起，PB-1 修复）

```text
preflight 回答的是"**当前要交付的 Blueprint 现在是否仍有阻塞问题**"，
而不是"这个作品历史上是否出现过阻塞问题"。

因此 delivery 只消费 Quality Store 里的 **live issue**：
  status ∈ {open, repairing}
  AND 该 issue 仍出现在**最新一份覆盖其 scope 节点**的质量报告里
  AND （按被选 revision）该报告评估的正是这个 revision

已 resolved / accepted_risk / ignored 的 issue **不再阻塞**；
被新报告取代的历史 issue（最新报告里没有它）也**不再阻塞**；
仍然 open 且仍在最新报告里的 blocker / major 照常阻塞（policy 开关也无法放宽）。
唯一 owner 是 Quality Store（`latest_coverage()` / `live_issues()`），delivery 不重新实现判定。
```

## 不变量

```text
REVISION_PINNED：快照记录每个 node_id → revision，导出始终基于快照
NO_INVENTED_CONTENT：编译器只输出 visible 字段，内部 metadata 不进正文
VALIDATED_BEFORE_RELEASE：preflight 通过才发布；失败给 blocking_reason
ATOMIC_AND_IDEMPOTENT：部分失败不留半个交付物；同一 idempotency_key 不产生第二个快照
NOVEL_ISOLATED：跨作品读取被拒绝
LIVE_ISSUES_ONLY：只有"仍是当前真相"的 quality issue 才参与阻断（V4.0.2）
```

## 当前边界（见 `docs/v4/V4_0_1_SKILL_GAPS.md`）

```text
GAP-007  explicit_revisions / include_node_types 只有 REST / Application 入口，UI 无对应控件
格式清单（含插件 exporter）经 GET /studio/delivery/formats 读取，不要在客户端硬编码
```
