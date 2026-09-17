"""JourneyService —— 唯一 JourneyProjection 入口（V4-01，ADR-004）。

为什么存在：V3 里同一本书的「阶段 / 进度 / 下一步」有两个计算入口
（`story_builder/v3_projection._journey_projection()` 与 `story_builder/ui_flow.py` 自己的
stage/next-step），这与 NF-005 的修复目标冲突。V4-01 把投影收编为服务层唯一入口：

```text
UI（Landing / Command Center / 引导流）
REST（/v3/.../command-center、/v3/.../journey、/guided-flow）
MCP（V4-08 的 journey resource）
        ↓
JourneyService → JourneyProjection（唯一公式）
```

迁移策略（Strangler）：V4-01 的实现仍然委托给既有 `v3_projection.journey_projection`
（V3 application 层），只把**入口**收敛到服务层；计算实现的搬迁属于 V4-04/V4-10。
V4-01 不允许新增第三套 progress 公式。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from novelforge.story_builder import v3_projection

#: V3 阶段 → 既有 UI 粗粒度分组（**纯展示映射**，不参与任何进度计算）
STAGE_TO_DISPLAY_GROUP: dict[str, str] = {
    "creation": "design",
    "world": "design",
    "characters": "design",
    "story": "design",
    "simulation": "occurred",
    "outline": "output",
    "review": "governance",
    "export": "output",
}


class JourneyService:
    """按 (project_root, novel_id) 计算只读 JourneyProjection。"""

    def __init__(self, project_root: Path | str, novel_id: str) -> None:
        self.project_root = Path(project_root)
        self.novel_id = str(novel_id or "").strip()
        if not self.novel_id:
            raise ValueError("JourneyService 需要显式 novel_id（不允许隐式当前作品）")

    # ------------------------------------------------------------------ 投影
    def projection(self) -> dict[str, Any]:
        """唯一进度投影：阶段 / 目标 / 进度 / 下一步 / 风险（只读）。"""

        return v3_projection.journey_projection(self.project_root, self.novel_id)

    def command_center(self) -> dict[str, Any]:
        """Command Center 完整投影（Landing 与工作台共用同一数据源）。"""

        return v3_projection.command_center(self.project_root, self.novel_id)

    def display_group(self, projection: Mapping[str, Any] | None = None) -> str:
        """当前阶段在既有 UI 分组下的展示归类（design / occurred / output / governance）。

        `projection` 可传入已计算的投影，避免同一请求重复计算（调用方缓存友好）。
        """

        data = projection if projection is not None else self.projection()
        stage = str((data.get("journey") or {}).get("current_stage") or "")
        return STAGE_TO_DISPLAY_GROUP.get(stage, "design")

    def next_action(self) -> Mapping[str, Any]:
        """当前推荐下一步（来自同一投影，不允许 UI 自行推导）。"""

        return self.projection().get("next_action") or {}


def journey_service(project_root: Path | str, novel_id: str) -> JourneyService:
    """工厂函数：`journey_service(root, novel_id).projection()`。"""

    return JourneyService(project_root, novel_id)


__all__ = ["JourneyService", "STAGE_TO_DISPLAY_GROUP", "journey_service"]
