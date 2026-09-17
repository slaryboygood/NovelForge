"""M2B：Planning → Canon / StoryState 的**提案**（proposal），不直接写任何 truth。

- `CanonBootstrapProposal`：小说开始前已经确认存在的稳定事实候选
  （confirmed world hard rule / character identity / starting relationship / location）。
  未来 PlotNode 绝不 bootstrap 成 happened Canon。
- `StoryStateInitProposal`：故事开场时已经成立的初始状态。
  不包含未来 Volume / PlotNode / 成长 / 关系变化；库存永远为空（只能由事件写入）。

两个 proposal 都必须经过正式 service 才能应用（`require_confirmation=True`、
`applied=False` 是模型上的硬标记）。
"""

from __future__ import annotations

from typing import Any, Iterable, Literal

from pydantic import Field

from novelforge.models import StrictModel

from .models import StoryPlanningIR
from .versioning import planning_digest

BASELINE_RULE_TYPES: tuple[str, ...] = ("hard_rule", "soft_rule")
FUTURE_COLLECTIONS: tuple[str, ...] = (
    "plot_nodes", "spines", "volumes", "arcs", "information_moves", "foreshadow_moves",
    "progression_milestones", "relationship_stages",
)


class PlanningProposalError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


class BootstrapEntity(StrictModel):
    entity_ref: str = Field(default="", max_length=160)
    kind: str = Field(default="character", max_length=32)
    display_name: str = Field(default="", max_length=120)
    source_planning_id: str = Field(default="", max_length=64)
    provenance: str = Field(default="supplied", max_length=32)


class BootstrapFact(StrictModel):
    statement: str = Field(default="", max_length=400)
    category: str = Field(default="world_rule", max_length=32)
    rule_type: str = Field(default="hard_rule", max_length=32)
    source_planning_id: str = Field(default="", max_length=64)
    provenance: str = Field(default="supplied", max_length=32)


class BootstrapRelationship(StrictModel):
    participants: list[str] = Field(default_factory=list)
    kind: str = Field(default="relationship", max_length=64)
    state: str = Field(default="", max_length=300)
    source_planning_id: str = Field(default="", max_length=64)


class BootstrapLocation(StrictModel):
    location_ref: str = Field(default="", max_length=160)
    display_name: str = Field(default="", max_length=120)
    parent_region: str = Field(default="", max_length=64)
    source_planning_id: str = Field(default="", max_length=64)


class CanonBootstrapProposal(StrictModel):
    proposal_id: str = Field(default="", max_length=64)
    novel_id: str = Field(default="", max_length=96)
    planning_id: str = Field(default="", max_length=64)
    planning_revision_id: str = Field(default="", max_length=64)
    content_digest: str = Field(default="", max_length=64)
    entities: list[BootstrapEntity] = Field(default_factory=list)
    facts: list[BootstrapFact] = Field(default_factory=list)
    relationships: list[BootstrapRelationship] = Field(default_factory=list)
    locations: list[BootstrapLocation] = Field(default_factory=list)
    excluded_non_baseline: list[str] = Field(default_factory=list)
    future_refs_excluded: list[str] = Field(default_factory=list)
    require_confirmation: Literal[True] = True
    applied: Literal[False] = False
    note: str = Field(default="", max_length=300)


class StoryStateCharacterInit(StrictModel):
    character_id: str = Field(default="", max_length=64)
    entity_ref: str = Field(default="", max_length=160)
    location_id: str = Field(default="", max_length=64)
    status: str = Field(default="", max_length=200)


class StoryStateKnowledgeInit(StrictModel):
    truth_id: str = Field(default="", max_length=64)
    holder_ids: list[str] = Field(default_factory=list)
    certainty: str = Field(default="fact", max_length=16)


class StoryStateInitProposal(StrictModel):
    proposal_id: str = Field(default="", max_length=64)
    novel_id: str = Field(default="", max_length=96)
    planning_id: str = Field(default="", max_length=64)
    planning_revision_id: str = Field(default="", max_length=64)
    content_digest: str = Field(default="", max_length=64)
    opened_at_node_id: str = Field(default="", max_length=64)
    characters: list[StoryStateCharacterInit] = Field(default_factory=list)
    location_ids: list[str] = Field(default_factory=list)
    world_state: dict[str, str] = Field(default_factory=dict)
    knowledge: list[StoryStateKnowledgeInit] = Field(default_factory=list)
    resources: list[str] = Field(default_factory=list)
    future_refs_excluded: list[str] = Field(default_factory=list)
    require_confirmation: Literal[True] = True
    applied: Literal[False] = False
    note: str = Field(default="", max_length=300)


def build_canon_bootstrap_proposal(plan: StoryPlanningIR, *, revision_id: str = "",
                                   include_ids: Iterable[str] = (),
                                   require_confirmed: bool = False
                                   ) -> CanonBootstrapProposal:
    """只把"开场前已经确认存在"的稳定事实做成候选；未来内容显式排除。"""

    wanted = set(include_ids)
    allowed = ("confirmed",) if require_confirmed else ("supplied", "confirmed")
    excluded: list[str] = []
    entities: list[BootstrapEntity] = []
    for character in plan.characters:
        if wanted and character.character_id not in wanted:
            continue
        if character.provenance not in allowed or not (character.entity_ref
                                                       or character.display_name):
            excluded.append(character.character_id)
            continue
        entities.append(BootstrapEntity(entity_ref=character.entity_ref or character.display_name,
                                        kind="character", display_name=character.display_name,
                                        source_planning_id=character.character_id,
                                        provenance=character.provenance))
    for faction in plan.factions:
        if wanted and faction.faction_id not in wanted:
            continue
        if faction.provenance not in allowed or not (faction.entity_ref
                                                     or faction.display_name):
            excluded.append(faction.faction_id)
            continue
        entities.append(BootstrapEntity(entity_ref=faction.entity_ref or faction.display_name,
                                        kind="faction", display_name=faction.display_name,
                                        source_planning_id=faction.faction_id,
                                        provenance=faction.provenance))
    facts: list[BootstrapFact] = []
    for rule in (plan.world.world_rules if plan.world else []):
        if rule.rule_type not in BASELINE_RULE_TYPES:
            excluded.append(rule.rule_id)
            continue
        if rule.provenance not in allowed:
            excluded.append(rule.rule_id)
            continue
        facts.append(BootstrapFact(statement=rule.statement, category="world_rule",
                                   rule_type=rule.rule_type, source_planning_id=rule.rule_id,
                                   provenance=rule.provenance))
    relationships = [BootstrapRelationship(participants=list(arc.participants),
                                           state=arc.start_state,
                                           source_planning_id=arc.arc_id)
                     for arc in plan.relationship_arcs if arc.start_state]
    locations = [BootstrapLocation(location_ref=item.entity_ref or item.display_name,
                                   display_name=item.display_name,
                                   parent_region=item.parent_region,
                                   source_planning_id=item.location_id)
                 for item in plan.locations]
    proposal = CanonBootstrapProposal(
        proposal_id=f"PLANBOOT_{plan.planning_id or 'PLAN'}",
        novel_id=plan.novel_id, planning_id=plan.planning_id,
        planning_revision_id=revision_id, content_digest=planning_digest(plan),
        entities=entities, facts=facts, relationships=relationships, locations=locations,
        excluded_non_baseline=sorted(set(excluded)),
        future_refs_excluded=_future_ids(plan),
        note="bootstrap 只包含开场前已确认的稳定事实；应用必须走正式 Canon service。")
    assert_no_future_content("CanonBootstrapProposal", proposal.model_dump(mode="json"))
    return proposal


def build_story_state_init_proposal(plan: StoryPlanningIR, *, revision_id: str = "",
                                    opened_at_node_id: str = "",
                                    starting_location_ids: Iterable[str] = (),
                                    initial_world_state: dict[str, str] | None = None
                                    ) -> StoryStateInitProposal:
    """只做开场初始状态：不给库存、不写未来成长、不写未来关系变化。"""

    characters = [StoryStateCharacterInit(
        character_id=item.character_id, entity_ref=item.entity_ref,
        status=item.story_function)
        for item in plan.characters if item.entity_ref or item.display_name]
    knowledge: list[StoryStateKnowledgeInit] = []
    for arc in plan.information_arcs:
        moves = {move.truth_id: move.move_type for move in arc.moves}
        for truth in arc.truths:
            if moves.get(truth.truth_id) in ("plant", "reveal", "payoff"):
                continue  # 开场还没有获得这条信息
            holders = list(truth.character_knows) + list(truth.faction_knows)
            if truth.protagonist_knows:
                holders.append("ENTITY_PROTAGONIST")
            if holders:
                knowledge.append(StoryStateKnowledgeInit(truth_id=truth.truth_id,
                                                         holder_ids=sorted(set(holders))))
    proposal = StoryStateInitProposal(
        proposal_id=f"PLANINIT_{plan.planning_id or 'PLAN'}",
        novel_id=plan.novel_id, planning_id=plan.planning_id,
        planning_revision_id=revision_id, content_digest=planning_digest(plan),
        opened_at_node_id=opened_at_node_id,
        characters=characters, location_ids=sorted(set(starting_location_ids)),
        world_state=dict(initial_world_state or {}), knowledge=knowledge, resources=[],
        future_refs_excluded=_future_ids(plan),
        note="只包含故事开场已经成立的初始状态；库存为空，正式应用必须走 StoryState service。")
    assert_no_future_content("StoryStateInitProposal", proposal.model_dump(mode="json"))
    return proposal


def _future_ids(plan: StoryPlanningIR) -> list[str]:
    rows = [node.node_id for node in plan.plot_nodes]
    rows += [volume.volume_id for volume in plan.volumes]
    rows += [arc.arc_id for arc in plan.arcs]
    rows += [move.move_id for arc in plan.information_arcs for move in arc.moves]
    rows += [move.move_id for item in plan.foreshadow_plans for move in item.moves]
    rows += [item.milestone_id for track in plan.progression_tracks
             for item in track.milestones]
    return sorted(rows)


def assert_no_future_content(label: str, payload: dict[str, Any]) -> None:
    """结构护栏：proposal 里不允许出现未来集合。"""

    for key in FUTURE_COLLECTIONS:
        if payload.get(key):
            raise PlanningProposalError("FUTURE_IN_PROPOSAL",
                                        f"{label} 不允许包含未来内容：{key}")


__all__ = [
    "BASELINE_RULE_TYPES",
    "BootstrapEntity",
    "BootstrapFact",
    "BootstrapLocation",
    "BootstrapRelationship",
    "CanonBootstrapProposal",
    "FUTURE_COLLECTIONS",
    "PlanningProposalError",
    "StoryStateCharacterInit",
    "StoryStateInitProposal",
    "StoryStateKnowledgeInit",
    "assert_no_future_content",
    "build_canon_bootstrap_proposal",
    "build_story_state_init_proposal",
]
