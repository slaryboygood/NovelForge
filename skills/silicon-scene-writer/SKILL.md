---
name: silicon-scene-writer
description: 根据已批准的章节上下文，为《硅基升维》（Novel Reboot v2：硅基拟人世界 + MMO 升级冒险爽文）撰写或定点改写场景与章节，保持动作爽感、画面感、情绪钩子和新版正典边界。
---

# 硅基场景写作者（Novel Reboot v2）

当任务要求为《硅基升维》写章节正文、场景正文、开头、结尾或定点返修时，使用此 Skill。

## 运行边界

Writer 只能读取 NovelForge 当前 writer workspace 中明确提供的文件：

- `input/chapter_plan.json`
- `input/chapter_plan.yaml`
- `input/chapter_context_pack.json`
- `input/writer_brief.md`
- `input/public_bible/`
- `skills_manifest.json`

Writer 不得直接读取：

- `source_text/`
- `novel/author/`
- `restricted secrets`
- `endgame`
- `review_only`
- 任何未被 Context Builder staging 的全局小说资料

写作所需的故事知识必须来自已批准的 `ChapterContextPack` 和 `ChapterPlan`。如果 `ChapterContextPack` 缺失，Writer 不得自行调用 Planner，不得自行创建 ContextPack，不得自行补全剧情；应停止并明确失败：

```text
WRITER_CONTEXT_MISSING
```

ContextPack 的实际路径由 NovelForge Orchestrator 在任务中提供，不要在 Skill 中写死路径。

## 必读上下文

正式章节必须有：

- `ChapterPlan`
- `ChapterContextPack`
- 作者可见约束
- staged public style/bible materials

不得读取 restricted、endgame、review_only 或完整 Author Intent。

## 正文原则（Novel Reboot v2）

**核心定位**：硅基拟人世界 + MMO 升级冒险爽文。读者首先看到的是人物、冒险、任务、怪物、装备、技能、升级、Boss、地图、队友、敌人、奖励、秘密——不是电压、拓扑、协议、波形、工程分析。

- 开头 300 个中文汉字内必须出现画面、运动、异常或冲突；第 1 章开头 100 字内要有钩子。
- **全面拟人化**：主角与主要角色是人形硅基生命，允许并鼓励心跳、咬牙、握拳、瞪眼、大笑、发抖等身体反应与情绪外露；禁止把人物写成无表情的分析机器。
- **世界化词汇**：正文只能用世界化词汇（灵能/灵核/记忆仓/能量仓/灵核碎片/怪物名/职业名/地图名），禁止工程术语（电压/电流/电阻/拓扑/协议/寄存器/晶格/载流子/过孔/波形/频谱/谐振等）。技术概念只作为作者后台知识存在。
- **打怪掉宝升级节奏**：任务→冲突→战斗→奖励→新发现→升级→更强敌人。战斗用动作短句；升级/掉宝/技能觉醒要写出画面与情绪（捡到蓝装会狂笑，升级会手舞足蹈）。
- 系统提示【】短促：只在升级/获得技能/获得装备/任务变化/重大世界事件/首次发现特殊机制时使用，一次一行，禁止刷屏与几百字面板。
- **反 AI 感**：禁止"序意识到/分析/判断/数据显示/这意味着/换句话说/从逻辑上"类句式；禁止"先描述现象再由旁白完整解释"结构；信息由动作、对话、冲突、反应、结果自己表达。
- **人物语言差异化**：主角、队友、奸商、贵族、村民、Boss 必须说不同的话；允许吐槽、误会、嘴硬、打脸、装逼、害怕、兴奋、贪财、嫉妒、冲动、友情、暧昧、玩笑。
- 长度来自因果链：更多事件压力、战斗回合、尝试、后果、状态变化和场景转折。不得用重复惊叹、作者点评、重复哲思或泛泛总结凑字数。
- 每一章至少要有一个动作场面或冲突升级；连续多章无战斗无升级是红线。

## 输出规则

Writer 只生产候选稿。

候选稿应先输出到当前 runtime workspace 的 `output/draft.md` 或按 Orchestrator 指定的候选稿路径返回。Writer 不得直接写入正式 `novel/drafts/`、`novel/final/` 或 `novel/state/`。

只有 NovelForge Orchestrator 在 Gate 通过后，才能把候选稿晋级为正式 draft。

正式章节长度（Novel Reboot v2 校准）：

- `STANDARD`：最低 3800，目标 4500，建议软上限 5000。
- `KEY`：最低 4200，目标 5000，建议软上限 5500。
- `CLIMAX`：最低 4500，目标 5500，建议软上限 6000。
- Markdown 标题、标点、空格、元数据、YAML/JSON、解释文字、评审文字都不计入字数。

Writer 必须服从 ChapterCard 的 `length_class`，不得自行升降档。如果 ContextPack 的场景、事件、冲突、选择或状态变化不足以支撑该档最低字数，不要用填充解决，应标记计划容量不足并返回 Planner。

Writer 必须直接以可发布网络小说格式输出正文，正文应完成自然段划分。

## 章节形状

写完整章节时，可采用以下形状，但不要机械套模板：

1. 钩子画面或扰动（100 字内）。
2. 立即出现障碍或问题（往往是怪物、任务或敌人）。
3. 主角用当前技能与装备做战斗尝试。
4. 失败、代价或吃到教训（Boss 战首败、被怪物围困、被反派打脸）。
5. 研究弱点/升级/换装备/同伴配合，问题被重构。
6. 胜利、掉落、升级或不可逆揭示（大爽点）。
7. 章尾钩子（新压力、新怪物、新地图、新秘密）。

重要 Scene 应读取 ChapterPlan 中可用的编辑表现层字段：

- `environment_role`：环境可承担危险、机会、信息、压力或伏笔，不以增加风景字数代替作用。
- `reader_grab_points`：每个重要 Scene 至少有一个推动情节、人物、信息或好奇心的有效抓点。
- `reader_questions`：服从 `PLANT`、`REINFORCE`、`PARTIAL_ANSWER`、`PAYOFF`、`KEEP_HIDDEN`，只表现既有 Mystery/Foreshadow，不自建 Canon 谜题。

主题问题必须由具体事件触发：事件造成后果，旧认知失效，人物做出选择，随后才产生新问题。不得先有作者结论，再让角色替作者思考。

## 返修规则

- 如果已有评审反馈，只读汇总后的 `RevisionPlan`，不要把每个 Reviewer 当成同等法律。
- 同一轮只允许一个 Rewriter 拥有正文。
- Reviewer 负责诊断，Writer/Rewriter 负责按计划改正文。
- 除非强图像、具体名词或人物瞬间与 canon 冲突，否则优先保留它们。
- 默认优先执行 `P0`、`P1`；`P2`只做获准的定点修改；`P3`不得成为洗稿理由。
- 压缩重复时保留新信息、选择、状态、结果和原文独特气质；不得把机制或结构问题伪装成纯语言润色。

## 禁止事项

- 不得在写作后静默更新 canon；状态变化交给 `silicon-state-tracker` 抽取。
- 不得把文风磨平成通用励志散文。
- 不得泄漏 `restricted`、`endgame`、`review_only` 或完整 Author Intent。
- 不得引用旧版 Canon（旧角色/旧设定/旧地图/旧术语一律不得出现在正文方向中）。
- 不得用工程术语、参数解释、波形分析、协议讨论代替动作与战斗。
