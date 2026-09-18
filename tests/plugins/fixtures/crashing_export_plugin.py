"""导出的运行期崩溃插件（V4-09 §98）：验证 Core 与其它插件不受影响。"""

from novelforge.plugins import sdk


def render(context):  # noqa: ARG001 - 故意抛错
    raise RuntimeError("exporter crash（测试用）")


def register(context):
    return [sdk.exporter_contribution(
        exporter_id="crasher", format="crash", mime_type="text/plain",
        extension="crash", factory=render)]


__all__ = ["register"]
