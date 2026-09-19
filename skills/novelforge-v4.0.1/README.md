# NovelForge V4.0.1 — 操作知识层（Skill Library）

> 这是 **V4.0.1 的版本化稳定基线**（`status: frozen-baseline`）。
> 目的：新的 Codex / Agent 进入本仓库时不必重新逆向 800 个文件 —— 读这里就够了。

## 先读什么

```text
1 SKILL_CATALOG.md     有哪些 module / skill，各自解决什么意图
2 <module>/README.md   该能力模块的 Public Contract（owner / 边界 / 禁止事项）
3 <module>/<skill>/SKILL.md  具体怎么做（preconditions → procedure → verification）
4 SOURCE_MAP.md        每个 skill 对应的 Contract / 源码 / REST / MCP / tests
5 DEPENDENCY_MAP.md    skill 之间的前置关系与标准路径
```

配套文档（人看 + 技术 SSOT）：

```text
docs/v4/V4_0_1_FEATURE_USAGE_CATALOG.md  current 能力与用法总表
docs/v4/V4_0_1_INTERFACE_MAP.md           UI / REST / Application / MCP 映射
docs/v4/V4_0_1_USER_FEATURE_GUIDE.md      面向使用者的功能指南
docs/v4/V4_0_1_SKILL_COVERAGE.md          skill 覆盖率
docs/v4/V4_0_1_SKILL_GAPS.md              已知能力 / 接口缺口（本任务不修 runtime）
docs/v4/V4_*_CONTRACT.md                  技术 SSOT（contract > 本目录）
```

## 模块

| Module | 能力 | Skills |
| --- | --- | ---: |
| `project` | 作品生命周期 | 4 |
| `studio` | Story Studio（唯一产品面） | 4 |
| `blueprint` | Story Blueprint 节点图 | 5 |
| `generation` | 逐级结构化生成（proposal） | 9 |
| `memory` | 派生记忆与上下文装配 | 3 |
| `quality` | Q0–Q9 质量门禁 | 4 |
| `repair` | 定向修复与复核 | 4 |
| `editor` | 作者编辑（patch / rewrite / accept / restore） | 6 |
| `delivery` | revision-pinned 交付 | 6 |
| `canon` | 受保护真相（Canon） | 5 |
| `story-state` | StoryState 边界与只读检查 | 2 |
| `plugins` | 插件平台（Host 扩展点） | 5 |
| `agent` | 有界 Agent Mode | 6 |
| `mcp` | MCP 机器接口 | 5 |
| `ai` | LLM Gateway 与 provider 配置 | 4 |
| `workflows` | 组合层（不是 owner） | 5 |

总计 **77 个 skill（72 atomic + 5 workflow）**；catalog / source map / hash baseline 见
`SKILL_CATALOG.md`、`SOURCE_MAP.md`、`SKILL_MANIFEST.json`。

## 使用纪律（所有 skill 共有）

```text
· 显式携带 novel_id：禁止猜"当前作品"
· 写操作带 expected_revision + idempotency_key；冲突即停（不覆盖）
· 优先 UI / REST / Application / MCP；不直接编辑 Blueprint / Quality / Editor / Delivery 落盘文件
· AI 产出是 proposal；accept / reject / restore 属作者决定
· 质量通过 ≠ 作者已接受；交付默认 accepted + revision-pinned
· 不绕过 frozen 边界（Canon / StoryState / legacy 源 / frozen Repair Contract 与 Gate）
```

## 已退休能力（不得作为 current 出现在任何 skill 里）

```text
V2/V3 Story Builder 后端（引导流 / session / design tree / route_lab / inspector / 旧蓝图与大纲存储 /
模拟运行时 / 正文 writer / v3_projection / legacy 导出）已随 post-release cleanup 退休。
证据：docs/v4/V4_POST_RELEASE_CLEANUP_REPORT.md §96b–§96h。
旧 URL 只做一次性归一化（见 studio/handle-legacy-url）；不承诺旧功能，也不重建旧界面。
```

## 版本与冻结政策

```text
本目录 = V4.0.1 的 documentation/tooling baseline，**不是** product frozen tag。
未发布的版本（V4.0.2 / V4.1 / V5）应建立自己的版本化 baseline，并显式记录继承关系；
不要静默修改本目录。必须纠正文档错误时，走 SKILL_BASELINE_UPDATE：
说明原因 → 更新 SKILL_MANIFEST.json 哈希 → 更新测试。
```

## 本地校验

```powershell
.venv\Scripts\python.exe -m pytest -q tests/v4/skills
.venv\Scripts\python.exe scripts/validate_v4_0_1_skills.py
```
