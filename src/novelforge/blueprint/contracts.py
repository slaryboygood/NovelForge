"""Story Blueprint 节点契约（V4-04 §5–§10、§17–§28）。

Blueprint 不是"一个巨大 JSON blob"，而是**可独立 revision 的节点图**：

```text
   node_id / novel_id / node_type
   parent_id / revision / parent_revision
   status（proposed / draft / accepted / superseded）
   source_ids / context_digest / provenance
   created_at / updated_at / generation_contract(+version) / quality_status
```

节点 payload 用严格 pydantic 模型表达（模型只填内容，**ID 由系统分配**，§47）。
"""

from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass, field
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field

#: Blueprint schema 版本（§32：以后 V4-05 / MCP / Export 都依赖）
BLUEPRINT_SCHEMA_VERSION = 1

NodeType = Literal[
    "premise", "theme", "world", "character", "character_arc", "story_arc",
    "structural_unit", "chapter", "scene", "causal_link", "setup", "payoff",
]

NodeStatus = Literal["proposed", "draft", "accepted", "superseded"]

SceneFunction = Literal[
    "advance_plot", "reveal_information", "escalate_conflict", "character_change",
    "relationship_change", "setup", "payoff", "decision", "reversal", "transition",
]

CausalRelation = Literal["causes", "enables", "blocks", "reveals", "motivates",
                         "pays_off"]

SetupStatus = Literal["open", "partially_paid", "paid", "abandoned"]

TransitionKind = Literal["knowledge", "relationship", "resource", "location",
                         "promise", "identity", "flag", "progression"]

#: 系统分配的 ID 前缀（§47：模型不得自造 id）
NODE_ID_PREFIX: dict[str, str] = {
    "premise": "premise",
    "theme": "theme",
    "world": "world",
    "character": "char",
    "character_arc": "arc",
    "story_arc": "story_arc",
    "structural_unit": "unit",
    "chapter": "ch",
    "scene": "sc",
    "causal_link": "cl",
    "setup": "setup",
    "payoff": "payoff",
}

_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")


def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def slug(text: str, *, limit: int = 24, fallback: str = "item") -> str:
    """把名称转成稳定 slug（系统分配 id 用）。"""

    ascii_part = re.sub(r"[^a-z0-9]+", "_", str(text or "").lower()).strip("_")
    if not ascii_part:
        return fallback
    return ascii_part[:limit].strip("_") or fallback


class StrictPayload(BaseModel):
    """节点 payload 基类：严格、禁止额外字段（V4 结构化生成的第一道门）。"""

    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------- payloads
class PremisePayload(StrictPayload):
    premise: str = Field(min_length=1, max_length=1000)
    central_conflict: str = Field(default="", max_length=600)
    protagonist_goal: str = Field(default="", max_length=600)
    stakes: str = Field(default="", max_length=600)
    dramatic_question: str = Field(default="", max_length=400)
    story_promise: str = Field(default="", max_length=600)
    genre: str = Field(default="", max_length=64)
    tone: str = Field(default="", max_length=64)
    constraints: list[str] = Field(default_factory=list, max_length=12)


class ThemePayload(StrictPayload):
    theme: str = Field(min_length=1, max_length=300)
    statement: str = Field(default="", max_length=600)
    counter_theme: str = Field(default="", max_length=600)
    motifs: list[str] = Field(default_factory=list, max_length=12)


class WorldPayload(StrictPayload):
    rules: list[str] = Field(default_factory=list, max_length=16)
    locations: list[dict[str, Any]] = Field(default_factory=list, max_length=40)
    factions: list[dict[str, Any]] = Field(default_factory=list, max_length=24)
    resources: list[str] = Field(default_factory=list, max_length=24)
    technology_or_magic: list[str] = Field(default_factory=list, max_length=16)
    social_constraints: list[str] = Field(default_factory=list, max_length=16)
    conflict_sources: list[str] = Field(default_factory=list, max_length=16)
    story_relevant_history: list[str] = Field(default_factory=list, max_length=16)


class CharacterPayload(StrictPayload):
    name: str = Field(min_length=1, max_length=80)
    role: str = Field(default="", max_length=80)
    kind: Literal["player", "npc", "faction", "other"] = "npc"
    goal: str = Field(default="", max_length=400)
    motivation: str = Field(default="", max_length=400)
    need: str = Field(default="", max_length=400)
    fear: str = Field(default="", max_length=400)
    misbelief: str = Field(default="", max_length=400)
    strength: str = Field(default="", max_length=400)
    flaw: str = Field(default="", max_length=400)
    conflict_source: str = Field(default="", max_length=400)
    relationships: list[dict[str, Any]] = Field(default_factory=list, max_length=16)
    story_function: str = Field(default="", max_length=400)
    constraints: list[str] = Field(default_factory=list, max_length=12)


class CharacterArcPayload(StrictPayload):
    character_id: str = Field(min_length=1, max_length=64)
    start_state: str = Field(default="", max_length=500)
    internal_conflict: str = Field(default="", max_length=500)
    external_pressure: str = Field(default="", max_length=500)
    key_turns: list[str] = Field(default_factory=list, max_length=12)
    midpoint_change: str = Field(default="", max_length=500)
    crisis: str = Field(default="", max_length=500)
    climax_choice: str = Field(default="", max_length=500)
    end_state: str = Field(default="", max_length=500)
    linked_chapters: list[str] = Field(default_factory=list, max_length=200)
    linked_scenes: list[str] = Field(default_factory=list, max_length=400)


class StoryArcPayload(StrictPayload):
    initial_state: str = Field(default="", max_length=600)
    inciting_incident: str = Field(default="", max_length=600)
    progressive_complications: list[str] = Field(default_factory=list, max_length=16)
    major_turns: list[str] = Field(default_factory=list, max_length=16)
    midpoint: str = Field(default="", max_length=600)
    crisis: str = Field(default="", max_length=600)
    climax: str = Field(default="", max_length=600)
    resolution: str = Field(default="", max_length=600)


class StructuralUnitPayload(StrictPayload):
    unit_type: Literal["act", "volume", "arc"]
    title: str = Field(min_length=1, max_length=120)
    goal: str = Field(default="", max_length=500)
    conflict: str = Field(default="", max_length=500)
    turn: str = Field(default="", max_length=500)
    outcome: str = Field(default="", max_length=500)
    child_units: list[str] = Field(default_factory=list, max_length=24)


class ChapterCardPayload(StrictPayload):
    title: str = Field(min_length=1, max_length=120)
    goal: str = Field(default="", max_length=500)
    pov: str = Field(default="", max_length=64)
    characters: list[str] = Field(default_factory=list, max_length=16)
    location: str = Field(default="", max_length=64)
    conflict: str = Field(default="", max_length=500)
    turn: str = Field(default="", max_length=500)
    outcome: str = Field(default="", max_length=500)
    hook: str = Field(default="", max_length=500)
    setup: list[str] = Field(default_factory=list, max_length=8)
    payoff: list[str] = Field(default_factory=list, max_length=8)
    state_change_intent: list[dict[str, Any]] = Field(default_factory=list, max_length=12)


class SceneCardPayload(StrictPayload):
    chapter_id: str = Field(default="", max_length=64)
    pov: str = Field(default="", max_length=64)
    location: str = Field(default="", max_length=64)
    time: str = Field(default="", max_length=64)
    scene_purpose: str = Field(min_length=1, max_length=500)
    character_goals: list[str] = Field(default_factory=list, max_length=12)
    conflict: str = Field(default="", max_length=500)
    escalation: str = Field(default="", max_length=500)
    turn: str = Field(default="", max_length=500)
    outcome: str = Field(default="", max_length=500)
    information_reveal: list[str] = Field(default_factory=list, max_length=12)
    character_change: str = Field(default="", max_length=500)
    relationship_change: str = Field(default="", max_length=500)
    setup: list[str] = Field(default_factory=list, max_length=8)
    payoff: list[str] = Field(default_factory=list, max_length=8)
    state_transition_intent: list[dict[str, Any]] = Field(default_factory=list,
                                                         max_length=12)
    next_hook: str = Field(default="", max_length=500)
    story_function: list[SceneFunction] = Field(default_factory=list, max_length=6)


class CausalLinkPayload(StrictPayload):
    source_node: str = Field(min_length=1, max_length=96)
    target_node: str = Field(min_length=1, max_length=96)
    relation: CausalRelation
    reason: str = Field(default="", max_length=500)


class SetupPayload(StrictPayload):
    content: str = Field(min_length=1, max_length=500)
    expected_payoff: str = Field(default="", max_length=500)
    status: SetupStatus = "open"


class PayoffPayload(StrictPayload):
    resolves_setup_ids: list[str] = Field(default_factory=list, max_length=8)
    result: str = Field(default="", max_length=500)
    status: Literal["planned", "paid", "abandoned"] = "planned"


PAYLOAD_MODELS: dict[str, type[BaseModel]] = {
    "premise": PremisePayload,
    "theme": ThemePayload,
    "world": WorldPayload,
    "character": CharacterPayload,
    "character_arc": CharacterArcPayload,
    "story_arc": StoryArcPayload,
    "structural_unit": StructuralUnitPayload,
    "chapter": ChapterCardPayload,
    "scene": SceneCardPayload,
    "causal_link": CausalLinkPayload,
    "setup": SetupPayload,
    "payoff": PayoffPayload,
}

#: 每类节点的合法父类型（None 表示允许为根；空集合表示不校验父类型）
ALLOWED_PARENT_TYPES: dict[str, tuple[str | None, ...]] = {
    "premise": (None,),
    "theme": (None,),
    "world": ("premise", None),
    "character": ("premise", "world", None),
    "character_arc": ("character",),
    "story_arc": ("premise", None),
    "structural_unit": ("story_arc", "structural_unit"),
    "chapter": ("structural_unit", "story_arc"),
    "scene": ("chapter",),
    "causal_link": ("story_arc", "structural_unit", "chapter", "scene", None),
    "setup": ("chapter", "scene", "structural_unit"),
    "payoff": ("chapter", "scene", "structural_unit"),
}


def validate_node_id(node_id: str) -> str:
    if not _ID_RE.match(str(node_id or "")):
        raise ValueError(f"blueprint node_id 非法：{node_id!r}")
    return str(node_id)


@dataclass(frozen=True)
class BlueprintNodeRef:
    node_id: str
    novel_id: str
    node_type: str
    revision: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {"node_id": self.node_id, "novel_id": self.novel_id,
                "node_type": self.node_type, "revision": self.revision}

    @property
    def ref(self) -> str:
        return f"{self.node_id}@{self.revision}"


@dataclass(frozen=True)
class BlueprintNode:
    """一个可独立 revision 的 Blueprint 节点（§9）。"""

    node_id: str
    novel_id: str
    node_type: str
    payload: Any
    parent_id: str = ""
    revision: int = 1
    parent_revision: int = 0
    status: NodeStatus = "proposed"
    source_ids: tuple[str, ...] = ()
    context_digest: str = ""
    created_at: str = ""
    updated_at: str = ""
    generation_contract: str = ""
    generation_contract_version: int = 0
    provenance: Mapping[str, Any] = field(default_factory=dict)
    quality_status: str = "unevaluated"
    schema_version: int = BLUEPRINT_SCHEMA_VERSION
    sequence: int = 0

    def __post_init__(self) -> None:
        validate_node_id(self.node_id)
        if not str(self.novel_id or "").strip():
            raise ValueError("BlueprintNode 需要显式 novel_id")
        if self.node_type not in PAYLOAD_MODELS:
            raise ValueError(f"未知 node_type：{self.node_type}")
        stamp = utc_now()
        if not self.created_at:
            object.__setattr__(self, "created_at", stamp)
        if not self.updated_at:
            object.__setattr__(self, "updated_at", stamp)
        if int(self.revision) < 1:
            raise ValueError("revision 必须 >= 1")

    @property
    def ref(self) -> BlueprintNodeRef:
        return BlueprintNodeRef(node_id=self.node_id, novel_id=self.novel_id,
                                node_type=self.node_type, revision=self.revision)

    def as_dict(self) -> dict[str, Any]:
        payload = (self.payload.as_dict() if hasattr(self.payload, "as_dict")
                   else (self.payload.model_dump(mode="json")
                         if isinstance(self.payload, BaseModel) else dict(self.payload)))
        return {"node_id": self.node_id, "novel_id": self.novel_id,
                "node_type": self.node_type, "parent_id": self.parent_id,
                "revision": self.revision, "parent_revision": self.parent_revision,
                "status": self.status, "sequence": self.sequence,
                "source_ids": list(self.source_ids),
                "context_digest": self.context_digest,
                "created_at": self.created_at, "updated_at": self.updated_at,
                "generation_contract": self.generation_contract,
                "generation_contract_version": self.generation_contract_version,
                "provenance": dict(self.provenance),
                "quality_status": self.quality_status,
                "schema_version": self.schema_version, "payload": payload}

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "BlueprintNode":
        node_type = str(raw.get("node_type") or "")
        model = PAYLOAD_MODELS.get(node_type)
        payload_raw = dict(raw.get("payload") or {})
        payload = model.model_validate(payload_raw) if model is not None else payload_raw
        return cls(node_id=str(raw.get("node_id") or ""),
                   novel_id=str(raw.get("novel_id") or ""),
                   node_type=node_type, payload=payload,
                   parent_id=str(raw.get("parent_id") or ""),
                   revision=int(raw.get("revision") or 1),
                   parent_revision=int(raw.get("parent_revision") or 0),
                   status=str(raw.get("status") or "proposed"),
                   source_ids=tuple(str(item) for item in (raw.get("source_ids") or [])),
                   context_digest=str(raw.get("context_digest") or ""),
                   created_at=str(raw.get("created_at") or ""),
                   updated_at=str(raw.get("updated_at") or ""),
                   generation_contract=str(raw.get("generation_contract") or ""),
                   generation_contract_version=int(
                       raw.get("generation_contract_version") or 0),
                   provenance=dict(raw.get("provenance") or {}),
                   quality_status=str(raw.get("quality_status") or "unevaluated"),
                   schema_version=int(raw.get("schema_version")
                                      or BLUEPRINT_SCHEMA_VERSION),
                   sequence=int(raw.get("sequence") or 0))


__all__ = [
    "ALLOWED_PARENT_TYPES", "BLUEPRINT_SCHEMA_VERSION", "BlueprintNode",
    "BlueprintNodeRef", "CausalLinkPayload", "CausalRelation", "ChapterCardPayload",
    "CharacterArcPayload", "CharacterPayload", "NODE_ID_PREFIX", "NodeStatus",
    "NodeType", "PAYLOAD_MODELS", "PayoffPayload", "PremisePayload", "SceneCardPayload",
    "SceneFunction", "SetupPayload", "SetupStatus", "StoryArcPayload",
    "StructuralUnitPayload", "StrictPayload", "ThemePayload", "TransitionKind",
    "WorldPayload", "slug", "utc_now", "validate_node_id",
]
