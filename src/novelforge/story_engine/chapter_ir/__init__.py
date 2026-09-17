"""Chapter Semantic IR V1（S01 起）：章节机器语义事实 + 字段编译。

三层严格区分：

- Canon：长程稳定事实（不可被 IR 覆盖）
- Chapter IR：某一章的叙事执行计划（结构即事实）
- StoryState：已发生 runtime truth

Writer-visible 文本只是 IR 的投影；文本不得反过来当事实源。
"""

from .models import (
    ChapterEffect,
    ChapterEventFrame,
    ChapterSemanticIR,
    ChapterStateTransition,
    CompiledChapter,
    DogRoleBinding,
    FieldEvidence,
    IRFlags,
)
from .state import TypedStateRegistry, default_registry

__all__ = [
    "ChapterEffect", "ChapterEventFrame", "ChapterSemanticIR", "ChapterStateTransition",
    "CompiledChapter", "DogRoleBinding", "FieldEvidence", "IRFlags",
    "TypedStateRegistry", "default_registry",
]
