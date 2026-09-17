"""LLM Writer 边界（V2-G）。

链路固定为：
StoryState → 引擎决定事件与结果 → WriterPackage（事实包）→ LLM 表现 → 事实校验 → 接受文本。
LLM 永远拿不到 StoryState 写入口；它返回的是结构化声明，由这里的校验层比对事实后才决定是否接受。
"""

from __future__ import annotations

from typing import Any, Callable, Literal

from pydantic import Field

from novelforge.models import StrictModel

from .actions import ActionCatalog
from .conditions import evaluate
from .events import EventCard, EventCardCatalog
from .memory import open_foreshadows, unresolved_conflicts
from .state import StoryState

ClaimKind = Literal["resource", "knowledge", "ability", "identity", "location", "relationship",
                    "history", "fact"]


class CharacterContext(StrictModel):
    """单个角色可见的上下文：只包含该角色合法知道与拥有的内容。"""

    character_id: str
    name: str = ""
    status: str = ""
    goals: list[str] = Field(default_factory=list)
    knowledge: list[str] = Field(default_factory=list)
    resources: dict[str, float] = Field(default_factory=dict)
    abilities: list[str] = Field(default_factory=list)
    identities: list[str] = Field(default_factory=list)
    relationships: dict[str, dict[str, float]] = Field(default_factory=dict)


class WriterPackage(StrictModel):
    event_id: str = ""
    time: dict[str, Any] = Field(default_factory=dict)
    location: str = ""
    participants: list[str] = Field(default_factory=list)
    characters: dict[str, CharacterContext] = Field(default_factory=dict)
    facts: list[str] = Field(default_factory=list)
    required_results: list[str] = Field(default_factory=list)
    forbidden: list[str] = Field(default_factory=list)
    creative_space: list[str] = Field(default_factory=list)
    history_digest: list[str] = Field(default_factory=list)
    occurred_events: list[str] = Field(default_factory=list)
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    foreshadows: list[dict[str, Any]] = Field(default_factory=list)
    style: dict[str, str] = Field(default_factory=dict)
    author_notes: list[str] = Field(default_factory=list)
    reader_visible: list[str] = Field(default_factory=list)
    # P2-08：明确区分“已知事实”“可自由创作”“属于长期人物事实、不得凭空新增”。
    known_facts: list[str] = Field(default_factory=list)
    creative_details: list[str] = Field(default_factory=list)
    persistent_character_facts: list[dict[str, Any]] = Field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def build_writer_package(state: StoryState, card: EventCard | None = None, *,
                         required_results: list[str] | None = None,
                         style: dict[str, str] | None = None) -> WriterPackage:
    """把 StoryState 投影成结构化事实包；按角色做知识隔离。"""

    participants = list(card.participants) if card else list(state.characters)
    characters: dict[str, CharacterContext] = {}
    for character_id in participants:
        entry = state.characters.get(character_id)
        if entry is None:
            continue
        relationships = {item.target_id: dict(item.dimensions)
                         for item in state.relationships if item.source_id == character_id}
        characters[character_id] = CharacterContext(
            character_id=character_id, name=entry.name, status=entry.status,
            goals=[str(item.title) for item in _goals(state, character_id)],
            knowledge=[item.id for item in state.knowledge if character_id in item.holders],
            resources={key: value.amount for key, value in state.resources.items()
                       if not value.holders or character_id in value.holders},
            abilities=sorted(item for item in state.abilities if _ability_owned(state, item, character_id)),
            identities=list(state.identities.get(character_id, [])),
            relationships=relationships)
    history = [f"{record.target}:{str((record.data or {}).get('result', ''))[:40]}"
               for record in state.effect_log if record.op in ("choice", "world_action", "world_event")][-5:]
    author_notes = [f"作者计划（未发生）：{item.id}" for item in state.author_knowledge]
    return WriterPackage(
        event_id=card.event_id if card else "",
        time={"tick": state.timeline.tick, "current_time": state.timeline.current_time,
              "markers": list(state.timeline.markers)},
        location=state.location.current, participants=participants, characters=characters,
        facts=[item.id for item in state.knowledge if item.certainty == "fact"],
        required_results=list(required_results or (card.scene_goal and [card.scene_goal] or [])
                              if card is not None else (required_results or [])),
        forbidden=["不得让角色知道未获得的知识", "不得凭空增加资源、能力或身份",
                   "不得改写已发生事实", "不得把作者计划写成既成事实",
                   "不得让角色出现在不可能的地点", "不得复活已死亡的参与者"],
        creative_space=["对白措辞", "动作细节", "场景描写", "节奏与修辞", "次要气氛"],
        history_digest=history, conflicts=[item.model_dump(mode="json") for item in unresolved_conflicts(state)],
        occurred_events=sorted({str(record.target) for record in state.effect_log
                                if record.op in ("fire_event", "world_event") and record.target}),
        foreshadows=[{"id": item.id, "status": item.status} for item in open_foreshadows([])],
        style=dict(style or {}), author_notes=author_notes,
        reader_visible=[item.id for item in state.knowledge if item.reader_visible],
        known_facts=sorted({item.id for item in state.knowledge if item.certainty == "fact"}),
        creative_details=["神态", "临时动作", "环境细节", "非事实性修辞", "不产生长期约束的对白措辞"],
        persistent_character_facts=_persistent_character_facts(state))


def _persistent_character_facts(state: StoryState) -> list[dict[str, Any]]:
    """长期人物事实：来自角色 data 里的显式声明，未声明的不得由 LLM 自行补齐。"""

    rows: list[dict[str, Any]] = []
    for character_id, entry in sorted(state.characters.items()):
        data = dict(entry.data or {})
        declared = {key: data[key] for key in
                    ("age", "birthplace", "family", "appearance", "past", "habits", "injuries",
                     "role")
                    if data.get(key)}
        rows.append({"character_id": character_id, "name": entry.name,
                     "declared": declared, "identities": list(state.identities.get(character_id, []))})
    return rows


def foreshadow_runtime_status(state: StoryState, foreshadow_id: str) -> str:
    """伏笔的运行时状态：优先取 StoryState.flags 里的记录，没有则回落内容包定义。"""

    registry = state.flags.get("foreshadows", {}) or {}
    entry = registry.get(foreshadow_id) if isinstance(registry, dict) else None
    return str((entry or {}).get("status", "") or "")


def _goals(state: StoryState, character_id: str) -> list[Any]:
    from .characters import active_goals

    return active_goals(state, character_id)


def _ability_owned(state: StoryState, ability_id: str, character_id: str) -> bool:
    entry = state.abilities.get(ability_id)
    if entry is None:
        return False
    holders = entry.data.get("holders")
    return not holders or character_id in holders


class WriterClaim(StrictModel):
    kind: ClaimKind
    id: str = ""
    holder: str = ""
    value: Any = None
    note: str = ""


class WriterOutput(StrictModel):
    narration: str = ""
    claims: list[WriterClaim] = Field(default_factory=list)
    proposed_actions: list[str] = Field(default_factory=list)
    proposed_events: list[str] = Field(default_factory=list)
    dialogue_hints: list[str] = Field(default_factory=list)
    # P2-08：正文里新出现的“长期人物事实”（年龄、身世、亲属、固定外貌、出生地、
    # 过去经历、身份、能力、长期习惯/伤病、重要装备与关系）。这些不写进 StoryState，
    # 只作为待作者确认的提议返回，避免 LLM 悄悄给人物加设定。
    proposed_new_facts: list[dict[str, Any]] = Field(default_factory=list)


class ValidationResult(StrictModel):
    accepted: bool
    problems: list[str] = Field(default_factory=list)
    dropped_actions: list[dict[str, Any]] = Field(default_factory=list)
    dropped_events: list[dict[str, Any]] = Field(default_factory=list)
    accepted_actions: list[str] = Field(default_factory=list)
    accepted_events: list[str] = Field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def validate_writer_output(state: StoryState, package: WriterPackage, output: WriterOutput, *,
                           catalog: ActionCatalog | None = None,
                           event_catalog: EventCardCatalog | None = None,
                           actor: str = "") -> ValidationResult:
    """结构化事实校验：把声明与 StoryState / WriterPackage 逐条比对。"""

    problems: list[str] = []
    # P2-08：长期人物事实（年龄 / 身世 / 亲属 / 固定外貌 / 出生地 / 过去经历 / 长期习惯 /
    # 长期伤病）只能作为提议返回，由作者确认后才能进入长期事实；这里只做“声明格式”校验，
    # 不解析正文、不使用关键词黑名单。
    for proposal in output.proposed_new_facts:
        if not isinstance(proposal, dict) or not proposal.get("character_id"):
            problems.append("PERSISTENT_DETAIL_INVALID：proposed_new_facts 需要 character_id 与 detail")
    for claim in output.claims:
        holder = claim.holder or actor
        context = package.characters.get(holder)
        if claim.kind == "resource":
            stock = state.resources.get(claim.id)
            current = stock.amount if stock else 0.0
            if claim.value is not None and float(claim.value) != float(current):
                problems.append(f"RESOURCE_MISMATCH：{claim.id} 声明 {claim.value}，实际 {current}")
        elif claim.kind == "knowledge":
            legal = set(context.knowledge) if context else set()
            if claim.id not in legal:
                problems.append(f"KNOWLEDGE_LEAK：{holder} 不可能知道 {claim.id}")
        elif claim.kind == "ability":
            legal = set(context.abilities) if context else set()
            if claim.id not in legal:
                problems.append(f"ABILITY_NOT_OWNED：{holder} 没有 {claim.id}")
        elif claim.kind == "identity":
            legal = set(context.identities) if context else set()
            if claim.id not in legal:
                problems.append(f"IDENTITY_MISMATCH：{holder} 没有身份 {claim.id}")
        elif claim.kind == "location":
            claimed = str(claim.value or claim.id)
            current = state.location.known.get(package.location)
            # 地点既可以用 id 声明，也可以用 StoryState 里的显示名声明。
            legal_names = {package.location, current.name if current is not None else ""}
            if claimed not in legal_names:
                problems.append(f"LOCATION_MISMATCH：场景在 {package.location}，被写到 {claimed}")
        elif claim.kind == "relationship":
            dimensions = dict(context.relationships.get(claim.id, {})) if context else {}
            related_id = claim.id
            if context is not None and claim.id not in context.relationships:
                # 允许把维度名写在 id 上（例如 id="hostility"）：反查真正持有该维度的对象。
                for target, dims in context.relationships.items():
                    if claim.id in dims:
                        dimensions = dict(dims)
                        related_id = target
                        break
            legal_values = set(dimensions)
            legal_values.update(str(value) for value in dimensions.values())
            legal_values.add(claim.id)
            legal_values.add(related_id)
            target_entry = state.characters.get(related_id)
            if target_entry is not None:
                legal_values.add(target_entry.name or related_id)
            # 关系阶段写在 RelationshipState.data["stage"]，也允许声明。
            for item in state.relationships:
                if item.source_id == holder and item.target_id == related_id:
                    stage = str(item.data.get("stage", "") or "")
                    if stage:
                        legal_values.add(stage)
            if claim.note and claim.note not in legal_values:
                problems.append(f"RELATIONSHIP_UNKNOWN：{holder} 与 {related_id} 没有 {claim.note} 这类关系事实")
        elif claim.kind == "history":
            if (claim.id not in package.history_digest
                    and claim.id not in package.occurred_events
                    and claim.id not in state.legacy.get("history_ids", [])):
                problems.append(f"HISTORY_REWRITE：{claim.id} 不在已发生历史中")
        elif claim.kind == "fact":
            if claim.id not in package.facts and claim.id not in package.reader_visible:
                if claim.id in {item.id for item in state.author_knowledge}:
                    problems.append(f"PLAN_AS_FACT：{claim.id} 仍是作者计划，尚未发生")
                else:
                    problems.append(f"FACT_UNKNOWN：{claim.id} 不是已确认事实")

    accepted_actions: list[str] = []
    dropped_actions: list[dict[str, Any]] = []
    for action_id in output.proposed_actions:
        if catalog is None:
            dropped_actions.append({"action": action_id, "code": "NO_CATALOG"})
            continue
        try:
            action = catalog.by_id(action_id)
        except KeyError:
            dropped_actions.append({"action": action_id, "code": "ACTION_NOT_REGISTERED"})
            continue
        failed = next((item for item in action.requirements
                       if not evaluate(item, state, actor=actor).ok), None)
        if failed is not None:
            dropped_actions.append({"action": action_id, "code": "REQUIREMENT_NOT_SATISFIED"})
            continue
        accepted_actions.append(action_id)

    accepted_events: list[str] = []
    dropped_events: list[dict[str, Any]] = []
    for event_id in output.proposed_events:
        if event_catalog is None or all(card.event_id != event_id for card in event_catalog.cards):
            dropped_events.append({"event": event_id, "code": "EVENT_NOT_REGISTERED"})
            continue
        accepted_events.append(event_id)
    return ValidationResult(accepted=not problems, problems=problems,
                            dropped_actions=dropped_actions, dropped_events=dropped_events,
                            accepted_actions=accepted_actions, accepted_events=accepted_events)


class WriterResult(StrictModel):
    text: str
    accepted: bool
    fallback_used: bool = False
    problems: list[str] = Field(default_factory=list)
    validation: ValidationResult | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"text": self.text, "accepted": self.accepted, "fallback_used": self.fallback_used,
                "problems": list(self.problems),
                "validation": self.validation.model_dump(mode="json") if self.validation else None}


def fallback_text(package: WriterPackage) -> str:
    """LLM 不可用时的确定性最小表现，不改变任何事实。"""

    participants = "、".join(package.characters[key].name or key for key in package.characters) or "在场角色"
    goal = package.required_results[0] if package.required_results else "推进当前目标"
    return f"（降级表现）{participants} 在{package.location or '当前地点'}继续行动，目标是{goal}。"


def render_scene(state: StoryState, package: WriterPackage,
                 generator: Callable[[WriterPackage], WriterOutput] | None = None, *,
                 catalog: ActionCatalog | None = None,
                 event_catalog: EventCardCatalog | None = None, actor: str = "") -> WriterResult:
    """完整链路：生成 → 校验 → 接受或降级；任何一步失败都不会丢状态。"""

    if generator is None:
        return WriterResult(text=fallback_text(package), accepted=False, fallback_used=True,
                            problems=["LLM_UNAVAILABLE"])
    try:
        output = generator(package)
    except Exception as exc:  # noqa: BLE001 - LLM 任何异常都走降级
        return WriterResult(text=fallback_text(package), accepted=False, fallback_used=True,
                            problems=[f"LLM_ERROR：{exc}"])
    if not isinstance(output, WriterOutput):
        return WriterResult(text=fallback_text(package), accepted=False, fallback_used=True,
                            problems=["LLM_OUTPUT_INVALID"])
    validation = validate_writer_output(state, package, output, catalog=catalog,
                                        event_catalog=event_catalog, actor=actor)
    if not validation.accepted or not output.narration.strip():
        return WriterResult(text=fallback_text(package), accepted=False, fallback_used=True,
                            problems=validation.problems or ["LLM_OUTPUT_EMPTY"], validation=validation)
    return WriterResult(text=output.narration, accepted=True, validation=validation)
