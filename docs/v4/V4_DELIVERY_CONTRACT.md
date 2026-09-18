# NovelForge V4 — Delivery & Export Contract（V4-07 冻结，SSOT）

> 状态：**V4-07 Delivery, Export & NovelForge Package**（2026-09-18 实施完成）
> 定位：**交付链的最终 SSOT**。`docs/v4/V4_EXPORT_SPEC.md`（V4-00 设计稿）自本文件起
> 降级为**设计输入 / 历史依据**，不再声称自己是 SSOT。
> 依据：任务书 §5–§53；ADR-024 / ADR-025 / ADR-026

---

## 1. 不变量（§5）

```text
DELIVERY_READS_CANONICAL_ARTIFACTS     只读 blueprint / quality / editor metadata
DELIVERY_NEVER_INVENTS_STORY_CONTENT   不创作、不修复、不猜内容
DELIVERY_IS_REVISION_PINNED            snapshot 决定一切读取
DELIVERY_IS_NOVEL_ISOLATED             A 的交付不含 B 的任何数据
DELIVERY_IS_REPRODUCIBLE               同 snapshot + policy + exporter version → 同内容
DELIVERY_IS_VALIDATED_BEFORE_RELEASE   preflight + post-build 双重校验
```

交付链（§6）：

```text
DeliverySelection → Revision Resolution → DeliverySnapshot → preflight Validation
→ BlueprintCompiler → Exporters(staging) → post-build Validation → publish
→ Manifest(+checksums) → DeliveryResult
```

**0 次 LLM 调用**（§49）；**不修 Quality Issue**（§50）；**不写 Blueprint / Canon / StoryState**。

**V4-09 additive 扩展（插件 exporter，不改变 Core 语义）**：

```text
· ExporterSpec 增加 owner_type（core|plugin）+ owner_id（§75）
· ExporterRegistry.register：同 format 且 owner 不同 → DeliveryFormatError；
  同 owner 重复注册 = 该 owner 更新自己的 handler（Core 行为不变）
· ExporterRegistry 增加 unregister_owner / owners（Core 注册永不被卸载）
· DeliverySelection 增加只用于构造期校验的 accepted_formats（= Host 注入 registry 的 formats）；
  不参与 selection digest → Core 交付语义不变（未知格式仍被拒绝）
· 插件 exporter 产出的 artifact 与 nfpack 一样经过 secret scan；post-build 校验 /
  path validation / manifest / checksum 一律不可绕过

见 `V4_PLUGIN_CONTRACT.md` §9。
```

---

## 2. Public Contract（§19）

```text
src/novelforge/delivery/__init__.py

DeliveryService / delivery_service     交付编排（describe / validate / snapshot / deliver）
DeliveryStore                          快照 / manifest / artifact 落盘（原子发布）
DeliveryRequest / DeliveryResult       请求与统一结果
DeliveryPolicy / DeliverySelection     放行规则 / 选择策略
DeliverySnapshot / DeliveryManifest    钉住的 revision / 交付清单
DeliveryValidationResult / DeliveryIssue preflight·post-build 结论 / 稳定 issue code
ExportArtifact / NovelForgePackage     交付物 / .nfpack 结构
ExporterRegistry / ExporterSpec        exporter 注册表（插件留给 V4-09）
DeliveryError 家族
```

Application（唯一 facade）：

```text
application.services.ExportService（V4-01 建立，V4-07 收敛为 facade）
  legacy：projection / validate / export / writer_bundle   ← V3 planning export（compatibility）
  V4：    delivery_selection / describe_delivery / validate_delivery /
          create_snapshot / deliver / delivery_snapshot / delivery_manifest /
          delivery_artifact / delivery_snapshots
```

REST（thin，`api/delivery_routes.py`）：

```text
POST /api/story-builder/delivery
GET  /api/story-builder/delivery/snapshots
GET  /api/story-builder/delivery/{snapshot_id}
GET  /api/story-builder/delivery/{snapshot_id}/manifest
GET  /api/story-builder/delivery/{snapshot_id}/artifacts/{artifact_path:path}
novel_id 必须显式传入；错误映射 400 / 403 / 409 / 422
```

---

## 3. DeliverySelection 与 mode（§7–§8）

```text
novel_id / selection_mode / explicit_revisions / include_node_types / formats /
profile / include_quality_report / include_provenance / include_revision_history /
include_review_metadata / package_includes_node_files / created_by / request_id / policy
```

| mode | 语义 | 风险 |
| --- | --- | --- |
| `accepted`（默认） | 每个节点取 status == accepted 的最新 revision（未被 review 拒绝） | 无 accepted revision 的节点进入 `excluded`（交付 blocker） |
| `explicit_revisions` | 调用方显式钉住 node_id → revision | revision 不存在 / 归属不符 → `DeliverySelectionError` |
| `current` | 当前 revision（可能是 proposed / unevaluated） | 默认 policy 会因未 accepted / 未评估而**阻断**；放宽必须显式写进 policy |

`selection.digest` 与顺序无关、与内容相关 → 同一 selection 得到同一 `snapshot_id`。

---

## 4. quality / review 判定（§9–§14）

```text
accepted 要求   ← Blueprint lifecycle（status == accepted）
review 判定     ← editor metadata（ReviewDecision：accepted / rejected）
质量真相        ← Quality Store（issue + report），不是节点上的 quality_status 投影
```

质量状态（per 选中 revision R）：

| 条件 | state | 交付后果（require_quality_pass=True） |
| --- | --- | --- |
| R 上有 blocking issue（severity ∈ policy.blocking_severities） | `failed` | `DELIVERY_QUALITY_FAILED`（blocker） |
| 存在报告记录 `node_revisions[node] == R` 且无 blocking issue | `passed` | 通过 |
| 最近一次评估的 revision ≠ R | `stale` | `DELIVERY_QUALITY_STALE`（blocker；`allow_stale_quality=True` 时降为 warning） |
| 完全没有质量证据 | `unevaluated` | `DELIVERY_QUALITY_UNEVALUATED`（blocker；`allow_unevaluated=True` 时豁免） |

```text
§69→§76 的具体化：r3 评估通过后编辑成 r4（未评估）→
  current 导出 + require_quality_pass → DELIVERY_QUALITY_STALE（不得继承 r3 的 PASS）
§14：质量评估之后又发生编辑（EditorOperationRecord.created_at 晚于报告）→
  DELIVERY_INVALIDATION_PENDING（默认 blocker，可 policy 降级）
```

> 实现依赖：V4-05 的 `QualityReport.node_revisions`（报告声明"这次评估覆盖了哪些 revision"，
> 见 `V4_QUALITY_CONTRACT.md` §3.5）。这是本题 "质量结论针对的就是这些 revision" 的唯一依据。

---

## 5. DeliveryPolicy（§15）

```text
require_accepted                 默认 True
require_quality_pass             默认 True（与 accepted 互相独立，§11）
blocking_severities              默认 (blocker, major)
allow_unevaluated                默认 False
allow_stale_quality              默认 False
require_no_orphans               默认 True
require_no_unpaid_required_setup 默认 True
require_no_placeholders          默认 True
require_no_pending_invalidation  默认 True
partial_allowed                  默认 False
DeliveryPolicy.relaxed()         current 草稿预览用（显式放宽，不隐藏风险）
```

---

## 6. DeliveryValidator（§16–§18、§51）

```text
Q9（V4-05）        = story-level delivery readiness（已存在 Quality Store 的结论）
DeliveryValidator  = 真实 export 请求 + 选中的 revision + package 完整性
```

preflight 检查：ownership / revision 可用性 / schema 兼容 / accepted / review 拒绝 /
质量存在与 revision 匹配 / stale / Q9 blocker（复用 Quality Store，不重复实现）/
必需节点 / orphan / 引用完整性 / 未回收 setup / 占位内容（复用 Q8·Q9 结论）/ 跨作品.

post-build 检查：artifact 非空 / manifest 一致 / 路径安全 / 文本格式可读 / checksum。

稳定 issue code：

```text
DELIVERY_NO_ACCEPTED_REVISION      DELIVERY_REVISION_MISSING
DELIVERY_SCHEMA_UNSUPPORTED        DELIVERY_REJECTED_REVISION
DELIVERY_QUALITY_UNEVALUATED       DELIVERY_QUALITY_FAILED
DELIVERY_QUALITY_STALE             DELIVERY_Q9_BLOCKER
DELIVERY_INVALIDATION_PENDING      DELIVERY_MISSING_REQUIRED_NODE
DELIVERY_ORPHAN_NODE               DELIVERY_REFERENCE_BROKEN
DELIVERY_CROSS_NOVEL_REFERENCE     DELIVERY_PLACEHOLDER_CONTENT
DELIVERY_UNPAID_REQUIRED_SETUP     DELIVERY_OWNERSHIP_MISMATCH
DELIVERY_ARTIFACT_MISSING          DELIVERY_ARTIFACT_EMPTY
DELIVERY_CHECKSUM_MISMATCH         DELIVERY_MANIFEST_MISMATCH
DELIVERY_PATH_UNSAFE
```

---

## 7. Snapshot（§22–§25）

```text
snapshot_id / novel_id / node_revisions / node_types / quality_refs / review_refs /
excluded / policy / selection_digest / schema_version / created_at / request_id /
input_digest（内容锚点，不含时间戳）
```

```text
· 解析一次，之后所有读取都用钉住的 revision（§23–§24）
· snapshot 不产生 Blueprint revision（§25）：导出是只读快照，不是新版本
· 落盘：delivery/<novel_id>/snapshots/<snapshot_id>.json
```

---

## 8. Compiler 与顺序（§26–§31）

```text
BlueprintCompiler：canonical Blueprint graph → 有序交付表示
唯一顺序：node_type order → parent → sequence → node_id tie-break（§27）
唯一可见字段：VISIBLE_FIELDS（作者语言）；INTERNAL_FIELDS 永不出现在 Markdown / DOCX
```

---

## 9. 格式与 profile（§28–§35、§55–§57）

| format | exporter_id | mime | 内容 |
| --- | --- | --- | --- |
| JSON | `delivery.json.v1` | application/json | schema / manifest / novel / profile / blueprint（含 revision / provenance / source_ids）/ quality_summary / review / provenance / revision_history |
| Markdown | `delivery.markdown.v1` | text/markdown | 人类可读分区（前提 / 主题 / 世界 / 人物 / 人物弧 / 故事结构 / 单元 / 章节 / 场景 / 伏笔 / 回收 / 因果） |
| DOCX | `delivery.docx.v1` | …wordprocessingml.document | Story Blueprint Document（最小 OOXML，确定性 ZIP） |
| nfpack | `delivery.nfpack.v1` | application/zip | manifest / blueprint（+ 可选 nodes）/ quality / revisions / provenance / editor / exports |

```text
profile：reader（只看故事）/ author（+ revision / quality 摘要）/
         machine（完整结构化 contract）/ audit（+ provenance / history / operations）
EPUB / screenplay / Fountain：本阶段不实现（正文与剧本格式属插件方向，§33 / §35）
```

---

## 10. Manifest / checksum / 可复现（§39–§44、§42、§79）

```text
DeliveryManifest = package_version / delivery_schema_version / blueprint_schema_version /
  novel_id / project_id / snapshot_id / created_at / selected_revisions / formats /
  exporters(id, version) / quality_policy / quality_summary / review_policy /
  source_ids / artifacts{path, mime_type, checksum(sha256), size} / excluded / input_digest
```

```text
· 每个 artifact 记录 sha256（§41）
· 可复现性：同一 snapshot + policy + exporter version →
  JSON / Markdown 字节一致（artifact checksum 只取决于 revision + policy + exporter version）；
  nfpack 内含 manifest.json（带 created_at）→ package 字节受时间戳影响（明确规范，§42）；
  ZIP 条目名与条目时间戳固定（1980-01-01）→ 除 manifest 时间戳外确定性
· DELIVERY_SCHEMA_VERSION 与 BLUEPRINT_SCHEMA_VERSION 相互独立（§44）
```

---

## 11. 原子性 / 部分失败 / 幂等（§64–§66）

```text
staging（<snapshot_id>.staging）→ 构建全部 artifact → post-build 校验 → 原子 rename 发布
失败：删除 staging，不留伪成功 package；不写 manifest
exporter 失败：默认整单 FAIL（blocked）；policy.partial_allowed=True 时才允许
               status="partial"，并在 manifest.extra.exporter_failures 明示
idempotency_key：同 key 重放返回原 snapshot（idempotent=True），不重复生成 package
```

---

## 12. 安全与归属（§62、§68–§72）

```text
路径：全部经 persistence.paths（delivery_dir / snapshots / manifests / packages / artifacts）
novel_id 必须显式；跨作品 → DeliveryOwnershipError（读 / 写 / 打包全部拒绝）
package 条目名：拒绝 ../ / 绝对路径 / 盘符 / .env / secret 等（§70）
package 内容：不包含 .env / API key / Authorization / 完整 prompt / raw provider response（§71）
机械测试：扫描 package 内所有 JSON/Markdown 文本，确认没有其他作品的唯一标记（§72）
```

---

## 13. 边界（§82–§83）

```text
delivery  → blueprint / quality Public Contract / editor metadata（只读）/ core / persistence.paths
禁止      → api / application / ai / memory / story_engine / HTTP client / 自行拼路径 /
            修 Quality issue / 写 Blueprint · Canon · StoryState
反向      → core / domain / ai / memory / blueprint / generation / quality / editor → delivery 禁止
Application → 可以依赖 delivery（ExportService 是唯一 facade）
Interfaces  → 只依赖 application.services.export
```

---

## 14. 验收判据（V4-07）

```text
[x] delivery 是独立模块；Application ExportService 是唯一 facade；exporter 不做业务选择
[x] accepted / explicit / current 三种 selection；rejected 与 proposed 不会误发布
[x] DeliverySnapshot 钉 revision；并发不改变 snapshot；不产生 Blueprint revision
[x] quality 要求与 accepted 要求独立；Quality Store 是正式来源；stale / unevaluated / rejected 可检
[x] preflight + post-build 校验；复用 Q9；稳定 issue code
[x] BlueprintCompiler 唯一顺序；visible / internal 分离
[x] JSON / Markdown / DOCX / NovelForge Package；exporter 版本化；registry 可扩展
[x] manifest + checksums + artifact ownership + selected revision map + quality summary
[x] no secrets / no other novel / package ≠ repository backup
[x] path traversal 防护 + 原子发布 + 失败不留伪成功 + 幂等
[x] JSON / Markdown 可复现（同 snapshot 字节一致）
[x] 0 LLM 调用；legacy 导出路径盘点 + 移除条件登记
```
