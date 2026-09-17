# ADR-011 — Story Blueprint Is The Primary Creative Artifact

```
Status    : Accepted（作者决策，V4-01）
Date      : 2026-09-17
Context   : V4-01 Boundary Foundation & Legacy Cleanup
Supersedes: ADR-003（Canonical Writer Store）
Related   : V4_ARCHITECTURE.md §6；ADR-006（Revision）；ADR-010（Structured Generation）；
            V4_DELETION_PLAN.md §2.1；NOVELFORGE_V4_MASTER_PLAN.md §1–4、§25、§31、§45
```

## Context

V4-00 的架构隐含一个假设：V4 最终会走向「可编辑正文 + revision 历史」，
因此把 canonical prose writer store 列为 V4-06 核心目标，
并把无 owner 的 `novel/final/*.md` 当成待裁定的「正文资产」。

作者在 V4-01 明确否定了这个方向：

```text
V4 的最终目标不是自动写完一部长篇小说正文。
V4 的核心产品 = 高质量、可编辑、可验证、可持续修订的 Story Blueprint
                （小说大纲 / 影视式故事蓝图）
```

正文生成若未来需要，应作为 **Plugin / 下游 Agent / 外部写作工具**，
而不是重新侵入 V4 Core（Master Plan §45 第四条边界）。

## Decision

1. **canonical creative artifact = `StoryBlueprint`**，不是正文 draft。

   ```text
   Premise / Theme / World / Characters / Character Arcs /
   Story Arc / Act·Volume·Arc / Chapter Cards / Scene Cards /
   Causal Graph / Setup·Payoff / Timeline / Story State Transitions /
   Knowledge State / Relationship Changes / Quality Result / Revision History
   ```

2. **Writer → Blueprint Editor / Story Studio**：围绕结构节点（含 Scene Card）的编辑器，
   不是长篇正文编辑器。
3. **Draft 不再是核心 artifact**：`WriterPackage` / `render_scene` / `fallback_text`
   仅作为既有能力的兼容保留，不再作为 V4 完成目标。
4. **`novel/final/**` 直接删除**：不迁移、不归档、不导入为 revision（作者确认无产品价值）。
5. **570 章 historical 直接删除**：不导入、不做 fixture、不进 `legacy/`。
6. **Revision 语义保留、对象改变**：ADR-006 的 revision primitive 继续有效，
   但它服务 Blueprint 节点、StoryState、Quality/Repair、Agent mutation，而不是「正文版本历史」。
7. **Export 目标改变**：核心交付物是 Story Blueprint Package（Markdown / JSON / DOCX /
   structured package）；EPUB 等正文型交付降级为插件方向。

## Consequences

正面：

* V4-06 范围从「正文编辑器 + 大段文本 diff」收敛为「结构编辑器 + 节点 diff」。
* Quality 门（Q0–Q9）聚焦结构 / 因果 / 人物弧 / setup·payoff，而不是文学文风。
* 两个历史资产类被删除，仓库与运行时不再为「另一部作品」保留路径。

代价 / 风险：

* `story_builder/writer_integration.py`（writer context + draft + fact sync）与
  `story_engine/writer.py` 的定位需重新表述为「Blueprint 上下文装配 + 预览」；
  V4-01 只做边界标注，不做重写。
* V3 已发布文档中描述 Writer 的部分仍然存在；**V3 历史记录不改写**，
  但描述「当前兼容路径」的部分随删除同步更新。
* 若用户把 NovelForge 当正文生成器使用，V4 中将找不到对应能力 —— 这是**有意的产品定位**，
  需在 README / UI 文案中表达（V4-10）。

## Alternatives considered

| 方案 | 为什么不选 |
| --- | --- |
| 继续以正文为 canonical artifact | 与产品定位冲突；正文生成的上下文与质量成本远超 V4 Core 能力 |
| 双 canonical（正文 + Blueprint） | 两个 canonical artifact 会让 ownership / quality / export / revision 全部分叉 |
| 保留 `novel/final` 作为只读参考 | 作者判定无价值；保留会持续产生「这是不是作品事实」的歧义与串稿风险 |

## Evidence

```text
docs/NOVELFORGE_V4_MASTER_PLAN.md §1–4、§25、§31、§45
作者 V4-01 决策 A / B / C（V4_MIGRATION_PLAN.md §6；V4_DELETION_PLAN.md §2.1）
src/novelforge/story_builder/writer_integration.py   现状：只有 create/list/get/sync-facts，无 update
src/novelforge/story_engine/writer.py               现状：fallback_text / render_scene（确定性降级文本）
git ls-files novel/final                             69 个 tracked 正文文件（V4-01 删除）
workspace/wasteland_001_exports                      1918 文件 / 62 MB（V4-01 删除）
```

