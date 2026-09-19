# NovelForge V4.0.1 — User Feature Guide（给人看的）

> 三层职责：**本文件 = 人看**；`skills/novelforge-v4.0.1/**` = Codex / Agent 执行；
> `docs/v4/V4_*_CONTRACT.md` = 技术 SSOT。
> 本文件不复制契约细节，只回答「我该在哪里做什么、会得到什么」。

## 0. 一分钟了解 V4.0.1

NovelForge V4 是**故事蓝图运行时 + 创作工作台**：把一部长篇故事的方案结构化（12 类节点、
append-only revision），用 Q0–Q9 门禁检查，做定向修复，由作者决定接受与否，最后打成
可复现、可追溯的交付物。

```text
规划（Blueprint proposal） ≠ 已发生事实（Canon / StoryState）
AI 产出永远是 proposal；accept / reject / restore 只属于作者
质量通过 ≠ 作者已接受；两者都是交付的前提条件（交付默认选择 accepted）
```

## 1. 作品生命周期（Project）

- 启动：`.venv\Scripts\python.exe scripts/start_novelforge_ui.py --rebuild-ui` → `http://127.0.0.1:8000/`
- 新建：Landing →「新建作品」，填 `novel_id`（≥3 字符，字母数字 / `-` / `_`）与标题、题材。
- 查看：Overview 显示节点计数、质量状态、交付状态与「下一步」建议。
- 重命名：只改作者可见名字，不动任何事实。
- 删除：等于**整体归档**（二次确认 `confirm=true`），可恢复，不留孤儿文件。

## 2. Story Studio（唯一产品面）

左侧导航：总览 / 创造 / 世界 / 人物 / 故事 / 场景 / 检查 + 交付 / 插件 / Agent。

```text
#/studio                     作品选择 / 新建
#/studio/n/<novelId>         总览
#/studio/n/<novelId>/<view>[/<id>]   工作区（可深链接，刷新不丢位置）
```

旧书签（`?ui=v3` / `#/v3…` / `?ui=v2` / `#/story-builder…`）不会 404，会一次性归一化回
Story Studio；V2/V3 界面已不在 current tree 里。

## 3. Story Blueprint

12 类节点：premise / theme / world / character / character_arc / story_arc /
structural_unit / chapter / scene / setup / payoff / causal_link。

- 每个节点是**有序节点图**的一部分，节点 id 由系统分配（模型不得自造）。
- 每次修改都产生**新 revision**；旧 revision 永不删除。
- 节点状态：`draft`（无证据草稿）/ `proposed`（AI 生成待作者决定）/ `accepted`（作者已接受）。
- `quality_status` 与 `status` 各自独立：质量通过不会自动接受。

## 4. Generation（逐级生成）

顺序：premise → theme → world → character → character_arc → story_arc →
structural_unit → chapter → scene（→ 由系统确定性建立 setup / payoff / causal_link）。

```text
「创造」= 前提 / 主题 / 核心冲突
「世界」= 规则 / 地点 / 势力 / 资源
「人物」= 人物卡 + 人物弧
「故事」= 故事弧 / 结构单元 / 章节卡
「场景」= 场景卡（正面回答「这场戏为什么存在」）
```

生成结果是 proposal：可以逐字段改、可以 AI 改写、可以重新生成，最后由你接受。
**默认不启用任何模型 provider**，因此开箱时生成会返回稳定错误码 `GENERATION_UNAVAILABLE`。

## 5. Memory / Context（派生记忆）

记忆是**派生且可重建**的：它不拥有真相，只按预算与 scope 组装「这次生成需要看什么」。
真相仍然是 Canon / StoryState / Blueprint。当前没有面向用户的记忆界面（MCP 也 DEFER）。

## 6. Quality（Q0–Q9 门禁）

```text
Q0 Schema / Q1 Integrity / Q2 Canon / Q3 Continuity / Q4 Character /
Q5 Causality / Q6 Semantic / Q7 Narrative / Q8 Blueprint Style / Q9 Delivery Readiness
```

- **没有权威总分**：每个 gate 各自给结论（passed / failed / blocked / unevaluated）。
- 每条 issue 带 severity（info / minor / major / blocker）、evidence、所属 revision、evaluator。
- 在「检查」里能看 gates、issue 列表与证据，点进节点能看到该节点的 issue。
- Blocker 会阻止交付资格（Q9 / DeliveryValidator 语义）。

## 7. Repair（定向修复）

```text
issue → plan（dry-run，0 mutation）→ 执行（新 revision + repair 记录）→ verify（复核）
```

修复是**最小范围 + preserve 硬约束**：只允许改 contract 声明的字段，其余字段必须逐字保持。
复核确认「问题真的解决了」才算 resolved；无法安全自动修复 → 需要作者决定（needs human review），
不会偷偷扩大范围。

## 8. Editor（作者掌控）

- 字段级修改（patch）：不知道的字段会被拒绝；`node_id` / `parent_id` / `status` 等身份字段受保护。
- AI 改写：只允许改你指定的 `target_fields`；改到别处会被拒绝且不写入。
- 接受 / 拒绝：接受会让该 revision 成为 accepted，并产生新的 accepted revision；拒绝只记录决定。
- 恢复：把历史 revision 的内容写成一个**新** revision（历史永不删除），并标注 `restored_from`。
- 冲突：如果 revision 变了，操作会以 revision conflict 失败，而不是覆盖别人的修改。

## 9. Delivery（revision-pinned 交付）

```text
选择（默认 accepted）→ preflight 校验 → 快照（钉住每个节点的 revision）
→ manifest + checksum → 原子发布 → 下载
```

- 格式：JSON / Markdown / DOCX / `.nfpack`（插件可追加 exporter 格式）。
- profile：reader / author / machine / audit（决定是否包含质量报告、provenance、revision history）。
- 交付物经过 secret scan；内部 metadata（node_id / status / provenance 等）不会出现在
  Markdown / DOCX 里。
- 未 accepted 或质量未通过时，默认会被 preflight 拦住（可用 policy 显式放宽，但会记录）。

## 10. Canon / StoryState（受保护真相）

Canon = 已确认事实（事实 / 事件 / 实体 / 知识 / 伏笔 / 依赖图），StoryState = 当前状态。
两者都是**只读真相**：V4 生成只把它们当作上下文约束，不写入。

```text
GET  /api/story-builder/canon/facts             已确认事实（planned / happened）
GET  /api/story-builder/canon/events            事件（planned / occurred）
GET  /api/story-builder/canon/entities          实体
GET  /api/story-builder/canon/knowledge         谁知道什么
GET  /api/story-builder/canon/foreshadows       伏笔
GET  /api/story-builder/canon/graph             依赖图摘要
GET  /api/story-builder/canon/validate          Canon 一致性校验
POST /api/story-builder/canon/rebuild           受控重建（失败保留原 DB）
POST /api/story-builder/canon/validate-outline  规划对照 Canon（只读检查）
```

## 11. Plugins（插件平台）

插件只能通过 Host 明确的扩展点**追加**能力：delivery exporter / quality evaluator / MCP
tool / MCP resource。Core 注册不可被覆盖，禁用会精确卸载该插件自己的注册项。

```text
当前信任模型 = trusted in-process（permission 是 Host 能力治理，不是 OS 沙箱）
安装 / 启用 / 禁用属于 operator 接口（Application Service），当前没有 REST / MCP 入口
「插件」页只展示只读状态与信任模型
```

## 12. Agent（有界自治）

```text
给出目标 → 计划预览（0 mutation）→ 有界执行 → 遇到 protected action 请求批准
→ 检查点 → 可恢复 / 可取消
```

Agent 只用既有 Application 能力（不跑 shell / 不读文件 / 不直连模型），
默认**不自动接受** revision、**不自动正式交付**；13 个已注册 action 之外的字符串一律拒绝。

## 13. MCP（机器接口）

```text
NOVELFORGE_PROJECT_ROOT=<root> .venv\Scripts\python.exe -m novelforge.interfaces.mcp
```

23 个 tool（生成 / 编辑 / 质量 / 修复 / 交付）+ 13 个 resource（作品 / 蓝图 / 场景 / 质量 /
评审 / 交付）。所有调用必须显式带 `novel_id`；跨作品会被拒绝；返回值是统一 Result Envelope
（结构化字段才是 contract，`summary` 只是补充）。

## 14. AI 配置

唯一被 current 代码读取的 provider 配置：`novel/config/ai/providers.json`
（全部 `enabled=false` 是默认值）。

```text
开箱行为：不调用模型；生成 / 改写返回稳定错误码（不静默降级成规则式假内容）
接模型：把 enabled 改 true + 设置 api_key_env 指向的环境变量（key 绝不写进仓库）
所有模型调用统一经过 src/novelforge/ai（不使用第二套调用路径）
```

## 15. 端到端工作流

```text
① 新建作品 → ② 创造（前提 / 主题）→ ③ 世界 / 人物 → ④ 故事 / 场景
→ ⑤ 检查（Q0–Q9）→ ⑥ 修复 + 复核（必要时返回 ④ 改选）→ ⑦ 接受
→ ⑧ 交付（preflight → 快照 → 下载）
```

可选旁路：

```text
Agent：把「目标」交给 Agent，先看计划再执行（敏感动作需要你批准）
MCP：把同一批能力接到机器客户端（步骤完全等价于 UI 路径）
插件：为交付格式 / 质量 evaluator / MCP surface 追加能力
```

可执行版本的同样流程见 `skills/novelforge-v4.0.1/workflows/*/SKILL.md`。
