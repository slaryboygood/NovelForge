"""NovelForge `interfaces.mcp` —— MCP Server & Machine Interface（V4-08）。

**MCP IS NOT THE BUSINESS LAYER.**

Public Contract：

```text
MCPDispatcher / ResourcePayload       协议无关的调用入口（in-process 测试与 server 共用）
create_mcp_server / create_dispatcher  服务工厂（依赖注入 project_root / services_factory）
MCPToolRegistry / MCPResourceRegistry  工具与资源注册表（唯一 tool / resource SSOT）
ToolSpec / ResourceSpec / ToolResult   tool 声明 / resource 声明 / 统一 Result Envelope
parse_uri / ResourceTarget / paginate  URI 规范与分页
map_error / MCPError 家族              稳定错误映射
MCP_INTERFACE_VERSION                  接口版本（与 blueprint / delivery schema 版本无关）
InvocationRecord                       接口层 observability（不写业务 store）
```

边界（§2、§7、§59–§61）：

```text
interfaces.mcp → application.services（唯一依赖）
禁止           → blueprint / generation / quality / editor / delivery / memory / ai /
                 persistence / story_engine / api / 直接 HTTP
禁止           → MCP 自行创作、判断质量、规划修复、修改 revision
```

启动（stdio transport）：`python -m novelforge.interfaces.mcp`
"""

from .contracts import (
    MCP_INTERFACE_VERSION,
    MCP_SERVER_NAME,
    PERMISSIONS,
    ResourceSpec,
    ToolResult,
    ToolSpec,
    resource_table,
    tool_table,
)
from .dispatch import MCPDispatcher, map_error
from .errors import (
    MCP_ERROR_CODES,
    MCPDeliveryBlocked,
    MCPError,
    MCPInvalidArgument,
    MCPInternalError,
    MCPLLMUnavailable,
    MCPNodeNotFound,
    MCPOperationRejected,
    MCPOwnershipMismatch,
    MCPPreserveViolation,
    MCPQualityBlocked,
    MCPRequiresReview,
    MCPResourceNotFound,
    MCPRevisionConflict,
    MCPToolNotFound,
    InvocationRecord,
)
from .payloads import ResourcePayload, as_payload, json_payload
from .registry import MCPResourceRegistry, MCPToolRegistry
from .serialization import (
    DEFAULT_MIME,
    MIME_TYPES,
    assert_no_secrets,
    mime_for,
    sanitize,
)
from .server import (
    MCP_SDK_AVAILABLE,
    MCPSdkUnavailable,
    MCPToolFailure,
    create_dispatcher,
    create_mcp_server,
)
from .uri import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    ResourceTarget,
    artifact_uri,
    blueprint_uri,
    decode_cursor,
    delivery_uri,
    encode_cursor,
    issues_uri,
    manifest_uri,
    node_uri,
    novel_uri,
    paginate,
    parse_uri,
    quality_uri,
    review_uri,
    revision_uri,
    scenes_uri,
)

__all__ = [
    # contracts
    "MCP_INTERFACE_VERSION", "MCP_SERVER_NAME", "PERMISSIONS", "ResourceSpec",
    "ToolResult", "ToolSpec", "resource_table", "tool_table",
    # dispatch / registries
    "MCPDispatcher", "MCPResourceRegistry", "MCPToolRegistry", "map_error",
    # resources
    "ResourcePayload", "as_payload", "json_payload",
    # serialization
    "DEFAULT_MIME", "MIME_TYPES", "assert_no_secrets", "mime_for", "sanitize",
    # server
    "MCP_SDK_AVAILABLE", "MCPSdkUnavailable", "MCPToolFailure",
    "create_dispatcher", "create_mcp_server",
    # uri
    "DEFAULT_LIMIT", "MAX_LIMIT", "ResourceTarget", "artifact_uri",
    "blueprint_uri", "decode_cursor", "delivery_uri", "encode_cursor",
    "issues_uri", "manifest_uri", "node_uri", "novel_uri", "paginate", "parse_uri",
    "quality_uri", "review_uri", "revision_uri", "scenes_uri",
    # errors
    "InvocationRecord", "MCPDeliveryBlocked", "MCPError", "MCPInvalidArgument",
    "MCPInternalError", "MCPLLMUnavailable", "MCPNodeNotFound", "MCPOperationRejected",
    "MCPOwnershipMismatch", "MCPPreserveViolation", "MCPQualityBlocked",
    "MCPRequiresReview", "MCPResourceNotFound", "MCPRevisionConflict",
    "MCPToolNotFound", "MCP_ERROR_CODES",
]
