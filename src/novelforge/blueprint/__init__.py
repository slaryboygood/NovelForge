"""NovelForge `blueprint` —— Story Blueprint 节点模型与 canonical store（V4-04）。

Public Contract：

```text
BlueprintNode / BlueprintNodeRef           节点与引用
BLUEPRINT_SCHEMA_VERSION / 节点枚举          schema 版本与类型（NodeType / NodeStatus / …）
PAYLOAD_MODELS                              node_type → 严格 payload 模型
BlueprintRepository                         canonical store（append-only revision）
validate_node / validate_graph / require_valid   结构 / 引用 / ownership 校验
ALLOWED_STATUS_TRANSITIONS / assert_can_regenerate  状态流转
BlueprintError 家族
```

注意：Blueprint 是**提案层**（generated content is proposal until promoted，ADR-017）。
生成结果默认 `status="proposed"`，不会写入 Canon / StoryState。
"""

from .contracts import (
    ALLOWED_PARENT_TYPES,
    BLUEPRINT_SCHEMA_VERSION,
    NODE_ID_PREFIX,
    PAYLOAD_MODELS,
    BlueprintNode,
    BlueprintNodeRef,
    CausalLinkPayload,
    ChapterCardPayload,
    CharacterArcPayload,
    CharacterPayload,
    NodeStatus,
    NodeType,
    PayoffPayload,
    PremisePayload,
    SceneCardPayload,
    SetupPayload,
    StoryArcPayload,
    StructuralUnitPayload,
    ThemePayload,
    WorldPayload,
    slug,
    utc_now,
)
from .errors import (
    BlueprintError,
    BlueprintNodeNotFound,
    BlueprintOwnershipError,
    BlueprintStatusError,
    BlueprintValidationError,
)
from .lifecycle import (
    ALLOWED_STATUS_TRANSITIONS,
    AUTHOR_CONFIRMED_STATUSES,
    assert_can_regenerate,
    next_status_for_regeneration,
)
from .repository import BlueprintRepository
from .validation import require_valid, validate_graph, validate_node

__all__ = [
    # node model
    "BlueprintNode", "BlueprintNodeRef", "NodeType", "NodeStatus",
    "BLUEPRINT_SCHEMA_VERSION", "NODE_ID_PREFIX", "PAYLOAD_MODELS",
    "ALLOWED_PARENT_TYPES", "slug", "utc_now",
    # payloads
    "PremisePayload", "ThemePayload", "WorldPayload", "CharacterPayload",
    "CharacterArcPayload", "StoryArcPayload", "StructuralUnitPayload",
    "ChapterCardPayload", "SceneCardPayload", "CausalLinkPayload", "SetupPayload",
    "PayoffPayload",
    # store + validation + lifecycle
    "BlueprintRepository", "validate_node", "validate_graph", "require_valid",
    "ALLOWED_STATUS_TRANSITIONS", "AUTHOR_CONFIRMED_STATUSES",
    "assert_can_regenerate", "next_status_for_regeneration",
    # errors
    "BlueprintError", "BlueprintNodeNotFound", "BlueprintOwnershipError",
    "BlueprintStatusError", "BlueprintValidationError",
]

