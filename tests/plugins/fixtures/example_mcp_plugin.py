"""测试用 MCP 插件（V4-09 §68、§97）：只依赖 plugin SDK。"""

from novelforge.plugins import sdk

PLUGIN_ID = "com.example.mcpext"


def blueprint_stats(context, arguments):
    view = context.blueprint_view()
    blueprint = dict(view.get("blueprint") or {})
    return {"ok": True, "node_count": int(blueprint.get("node_count") or 0),
            "summary": "示例插件工具：统计 Blueprint 节点数"}


def plugin_manifest_resource(context, target):
    return {"plugin": PLUGIN_ID, "uri": str(getattr(target, "uri", "")),
            "note": "示例插件资源"}


def register(context):
    return [
        sdk.mcp_tool_contribution(
            name="blueprint_stats", factory=blueprint_stats,
            input_schema={"type": "object", "properties":
                          {"novel_id": {"type": "string"}},
                          "additionalProperties": False},
            description="示例插件工具（namespaced）", read_only=True),
        sdk.mcp_resource_contribution(
            uri="manifest", factory=plugin_manifest_resource,
            name="plugin-manifest", mime_type="application/json"),
    ]


__all__ = ["PLUGIN_ID", "blueprint_stats", "register"]
