"""Application layer（V4-01 起）。

本层是 UI / REST / MCP / Agent 的**唯一业务入口**（见 `docs/v4/adr/ADR-001`、
`docs/v4/V4_MODULE_BOUNDARIES.md` §3.2）。

V4-01 采用 Strangler 迁移策略：

* 只把边界清楚、风险低、测试充分的 orchestration 收编进 `application.services`；
* 既有 `story_builder/*`（V3 application）作为过渡实现被服务层包装，
  待对应阶段（V4-04…V4-07）替换；
* 接口层（`api/`、未来 `interfaces/mcp/`）只调用服务层，不再直接 import `story_engine.*`
  （存量例外见 `tests/v4/isolation/test_module_boundaries.py` 白名单）。
"""

__all__: list[str] = []

