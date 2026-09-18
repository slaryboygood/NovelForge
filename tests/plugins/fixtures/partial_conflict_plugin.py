"""原子注册测试插件（V4-09 §49）：第 1 个贡献合法，第 2 个与 Core 冲突。

要求：整个插件注册回滚 —— 第一个 exporter 不得留下（不得半激活）。
"""

from novelforge.plugins import sdk


def render(context):  # noqa: ARG001 - 原子性测试不关心内容
    return b"partial\n"


def register(context):
    return [
        # 合法：format 未被 Core 占用
        sdk.exporter_contribution(
            exporter_id="partial-poly", format="poly", mime_type="text/plain",
            extension="poly", factory=render),
        # 非法：与 Core MCP tool 同名 → 触发 PLUGIN_REGISTRATION_CONFLICT
        sdk.mcp_tool_contribution(
            name="generate_scene_plan", factory=lambda c, a: {"ok": True},
            input_schema={"type": "object", "properties": {}}),
    ]


__all__ = ["register", "render"]
