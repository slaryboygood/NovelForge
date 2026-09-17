"""Journey Runtime：用内容包 + StoryState 渲染旅程场景（主计划 T08d-02）。

与旧 `adventures.py` 的分工对比：

- 旧实现：场景文案、选项、数值都写在 Python 里，事实态存在 Adventure 固定字段。
- 新实现：文案与选项来自 ContentPack，事实态是 StoryState，数值变化由 ActionResolver 执行。

引擎不认识任何题材或小说名词：`JourneyDesign` 只携带作者设计（选项快照），
`StoryState` 只携带事实，文本片段全部来自内容包。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import Field

from novelforge.models import StrictModel

from .content import ContentPack
from .conditions import evaluate
from .effects import apply_effects
from .resolver import ActionResult, ActionResolver
from .state import StoryState


class JourneyDesign(StrictModel):
    """作者设计快照：设计节点 → 选项 id，以及该选项的效果。"""

    selected_options: dict[str, str] = Field(default_factory=dict)
    section_options: list[str] = Field(default_factory=list)
    effects: dict[str, dict[str, str]] = Field(default_factory=dict)

    def option(self, field_id: str) -> str:
        return self.selected_options.get(field_id, "")

    def effect(self, field_id: str, key: str, default: str = "") -> str:
        return self.effects.get(field_id, {}).get(key, default)


class JourneyChoice(StrictModel):
    id: str
    label: str
    cost: str = ""
    suggested: bool = False


class JourneyScene(StrictModel):
    title: str
    text: str
    goal: str = ""
    success: str = ""
    next_question: str = ""
    completed: bool = False
    warnings: list[str] = Field(default_factory=list)
    choices: list[JourneyChoice] = Field(default_factory=list)
    revision: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "text": self.text,
            "goal": self.goal,
            "success": self.success,
            "next_question": self.next_question,
            "completed": self.completed,
            "warnings": list(self.warnings),
            "choices": [item.model_dump(mode="json") for item in self.choices],
        }


def journey_revision(state: StoryState) -> int:
    value = state.flags.get("journey_revision", 0)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    return int(value)


def actor_for(state: StoryState) -> str:
    """默认行动者：状态里的第一个角色；没有角色时使用通用标识。"""

    return next(iter(state.characters), "protagonist")


def initial_journey_state(pack: ContentPack, *, novel_id: str = "", actor: str = "protagonist") -> StoryState:
    """按内容包声明的起点创建初始状态；引擎不提供任何题材默认值。"""

    from .entities import Character, RelationshipState, ResourceStock

    resources = {key: ResourceStock(id=key, amount=float(amount), unit="份", holders=[actor])
                 for key, amount in pack.initial_resources.items()}
    # 起点关系网：内容包声明 source → target 的初始维度；与其它 initial_* 一样只是声明，
    # 后续变化仍由效果系统负责（这里不接受任何题材专属缺省值）。
    relationships: list[RelationshipState] = []
    for index, entry in enumerate(pack.initial_relationships):
        payload = dict(entry)
        payload.setdefault("source_id", actor)
        payload.setdefault("target_id", "")
        payload.setdefault("data", {})
        payload["data"].setdefault("order", index + 1)
        relationships.append(RelationshipState.model_validate(payload))
    # 主角也要吃到自己声明的起点数据（目标 / 欲望 / 恐惧 / 底线）：
    # 起点状态本来就会创建 actor，因此这里把声明合并进去，而不是丢掉。
    actor_entry = Character(id=actor, kind="player")
    actor_payload = pack.initial_characters.get(actor)
    if isinstance(actor_payload, Mapping):
        declared = Character.model_validate({"id": actor, **dict(actor_payload)})
        actor_entry = declared.model_copy(update={"id": actor, "kind": "player",
                                                 "data": {**declared.data, **actor_entry.data}})
    return StoryState(
        novel_id=novel_id,
        characters={actor: actor_entry},
        resources=resources,
        relationships=relationships,
        flags=dict(pack.initial_flags),
    )


def design_from_blueprint(blueprint: Any) -> JourneyDesign:
    """从既有 StoryBlueprint 读取设计快照；不读取也不写入小说正文。"""

    choices = getattr(blueprint, "design_choices", {}) or {}
    selected = {}
    for field_id, selection in choices.items():
        option_id = getattr(selection, "option_id", None) or ""
        if option_id:
            selected[field_id] = option_id
    section_options = [option_id for section in (getattr(blueprint, "sections", []) or [])
                       for option_id in (getattr(section, "selected_option_ids", []) or [])]
    return JourneyDesign(selected_options=selected, section_options=section_options,
                         effects={key: dict(value) for key, value in (getattr(blueprint, "design_effects", {}) or {}).items()})


class JourneyRuntime:
    """按内容包渲染场景，并可用统一 resolver 执行选择。"""

    def __init__(self, pack: ContentPack, resolver: ActionResolver | None = None) -> None:
        self.pack = pack
        self.resolver = resolver or ActionResolver()

    # ---- 场景 ----------------------------------------------------------

    def _place(self, design: JourneyDesign) -> str:
        place = design.effect("home_region", "place")
        if place:
            return place
        ids = list(design.section_options) + [item for item in design.selected_options.values() if item]
        return self.pack.text.place_for(ids)

    def _opening_profile(self, design: JourneyDesign):
        pattern = design.option("opening_pattern")
        if not pattern:
            pattern = self.pack.text.crisis_default_opening.get(design.option("present_crisis"), "opening_survival")
        profile = self.pack.text.opening_profiles.get(pattern) or self.pack.text.opening_profiles.get("opening_survival")
        return pattern, profile

    def _goal(self, design: JourneyDesign) -> str:
        return (design.effect("present_crisis", "goal")
                or design.effect("opening_pattern", "goal")
                or "解决眼前的困境")

    def _success(self, design: JourneyDesign, fallback: str) -> str:
        crisis = design.option("present_crisis")
        return self.pack.text.crisis_success.get(crisis, fallback) if crisis else fallback

    def _companion(self, design: JourneyDesign) -> str:
        line = self.pack.text.companion_lines.get(design.option("companion_history"),
                                                  "附近有人也被这场变故绊住了脚步。")
        return line + design.effect("companion_boundary", "scene")

    def _pressure(self, design: JourneyDesign) -> str:
        return self.pack.text.opponent_pressure.get(
            design.option("opponent_temperament"), "负责通行的人要求你先证明有资格继续介入。")

    def _choices(self, revision: int, state: StoryState, design: JourneyDesign, pattern: str,
                 suggestions: tuple[str, ...]) -> list[JourneyChoice]:
        ids = self._choice_ids(f"rev{revision}", state, pattern)
        return [JourneyChoice(id=self.pack.public_choice_id(action_id), label=self.pack.action(action_id).name,
                              cost=self.pack.action(action_id).data.get("cost_text", ""),
                              suggested=action_id in suggestions)
                for action_id in ids]

    def _choice_ids(self, scene_key: str, state: StoryState, pattern: str,
                    actor: str = "protagonist") -> list[str]:
        """按内容包声明的场景规则与可用性挑选行动；引擎不认识具体行动 id。"""

        rules = self.pack.choice_sets.get(scene_key)
        if rules is None:
            rules = self.pack.choice_sets.get("followup", [])
        ids: list[str] = []
        for rule in sorted(rules, key=lambda item: (item.order, item.action_id)):
            if rule.when_patterns and pattern not in rule.when_patterns:
                continue
            if pattern and pattern in rule.unless_patterns:
                continue
            if not self._action_available(rule.action_id, state, actor):
                continue
            ids.append(rule.action_id)
        return ids

    def _action_available(self, action_id: str, state: StoryState, actor: str) -> bool:
        action = self.pack.action(action_id)
        for requirement in action.requirements:
            if not evaluate(condition=requirement, state=state, actor=actor).ok:
                return False
        paid = apply_effects(state, action.costs, actor=actor, source=f"check:{action_id}")
        return paid.ok

    def suggestions_for(self, design: JourneyDesign) -> tuple[str, ...]:
        return {
            "hero_cautious": ("journey_clue", "journey_wait", "journey_leave"),
            "hero_bargainer": ("journey_supply", "journey_pay", "journey_rescue"),
            "hero_impulsive": ("journey_help", "journey_ally", "journey_expose"),
        }.get(design.option("hero_temperament"), ())

    def scene(self, state: StoryState, design: JourneyDesign, *, warnings: list[str] | None = None) -> JourneyScene:
        revision = journey_revision(state)
        if revision >= 4:
            return self._followup_scene(state, design, warnings=warnings)
        place = self._place(design)
        pattern, profile = self._opening_profile(design)
        goal = self._goal(design)
        success = self._success(design, profile.success if profile else "")
        title = profile.title if profile else ""
        text = self.pack.text.scene_texts.get("rev0", "").format(
            place=place, goal=goal, incident=profile.incident if profile else "",
            memory=self.pack.text.hero_memories.get(design.option("hero_history"), ""),
            companion=self._companion(design))
        if revision == 1:
            title = self.pack.text.scene_titles.get("rev1", title)
            text = self.pack.text.scene_texts.get("rev1_base", "").format(
                goal=goal, place=place, pressure=self._pressure(design))
            if state.flags.get("ally"):
                text += self.pack.text.scene_texts.get("rev1_ally", "")
            if state.flags.get("clue"):
                text += self.pack.text.scene_texts.get("rev1_clue", "")
            if _last_choice(state) == "journey_supply":
                text += self.pack.text.scene_texts.get("rev1_supply", "")
        elif revision == 2:
            title = self.pack.text.scene_titles.get("rev2", title)
            text = self.pack.text.scene_texts.get("rev2_base", "").format(goal=goal)
            text += self.pack.text.scene_texts.get(
                "rev2_wait" if _last_choice(state) == "journey_wait" else "rev2_open", "")
        elif revision >= 3:
            title = self.pack.text.scene_titles.get("rev3", title)
            text = _last_result(state)
        choices = self._choices(revision, state, design, pattern, self.suggestions_for(design))
        return JourneyScene(title=title, text=text, goal=goal, success=success,
                            next_question=profile.question if profile else "",
                            completed=revision == 3, warnings=list(warnings or []),
                            choices=choices, revision=revision)

    def _followup_scene(self, state: StoryState, design: JourneyDesign, *,
                        warnings: list[str] | None = None) -> JourneyScene:
        revision = journey_revision(state)
        texts = self.pack.text
        supplies = int(state.resources["supplies"].amount) if "supplies" in state.resources else 0
        debt = int(_counter(state, "debt"))
        trust = _counter(state, "trust")
        knowledge_ids = {item.id for item in state.knowledge}
        if state.flags.get("arc_finished"):
            return JourneyScene(title=texts.followup_titles.get("finished", "篇章已收束"),
                                text=_last_result(state), completed=True,
                                warnings=list(warnings or []), choices=[], revision=revision)
        companion_goal = design.effect("companion_motive", "goal", "兑现原来的承诺")
        opponent_goal = design.effect("opponent_motive", "goal", "维持眼前的资源分配")
        if revision == 4:
            title = texts.followup_titles.get("rev4", "")
            text = (texts.followup_texts.get("rev4_ally", "") if state.flags.get("ally")
                    else texts.followup_texts.get("rev4_alone", ""))
            text = text.replace("{companion_goal}", companion_goal)
            text += texts.followup_texts.get("rev4_state", "").replace("{supplies}", str(supplies)).replace("{debt}", str(debt))
            if state.flags.get("ally"):
                text += design.effect("companion_boundary", "scene")
            ids = self._choice_ids("rev4", state, "", actor=actor_for(state))
        elif revision == 5:
            title = texts.followup_titles.get("rev5", "")
            text = texts.followup_texts.get("rev5_base", "").replace("{opponent_goal}", opponent_goal)
            text += texts.followup_texts.get("rev5_trust" if trust > 0 else "rev5_alone", "")
            ids = self._choice_ids("rev5", state, "", actor=actor_for(state))
        elif revision == 6:
            title = texts.followup_titles.get("rev6", "")
            if "receipt" in knowledge_ids:
                text = texts.followup_texts.get("rev6_receipt", "")
                ids = self._choice_ids("rev6", state, "", actor=actor_for(state))
            else:
                text = texts.followup_texts.get("rev6_no_receipt", "")
                ids = self._choice_ids("rev6", state, "", actor=actor_for(state))
        else:
            title = texts.followup_titles.get("rev7", "")
            text = texts.followup_texts.get("rev7_base", "")
            ids = self._choice_ids("rev7", state, "", actor=actor_for(state))
        suggestions = self.suggestions_for(design)
        choices = [JourneyChoice(id=self.pack.public_choice_id(action_id), label=self.pack.action(action_id).name,
                                 cost=self.pack.action(action_id).data.get("cost_text", ""),
                                 suggested=action_id in suggestions)
                   for action_id in ids]
        return JourneyScene(title=title, text=text, completed=False, warnings=list(warnings or []),
                            choices=choices, revision=revision)

    # ---- 选择 ----------------------------------------------------------

    def choose(self, state: StoryState, design: JourneyDesign, action_id: str, *,
               actor: str = "protagonist", warnings: list[str] | None = None) -> ActionResult:
        try:
            resolved_id = self.pack.action_id_for_choice(action_id)
            action = self.pack.action(resolved_id)
        except Exception as exc:  # noqa: BLE001 - 未知行动按 blocked 返回
            return ActionResult(ok=False, outcome="blocked", action_id=action_id,
                                code="ACTION_NOT_FOUND", message=str(exc), state=state)
        revision = journey_revision(state)
        result_text = self._result_text(action, revision, design, state)
        resolved = self.resolver.resolve(action, state, actor=actor)
        if not resolved.ok:
            return resolved
        working = record_choice(resolved.state, resolved_id, result=result_text,
                                rules=self.pack.recompute, actor=actor)
        return resolved.model_copy(update={"state": working})

    def apply_choice(self, state: StoryState, design: JourneyDesign, action_id: str, *,
                     actor: str = "protagonist", warnings: list[str] | None = None) -> tuple[ActionResult, JourneyScene]:
        """执行一次选择并返回新状态与下一场景；供运行态接线直接使用。"""

        resolved = self.choose(state, design, action_id, actor=actor, warnings=warnings)
        return resolved, self.scene(resolved.state if resolved.ok else state, design, warnings=warnings)

    def _result_text(self, action: Any, revision: int, design: JourneyDesign, state: StoryState) -> str:
        data = action.data or {}
        template = str(data.get("result", ""))
        if revision == 0 and data.get("result_rev0"):
            template = str(data["result_rev0"])
        profile = self._opening_profile(design)[1]
        return template.format(goal=self._goal(design),
                              success=self._success(design, profile.success if profile else ""),
                              next_question=profile.question if profile else "")

def _last_choice(state: StoryState) -> str:
    for record in reversed(state.effect_log):
        if record.op == "choice":
            return record.target
    return ""


def _last_result(state: StoryState) -> str:
    for record in reversed(state.effect_log):
        if record.op == "choice" and (record.data or {}).get("result"):
            return str(record.data["result"])
    history = state.legacy.get("history", []) if isinstance(state.legacy, dict) else []
    return str(history[-1].get("result", "")) if history else ""


def _counter(state: StoryState, name: str) -> float:
    value = state.flags.get(name, 0)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    return float(value)


def recompute_from_choices(state: StoryState, rules: "RecomputeRules", *, actor: str = "protagonist") -> StoryState:
    """按内容包规则从选择历史重新计算计数器、知识、结局标记。"""

    from .entities import KnowledgeEntry

    choices = [record.target for record in state.effect_log if record.op == "choice"]
    values: dict[str, float] = {name: 0.0 for name in rules.floors}
    for choice in choices:
        for rule in rules.counters:
            if rule.when_choice and choice not in rule.when_choice:
                continue
            values[rule.counter] = values.get(rule.counter, 0.0) + rule.delta
            floor = rules.floors.get(rule.counter)
            if floor is not None:
                values[rule.counter] = max(floor, values[rule.counter])
    for counter, value in values.items():
        state.flags[counter] = int(value) if float(value).is_integer() else value
    for choice, knowledge_id in rules.knowledge_choices.items():
        if choice not in choices:
            continue
        existing = next((item for item in state.knowledge if item.id == knowledge_id), None)
        if existing is None:
            state.knowledge.append(KnowledgeEntry(id=knowledge_id, holders=[actor], source="choice"))
        elif actor not in existing.holders:
            existing.holders.append(actor)
    if any(choice in rules.arc_finished_choices for choice in choices):
        state.flags["arc_finished"] = True
    return state


def record_choice(state: StoryState, action_id: str, *, result: str = "",
                  rules: "RecomputeRules | None" = None, actor: str = "protagonist") -> StoryState:
    """记录一次选择（含结果），并按规则重算计数器/知识/结局标记。"""

    working = state.model_copy(deep=True)
    from .entities import EffectRecord

    working.effect_log.append(EffectRecord(id=f"choice:{action_id}:{len(working.effect_log) + 1}", op="choice",
                                           entity=actor, target=action_id, order=len(working.effect_log) + 1,
                                           data={"result": result}))
    # 每次选择推进一个场景；场景进度是引擎的通用规则，不由内容包逐条声明。
    current = working.flags.get("journey_revision", 0)
    working.flags["journey_revision"] = (int(current) if isinstance(current, (int, float))
                                         and not isinstance(current, bool) else 0) + 1
    if rules is not None:
        recompute_from_choices(working, rules, actor=actor)
    return working
