"""Application layer（V4-01 起）。

本层是 UI / REST / MCP / Agent 的**唯一业务入口**（见 `docs/v4/adr/ADR-001`、
`docs/v4/V4_MODULE_BOUNDARIES.md` §3.2）。

Strangler 迁移已经结束（post-release cleanup）：V3 的 `story_builder/*` 过渡实现
与 `api/story_builder_routes.py` 已整体删除，`application.services` 是唯一编排入口：

```text
project / blueprint / review / editor / export(delivery) / journey / agent
```

接口层（`api/`、`interfaces/mcp/`）只调用服务层；直接 import `story_engine.*` 的
存量例外只剩 `api/canon_routes.py` 与 `api/app.py`
（见 `tests/v4/isolation/test_module_boundaries.py` 白名单，只减不增）。
"""

__all__: list[str] = []

