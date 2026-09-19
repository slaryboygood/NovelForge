# Module: `delivery` — revision-pinned 交付

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

## 不变量

```text
REVISION_PINNED：快照记录每个 node_id → revision，导出始终基于快照
NO_INVENTED_CONTENT：编译器只输出 visible 字段，内部 metadata 不进正文
VALIDATED_BEFORE_RELEASE：preflight 通过才发布；失败给 blocking_reason
ATOMIC_AND_IDEMPOTENT：部分失败不留半个交付物；同一 idempotency_key 不产生第二个快照
NOVEL_ISOLATED：跨作品读取被拒绝
```

## 当前边界（见 `docs/v4/V4_0_1_SKILL_GAPS.md`）

```text
GAP-007  explicit_revisions / include_node_types 只有 REST / Application 入口，UI 无对应控件
格式清单（含插件 exporter）经 GET /studio/delivery/formats 读取，不要在客户端硬编码
```
