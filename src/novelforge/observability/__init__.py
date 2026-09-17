"""Observability（V4-02 起）。

只包含当前阶段真正需要的最小能力；**不**提前创建 metrics / dashboard / audit platform /
cost dashboard 空壳（见 V4-02 任务书 §19）。
"""

from .model_trace import InMemoryModelTraceStore, JsonlModelTraceStore

__all__ = ["InMemoryModelTraceStore", "JsonlModelTraceStore"]

