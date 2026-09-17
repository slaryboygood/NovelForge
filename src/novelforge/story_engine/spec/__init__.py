"""M3：NOVEL_SPEC V2 —— 一句话创意 → 规格 → 缺口 → 提案 → 作者确认 → Planning IR。

与四层 truth 的关系：

- NovelSpec / SpecProposal / SpecConfirmation 都是**作者输入与提案**，不是 truth；
- 编译产物是 Story Planning IR（future planning truth），必须过 Planning strict gate；
- M3 不生成 StorySpine / PlotNode / Volume / Arc（M6 / M8），也不写 Canon / StoryState。
"""

from .compiler import CONFIRMABLE_FIELDS, NovelSpecCompiler, SpecGateError
from .gaps import GAP_RULES, blocking_gaps, find_spec_gaps
from .llm import (
    LLMSpecProposalProvider,
    SpecProposalError,
    SpecProposalProvider,
    StaticSpecProposalProvider,
    build_spec_prompt,
    extract_proposal_payload,
    propose_spec,
)
from .models import (
    GapSeverity,
    NovelSpec,
    SPEC_ID_PREFIX,
    SpecCharacterSeed,
    SpecCompileResult,
    SpecConfirmation,
    SpecFactionSeed,
    SpecFieldProposal,
    SpecGap,
    SpecLocationSeed,
    SpecProposal,
    SpecWorldSeed,
    new_spec_id,
    spec_id,
)

__all__ = [
    "CONFIRMABLE_FIELDS",
    "GAP_RULES",
    "GapSeverity",
    "LLMSpecProposalProvider",
    "NovelSpec",
    "NovelSpecCompiler",
    "SPEC_ID_PREFIX",
    "SpecCharacterSeed",
    "SpecCompileResult",
    "SpecConfirmation",
    "SpecFactionSeed",
    "SpecFieldProposal",
    "SpecGap",
    "SpecGateError",
    "SpecLocationSeed",
    "SpecProposal",
    "SpecProposalError",
    "SpecProposalProvider",
    "SpecWorldSeed",
    "StaticSpecProposalProvider",
    "blocking_gaps",
    "build_spec_prompt",
    "extract_proposal_payload",
    "find_spec_gaps",
    "new_spec_id",
    "propose_spec",
    "spec_id",
]
