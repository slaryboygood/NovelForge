"""测试用 exporter 插件（V4-09 §68、§95）：只依赖 plugin SDK + stdlib。"""

from novelforge.plugins import sdk


def render(context):
    """把已选定的交付内容渲染成简单文本（不做任何 selection / quality 决策）。"""

    blueprint = dict((context or {}).get("blueprint") or {})
    lines = [f"# plugin export（{blueprint.get('node_count', 0)} nodes）"]
    for row in blueprint.get("nodes") or []:
        visible = dict(row.get("visible") or {})
        title = visible.get("title") or visible.get("name") or row.get("node_type")
        lines.append(f"- {row.get('node_type')}: {title}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def register(context):
    return [sdk.exporter_contribution(
        exporter_id="text-list", format="tlist", mime_type="text/plain",
        extension="tlist", factory=render, version=1,
        profiles_supported=("reader", "author", "machine", "audit"))]


__all__ = ["register", "render"]
