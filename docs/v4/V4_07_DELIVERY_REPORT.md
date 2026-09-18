# V4-07 DELIVERY / EXPORT RESULT

> 阶段：**V4-07 Delivery, Export & NovelForge Package**
> 分支：`v4-07-delivery-export`（integration branch，单 Agent 顺序执行）
> 基线：`v4-06-blueprint-editor`（V4-06 PASS，1392 passed / 7 skipped / 0 failed）
> 结论：**V4-07 = PASS**

---

## 1. Existing export inventory

见 [`V4_07_DELIVERY_INVENTORY.md`](V4_07_DELIVERY_INVENTORY.md)。要点：

```text
现有 4 条导出路径：export_package（planning）/ outlines（四级大纲）/
                  outline_revision（结构化大纲）/ writer_export_bundle（writer-ready）
全部经 persistence.paths（V4-01 起无硬编码路径），但**没有一条**基于 Story Blueprint revision；
它们无法回答"这次导出用了哪些 revision / 是否 accepted / 质量是否针对这些 revision"。
```

| 既有路径 | 处置 |
| --- | --- |
| `export_package.build_export_projection` / `serialize_export` / `export_package` | COMPATIBILITY_ONLY（V3 路由与隔离测试仍在用） |
| `export_package.validate_export_package` | ADAPT idea（section identity + digest） → DeliveryManifest |
| `outlines.export_outline_bundle` / `outline_revision.export_*` | COMPATIBILITY_ONLY |
| `outline_revision.docx_bytes` | ADAPT（思路）→ `delivery/exporters/docx_exporter.py`（数据源改为 snapshot/compiler） |
| `writer_integration.writer_export_bundle` | COMPATIBILITY_ONLY（§58，只服务旧正文） |
| API `/export/package`、`/export/writer-bundle`、`/outline/export`、`/outlines/{id}/export` | KEEP（compatibility）；V4 主路径改为 `/api/story-builder/delivery/**` |

---

## 2. Delivery architecture

```text
src/novelforge/delivery/
├── __init__.py        Public Contract（精简导出）
├── errors.py          DeliveryError 家族
├── contracts.py       Selection / Policy / Snapshot / Manifest / Issue / Result / Artifact
├── selection.py       RevisionSelector（accepted / explicit / current + quality/review 证据）
├── compiler.py        BlueprintCompiler（唯一顺序 + visible/internal 分离）
├── validation.py      DeliveryValidator（preflight + post-build，稳定 issue code）
├── manifest.py        DeliveryManifest + sha256 checksums
├── store.py           DeliveryStore（staging → 原子发布；快照 / manifest / 幂等记录）
├── exporters/         registry + json / markdown / docx / package exporters
└── service.py         DeliveryService（编排）
src/novelforge/application/services/export.py   ExportService（唯一 facade）
src/novelforge/api/delivery_routes.py           最小 REST（thin）
```

依赖方向（守卫测试机械校验）：

```text
delivery → blueprint / quality（Quality Store）/ editor（metadata）/ core / persistence.paths
application → delivery；interface → application
禁止：delivery → api / application / ai / memory / story_engine；下层 → delivery
```

## 3. Public contracts

```text
DeliveryService / delivery_service / DeliveryStore
DeliveryRequest / DeliveryResult / DeliveryPolicy / DeliverySelection
DeliverySnapshot / DeliveryManifest / DeliveryValidationResult / DeliveryIssue
ExportArtifact / NovelForgePackage / ExporterRegistry / ExporterSpec / DeliveryError 家族
```

## 4. Delivery policy

```text
require_accepted / require_quality_pass（互相独立）/ blocking_severities /
allow_unevaluated / allow_stale_quality / require_no_orphans /
require_no_unpaid_required_setup / require_no_placeholders /
require_no_pending_invalidation / partial_allowed；DeliveryPolicy.relaxed() 明确放宽
```

## 5. Revision selection

```text
accepted（默认）       status == accepted 的最新 revision（未被 review 拒绝）
explicit_revisions     调用方钉住 node_id → revision（不存在 / 归属不符即拒绝）
current                当前 revision（未 accepted / 未评估 → 默认 policy 阻断）
```

## 6. Accepted / rejected handling

```text
§74：r3 accepted / r4 proposed → 只导出 r3（测试断言 r4 独有文本不出现在产物中）
§75：r4 被 review 拒绝 → 不进入交付内容（reject 记录仍在 editor metadata）
§9 ：不是"编号最大就是最终版"，而是 lifecycle + review metadata
```

## 7. Quality / review validation

```text
质量真相 = Quality Store（issue + report），不是节点 quality_status 投影
报告记录 node_revisions → "该 revision 被评估过" 有据可依（V4-05 增补字段）
state：passed / failed / stale / unevaluated → 交付 blocker 或按 policy 降级为 warning
§14：质量评估之后的编辑 → DELIVERY_INVALIDATION_PENDING
§18：Q9 结论直接复用 Quality Store（不重新实现 evaluator）
```

## 8. Delivery snapshot

```text
snapshot_id / node_revisions / node_types / quality_refs / review_refs / excluded /
policy / selection_digest / schema_version / created_at / request_id / input_digest
落盘：delivery/<novel_id>/snapshots/<snapshot_id>.json
§25：snapshot 不产生 Blueprint revision（测试断言导出前后 revision 完全一致）
```

## 9. Blueprint compiler

```text
canonical Blueprint graph → CompiledBlueprint（CompiledNode：payload + visible + provenance）
所有 exporter 共用同一编译结果，不各自决定内容
```

## 10. Ordering

```text
node_type order（premise → … → causal_link）→ parent → sequence → node_id tie-break
测试断言：type rank 单调、场景按 node_id 稳定、输入顺序颠倒得到同一 digest
```

## 11. JSON export

```text
schema / manifest（预览）/ novel / profile / blueprint（nodes + revision + provenance）/
quality_summary / review / provenance / revision_history
versioned（delivery_schema_version + blueprint_schema_version + exporter id/version）
round-trip 可读；同 snapshot 两次导出字节一致（checksum 相同）
```

## 12. Markdown export

```text
分区：故事前提 / 主题 / 世界 / 人物 / 人物弧 / 故事结构 / 单元结构 / 章节 / 场景 /
      伏笔 / 回收 / 因果关系（顺序固定）
零内部 metadata：不出现 node_id / revision / request_id / digest / provider /
      truth_layer / (player) / (npc) / sqlite / export_id（测试逐项扫描）
```

## 13. DOCX export

```text
Story Blueprint Document（不是小说正文）；最小 OOXML（zip + document.xml），无第三方依赖
ZIP 条目时间戳固定 → 两次导出字节一致（checksum 相同）
不输出内部 metadata；不含 node id
```

## 14. NovelForge Package

```text
manifest.json / blueprint/blueprint.json（+ nodes/ 由 selection 决定）/
quality/{summary,issues}.json / revisions/snapshot.json / provenance/provenance.json /
editor/review-summary.json / exports/blueprint.*（同次交付生成的 md/docx）
不是项目目录备份：无 cache / logs / .env / .git / node_modules / 其他作品 / 运行数据
```

## 15. Manifest

```text
package_version / delivery_schema_version / blueprint_schema_version / novel_id /
project_id / snapshot_id / created_at / selected_revisions / formats /
exporters(id+version) / quality_policy / quality_summary / review_policy / source_ids /
artifacts{path, mime_type, checksum, size} / excluded / input_digest
同时写入 package 内的 manifest.json 与 delivery/<novel>/manifests/<snapshot>.json
```

## 16. Checksums

```text
每个 artifact 记录 sha256；测试逐项比对 manifest.checksum == sha256(content) 且 size 一致
```

## 17. Export profiles

```text
reader（只看故事）/ author（+ quality / provenance 摘要）/
machine（完整结构化 contract）/ audit（+ revision history / operations）
profile 默认值集中定义（PROFILE_DEFAULTS），selection 可显式覆盖，避免布尔参数爆炸
```

## 18. Visible / internal metadata separation

```text
compiler.VISIBLE_FIELDS 定义各类型可见字段；INTERNAL_FIELDS 列出绝不外显的字段
Markdown / DOCX 只用 visible；JSON / nfpack / audit profile 才包含内部 metadata
```

## 19. Preflight validation

```text
ownership / revision 可用 / schema 兼容 / accepted / review 拒绝 / 质量（存在·匹配·stale）/
Q9 blocker / 必需节点 / orphan / 引用完整性 / 未回收 setup / 占位内容 / 跨作品 /
invalidation pending —— 全部在**写文件之前**完成（§80）
```

## 20. Post-build validation

```text
artifact 非空 / manifest 一致 / 路径安全 / 文本格式可读 → 失败则不发布（§81）
```

## 21. Atomicity

```text
staging 目录构建 → 校验 → 原子 rename 发布；失败删除 staging（无伪成功 package）
§65：exporter 失败默认整单 blocked；只有 partial_allowed=True 才产出 status=partial 并明示
测试：模拟 docx exporter 崩溃 → 无 package / 无 manifest / 无 staging 残留
```

## 22. Reproducibility

```text
JSON / Markdown：同 snapshot + policy + exporter version → 字节一致（checksum 相同）
nfpack：条目时间戳固定；但内含 manifest.json（created_at）→ package 字节受时间戳影响
        （明确规范，§42）
```

## 23. Idempotency

```text
idempotency_key 记录在 delivery/<novel>/requests/<key>.json；
重放返回原 snapshot / manifest（idempotent=True），不重复生成 package（测试覆盖 API 与 service）
```

## 24. Ownership isolation

```text
所有入口要求显式 novel_id；跨作品 → DeliveryOwnershipError（读 / 写 / 打包）
novel_id 相同 node_id 的两本作品：snapshot / artifact / manifest 完全隔离（测试）
package 文本扫描确认不含其他作品唯一标记（§72）
```

## 25. Security / no-secrets

```text
ZIP 条目名：拒绝 ../ / 绝对路径 / 盘符 / ~ / .env / secret 等（§70）
内容扫描：package 不含 API_KEY / Authorization / Bearer / sk- / .env / raw response（§71）
发现命中 → 交付 blocked，不发布
```

## 26. Application ExportService

```text
唯一 facade：delivery_selection / describe_delivery / validate_delivery /
create_snapshot / deliver / delivery_snapshot / delivery_manifest / delivery_artifact /
delivery_snapshots；legacy 方法（projection / validate / export / writer_bundle）保留
REST（thin）：POST /delivery、GET /snapshots、GET /{id}、GET /{id}/manifest、
GET /{id}/artifacts/{path}；错误映射 400 / 403 / 409 / 422
```

## 27. Legacy export migration

```text
4 条 legacy 路径全部盘点并登记（删除条件：V4-10 UI 切换 + legacy 门禁退出）；
V4 主路径不再有多套 export assembly（守卫测试：路由只调用 application.services.export）
```

## 28. Module boundary verification

`tests/v4/isolation/test_delivery_boundaries.py`（11 个永久守卫）：

```text
delivery 不 import interface / application / ai / memory / domain / HTTP client
delivery 只依赖 blueprint / quality / editor metadata / core / persistence.paths
delivery 不自行拼 artifact 路径；不写 Blueprint · Canon · StoryState；不调用 repair
delivery 无模型调用面（gateway / LLMContract / model_policy）
下层（core / domain / ai / memory / blueprint / generation / quality / editor）不得 import delivery
delivery 顶层不 import application / api / ai / memory / domain
Public Contract 精简；REST 路由只调用 application.services.export
Application facade 经 DeliveryService / DeliveryRequest
```

---

## 29. Tests

```text
pytest -q                                1463 passed / 7 skipped / 0 failed（518s）
tests/delivery/**                          60 passed（contracts / selection / validation /
                                            exporters / package / service / facade+API）
tests/v4/**                                90 passed（含 11 个 delivery 边界守卫）
tests/editor/**                           110 passed（未受影响）
tests/quality/**                          122 passed（新增 report.node_revisions 后仍全绿）
tests/generation/**                        57 passed
tests/memory/**                            61 passed
tests/ai/**                                90 passed
python scripts/validate_project.py         PASS
tests/test_v2_frozen_guard.py + v3         12 passed
```

### 29.1 测试数量变化解释（V4-06 → V4-07）

| 类别 | 变化 | 原因 |
| --- | --- | --- |
| `tests/delivery/**` | **+60** | 本阶段新增：契约与注册表、revision 选择、preflight 校验、exporter（JSON/Markdown/DOCX）、package、交付服务（快照/原子/幂等/复现/隔离）、facade + REST |
| `tests/v4/isolation/**` | **+11** | 新增 delivery 模块边界守卫 |
| 既有测试 | ±0 | 只新增模块；quality 仅新增报告字段，blueprint / editor / generation 行为未变 |

离线保证（§78）：全部测试使用 StubProvider，`0` 次真实 API 调用；交付本身也不调用模型。

---

## 30. Browser / download verification

```text
本环境**不可用** Playwright / node_modules（tests/browser_*.cjs 需要的运行时不在此环境）。
因此没有执行浏览器下载门禁 —— 如实记录，不伪造 PASS（§86）。
替代验证：
  · 新增 REST 链路由 TestClient 端到端验证（POST → GET manifest → GET artifact 字节长度一致）
  · artifact 落盘与读取由 DeliveryStore 测试覆盖（读回字节 == 生成字节）
V4-10（UI 切换）时必须补跑对应的浏览器下载门禁。
```

---

## 31. Frozen boundary

```text
novelforge-product-v3-final tag        未移动
novel/authoring frozen digest          未变化（V2/V3 frozen guard PASS）
story_engine/repair.py / REPAIR_GATE_V1 未修改
Canon / StoryState 语义                 未修改（交付只读；测试断言前后字节一致）
Blueprint 语义                          未修改（导出不产生 revision）
quality 契约                            只新增报告字段 node_revisions（additive，不改变 gate 语义）
```

---

## 32. Files created

```text
src/novelforge/delivery/{__init__,errors,contracts,selection,compiler,validation,manifest,store,service}.py
src/novelforge/delivery/exporters/{__init__,json_exporter,markdown_exporter,docx_exporter,package_exporter}.py
src/novelforge/api/delivery_routes.py
tests/delivery/{delivery_support,test_delivery_contracts,test_selection,test_validation,
                test_exporters,test_package,test_delivery_service,
                test_export_facade_and_api}.py
tests/v4/isolation/test_delivery_boundaries.py
docs/v4/V4_07_DELIVERY_INVENTORY.md
docs/v4/V4_DELIVERY_CONTRACT.md
docs/v4/V4_07_DELIVERY_REPORT.md（本文件）
docs/v4/adr/ADR-024-delivery-is-revision-pinned.md
docs/v4/adr/ADR-025-accepted-and-quality-passed-are-independent-delivery-requirements.md
docs/v4/adr/ADR-026-novelforge-package-is-a-selected-artifact-not-a-repository-backup.md
```

## 33. Files modified

```text
src/novelforge/persistence/paths.py           新增 delivery 路径 + ARTIFACT_KINDS += delivery
src/novelforge/persistence/__init__.py        导出 delivery 路径函数
src/novelforge/quality/contracts.py           QualityReport.node_revisions（交付可验证质量归属）
src/novelforge/quality/service.py             填充 node_revisions
src/novelforge/quality/store.py               新增 reports()（按 revision 核对质量结论）
src/novelforge/application/services/export.py ExportService 收敛为 facade + V4 交付方法
src/novelforge/api/app.py                     安装 delivery 路由
docs/v4/V4_DELIVERY_CONTRACT.md（新增 SSOT）、V4_EXPORT_SPEC.md（降级为设计输入）
docs/v4/V4_QUALITY_CONTRACT.md                增补 node_revisions 说明
docs/v4/V4_MODULE_BOUNDARIES.md               §3.14 delivery + 禁令 + 守卫清单
docs/v4/V4_ARCHITECTURE.md                    §4.1 / §5（Export 边界 → Delivery）
docs/v4/V4_MIGRATION_PLAN.md                  V4-07 段按实际交付重写
docs/v4/V4_DELETION_PLAN.md                   legacy 导出路径移除条件登记
docs/v4/V4_BRANCH_STRATEGY.md                 V4-07 分支行 + 分支声明
docs/v4/adr/README.md                         ADR-024/025/026 登记
```

## 34. Files deleted

```text
无（legacy 导出路径全部保留为 V3 compatibility，移除条件已登记）
```

---

## 35. Git branches

```text
v4-07-delivery-export（integration branch，单 Agent 顺序执行）
```

## 36. Git commits

```text
（1）docs(v4): freeze delivery and export contracts
（2）feat(delivery): add revision selection and delivery snapshots
（3）feat(delivery): add delivery validation and manifests
（4）feat(delivery): add blueprint compiler and json markdown exporters
（5）feat(delivery): add docx and novelforge package exporters
（6）refactor(application): route exports through delivery service
（7）test(delivery): add revision pinning package and validation coverage
（8）test(v4): enforce delivery module boundaries
（9）docs(v4): record v4-07 result
```

---

## 37. Remaining risks

| 风险 | 状态 | 说明 |
| --- | --- | --- |
| nfpack 字节受 manifest 时间戳影响 | 已规范（§42） | JSON / Markdown 完全可复现；package 若需要 bit-for-bit 需版本化时间戳策略（后续阶段可加 `created_at` 冻结选项） |
| legacy 4 条导出路径仍存在 | 已登记 | 会被 V4 主路径取代，但 V3 UI 仍在用；删除属 V4-10 |
| 质量归属依赖 `QualityReport.node_revisions` | 新增字段 | 旧报告（V4-05/V4-06 期间生成、无该字段）视为"未记录" → 交付按 `unevaluated` 处理（保守，不误判为通过） |
| EPUB / screenplay / PDF | 明确不做（§33/§35） | 属插件方向（V4-09）或后续版本 |
| 浏览器下载门禁未执行 | 环境限制（§86） | 本环境无 Playwright / node_modules；V4-10 必须补 |
| `partial_allowed` 可能被滥用 | policy 显式 | 默认关闭；开启时 manifest 记录 `exporter_failures` 并返回 status=partial |
| artifact 大小 / 大量节点时的内存占用 | 已知 | 当前全部在内存构建（Blueprint 规模为百级节点）；超大项目需要流式写入（记入后续优化） |
| DeliveryStore 无并发锁 | 已知 | 单进程假设（与 V4 其余写路径一致）；并发交付同一 selection 会相互覆盖同名 staging/package |

---

## 38. V4-08 readiness

```text
[x] delivery 是独立模块；Application ExportService 是唯一 facade；exporter 不承载业务选择
[x] delivery 只读；不修改 Blueprint / Canon / StoryState；无反向依赖
[x] accepted / explicit / current 三种 selection；rejected 与 proposed 不会误发布
[x] DeliverySnapshot 钉 revision；并发不改变 snapshot；不产生 Blueprint revision
[x] quality 与 accepted 要求独立；Quality Store 是正式来源；stale / unevaluated / rejected 可检
[x] preflight + post-build 校验；复用 Q9；稳定 delivery issue code
[x] BlueprintCompiler 唯一顺序；visible / internal 分离
[x] JSON / Markdown / DOCX / nfpack；exporter 版本化；registry 可扩展（插件留给 V4-09）
[x] manifest + checksums + artifact ownership + selected revision map + quality summary + provenance policy
[x] no secrets / no other novel / package ≠ repository backup
[x] path traversal 防护 / 原子发布 / 失败不留伪成功 / 幂等
[x] JSON · Markdown 可复现；0 LLM 调用
[x] legacy 导出路径盘点 + 移除条件登记
[x] 1463 passed / 7 skipped / 0 failed；validate_project PASS；frozen guards PASS
```

V4-08（MCP）可以直接消费：

```text
DeliveryService.describe / validate / snapshot / deliver（机器可读结果 + manifest + checksums）
DeliverySelection / DeliveryPolicy（MCP tool 参数的自然映射）
DeliveryStore.get_snapshot / get_manifest / read_artifact（resource 读取）
machine / audit profile（稳定、版本化的 structured export）
```
（V4-07 不实现 MCP / 插件加载。）

---

# V4-07 = PASS
