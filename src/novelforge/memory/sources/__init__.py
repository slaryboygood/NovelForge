"""Memory source adapters（只读 canonical artifacts）。

边界：只允许读 domain 的 Public API 与 `persistence.paths`（§12）：
不得自行拼路径、不得扫描磁盘推断当前作品、不得 fallback 到其他作品。
"""

from .canon import CanonMemorySource
from .story_state import StoryStateMemorySource

__all__ = ["CanonMemorySource", "StoryStateMemorySource"]

