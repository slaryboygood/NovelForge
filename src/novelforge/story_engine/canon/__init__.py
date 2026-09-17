"""Canon Infrastructure V1（C01 起）：稳定事实身份、依赖与规划层。

StoryState 仍是 happened facts 的 runtime truth；Canon 只承载身份与规划关系。
"""

from .ids import new_canon_id, new_random_key, validate_canon_id, validate_canonical_key
from .models import (
    CanonConstraint,
    CanonDependency,
    CanonEntity,
    CanonEvent,
    CanonFact,
    CanonForeshadow,
    CanonKnowledge,
    CanonRelationship,
    CanonRenderRef,
    CanonSourceMapping,
    CanonSourceRef,
    CanonVersion,
)
from .schemas import (
    CanonProposal,
    CanonProposalBundle,
    ChapterPlan,
    EventProposal,
    KnowledgeProposal,
    NarrativeBeat,
    SceneGroup,
)

__all__ = [
    "CanonConstraint", "CanonDependency", "CanonEntity", "CanonEvent", "CanonFact",
    "CanonForeshadow", "CanonKnowledge", "CanonRelationship", "CanonRenderRef",
    "CanonSourceMapping", "CanonSourceRef", "CanonVersion",
    "CanonProposal", "CanonProposalBundle", "ChapterPlan", "EventProposal",
    "KnowledgeProposal", "NarrativeBeat", "SceneGroup",
    "new_canon_id", "new_random_key", "validate_canon_id", "validate_canonical_key",
]
