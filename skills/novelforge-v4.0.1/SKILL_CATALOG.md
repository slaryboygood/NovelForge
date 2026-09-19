# Skill Catalog — NovelForge V4.0.1

> Skill ID 格式：`novelforge-v4.0.1.<module>.<verb-object>`。
> 一旦进入 V4.0.1 baseline，ID 不得随意修改（见 README 的 `SKILL_BASELINE_UPDATE` 政策）。

## Project

| Skill ID | 意图 | 接口 |
| --- | --- | --- |
| `novelforge-v4.0.1.project.create-novel` | 新建作品 | UI / REST / Application |
| `novelforge-v4.0.1.project.inspect-novels` | 列出 / 查看作品 | UI / REST / Application / MCP（摘要） |
| `novelforge-v4.0.1.project.rename-novel` | 重命名（只改名字） | REST / Application |
| `novelforge-v4.0.1.project.archive-novel` | 归档作品（可恢复删除） | UI / REST / Application |

## Studio

| Skill ID | 意图 | 接口 |
| --- | --- | --- |
| `novelforge-v4.0.1.studio.open-story-studio` | 启动并打开产品面 | UI |
| `novelforge-v4.0.1.studio.navigate-studio-workspace` | 深链接到工作区 / 实体 | UI |
| `novelforge-v4.0.1.studio.inspect-overview` | 看总览与下一步 | UI / REST / MCP |
| `novelforge-v4.0.1.studio.handle-legacy-url` | 旧 URL 归一化 | UI |

## Blueprint

| Skill ID | 意图 | 接口 |
| --- | --- | --- |
| `novelforge-v4.0.1.blueprint.inspect-blueprint` | 看蓝图节点视图 | UI / REST / MCP |
| `novelforge-v4.0.1.blueprint.inspect-node` | 看节点（可编辑字段 / 质量） | UI / REST / MCP |
| `novelforge-v4.0.1.blueprint.inspect-revisions` | 看 revision 历史与评审 | UI / REST / MCP |
| `novelforge-v4.0.1.blueprint.inspect-scene-cards` | 看场景卡（为什么存在） | UI / REST / MCP |
| `novelforge-v4.0.1.blueprint.understand-blueprint-model` | 掌握节点 / 父层级 / 状态模型 | — |

## Generation

| Skill ID | 意图 | 接口 |
| --- | --- | --- |
| `novelforge-v4.0.1.generation.generate-premise` | 生成前提 | UI / REST / MCP |
| `novelforge-v4.0.1.generation.generate-theme` | 生成主题 | UI / REST / MCP |
| `novelforge-v4.0.1.generation.generate-world` | 生成世界设定 | UI / REST / MCP |
| `novelforge-v4.0.1.generation.generate-character` | 生成人物卡 | UI / REST / MCP |
| `novelforge-v4.0.1.generation.generate-character-arc` | 生成人物弧 | UI / REST / MCP |
| `novelforge-v4.0.1.generation.generate-story-arc` | 生成故事弧 | UI / REST / MCP |
| `novelforge-v4.0.1.generation.generate-structural-unit` | 生成结构单元 | UI / REST / MCP |
| `novelforge-v4.0.1.generation.generate-chapter-plan` | 生成章节卡 | UI / REST / MCP |
| `novelforge-v4.0.1.generation.generate-scene-plan` | 生成场景卡 | UI / REST / MCP |

## Memory

| Skill ID | 意图 | 接口 |
| --- | --- | --- |
| `novelforge-v4.0.1.memory.inspect-derived-memory` | 查看派生记忆检索结果 | Application（Python API） |
| `novelforge-v4.0.1.memory.build-generation-context` | 组装 / 复现生成上下文 | Application（Python API） |
| `novelforge-v4.0.1.memory.understand-truth-precedence` | 掌握真相优先级 | — |

## Quality

| Skill ID | 意图 | 接口 |
| --- | --- | --- |
| `novelforge-v4.0.1.quality.evaluate-blueprint` | 跑 Q0–Q9 | UI / REST / MCP |
| `novelforge-v4.0.1.quality.inspect-quality-report` | 看报告与 gate 结论 | UI / REST / MCP |
| `novelforge-v4.0.1.quality.list-quality-issues` | 列 issue（含证据） | UI / REST / MCP |
| `novelforge-v4.0.1.quality.understand-quality-gates` | 掌握 gate / severity / code 语义 | — |

## Repair

| Skill ID | 意图 | 接口 |
| --- | --- | --- |
| `novelforge-v4.0.1.repair.plan-repair` | 修复预览（dry run） | UI / REST / MCP |
| `novelforge-v4.0.1.repair.apply-repair` | 执行修复 | UI / REST / MCP |
| `novelforge-v4.0.1.repair.verify-repair` | 复核修复 | UI / REST / MCP |
| `novelforge-v4.0.1.repair.understand-repair-contract` | 掌握 preserve / 范围 / 预算 | — |

## Editor

| Skill ID | 意图 | 接口 |
| --- | --- | --- |
| `novelforge-v4.0.1.editor.patch-node` | 字段级手工修改 | UI / REST / MCP |
| `novelforge-v4.0.1.editor.rewrite-node` | AI 字段级改写 | UI / REST / MCP |
| `novelforge-v4.0.1.editor.accept-revision` | 接受 revision | UI / REST / MCP |
| `novelforge-v4.0.1.editor.reject-revision` | 拒绝 revision（只记录） | UI / REST / MCP |
| `novelforge-v4.0.1.editor.restore-revision` | 恢复历史内容为新 revision | UI / REST / MCP |
| `novelforge-v4.0.1.editor.diff-revisions` | 结构化 diff | UI / REST / MCP |

## Delivery

| Skill ID | 意图 | 接口 |
| --- | --- | --- |
| `novelforge-v4.0.1.delivery.validate-delivery` | 交付预检 | UI / REST / MCP |
| `novelforge-v4.0.1.delivery.create-delivery-snapshot` | 建立快照（钉 revision） | REST / Application / MCP |
| `novelforge-v4.0.1.delivery.deliver-blueprint` | 正式交付（json/md/docx/nfpack） | UI / REST / MCP |
| `novelforge-v4.0.1.delivery.inspect-delivery-manifest` | 看 manifest / checksum | UI / REST / MCP |
| `novelforge-v4.0.1.delivery.download-delivery-artifact` | 下载交付物 | UI / REST / MCP |
| `novelforge-v4.0.1.delivery.list-delivery-snapshots` | 列出交付快照 | UI / REST / MCP |

## Canon

| Skill ID | 意图 | 接口 |
| --- | --- | --- |
| `novelforge-v4.0.1.canon.inspect-canon-truth` | 查看事实 / 事件 / 实体 / 知识 / 伏笔 | REST |
| `novelforge-v4.0.1.canon.inspect-canon-graph` | 查看 Canon 依赖图摘要 | REST |
| `novelforge-v4.0.1.canon.validate-canon-integrity` | 校验 Canon 一致性 | REST |
| `novelforge-v4.0.1.canon.validate-planning-against-canon` | 规划对照 Canon | REST |
| `novelforge-v4.0.1.canon.rebuild-canon` | 受控重建 Canon（operator） | REST |

## StoryState

| Skill ID | 意图 | 接口 |
| --- | --- | --- |
| `novelforge-v4.0.1.story-state.understand-story-state-boundary` | 掌握 StoryState 边界 | — |
| `novelforge-v4.0.1.story-state.inspect-story-state` | 只读查看状态摘要 | Application（Python API） |

## Plugins

| Skill ID | 意图 | 接口 |
| --- | --- | --- |
| `novelforge-v4.0.1.plugins.inspect-plugins` | 查看插件与信任模型 | UI / REST / Application |
| `novelforge-v4.0.1.plugins.inspect-plugin-contributions` | 查看贡献与审计 | Application |
| `novelforge-v4.0.1.plugins.approve-plugin` | 批准插件 | Application（operator） |
| `novelforge-v4.0.1.plugins.enable-plugin` | 启用插件 | Application（operator） |
| `novelforge-v4.0.1.plugins.disable-plugin` | 禁用并精确卸载 | Application（operator） |

## Agent

| Skill ID | 意图 | 接口 |
| --- | --- | --- |
| `novelforge-v4.0.1.agent.plan-agent-goal` | 计划预览（0 mutation） | UI / REST / Application |
| `novelforge-v4.0.1.agent.start-agent-session` | 启动有界执行 | UI / REST / Application |
| `novelforge-v4.0.1.agent.inspect-agent-session` | 查看 session 与审计 | UI / REST / Application |
| `novelforge-v4.0.1.agent.approve-agent-run` | 批准 / 拒绝 protected step | UI / REST / Application |
| `novelforge-v4.0.1.agent.resume-agent-session` | 从检查点继续 | UI / REST / Application |
| `novelforge-v4.0.1.agent.cancel-agent-session` | 取消 session | UI / REST / Application |

## MCP

| Skill ID | 意图 | 接口 |
| --- | --- | --- |
| `novelforge-v4.0.1.mcp.start-mcp-server` | 启动 MCP server（stdio） | MCP |
| `novelforge-v4.0.1.mcp.discover-mcp-surface` | 枚举 23 tools / 13 resources | MCP |
| `novelforge-v4.0.1.mcp.read-mcp-resource` | 读只读资源 | MCP |
| `novelforge-v4.0.1.mcp.call-mcp-tool` | 调用工具并解读 envelope | MCP |
| `novelforge-v4.0.1.mcp.understand-mcp-boundary` | 掌握接口层边界 | — |

## AI

| Skill ID | 意图 | 接口 |
| --- | --- | --- |
| `novelforge-v4.0.1.ai.configure-llm-provider` | 配置 provider（无 secret） | Application + 配置文件 |
| `novelforge-v4.0.1.ai.inspect-llm-provider-config` | 查看解析后的 provider 配置 | Application |
| `novelforge-v4.0.1.ai.run-without-provider` | 无模型时的稳定行为 | UI / REST / MCP |
| `novelforge-v4.0.1.ai.understand-llm-gateway-boundary` | 掌握 Gateway 边界 | — |

## Workflows（组合层）

| Skill ID | 组合 |
| --- | --- |
| `novelforge-v4.0.1.workflows.create-new-story-blueprint` | create-novel → generation.* → quality → accept → delivery |
| `novelforge-v4.0.1.workflows.review-and-repair-blueprint` | evaluate → list issues → plan → apply → verify → accept |
| `novelforge-v4.0.1.workflows.prepare-final-delivery` | evaluate → accept → validate → deliver → manifest → download |
| `novelforge-v4.0.1.workflows.use-novelforge-through-mcp` | start-mcp-server → discover → read → call |
| `novelforge-v4.0.1.workflows.operate-with-agent` | inspect-overview → plan → start → approve → resume → audit |
