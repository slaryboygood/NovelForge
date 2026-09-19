# NOVELFORGE V4.0.1 — MODULAR FEATURE & SKILL LIBRARY RESULT

> 阶段：**V4.0.1 Feature Usage Documentation + Modular Skill Library + Versioned Skill Baseline**
> 结论：**PASS**（详见 §13 判定）

## 1. 基线（Git）

```text
Starting HEAD          afc57d8（= tag v4.0.1 = main = v4）
Branch                 v4-401-feature-skills（平面分支，从 SKILL_BASELINE_START 建立）
SKILL_BASELINE_START   afc57d8
Frozen tags            未移动（novelforge-product-v3-final / novelforge-product-v4-final /
                       v4.0.0 / v4.0.1）
历史改写 / force push   无
```

## 2. 阅读的文档与契约

```text
仓库规则              AGENTS.md、README.md
Cleanup 最终报告      docs/v4/V4_POST_RELEASE_CLEANUP_REPORT.md、V4_POST_RELEASE_CLEANUP_INVENTORY.md
V4 架构              V4_ARCHITECTURE.md、V4_MODULE_BOUNDARIES.md、V4_MODULE_CLASSIFICATION.md、
                     V4_DELETION_PLAN.md、V4_ARCHITECTURE_RISKS.md、V4_CODEBASE_INVENTORY.md
Current Contracts    V4_BLUEPRINT_CONTRACT / V4_EDITOR_CONTRACT / V4_QUALITY_CONTRACT /
                     V4_REPAIR_CONTRACT / V4_DELIVERY_CONTRACT / V4_MCP_CONTRACT /
                     V4_PLUGIN_CONTRACT / V4_AGENT_CONTRACT / V4_LLM_CONTRACT /
                     V4_UI_CONTRACT / V4_MEMORY_ARCHITECTURE
Final Acceptance     V4_12_ACCEPTANCE_MATRIX / V4_12_EVIDENCE_INDEX / V4_12_FINAL_ACCEPTANCE_REPORT /
                     V4_12_ARCHITECTURE_DEBT_REVIEW / V4_12_STATUS
阶段盘点（历史证据）   V4_04/05/06/07/08/09/10/11（*_INVENTORY / *_REPORT）
ADR                   docs/v4/adr/ADR-001…ADR-036（按引用阅读相关条目）
```

代码与运行期事实（DISK / RUNTIME WINS）：

```text
REST                 create_app(...) 的真实 route 表（46 个 API 路径）
MCP                  build_tool_registry() = 23 tools / build_resource_registry() = 13 resources
Application services  project / blueprint / review / editor / export / journey / agent / plugins / utility
UI                   ui/src/App.tsx、ui/src/studio/**、ui/src/api/studio.ts
Tests                tests/**（acceptance / v4 / studio / memory / generation / quality / editor /
                     delivery / mcp / plugins / agent / ai + frozen guards）
```

## 3. 当前能力（capability list）

```text
Project / Novel Lifecycle · Story Studio · Story Blueprint · Generation · Memory / Context ·
Quality（Q0–Q9）· Repair · Editor · Delivery / Export / .nfpack · Canon · StoryState / NovelContext ·
Plugins · Agent · MCP · AI / Provider Configuration
能力模块数 = 16（含组合层 workflows）
```

## 4. Use cases / Skills

```text
Use cases discovered      77（全部有 current 接口）
Atomic skills             72
Workflow skills            5
Skill 总数                77
Skill 覆盖率              100%（docs/v4/V4_0_1_SKILL_COVERAGE.md）
```

| Module | Skills |
| --- | ---: |
| project | 4 |
| studio | 4 |
| blueprint | 5 |
| generation | 9 |
| memory | 3 |
| quality | 4 |
| repair | 4 |
| editor | 6 |
| delivery | 6 |
| canon | 5 |
| story-state | 2 |
| plugins | 5 |
| agent | 6 |
| mcp | 5 |
| ai | 4 |
| workflows | 5 |

## 5. 接口映射

```text
UI mappings              docs/v4/V4_0_1_INTERFACE_MAP.md（用户动作 → 视图）
REST mappings            46 个 API 路径（/api/story-builder/{novels,canon,editor,delivery,studio,agent}）
Application mappings     application/services/{project,blueprint,review,editor,export,journey,agent,plugins}.py
MCP mappings             23 tools / 13 resources（含每个 tool 的能力归属）
Unsupported interfaces   记录为 N/A：memory REST/MCP、插件生命周期 REST/MCP、Canon MCP、
                         Agent 编排 MCP、正文写作类 tool（明确不存在）
```

## 6. Skill gaps（本任务不修 runtime）

```text
GAP-001 /studio/generate 的 dry_run 字段未实现
GAP-002 确定性因果链（build_links）没有 UI/REST/MCP 入口
GAP-003 Canon REST 绕过 Application Services（无 Canon MCP surface）
GAP-004 Memory 无 Application facade / REST / MCP
GAP-005 插件 install/enable/disable 无 REST / MCP（DEFER）
GAP-006 部分 Editor Application 能力（patch_batch / move / undo / change_impact / evaluate_and_repair）无 wire 入口
GAP-007 Delivery explicit_revisions / include_node_types 在 UI 无入口
GAP-008 StoryState 没有产品级读写入口（只读消费）
详见 docs/v4/V4_0_1_SKILL_GAPS.md
```

## 7. Baseline 与验证工具

```text
Skill manifest           skills/novelforge-v4.0.1/SKILL_MANIFEST.json（98 个文件的 sha256）
Hash baseline            CRLF → LF 归一化后 sha256（Windows autocrlf 兼容）
Module boundary 验证     tests/v4/skills/test_module_boundaries.py
REST 验证                tests/v4/skills/test_rest_references.py + test_interface_references.py
MCP 验证                 tests/v4/skills/test_mcp_references.py（含 23 tools 覆盖）
Source 验证              tests/v4/skills/test_source_map.py
Frozen baseline 验证     tests/v4/skills/test_frozen_baseline.py
统一验证器               scripts/validate_v4_0_1_skills.py（含 --write-manifest）
```

## 8. 验收结果（§91）

```text
tests/v4/skills/**         30 passed
tests/v4/**（含 isolation）  通过
tests/acceptance/**        通过
  ↑ 三者合计               174 passed
full pytest                954 passed, 1 skipped（505.98s）
validate_project.py        PASS（46 个 API 路径）
validate_v4_0_1_skills.py  PASS（77 skills / 16 modules / 23 MCP tools / 13 MCP resources）
浏览器 golden              未重跑（src/**、ui/** 0 改动，按 §91 免除无意义重跑；
                           相关门禁脚本仍保留：browser_v4_studio_golden / v4_11_agent / v4_legacy_entry）
```

## 9. Product Diff Gate（§92）

```text
git diff afc57d8..HEAD -- src ui novel   → 空（0 product semantic change）
变更分布                                 docs 5+ / scripts 1 / skills 99 / tests 9（收尾提交再加 docs 与根 README/AGENTS）
非必要产品改动                            无（本任务未修改任何 runtime 代码）
```

## 10. 产出文件

```text
新增 docs            V4_0_1_FEATURE_USAGE_CATALOG.md、V4_0_1_INTERFACE_MAP.md、
                     V4_0_1_USER_FEATURE_GUIDE.md、V4_0_1_SKILL_COVERAGE.md、
                     V4_0_1_SKILL_GAPS.md、V4_0_1_SKILL_LIBRARY_REPORT.md（本文件）
新增 skills          skills/novelforge-v4.0.1/**（README / SKILL_CATALOG / SOURCE_MAP /
                     DEPENDENCY_MAP / manifest.yaml / SKILL_MANIFEST.json / 16 module README /
                     77 SKILL.md）
新增 scripts         scripts/validate_v4_0_1_skills.py
新增 tests           tests/v4/skills/**（8 文件：7 个守卫 + 共享 helper）
修改                 README.md（新增入口）、AGENTS.md（新增操作知识层提示）
```

## 11. 提交（模块化，§87）

```text
0802342  docs(v4): inventory v4.0.1 current feature usage
c3c35e7  feat(skills): add project and studio modules
cc975c9  feat(skills): add blueprint and generation modules
2bae746  feat(skills): add memory quality and repair modules
e9c1fd6  feat(skills): add editor and delivery modules
ecdb2f9  feat(skills): add canon and story-state modules
e2c91a9  feat(skills): add plugins agent mcp and ai modules
56e5b40  feat(skills): add workflow module
9a9697a  docs(skills): add catalog source map coverage and baseline manifests
a372a75  test(skills): add modular v4.0.1 skill baseline guards
（收尾）  docs(v4): close v4.0.1 feature and skill inventory
```

## 12. 剩余风险与维护政策

```text
剩余风险
  · GAP-001…008：能力/接口不一致，本任务按规则只记录不修改（属未来产品任务）
  · Skills 描述的是"当前契约 + 当前运行时"；contract 变化会让对应 REST/MCP 测试先失败（这是设计目标）
  · 插件格式 / 插件 MCP surface 属运行时注入，不在 Core 基线内（已在 skill 中说明）

未来维护政策（§62 / §70 / §96）
  · skills/novelforge-v4.0.1/** 是 V4.0.1 的 documentation/tooling baseline，不是产品 frozen tag
  · 新版本（V4.0.2 / V4.1 / V5）建立自己的版本化 baseline，并显式记录继承关系
  · 必须纠正文档错误时走显式 SKILL_BASELINE_UPDATE：
    python scripts/validate_v4_0_1_skills.py --write-manifest（说明原因 + 更新哈希 + 更新测试）
  · 不创建 novelforge-v4.0.1-skills-final 之类的 Git tag（Skill freeze ≠ product tag）
  · 不移动 novelforge-product-v4-final / v4.0.0 / v4.0.1
```

## 13. Final verdict

```text
[x] V4.0.1 current functionality fully inventoried
[x] all meaningful supported use cases documented（77）
[x] every use case mapped to modular Skill(s)（coverage 100%）
[x] modules have explicit boundaries（16 module Public Contract，边界由测试守卫）
[x] Skill ↔ actual interfaces verified（REST 46 路径 / MCP 23 tools / 13 resources）
[x] V2/V3 retired functionality does not leak back（retired marker 守卫 + 术语扫描）
[x] versioned Skill baseline protected（SKILL_MANIFEST.json 哈希基线 + frozen baseline 测试）
[x] product runtime semantics unchanged（src / ui / novel diff = 0）

NOVELFORGE V4.0.1 MODULAR FEATURE & SKILL LIBRARY = PASS
```
