"""把 secret 形态内容写进交付物的插件（V4-09 §34、§100）。

Host 必须在 post-build / secret scan 阶段阻止发布 —— 插件不能绕过 DeliveryValidator。
"""

from novelforge.plugins import sdk


def render(context):  # noqa: ARG001 - 故意输出敏感内容
    return ("API_KEY=sk-live-0123456789abcdef\n"
            "Authorization: Bearer deadbeef\n").encode("utf-8")


def register(context):
    return [sdk.exporter_contribution(
        exporter_id="leaky-export", format="leak", mime_type="text/plain",
        extension="leak", text=True, factory=render)]


__all__ = ["register", "render"]
