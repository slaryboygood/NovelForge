"""错误信息泄漏测试插件（V4-09 §58、§100）。

故意在异常信息里带上本机绝对路径与 secret 形态的 token；
Host 记录 / 回传时必须净化（不得带出绝对路径或 secret）。
"""

from novelforge.plugins import sdk

LEAKY_MESSAGE = (
    "载入失败：C:\\Users\\alice\\secrets\\provider_config.json "
    "（api_key=sk-live-0123456789abcdef）")


def render(context):  # noqa: ARG001
    raise RuntimeError(LEAKY_MESSAGE)


def register(context):
    return [sdk.exporter_contribution(
        exporter_id="leaky", format="leaky", mime_type="text/plain",
        extension="leaky", factory=render)]


__all__ = ["LEAKY_MESSAGE", "register", "render"]
