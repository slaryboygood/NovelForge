# Dependency Map — NovelForge V4.0.1 Skill Library

> 这是 **skill 依赖**（操作顺序 / 前置条件），不是 Python import graph。

## 1. 标准创作主干

```text
project.create-novel
   ↓
generation.generate-premise
   ↓
generation.generate-theme
   ↓
generation.generate-world ──┐
   ↓                        │
generation.generate-character ←（可多个：index 决定 id）
   ↓
generation.generate-character-arc（每个主要人物）
   ↓
generation.generate-story-arc
   ↓
generation.generate-structural-unit（可多个）
   ↓
generation.generate-chapter-plan
   ↓
generation.generate-scene-plan
   ↓
quality.evaluate-blueprint
   ↓
repair.plan-repair → repair.apply-repair → repair.verify-repair
   ↓（不满意则改选）
editor.patch-node / editor.rewrite-node / generation.generate-*
   ↓
editor.accept-revision（作者决定）
   ↓
delivery.validate-delivery → delivery.deliver-blueprint → delivery.download-delivery-artifact
```

## 2. 只读链条（任何时刻可用）

```text
studio.inspect-overview
   ├→ blueprint.inspect-blueprint → blueprint.inspect-node → blueprint.inspect-scene-cards
   ├→ blueprint.inspect-revisions → editor.diff-revisions
   ├→ quality.inspect-quality-report → quality.list-quality-issues
   ├→ delivery.list-delivery-snapshots → delivery.inspect-delivery-manifest
   ├→ canon.inspect-canon-truth → canon.inspect-canon-graph → canon.validate-canon-integrity
   └→ story-state.inspect-story-state / memory.inspect-derived-memory
```

## 3. 硬前置（不满足则不要调用）

| Skill | 硬前置 |
| --- | --- |
| `generation.generate-character-arc` | 存在 character 节点（requires_parent） |
| `generation.generate-structural-unit` | 存在 story_arc（或显式 parent） |
| `generation.generate-chapter-plan` | 存在 unit / story_arc 父节点 |
| `generation.generate-scene-plan` | 存在 chapter 父节点 |
| `editor.patch-node` / `editor.rewrite-node` | 已读当前 revision 与 editable_fields |
| `editor.accept-revision` | 作者决定（protected；Agent 需 approval） |
| `editor.restore-revision` | from_revision 存在 |
| `repair.plan-repair` | 存在 open + repairable issue |
| `repair.apply-repair` | 已 plan 且未过期 |
| `repair.verify-repair` | 已执行修复 |
| `delivery.validate-delivery` | 有节点；accepted 模式需至少一个 accepted |
| `delivery.deliver-blueprint` | preflight 通过（或作者显式放宽） |
| `plugins.enable-plugin` | 插件 status=approved |
| `plugins.disable-plugin` | 插件当前 enabled / loaded / active / failed |
| `agent.start-agent-session` | 已 plan（session 存在） |
| `agent.approve-agent-run` | status=awaiting_approval 且有 approval_id |
| `agent.resume-agent-session` | checkpoint 存在且状态允许 |
| `mcp.call-mcp-tool` | 已 discover（知道 tool 名与参数） |
| `ai.*`（生成类） | 至少一个 provider enabled |

## 4. 跨模块边界（禁止的依赖）

```text
memory   ↛ 写 Canon / StoryState（派生视图）
quality  ↛ 修改 Blueprint（只读评估）→ 修复经 repair
delivery ↛ LLM / memory / repair / 修改真相（只读消费）
agent    ↛ MCP / REST 自调用；只用 Application Ports
mcp      ↛ 业务逻辑（只做适配）
plugins  ↛ 覆盖 Core 注册；不直接访问 store / repository
workflows↛ 拥有业务规则（只组合 atomic skill ID）
```

## 5. 常见分叉决策

```text
要改整节点        → generation.generate-*（重生成）
要改几个字段      → editor.patch-node
要模型改指定字段  → editor.rewrite-node
有质量 issue      → repair.plan-repair（先 dry run）
结构非法（不可自动修）→ 作者 / editor 手工处理
想回退            → editor.restore-revision
要交付            → workflows.prepare-final-delivery
要自动化多步      → workflows.operate-with-agent
机器客户端接入    → workflows.use-novelforge-through-mcp
```
