# NovelForge — 数据模型

> 本文件是数据模型 SSOT。每类对象都标注：**authoritative / derived**、
> **mutable / frozen**、以及它属于哪一层 truth。架构分层见 `docs/ARCHITECTURE.md`。
>
> **2026-09 更新**：V4 的数据模型权威文档是各 `docs/v4/V4_*_CONTRACT.md`
> 与 `docs/v4/V4_ARCHITECTURE.md`；current truth layers =
> `Canon`（已发生事实）/ `StoryState`（runtime truth）/`Story Blueprint`（提案层）/
> `Quality Store`（质量真相）/`Delivery Store`（交付快照）/`Memory`（派生、可重建）。
> 本文里 V3 工作台投影（v3_projection）、引导流 session、旧大纲 / writer 草稿等条目
> 已随 backend retirement 失效，保留为历史记录。

## 权威层级（truth layers）

```text
occurred            Canon + StoryState：唯一的「已发生事实」权威
planned             NovelProfile / Template / ContentPack / 路线 / 大纲 / planning：规划，未提交为事实
historical_repair   570 章 Historical Chapter IR + M11/M12 修复 lineage：历史修复证据，只读
preview             Writer 草稿 / 事实提议（PROPOSED）：不写事实
ui_derived          UI 派生视图 / 导出派生：不成为 truth source
application_derived Objective / Next Action / Command Center 状态：应用层派生，不是 story truth
```

长期不变式：`planning != occurred truth`、`historical repair != Canon source`、
`preview/export != committed truth`、`config != possession`。

## 设计态对象（planned / mutable）

| 对象 | 位置 | 说明 |
| --- | --- | --- |
| 十步目录与设计节点 | `novel/config/story_builder/step_catalogs.yaml` | 32 个可选节点、前置（硬）与推荐（软）分离；配置不是事实 |
| NovelProfile | `novel/authoring/story_engine/profiles/<novel_id>.json` | 小说档案：genre / content_pack_id / story_rules / cast / factions / future_plan / world_profile |
| Genre Template | `novel/config/story_engine/*.json`（templates / genre_packs / cases） | 题材模板与内容包数据；引擎不内建题材分支 |
| ContentPack | `novel/authoring/story_engine/packs/<novel_id>.json`（`novel/config/story_engine/genre_packs.json` 为模板） | 起点世界事实（locations / factions / characters / relationships / plots）+ actions / events / progressions / foreshadows |
| 设定候选与选择 | `settings/seed` 响应 + NovelProfile.world_profile.settings | 作者选择 / 改写；保存后生成内容包骨架 |
| Session / Blueprint | `novel/authoring/story_builder/sessions|blueprints/` | 十步选择、版本、设计快照、确认状态 |
| Outline（四级） | `novel/authoring/story_builder/outlines/` | BOOK → VOLUME → ARC → CHAPTER；`route_source` 记录来源分支与摘要，`pending_questions` 记未决项 |
| Planning（StoryPlanningIR） | `novel/authoring/story_engine/planning/<novel_id>/` | 规划 revision（不可变）+ index；规划不是已发生事实 |
| Writing Moodboard（W6-12） | 浏览器 localStorage（`novelforge.moodboard.<novel_id>`） | 纯设计态参考位，不进入任何服务端事实 |

## 运行态对象（occurred / mutable）

| 对象 | 位置 | 说明 |
| --- | --- | --- |
| StoryState | `novel/authoring/story_engine/state/<runtime_id>/vXXXXXX[_branch].json` | 新旅程唯一事实来源：world / timeline / location / characters / relationships / knowledge / resources / abilities / factions / flags / identities / promises / events / active+resolved plots / effect_log / delayed_effects |
| 分支事实 | 同一目录下的 `branch_<32hex>` 文件 | 路线实验室 fork 出的独立事实；源分支与主线不被修改 |
| 事实变更历史 | StoryState.effect_log | 每次推进的 op / target / source / tick（可追溯数值来源） |

写路径：`ActionResolver` 事务化应用 Action + Effect，失败回滚；客户端不能自证合法性。
读取路径：`creator_context` → `*_view.py` 投影（世界 / 角色 / 剧情 / 成长 / 记忆 / 导演 / 联动）。

## 历史与冻结对象（V4-01 起已删除）

> ⚠️ **V4-01 Boundary Foundation（作者决策 A / B）**：以下历史资产被判定为废弃并**直接删除**
> （不迁移、不归档、不做 fixture、不进 `legacy/`）：
>
> ```text
> novel/final/**（69 个 tracked 正文文件）
> workspace/wasteland_001_exports/**（570 章 historical IR / M11 证据 / 旧导出，1918 文件 / 62 MB）
> ```
>
> 表内条目仅作为 V3 历史记录保留（描述"曾经存在什么"），
> **不再是当前数据模型的一部分**。当前 ownership 见 `src/novelforge/persistence/paths.py`
> 与 `docs/v4/V4_MODULE_BOUNDARIES.md` §3.3。

### V3 历史记录（已删除）

| 对象 | 位置 | 说明 |
| --- | --- | --- |
| Canon | `novel/authoring/story_engine/canon/wasteland_001.sqlite` | 权威事实表（fact / entity / event）；只读引用 |
| ~~570 章 source Chapter IR~~ | ~~`workspace/wasteland_001_exports/chapter_ir_v1/`~~ | **V4-01 已删除** |
| ~~Historical IR（`ChapterSemanticIR` body）~~ | ~~`workspace/wasteland_001_exports/historical_chapter_ir_v1/`~~ | **V4-01 已删除** |
| ~~Repair overlay / reconciliation / ledger~~ | ~~`workspace/wasteland_001_exports/repair_adoption_v1/M11_*.json`~~ | **V4-01 已删除** |
| Run / batch reconciliation | 同上（`M11_RUN_*_RECONCILIATION.json`、`m11_run_*/`） | 每个 production run 的本地证据 |
| Milestone acceptance | 同上（`m12/`…`m18/`、`phase_snapshots/<phase_id>/`） | baseline / freeze guard / acceptance / readiness + write-once phase snapshot（含 digest manifest）；`m18/NOVELFORGE_PRODUCT_V2_RELEASE.json` 为 deterministic release manifest（无时间戳） |
| Contract / Gate | `M11_REPAIR_SYSTEM_CONTRACT_V1.json`、`REPAIR_GATE_V1.json` | frozen 修复契约与 gate digest |

## 派生对象（derived / preview / ui_derived）

| 对象 | 生成者 | 说明 |
| --- | --- | --- |
| ExportProjection（Story Bible / 卡片 / Timeline / 大纲 / planning / canon_refs） | `story_builder/export_package.py`（入口 `application.services.export.ExportService`） | 只读导出投影；每个 section 带 truth_layer / source / identity / digest；serializer 输出 json / markdown / docx。V4-01 起不再包含 spine / historical_ir 分区 |
| WriterContext | `story_builder/writer_integration.py` | 6 层 block（canon_truth / story_state / historical_repair / planning / chapter_plan / writer_guidance），每块带 source / identity / digest；跨块去重 + 预算 |
| WriterDraft（canonical） | `novel/authoring/story_engine/writer/<novel_id>/`（`index.json` + `drafts/*.json`） | writer 输出（preview 层）：narration + 声明 + 既有校验结果。写入与读取（V3 投影 / 导出）共用同一个常量 `writer_integration.WRITER_DIR` |
| ~~WriterDraft（历史路径，只读兼容）~~ | ~~`workspace/wasteland_001_exports/writer_v1/<novel>/drafts/`~~ | **V4-01 已删除**；草稿只从 canonical 目录读取，不再有任何历史回退 |
| 已归档作品 | `workspace/archived_novels/<novel_id>_<UTC>/`（含 `ARCHIVE_MANIFEST.json`） | 删除作品＝整体归档：profile / 内容包 / StoryState / 大纲 / 写作草稿一起移动，可恢复、不留孤儿（gitignored） |
| FactProposal | 同目录 `proposals/` | `sync-facts` 产生的 `PROPOSED` 事实提议（需作者或修复流程确认） |
| Inspector 记录 | `story_builder/inspector.py` 运行时投影 | 跨层只读检查结果 + provenance（source refs / repair replay / reconciliation） |
| UI 投影 | `story_builder/ui_flow.py` + `ui/src/*` | 引导流状态、影响范围、总览 / 区域 / 关系视图；不写事实 |
| V3 工作台投影 | `story_builder/v3_projection.py` → `ui/src/v3/` | Command Center / 作者旅程 / Objective / Next Action / 实体与关系 / 推演（候选·影响）/ 大纲与章节 / 检查与修复 / 导出就绪度；全部只读，完成状态由 deterministic rules 派生 |

## 目录速查

```text
novel/config/                     模板 / 内容包 / 十步目录（数据）
novel/authoring/story_engine/     Canon / StoryState / profiles / packs / planning
novel/authoring/story_builder/    sessions / blueprints / outlines
workspace/                       运行期产物（V4-01 起不再包含 wasteland 历史导出）
ui/src/                           前端（React + TS）
```

写入采用原子替换 + 单进程锁；单进程部署，不承诺跨进程事务。
