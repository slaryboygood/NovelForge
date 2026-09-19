# NovelForge V4.0.1 — Skill Coverage

> 判据：**每一个正式 supported user / operator intent 至少有一个 Skill**（§58）。
> 覆盖率 = covered use cases / supported use cases。`N/A` 表示没有 current 接口，因此
> 不构成 supported use case（记录在 `V4_0_1_SKILL_GAPS.md`）。

| Capability | Supported Use Cases | Skills | Coverage | Missing |
| --- | ---: | ---: | ---: | --- |
| Project | 4 | 4 | 100% | — |
| Studio | 4 | 4 | 100% | — |
| Blueprint | 5 | 5 | 100% | patch / regenerate 由 Editor / Generation 模块拥有 |
| Generation | 9 | 9 | 100% | — |
| Memory | 3 | 3 | 100% | REST / MCP surface（GAP-004） |
| Quality | 4 | 4 | 100% | — |
| Repair | 4 | 4 | 100% | — |
| Editor | 6 | 6 | 100% | batch / move / undo 无接口（GAP-006） |
| Delivery | 6 | 6 | 100% | — |
| Canon | 5 | 5 | 100% | Canon 路由不经 Application（GAP-003） |
| StoryState | 2 | 2 | 100% | 无产品级读写入口（GAP-008） |
| Plugins | 5 | 5 | 100% | install / enable / disable 无 REST / MCP（GAP-005） |
| Agent | 6 | 6 | 100% | — |
| MCP | 5 | 5 | 100% | — |
| AI | 4 | 4 | 100% | — |
| Workflows | 5 | 5 | 100% | — |
| **合计** | **77** | **72 atomic + 5 workflow** | **100%** | 见 `V4_0_1_SKILL_GAPS.md` |

## 覆盖口径说明

```text
· Workflow skill 只组合 atomic skill ID，不复制底层步骤，也不是 product owner。
· 「supported use case」= 当前存在 UI / REST / Application / MCP 任一可达入口的意图。
· 内部 Python 函数（如 CanonService.update_fact、EditorService.patch_batch）不自动成为 Skill。
· 覆盖率统计只针对 current 能力；V2/V3 已退休能力不参与统计（也不允许出现在 Skill 中）。
```
