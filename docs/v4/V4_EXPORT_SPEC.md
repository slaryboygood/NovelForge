# NovelForge V4 — Export Spec（设计稿）

> 状态：**V4-00 Architecture / Proposed**，已按 **V4-01 作者决策**对齐（2026-09-17）
> 依据：`docs/v4/V4_ARCHITECTURE.md` §1.6（ownership）、§6（Export 归属）、§5（Export 边界）
> 硬约束：**所有导出必须经过 `ExportService`。UI / API / MCP 不允许各自拼装导出内容。**

### 0.1 V4-01 对齐

```text
核心交付物 = Story Blueprint Package（Markdown / JSON / DOCX / structured package / ZIP）
EPUB 降级：正文型交付不再是 V4 核心优先级（可后续由插件提供）
prose 分区：不再是 V4 导出必选分区（novel/final 已删除；writer draft 仅 preview）
```

| 位置 | V4-00 原文 | V4-01 修正 |
| --- | --- | --- |
| §3 格式表 `EPUB` | 读者交付（V4 新增） | 降级为插件方向（正文非核心） |
| §5 nfpack `chapters/ch001.md` | 来自 writer revision | 改为 `blueprint/{premise,story_arc,acts,chapters,scenes,...}.json` 为主，正文可选 |
| §6 O3 | 「`novel/final` 默认不可导出，需先导入」 | 文件已删除；规则改为「无归属数据一律不可导出」 |

---

## 1. 现状：导出能力分散在四处

| 位置 | 产物 | 问题 |
| --- | --- | --- |
| `story_builder/export_package.py` | `planning_export_<novel>_<branch>.{json,md,docx}` | 8 个 section，其中 3 个来源路径硬编码 `wasteland_001`（`RECON_DIR` / `PLANNING_INDEX` / `canon/wasteland_001.sqlite`） |
| `story_builder/outlines.py` | 大纲包导出（md / json / docx） | 与上面并存，第四种拼装 |
| `story_engine/outline_revision.py` | `docx_bytes()` | 被 `export_package` 复用，但没有统一出口 |
| `story_builder/writer_integration.py` | `writer_export_bundle` | writer-ready 联合入口（第三套「导出」概念） |

已知缺陷（`docs/V3_FINAL_FREEZE.md`）：

```text
NR-002  导出包固定包含与当前作品无关的 V2 分区（StorySpine / StoryPlanningIR /
        Canon 事实 / 570 章 historical IR）        ← 根因 = ownership 缺失
NR-003  Markdown 角色行带机器枚举（player / npc），分区标题中英混排
NR-004  导出面板正文显示 export_id
```

V4 的导出目标不是「修这四个 bug」，而是**让这四个 bug 在结构上不可能出现**。

---

## 2. ExportService

```python
class ExportService:
    def describe(self, novel_id: str, *, branch_id: str = "main") -> ExportPlan:
        """只读：告诉调用方会导出什么（分区 / 来源 / 缺失项）。"""

    def export(self, novel_id: str, *, fmt: str, options: ExportOptions) -> ExportArtifact:
        """唯一出口：projection → validate → serialize → 落盘 → 返回 artifact。"""

    def validate(self, novel_id: str, *, fmt: str) -> DeliveryReport:
        """交付校验（见 §4），不产生文件。"""
```

### 2.1 只从 repository 读

```text
profile         → persistence.profile
content pack    → persistence.content_pack
StoryState      → persistence.story_state
outline         → persistence.outline
chapter IR      → persistence.planning_repo / chapter_ir_store
canon           → persistence.canon_repo（按 novel_id 打开）
writer revision → persistence.writer_store（按 novel_id）
author prefs    → persistence（按 novel_id）

禁止：
  · 模块级路径常量（RECON_DIR / PLANNING_INDEX / canon sqlite 字面量）
  · 跨 novel 读取（包括「历史证据」）
  · 任何写操作（导出只读）
```

### 2.2 ExportPlan（新增：导出前就能看到会导出什么）

```json
{
  "novel_id": "…",
  "branch_id": "main",
  "revision": 12,
  "sections": [
    { "section_id": "story_bible", "truth_layer": "planned", "source": "profile+pack",
      "item_count": 12, "included": true },
    { "section_id": "chapters",    "truth_layer": "planned", "source": "outline",
      "item_count": 30, "included": true },
    { "section_id": "prose",       "truth_layer": "occurred", "source": "writer_revisions",
      "item_count": 0,  "included": false, "reason": "NO_REVISION_IMPORTED" }
  ],
  "excluded": [
    { "section_id": "legacy_historical_ir", "reason": "NOT_OWNED_BY_NOVEL" }
  ]
}
```

规则：**归属不明的内容必须出现在 `excluded`，而不是静默混入。**
这就是 NR-002 的结构性修复。

---

## 3. 输出格式

| 格式 | 用途 | 内容范围 | 是否包含内部 metadata |
| --- | --- | --- | --- |
| **Markdown** | 作者 / 编辑阅读、交付给写作环节 | 作品正文 + 大纲 + 卡片（作者语言） | ❌ 不包含（不得出现 `export_id` / `truth_layer` / `player` 等机器字段） |
| **JSON** | 机器消费、Agent 输入 | 完整 projection（含 provenance） | ✅ 包含（内部字段只在这里） |
| **DOCX** | 交付、打印 | 同 Markdown | ❌ 不包含 |
| **EPUB** | 读者交付（V4 新增） | 仅正文（按卷 / 章） | ❌ 不包含 |
| **Structured Package（nfpack）** | 迁移 / 交换 / 归档 | 全部结构化对象 + provenance | ✅ 包含（分离在 `manifest.json` 与 `provenance/`） |

### 3.1 内部 metadata 与用户可见正文不是一回事

```text
内部 metadata（id / digest / truth_layer / revision / source_ids / model usage）
  → 只允许出现在：JSON、nfpack 的 manifest / provenance、日志、调试视图

最终用户可见正文（作者 + 读者）
  → 只允许出现：标题、正文、结构化故事元素（角色 / 地点 / 大纲条目）
  → 禁止：export_id、机器枚举 (player)/(npc)、sqlite 路径、内部组件名、
          truth_layer 英文名、设计态字段标签（阶段目标 / 长期方向）
```

> 现状证据：`export_package.serialize_export()` 的 markdown 分支写出
> `f"- export_id：{manifest.get('export_id')}"`，角色行写出 `（{item.get('kind')}）`
> —— 直接对应 NR-003 / NR-004。

---

## 4. DeliveryValidator

导出前必须逐项检查；任一 `blocker` 阻止导出。

| 检查 | 级别 | 依据 | V3 现状 |
| --- | --- | --- | --- |
| 未处理 blocker（Quality blocker / 未解决冲突） | blocker | `QualityResult.status` | 部分（导出就绪度 6 步） |
| 内部 id / 机器枚举泄漏 | blocker | 文本扫描（`_id` 模式 / `player` / `npc` / `export_id`） | ❌ 无 |
| placeholder 名称（未命名作品 / 占位角色名） | major | 名称表 | 部分（NF-016） |
| 章节缺失 / 编号断裂 | blocker | outline 与 revisions 对照 | ❌ 无 |
| StoryState 与大纲一致性 | major | 来源一致性 | 部分（stale 检测） |
| 大面积标题语义重复 | major | Q6（语义重复） | 部分（字面唯一性） |
| 混入其他 novel 数据 | **blocker** | artifact ownership 校验 | ❌ 无（NR-002 未修） |
| 文档标题统一（中英混排） | minor | 文案规范 | ❌ 无（NR-003） |
| 调试字段（debug / 内部组件名） | minor | 文本扫描 | ❌ 无 |
| source trace 完整性 | major | 每个 section 有 source + revision | ✅ 已有（`section.source` / `identity` / `digest`） |
| 设计态字段标签进入正文 | major | Q6 + 字段标签黑名单 | 部分（`FIELD_LABEL_BLACKLIST`） |

```python
class DeliveryReport:
    report_id: str
    novel_id: str
    revision: int
    fmt: str
    status: str                     # passed | passed_with_issues | failed
    checks: list[DeliveryCheck]     # {check_id, level, passed, evidence, hint}
    issues: list[QualityIssue]      # 与 Quality Contract 同一对象（Q9）
```

**DeliveryReport 是 Q9 的实现**，不是第二套质量体系
（见 `V4_QUALITY_CONTRACT.md` §3 的 Gate → 实现映射）。

---

## 5. NovelForge Package（nfpack）

```text
<title>.nfpack/
├── manifest.json          # novel_id / project_id / revision / created_at / format_version
│                          # source_ids / tool_version / plugin_versions
├── novel.json             # 作品元数据（title / genre / tone / themes）
├── canon/
│   ├── facts.json
│   ├── entities.json
│   └── lineage.json
├── story_state/
│   ├── latest.json        # 当前事实（含 branch）
│   └── history/           # 可选：按 revision
├── outline/
│   ├── book.json / volumes.json / arcs.json / chapters.json
├── chapters/
│   ├── ch001.md           # 正文（来自 writer revision，不是 preview draft）
│   └── …
├── memory/
│   └── summary.json       # 只导出摘要（memory 是派生层）
├── quality/
│   ├── report.json
│   └── unresolved_issues.json
├── provenance/
│   ├── source_map.json    # 每个 section → source refs + revision
│   └── model_usage.json   # tokens / cost / model（不含完整 prompt）
└── README.md              # 人类可读说明（不含内部字段）
```

规则：

```text
1. nfpack 是可迁移 / 可归档交付物，不是运行时存储
2. 必须包含 revision 与 source_ids；无 revision 的数据不允许进入 nfpack
3. memory 默认只导出 summary（可重建，避免把派生结果当事实传播）
4. legacy 历史证据（wasteland_001 系列）只在显式 legacy 导出时包含
5. nfpack 导入属于 V5+ 议题（V4 只导出）
```

---

## 6. Ownership 规则（导出层）

```text
export(novel_id) → 只能获取属于该 novel 的数据
```

| 规则 | 说明 | 现状违反点 |
| --- | --- | --- |
| O1 | 每个 section 的 `identity` 必须等于请求的 novel_id 或该作品的 branch | `export_package` 的 spine / planning / canon 分区与请求作品无关 |
| O2 | 打开任何存储（含 Canon SQLite）必须按 novel_id | 4 处硬编码 `wasteland_001.sqlite` |
| O3 | 无 owner 数据（`novel/final/**`）默认不可导出；需先导入为 revision | 无 ownership |
| O4 | 跨作品数据（frozen 证据）只能在显式 legacy 导出中出现，并带 `legacy: true` | NR-002 |
| O5 | 导出物必须带 `revision`；无 revision 的 section 不允许 `included: true` | 部分（writer draft 无 revision） |

---

## 7. 迁移路径（V4-07）

| 步骤 | 动作 | 验收 |
| --- | --- | --- |
| 1 | 建立 `persistence/paths.py`，收敛全部路径常量 | 源码中不存在 `wasteland_001` 字面量（legacy 命名空间除外） |
| 2 | 建立 `ExportService.describe()` 与 `ExportPlan` | `excluded` 能正确列出跨作品数据 |
| 3 | 合并四条导出路径到唯一出口 | UI / API 只调用 `ExportService` |
| 4 | Markdown / DOCX 移除内部字段 | 文本扫描测试：无 `export_id` / `player` / `npc` / `sqlite` |
| 5 | 实现 DeliveryValidator（Q9） | 未通过 Q9 无法导出（测试） |
| 6 | 实现 nfpack 导出 | 结构断言 + revision / source_ids 断言 |
| 7 | 导出物纳入 acceptance | 真实浏览器导出 → 打开产物 → 人工可读性检查 |

---

## 8. 验收判据（V4-07）

```text
[ ] 只有 ExportService 能产生导出物（源码守卫：其他模块不 import docx 序列化器）
[ ] export(novel_id) 不包含任何其他 novel 的数据（含 canon / spine / planning）
[ ] Markdown / DOCX / EPUB 无内部字段（文本扫描测试）
[ ] 每个 section 带 source + revision + digest
[ ] DeliveryReport 与 QualityResult 使用同一 issue 契约（Q9）
[ ] 无 revision 的内容不进入 nfpack
[ ] 导出失败时无半成品文件残留（原子写）
[ ] MCP export tool 与 UI 导出产生同一 artifact digest（同一输入）
```
