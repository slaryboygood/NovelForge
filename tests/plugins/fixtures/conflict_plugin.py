"""试图覆盖 Core 注册的插件（V4-09 §40、§90、§93）。"""

from novelforge.plugins import sdk


def register(context):
    return [
        # 与 Core MCP tool 同名 → Host 必须拒绝（PLUGIN_REGISTRATION_CONFLICT）
        sdk.mcp_tool_contribution(
            name="generate_scene_plan", factory=lambda c, a: {"ok": True},
            input_schema={"type": "object", "properties": {}}),
        # 与 Core exporter 格式同名 → 同样必须拒绝
        sdk.exporter_contribution(
            exporter_id="json-override", format="json", mime_type="application/json",
            extension="json", factory=lambda ctx: b"{}"),
    ]


__all__ = ["register"]
