"""NovelForge `story_engine` —— **current domain 层**（post-release cleanup 后）。

保留的真实 current 能力（V4）：

```text
entities / state / storage    StoryState 模型与 canonical store（memory 读它）
profile                       NovelProfile + canonical store
context                       NovelContext（只读读取上下文，取代 V2 creator）
templates                     作品模板与 profile 装配（apply_template）
canon/**                      Canon Infrastructure（身份 / 依赖 / 校验 / 规划）
chapter_ir/{models,function_policy}   frozen Repair 实现的依赖（frozen slice）
repair                        frozen M10/M11 Repair Contract 实现（只读历史）
```

已退休（V4 post-release cleanup）：模拟运行时（driver / effects / events /
foreshadow / progression / journey）、V2 视图（*_view）、route_lab、
outline_forge / outline_revision、planning/**、spec/**、chapter IR 提取与校验、
creative / settings_gen / settings_check、historical_ir / reconstruction /
historical_adoption / phase_snapshot / milestone_acceptance、writer。
历史证据由 Git 与 `docs/FROZEN_EVIDENCE_MANIFEST.json` 承担。
"""

from .canon import (
    CanonConstraint,
    CanonDependency,
    CanonEntity,
    CanonEvent,
    CanonFact,
    CanonForeshadow,
    CanonKnowledge,
    CanonProposal,
    CanonProposalBundle,
    CanonRelationship,
    CanonRenderRef,
    CanonSourceMapping,
    CanonSourceRef,
    CanonVersion,
    ChapterPlan,
    EventProposal,
    KnowledgeProposal,
    NarrativeBeat,
    SceneGroup,
    new_canon_id,
    new_random_key,
    validate_canon_id,
    validate_canonical_key,
)
from .context import (
    DEFAULT_BRANCH,
    NovelContext,
    NovelContextError,
    RUNTIME_VERSION,
    resolve_novel_context,
    runtime_key_for,
    story_state_preview,
    without_preview_flag,
)
from .entities import (
    Ability,
    Character,
    EffectRecord,
    Faction,
    KnowledgeEntry,
    Location,
    PromiseState,
    RelationshipState,
    ResourceDefinition,
    ResourceStock,
    StateEntry,
)
from .profile import (
    DEFAULT_NOVEL_ID,
    NOVEL_PROFILE_SCHEMA_VERSION,
    NovelProfile,
    NovelProfileError,
    NovelProfileRepository,
    StoredNovelProfile,
)
from .state import (
    STORY_STATE_SCHEMA_VERSION,
    LocationState,
    StoryState,
    StoryStateError,
    TimelineState,
    WorldState,
    from_legacy_adventure,
    story_state_from_payload,
    upgrade_story_state_payload,
)
from .storage import (
    StoredStoryState,
    StoryStateRepository,
    StoryStateStorageError,
)
from .templates import (
    GenreTemplate,
    GenreTemplateError,
    apply_template,
    get_template,
    list_templates,
)

__all__ = [
    # canon
    "CanonConstraint", "CanonDependency", "CanonEntity", "CanonEvent", "CanonFact",
    "CanonForeshadow", "CanonKnowledge", "CanonProposal", "CanonProposalBundle",
    "CanonRelationship", "CanonRenderRef", "CanonSourceMapping", "CanonSourceRef",
    "CanonVersion", "ChapterPlan", "EventProposal", "KnowledgeProposal",
    "NarrativeBeat", "SceneGroup", "new_canon_id", "new_random_key",
    "validate_canon_id", "validate_canonical_key",
    # context
    "DEFAULT_BRANCH", "NovelContext", "NovelContextError", "RUNTIME_VERSION",
    "resolve_novel_context", "runtime_key_for", "story_state_preview",
    "without_preview_flag",
    # entities / state / storage
    "Ability", "Character", "EffectRecord", "Faction", "KnowledgeEntry", "Location",
    "PromiseState", "RelationshipState", "ResourceDefinition", "ResourceStock",
    "StateEntry",
    "STORY_STATE_SCHEMA_VERSION", "LocationState", "StoryState", "StoryStateError",
    "TimelineState", "WorldState", "from_legacy_adventure",
    "story_state_from_payload", "upgrade_story_state_payload",
    "StoredStoryState", "StoryStateRepository", "StoryStateStorageError",
    # profile / templates
    "DEFAULT_NOVEL_ID", "NOVEL_PROFILE_SCHEMA_VERSION", "NovelProfile",
    "NovelProfileError", "NovelProfileRepository", "StoredNovelProfile",
    "GenreTemplate", "GenreTemplateError", "apply_template", "get_template",
    "list_templates",
]
