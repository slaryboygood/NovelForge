"""Provider 实现（V4-02）。

Provider SDK / HTTP client 只允许出现在本目录（`tests/v4/isolation/test_module_boundaries.py`
机械守卫）。上游只依赖 `novelforge.ai` 的 Public Contract。
"""

from .openai_compatible import OpenAICompatibleProvider, default_transport

__all__ = ["OpenAICompatibleProvider", "default_transport"]

