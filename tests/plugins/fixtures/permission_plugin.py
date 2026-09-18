"""权限越界插件（V4-09 §92）：manifest 只批准 delivery.export，贡献却要 ai.invoke。"""

from novelforge.plugins import sdk


class _Contribution:
    """故意伪造：contribution 要求的权限超出 manifest 声明。"""

    def __init__(self) -> None:
        self.inner = sdk.exporter_contribution(
            exporter_id="cheat", format="cheat", mime_type="text/plain",
            extension="cheat", factory=lambda ctx: b"cheat")

    def as_host_contribution(self):
        from dataclasses import replace        # stdlib only（§89）

        escalated = replace(self.inner, permissions_required=("ai.invoke",))
        return escalated.as_host_contribution()


def register(context):
    return [_Contribution()]


__all__ = ["register"]
