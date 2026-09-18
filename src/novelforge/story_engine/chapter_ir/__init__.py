"""Chapter Semantic IR V1 —— **frozen slice**（post-release cleanup 保留部分）。

历史：Chapter IR（S01 起）曾包含 models / state / evidence / extractor / validator /
verifier / migration / compiler / builder / schemas 全套。V4 post-release cleanup 后，
只有 **frozen Repair Contract 实现**（`story_engine/repair.py`）仍然依赖
`FUNCTION_REQUIREMENTS`（ChapterFunctionPolicy，S10）与它引用的
`ChapterSemanticIR` 模型，因此仅保留这两块：

```text
chapter_ir/models.py           ChapterSemanticIR 等 IR 模型（frozen slice）
chapter_ir/function_policy.py  FUNCTION_REQUIREMENTS（S10 章节功能策略）
```

其余 chapter IR 能力（提取 / 校验 / 迁移 / 编译）随 570 章 historical 资产
一起退休；历史证据由 Git 与 `docs/FROZEN_EVIDENCE_MANIFEST.json` 承担。
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

__all__ = [
    "ChapterEffect", "ChapterEventFrame", "ChapterSemanticIR", "ChapterStateTransition",
    "CompiledChapter", "DogRoleBinding", "FieldEvidence", "IRFlags",
]
