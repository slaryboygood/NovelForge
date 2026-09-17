"""S04：ChapterIRBuilder —— 两个入口。

A. 新 Canon-aware Planner 直接产 IR（调用方给结构化输入）
B. legacy chapter → provisional IR（Pilot 用这个）
"""

from __future__ import annotations

from typing import Any, Mapping

from .migration import LegacyChapterMigration
from .models import ChapterSemanticIR


class ChapterIRBuilder:
    def __init__(self, *, novel_id: str, dog_id: str = "", dog_name: str = "阿灰",
                 protagonist_id: str = "", actor_names: dict[str, str] | None = None) -> None:
        self.migration = LegacyChapterMigration(
            novel_id=novel_id, dog_id=dog_id, dog_name=dog_name,
            protagonist_id=protagonist_id, actor_names=actor_names)

    def from_legacy(self, chapter: Mapping[str, Any], *,
                    name_to_id: dict[str, str] | None = None,
                    index: int = 0) -> ChapterSemanticIR:
        return self.migration.migrate(chapter, name_to_id=name_to_id, index=index)

    def from_planner(self, payload: Mapping[str, Any]) -> ChapterSemanticIR:
        """Planner 直接产 IR：payload 必须是 IR 结构（仍需过严格 gate）。"""

        return ChapterSemanticIR.model_validate(dict(payload), strict=True)
