"""NovelForge Plugin SDK（V4-09 §8）—— 第三方插件的**唯一稳定依赖**。

```text
Contribution / exporter_contribution / quality_contribution /
mcp_tool_contribution / mcp_resource_contribution    声明贡献
PluginContext                                        Host 注入的窄上下文（least privilege）
PluginAIClient                                       窄 AI 能力协议
PLUGIN_SDK_VERSION / PERMISSIONS / CONTRIBUTION_KINDS
```

第三方插件**不得** import `novelforge` 的其他模块（有守卫测试与文档说明）：
repository / store / persistence / provider / ai.providers 全部不可见。
"""

from .context import PluginContext
from .quality import quality_issue
from .contracts import (
    CONTRIBUTION_KINDS,
    PERMISSIONS,
    PLUGIN_SDK_VERSION,
    Contribution,
    ContributionKind,
    PluginAIClient,
    exporter_contribution,
    mcp_resource_contribution,
    mcp_tool_contribution,
    quality_contribution,
)

__all__ = [
    "CONTRIBUTION_KINDS", "PERMISSIONS", "PLUGIN_SDK_VERSION", "Contribution",
    "ContributionKind", "PluginAIClient", "PluginContext",
    "exporter_contribution", "mcp_resource_contribution", "mcp_tool_contribution",
    "quality_contribution", "quality_issue",
]
