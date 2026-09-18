"""加载即失败的插件（V4-09 §19、§98）：用于验证失败隔离。"""


def register(context):  # noqa: ARG001 - 故意抛错
    raise RuntimeError("boom: 插件初始化失败（测试用）")


__all__ = ["register"]
