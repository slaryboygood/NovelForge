"""Application Services（V4-01）。

已收编的服务：

```text
journey_service : JourneyProjection（唯一进度 / 下一步投影）—— ADR-004
export_service  : ExportService（唯一导出出口）            —— ADR-007 / V4_EXPORT_SPEC
project_service : ProjectService（作品生命周期）            —— ADR-001
utility_service : UtilityService（最小 application → ai 集成路径）—— V4-02 §25
blueprint_service : BlueprintService（Story Blueprint 生成/读取入口）—— V4-04 §52
review_service  : ReviewService / QualityLoopService（质量评审 + 定向修复闭环）—— V4-05 §55–§56
editor_service  : EditorService（Blueprint 编辑 / revision / diff / approve）—— V4-06 §7
```

边界：只允许依赖 domain（story_engine）、persistence、core、legacy（只读）；
禁止依赖 interfaces（api / mcp）、ai provider，禁止直接拼文件路径或写 SQL。
"""

from .blueprint import BlueprintService, blueprint_service
from .editor import EditorService, editor_service
from .export import ExportService, export_service
from .journey import JourneyService, journey_service
from .project import ProjectService, project_service
from .review import (
    QualityLoopResult,
    QualityLoopService,
    RepairOutcome,
    ReviewService,
    review_service,
)
from .utility import UTILITY_LABEL_CONTRACT, UtilityService, utility_service

__all__ = [
    "BlueprintService", "EditorService", "ExportService", "JourneyService",
    "ProjectService",
    "QualityLoopResult", "QualityLoopService", "RepairOutcome", "ReviewService",
    "UtilityService", "UTILITY_LABEL_CONTRACT", "blueprint_service",
    "editor_service", "export_service", "journey_service", "project_service",
    "review_service", "utility_service",
]
