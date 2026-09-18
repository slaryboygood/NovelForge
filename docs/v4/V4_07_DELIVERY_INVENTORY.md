# V4-07 — Delivery / Export Inventory

> 阶段：**V4-07 Delivery, Export & NovelForge Package**
> 目的：在写任何新 exporter 之前，把现有导出路径盘清楚（任务书 §3–§4、§58–§61）。
> 原则：**先盘点，再重建；能 ADAPT 的不重写；只服务旧正文的降级为 compatibility。**

---

## 1. 现有导出路径总表

| Existing Path | Artifact | Source | Format | Ownership | Problems | V4 Action | Target |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `story_builder/export_package.py::build_export_projection` | planning export projection（8 个 section） | profile / content pack / StoryState / outline / planning / canon（按 novel_id） | dict | ✅ V4-01 已参数化（历史分区已删） | 面向 V3 规划对象，不是 Story Blueprint；section 与 Blueprint 不同构 | **COMPATIBILITY_ONLY**（V3 路由仍在用） | `application.services.export` 的 legacy 方法 |
| `story_builder/export_package.py::serialize_export` / `export_package` | `planning_export_<novel>_<branch>.{json,md,docx}` | 同上 | JSON / Markdown / DOCX | ✅ | 同上；Markdown 面向规划对象 | **COMPATIBILITY_ONLY** | 同上 |
| `story_builder/export_package.py::validate_export_package` | validation report（section identity / truth separation / stability） | projection | dict | ✅ | 校验对象是 V3 projection；与 DeliveryValidator 语义不同 | **ADAPT idea**（section identity + digest 思路） | `delivery/validation.py` |
| `story_builder/outlines.py::export_outline_bundle`（`export_outline`） | 大纲导出 md / json / docx | OutlinePackage（四级大纲） | Markdown / JSON / DOCX | ✅ | 第四种拼装路径；面向 outline 产品面 | **COMPATIBILITY_ONLY** | 未变（V4 主路径不依赖） |
| `story_engine/outline_revision.py::docx_bytes` | 最小 OOXML 文档（zip + document.xml） | paragraphs（调用方给） | DOCX bytes | ✅（纯函数） | 无第三方依赖，成熟可复用 | **ADAPT**（保留思路，Blueprint 版本独立实现于 `delivery/exporters/docx_exporter.py`，数据源改为 DeliverySnapshot） | `delivery/exporters/docx_exporter.py` |
| `story_engine/outline_revision.py::export_structured_json` / `export_docx` / `export_outline` | 大纲结构化导出 | outline chain | JSON / DOCX / Markdown | ✅ | 面向 outline | **COMPATIBILITY_ONLY** | 未变 |
| `story_builder/writer_integration.py::writer_export_bundle` | Writer-ready package（export manifest + 分层 writer context） | export projection + writer context | JSON | ✅ | 只服务旧正文 writer 流程（§58） | **COMPATIBILITY_ONLY** + 登记移除条件 | `ExportService.writer_bundle()`（legacy） |
| `story_builder/writer_integration.py::WriterDraftService`（drafts / proposals） | 正文 preview 草稿 | CreatorContext + claims | JSON（preview 层） | ✅ | 正文能力，非 Blueprint | **KEEP**（不属于 delivery） | — |
| `story_builder/inspector.py` 相关导出/诊断 | 诊断报告 | pack / outline | dict | ✅ | 诊断，不是交付物 | **KEEP** | — |
| `api/story_builder_routes.py` `/export/package` `/export/writer-bundle` `/outline/export` `/outlines/{id}/export` | HTTP 下载 | 上述各路径 | 混合 | ✅ | **四套 export assembly 并存**（§60 禁止继续作为 V4 主路径） | **KEEP as compatibility**；新增 `/delivery/**` 作为 V4 主路径 | `api/delivery_routes.py` |
| `ui/src/**` 导出按钮 | 调用上述 route | — | — | ✅ | UI 大改属 V4-10 | **KEEP**（保证兼容，不新增 UI） | V4-10 |
| `story_engine/repair.py`（M11）、historical IR | 历史修复产物 | Historical IR | — | frozen | 与交付无关 | **FROZEN** | — |

---

## 2. 重点回答（§4）

```text
目前有几套 export pipeline？
  4 套：export_package（planning）/ outlines（四级大纲）/ outline_revision（结构化大纲）/
        writer_export_bundle（writer-ready）。另有 inspect/repair 诊断产物不属于交付。

每套从哪里取数据？
  全部经 repository / persistence.paths（V4-01 起不再有 wasteland_001 硬编码）；
  但取的是 V3 规划对象（profile / pack / outline / planning / canon），
  而不是 V4-06 的 Story Blueprint revision。

哪些会自行拼文件？
  无（V4-01 已收敛到 persistence.paths）；但**导出装配点有 4 处**（route → 4 条实现路径）。

哪些直接扫描 workspace？
  无（`tests/v4/isolation/test_no_implicit_disk_discovery.py` 守卫）。

哪些导出旧正文？
  无（`novel/final/**` 已删除；writer draft 只作为 preview 草稿，不出现在导出里）。

哪些使用 Writer bundle？
  `/export/writer-bundle`（legacy 产品面）。

哪些导出 OutlinePackage？
  `outlines.py` 与 `outline_revision.py` 两条（V3 大纲产品面）。

哪些与 Blueprint 重复？
  全部：它们导出的是"V3 规划视图"，而 V4 的核心交付物是 Story Blueprint revision graph。
  V4-07 必须建立**唯一**的 Blueprint 交付链，而不是给旧路径再包一层。
```

---

## 3. 处置清单

```text
ADAPT（思路，不复制实现）
  · export_package 的 section identity + digest + manifest 思路 → DeliveryManifest / checksums
  · outline_revision.docx_bytes 的最小 OOXML 思路 → delivery/exporters/docx_exporter.py
    （数据源改为 DeliverySnapshot / BlueprintCompiler，不再读 outline）
  · V4-05 Q9（Delivery Readiness）的 issue → DeliveryValidator 的 preflight 输入（不重复实现）
  · V4-06 EditorStore 的 review / operation metadata → 交付审批与审计（只读）

KEEP（V3 产品面兼容，不进入 V4 主路径）
  · story_builder/export_package.py（planning export）+ `/export/package` 路由
  · story_builder/outlines.py / outline_revision.py（大纲导出）+ 对应路由
  · writer_export_bundle + `/export/writer-bundle`
  · UI 现有导出按钮（V4-10 再切换）

DELETE（登记，等 V4-10 UI 切换后再执行）
  · 上述四条 legacy 导出路径中，被 Delivery 完全取代的部分
  · 移除条件：V4-10 导出 UI 切到 `/delivery/**` + legacy 浏览器门禁退出
  · 登记位置：docs/v4/V4_DELETION_PLAN.md §3
```

---

## 4. 与既有模块的边界

```text
delivery      → blueprint（canonical revision graph，只读）
              → quality Public Contract（Quality Store：issue / report，只读）
              → editor metadata（EditorStore：review / operation，只读）
              → core（ids / digest）、persistence.paths
禁止          → delivery 调用 LLM / memory retrieval / repair / editor.patch / 修改任何 truth
禁止          → Application 之外直接调用 delivery（唯一 facade = application.services.export）
反向          → core / domain / ai / memory / blueprint / generation / quality / editor 不得依赖 delivery
```

---

## 5. 结论（为什么必须重建交付链）

```text
1. 现有 4 条导出路径没有一条基于 Story Blueprint revision graph；
   它们无法回答"这次导出用了哪些 revision / 是否 accepted / 质量是否针对这些 revision"。
2. V4-05 已经给出质量真相（Quality Store），V4-06 已经给出 review 决定（editor metadata），
   但这些信息目前完全不参与导出 → 交付物无法被证明。
3. 因此 V4-07 建立新的唯一交付链：

   DeliverySelection → Revision Resolution(accepted/quality/review) → DeliverySnapshot
   → preflight DeliveryValidator → BlueprintCompiler → Exporters
   → post-build validation → Manifest + checksums → NovelForge Package

   旧四条路径保持兼容，但**不得**成为新交付物的底层（§58–§61）。
```

