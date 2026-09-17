"""S08：LegacyIRSemanticExtractor —— legacy chapter → 结构化 IR proposal。

两种 backend：

- deterministic：规则抽取（默认；可离线运行）
- llm：外部模型提供的结构化 proposal（仍必须过 strict Pydantic + deterministic validator）

核心原则：LLM 只做结构抽取，不做事实裁决；不确定的实体一律 AMBIGUOUS_ENTITY，不猜。
"""

from __future__ import annotations

import re
from typing import Any, Callable, Literal, Mapping, Sequence

from pydantic import Field

from novelforge.models import StrictModel

from .models import (
    DECISION_ACTIONS,
    ChapterEffect,
    ChapterEventFrame,
    ChapterSemanticIR,
    ChapterStateTransition,
    DogRoleBinding,
    FieldEvidence,
)

Backend = Literal["deterministic", "llm"]
AMBIGUOUS_ENTITY = "AMBIGUOUS_ENTITY"

# ---- proposal schema（strict；LLM 必须输出这些结构，不得输出自由解释） -------------


class ExtractedEvent(StrictModel):
    event_id: str = Field(min_length=3, max_length=48)
    actor_ids: list[str] = Field(default_factory=list)
    mentioned_entity_ids: list[str] = Field(default_factory=list)
    action_type: str = Field(default="action", max_length=48)
    action_text: str = Field(default="", max_length=300)
    decision_action: str = Field(default="", max_length=32)
    alternatives: list[str] = Field(default_factory=list)
    selected_action: str = Field(default="", max_length=200)
    changes_followup_path: bool = False
    agency: Literal["autonomous", "reactive", "forced", "systemic"] = "reactive"
    physical_presence: bool = True
    temporal_order: int = Field(default=0, ge=0)
    confidence: float = Field(default=0.6, ge=0, le=1)


class ExtractedEffect(StrictModel):
    effect_id: str = Field(min_length=3, max_length=48)
    effect_type: str = Field(default="state", max_length=32)
    target_id: str = Field(default="", max_length=120)
    after_state: str = Field(default="", max_length=200)
    polarity: Literal["positive", "negative", "neutral", "mixed"] = "neutral"
    caused_by_event_ids: list[str] = Field(default_factory=list)
    is_narrative_pivot: bool = False
    confidence: float = Field(default=0.6, ge=0, le=1)


class ExtractedStateAssertion(StrictModel):
    assertion_id: str = Field(min_length=3, max_length=48)
    state_key: str = Field(min_length=3, max_length=64)
    from_state: str = Field(default="", max_length=64)
    to_state: str = Field(default="", max_length=64)
    mode: Literal["transition", "observation", "historical_reference", "expectation",
                  "hypothesis", "future_intention"] = "observation"
    narrative_role: Literal["primary", "secondary", "derived"] = "derived"
    evidence_event_ids: list[str] = Field(default_factory=list)


class ExtractedDecision(StrictModel):
    decision_id: str = Field(min_length=3, max_length=48)
    actor_id: str = Field(default="", max_length=120)
    choice: str = Field(default="", max_length=200)
    alternatives: list[str] = Field(default_factory=list)
    selected_action: str = Field(default="", max_length=200)
    changes_followup_path: bool = False
    evidence_event_ids: list[str] = Field(default_factory=list)


class ExtractedTurn(StrictModel):
    turn_id: str = Field(min_length=3, max_length=48)
    turn_type: Literal["state_transition", "knowledge_reveal", "relationship_reversal",
                       "strategic_reversal", "authority_transfer", "goal_reversal"] = \
        "state_transition"
    transition_id: str = Field(default="", max_length=48)
    effect_id: str = Field(default="", max_length=48)
    summary: str = Field(default="", max_length=200)


class ExtractedDog(StrictModel):
    dog_entity_id: str = Field(default="", max_length=64)
    physical_presence: bool = False
    role: Literal["involved", "supportive", "independent", "offscreen_effect", "absent"] = \
        "absent"
    evidence_event_ids: list[str] = Field(default_factory=list)
    effect_ids: list[str] = Field(default_factory=list)
    absence_effect: str = Field(default="", max_length=200)
    affects_decision_or_state: bool = False


class ExtractedChapterIRProposal(StrictModel):
    chapter_uuid: str = Field(min_length=3, max_length=128)
    backend: Backend = "deterministic"
    events: list[ExtractedEvent] = Field(default_factory=list)
    effects: list[ExtractedEffect] = Field(default_factory=list)
    state_assertions: list[ExtractedStateAssertion] = Field(default_factory=list)
    decision_candidates: list[ExtractedDecision] = Field(default_factory=list)
    turn_candidates: list[ExtractedTurn] = Field(default_factory=list)
    dog_presence: ExtractedDog = Field(default_factory=ExtractedDog)
    dog_action_candidates: list[str] = Field(default_factory=list)
    ambiguous_entity_ids: list[str] = Field(default_factory=list)
    note: str = Field(default="", max_length=300)


# ---- deterministic extraction rules ------------------------------------------

DECISION_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"没有(?:追|阻拦|呼唤|拦)"), "withdraw"),
    (re.compile(r"(?:拒绝|不签|不肯|回绝|不接)"), "refuse"),
    (re.compile(r"(?:接受|接下|同意)"), "accept"),
    (re.compile(r"(?:担下|承担|扛下)"), "commit"),
    (re.compile(r"(?:暂缓|推迟|留到|往后压)"), "defer"),
    (re.compile(r"(?:放行|允许)"), "allow"),
    (re.compile(r"(?:禁止|不许|不准)"), "forbid"),
    (re.compile(r"(?:派|交给|列为|指派)"), "assign"),
    (re.compile(r"(?:留在|留下|保留)"), "retain"),
    (re.compile(r"(?:放弃|弃掉)"), "abandon"),
    (re.compile(r"(?:扣下|不交|封存|只交出|只给|隐去|瞒下)"), "withhold"),
    (re.compile(r"(?:先|优先)"), "prioritize"),
    (re.compile(r"(?:换取|换成|以.+换)"), "trade_off"),
    (re.compile(r"(?:签下|署名|落笔|刻下|签署)"), "sign"),
    (re.compile(r"(?:表决通过|点头通过|批准)"), "approve"),
    (re.compile(r"(?:驳回|否决)"), "reject"),
    (re.compile(r"(?:决定|选择|定下|拍板|裁定|议定)"), "decide"),
)
ALTERNATIVE_PATTERN = re.compile(r"(?:还是|或者|要么|或|否则|二选一|权衡|代价|但)")
FUTURE_PATTERN = re.compile(r"(?:将在|将要|之后会|准备|即将|下一步)")
HISTORICAL_PATTERN = re.compile(r"(?:此前|早已|已经|后来|当年|记录里|留下的)")
OBSERVATION_PATTERN = re.compile(r"(?:仍|被确认|显示|表明|看得出|记录显示)")
EXPECTATION_PATTERN = re.compile(r"(?:如果|要是|一旦|将会)")
HYPOTHESIS_PATTERN = re.compile(r"(?:怀疑|可能|似乎|也许)")

COST_MARKERS = ("代价", "损失", "被夺", "被扣", "伤", "暴露", "欠", "耗", "减", "失")
BENEFIT_MARKERS = ("达成", "得到", "换回", "保住", "拿下", "确认", "通过", "成立", "到手")
PIVOT_MARKERS = ("翻", "反", "暴露", "夺回", "易手", "权限", "身份", "真相", "改写",
                 "开始产出", "变成", "转为", "确立", "失守", "落入", "失去", "获得",
                 "揭开", "反超", "失控", "定型", "坐实", "公开", "承认")


class LegacyIRSemanticExtractor:
    def __init__(self, *, novel_id: str, dog_entity_id: str = "ENTITY_DOG_AHUI",
                 protagonist_id: str = "ENTITY_PROTAGONIST",
                 entity_aliases: Mapping[str, str] | None = None,
                 kind_index: Mapping[str, Sequence[str]] | None = None,
                 state_bindings: Mapping[str, int] | None = None,
                 llm_provider: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None) -> None:
        self.novel_id = novel_id
        self.dog_entity_id = dog_entity_id
        self.protagonist_id = protagonist_id
        # alias → entity_id（阿灰 / 它 / 那只狗 … 的显式别名由调用方提供；未提供的代词不猜）
        self.entity_aliases = dict(entity_aliases or {})
        self.kind_index = {key: list(value) for key, value in (kind_index or {}).items()}
        self.state_bindings = dict(state_bindings or {})
        self.llm_provider = llm_provider

    # ---- backend -----------------------------------------------------------
    def extract(self, chapter: Mapping[str, Any], *, backend: Backend = "deterministic",
                ) -> ExtractedChapterIRProposal:
        if backend == "llm":
            if self.llm_provider is None:
                raise RuntimeError("llm backend 需要传入 llm_provider（结构化 proposal 提供者）")
            payload = dict(self.llm_provider(chapter))
            payload.setdefault("chapter_uuid", str(chapter.get("chapter_uuid") or ""))
            payload["backend"] = "llm"
            return ExtractedChapterIRProposal.model_validate(payload, strict=True)
        return self._deterministic(chapter)

    # ---- deterministic backend --------------------------------------------
    def _deterministic(self, chapter: Mapping[str, Any]) -> ExtractedChapterIRProposal:
        events: list[ExtractedEvent] = []
        goal = str(chapter.get("goal") or "")
        focal_owner = self._focal_decision_owner(goal)
        for order, raw in enumerate(chapter.get("events") or [], start=1):
            text = str(raw)
            actors, ambiguous = self._resolve_actors(text)
            mentions = sorted({entity for alias, entity in self.entity_aliases.items()
                               if alias and alias in text and entity != "AMBIGUOUS"})
            decision_action, alternatives, selected = self._decision(
                text, actors=actors, focal_owner=focal_owner)
            events.append(ExtractedEvent(
                event_id=f"CE_{order:03d}", actor_ids=actors,
                mentioned_entity_ids=mentions,
                action_type=self._action_type(text), action_text=text,
                decision_action=decision_action, alternatives=alternatives,
                selected_action=selected,
                changes_followup_path=bool(decision_action) and (
                    bool(alternatives) or bool(selected) or order >= len(chapter.get("events") or [])),
                agency=self._agency(text), physical_presence=bool(actors),
                temporal_order=order, confidence=0.6))
        effects = self._effects(chapter, events)
        assertions = self._state_assertions(chapter, events)
        decisions = self._decisions(events)
        turns = self._turns(assertions, effects)
        dog, dog_actions, dog_ambiguous = self._dog(chapter, events)
        return ExtractedChapterIRProposal(
            chapter_uuid=str(chapter.get("chapter_uuid") or ""), backend="deterministic",
            events=events, effects=effects, state_assertions=assertions,
            decision_candidates=decisions, turn_candidates=turns, dog_presence=dog,
            dog_action_candidates=dog_actions, ambiguous_entity_ids=sorted(set(dog_ambiguous)),
            note="deterministic rules")

    # ---- entity / coreference --------------------------------------------
    def _focal_decision_owner(self, goal: str) -> str:
        """focal decision owner：默认 protagonist；只有 goal 明确写伙伴自主选择时才换。"""

        dog_aliases = [alias for alias, entity in self.entity_aliases.items()
                       if entity == self.dog_entity_id and alias not in ("它", "那只狗")]
        if any(alias in goal for alias in dog_aliases) and any(
                keyword in goal for keyword in ("自己决定", "自主选择", "自己选择", "去留",
                                                "选择留下", "选择回来")):
            return self.dog_entity_id
        return self.protagonist_id

    def _resolve_actors(self, text: str) -> tuple[list[str], list[str]]:
        actors: list[str] = []
        ambiguous: list[str] = []
        for alias, entity_id in self.entity_aliases.items():
            if not alias or alias not in text or entity_id in actors:
                continue
            if any(self._is_actor_mention(text, alias, match.start(), match.end(),
                                          entity_is_dog=(entity_id in
                                                         set(self.kind_index.get("dog", []))))
                   for match in re.finditer(re.escape(alias), text)):
                actors.append(entity_id)
        # 代词：只有唯一同类候选才解析，否则 AMBIGUOUS_ENTITY
        if re.search(r"(?:它|那只狗|那条狗|这条狗)", text):
            dog_kinds = self.kind_index.get("dog", [])
            explicit = [entity for entity in dog_kinds if entity in actors]
            if len(explicit) == 1:
                pass
            elif len(dog_kinds) == 1 and not any(
                    other in text for other in self._other_dog_aliases()):
                if dog_kinds[0] not in actors:
                    actors.append(dog_kinds[0])
            else:
                ambiguous.append(AMBIGUOUS_ENTITY)
        return actors, ambiguous

    SUBJECT_MARKERS = ("，", "。", "；", "：", "、", "然后", "随后", "于是", "接着", "直到", "最后")
    POSSESSIVE_SUFFIX = ("铭牌", "编号", "校验码", "身上", "的", "名字", "档案")
    ACTOR_VERB_PREFIX = re.compile(
        r"(?:自己|们)?(?:把|将|用|带|咬|拖|叼|扑|冲|走|退|守|低吼|闻|嗅|刨|发现|拒绝|决定|签|"
        r"没有|不|让|背|顶|按|拉|救|守夜|看向|问|说)")

    @classmethod
    def _is_actor_mention(cls, text: str, alias: str, start: int, end: int, *,
                          entity_is_dog: bool = False) -> bool:
        """判断某个实体提及是不是本事件的 actor（而不是所有格 / 宾语）。"""

        prefix = text[:start]
        suffix = text[end:end + 6]
        if re.match(r"^(?:不在|已经|早已|留在|未归|随队|被留在|没能)", suffix):
            return False
        if entity_is_dog and not re.match(
                r"^(?:自己|们)?(?:来回|一起|先|又|再|最后|独自|主动|马上|当即|跟着|回头)*"
                r"(?:用|拿|送|绕|拱|扒|盯|把|将|咬|叼|扑|冲|走|退|守|低吼|闻|嗅|刨|"
                r"发现|顶|按|拉|救|挖|找|坐|跟|挡|拦|带路|巡)", suffix):
            return False
        if suffix.startswith(cls.POSSESSIVE_SUFFIX) and not suffix.startswith("的编号"):
            return False
        if start <= 1 or any(marker in prefix[-3:] for marker in cls.SUBJECT_MARKERS):
            return True
        if "自己" in suffix[:4] or cls.ACTOR_VERB_PREFIX.match(suffix):
            return True
        return False

    def _other_dog_aliases(self) -> list[str]:
        return [alias for alias, entity in self.entity_aliases.items()
                if entity != self.dog_entity_id and alias in ("编号犬", "荒原犬", "同类",
                                                              "笼中同类", "猎团犬")]

    # ---- actions ----------------------------------------------------------
    @staticmethod
    def _action_type(text: str) -> str:
        if any(keyword in text for keyword in ("不许", "禁止", "规定", "制度", "门槛", "规则")) \
                and "阿灰" in text and "低吼" not in text:
            return "rule"
        for keywords, action in ACTION_RULESET:
            if any(keyword in text for keyword in keywords):
                return action
        return "action"

    @staticmethod
    def _agency(text: str) -> str:
        if any(keyword in text for keyword in ("不许", "禁止", "规定", "制度", "门槛证明")):
            return "systemic"
        if re.search(r"自己|自主|主动|独自", text):
            return "autonomous"
        if any(keyword in text for keyword in ("被迫", "被逼", "只能")):
            return "forced"
        if any(keyword in text for keyword in ("系统", "门禁", "潮", "规则", "反噬")):
            return "systemic"
        return "reactive"

    @classmethod
    def _decision(cls, text: str, *, actors: Sequence[str],
                  focal_owner: str) -> tuple[str, list[str], str]:
        # decision owner 规则：只有 focal owner 真的作为 actor 时才算 decision
        if focal_owner not in actors:
            return "", [], ""
        for pattern, action in DECISION_PATTERNS:
            match = pattern.search(text)
            if not match:
                continue
            alternatives: list[str] = []
            if ALTERNATIVE_PATTERN.search(text):
                alternatives = [text[max(0, match.start() - 20):match.end() + 20]]
            return action, alternatives, text[:120]
        return "", [], ""

    # ---- effects ----------------------------------------------------------
    def _effects(self, chapter: Mapping[str, Any],
                 events: Sequence[ExtractedEvent]) -> list[ExtractedEffect]:
        effects: list[ExtractedEffect] = []
        counter = 1
        loss_text = str(chapter.get("loss") or "")
        cost_text = str(chapter.get("cost") or "")
        if loss_text or cost_text:
            detail = loss_text or cost_text
            if any(marker in detail for marker in COST_MARKERS) or loss_text:
                effects.append(ExtractedEffect(
                    effect_id=f"EF_{counter:03d}", effect_type="cost",
                    target_id=self.protagonist_id, after_state=detail[:120],
                    polarity="negative",
                    caused_by_event_ids=[event.event_id for event in events[-2:]],
                    is_narrative_pivot=any(marker in detail for marker in PIVOT_MARKERS),
                    confidence=0.6))
                counter += 1
        payoff_text = str(chapter.get("payoff") or "")
        if payoff_text:
            effects.append(ExtractedEffect(
                effect_id=f"EF_{counter:03d}", effect_type="benefit",
                target_id=self.protagonist_id, after_state=payoff_text[:120],
                polarity="positive",
                caused_by_event_ids=[events[-1].event_id] if events else [],
                confidence=0.6))
            counter += 1
        turn_text = str(chapter.get("turn") or "")
        if turn_text and any(marker in turn_text for marker in PIVOT_MARKERS):
            effects.append(ExtractedEffect(
                effect_id=f"EF_{counter:03d}", effect_type="narrative_pivot",
                target_id=self.protagonist_id, after_state=turn_text[:120], polarity="mixed",
                caused_by_event_ids=[events[-1].event_id] if events else [],
                is_narrative_pivot=True, confidence=0.6))
        return effects

    # ---- state assertions -------------------------------------------------
    def _state_assertions(self, chapter: Mapping[str, Any],
                          events: Sequence[ExtractedEvent]) -> list[ExtractedStateAssertion]:
        text = " ".join([str(chapter.get("goal") or ""),
                         *[event.action_text for event in events],
                         str(chapter.get("world_state_change") or ""),
                         str(chapter.get("end_state") or "")])
        assertions: list[ExtractedStateAssertion] = []
        for state_key, from_state, to_state, keywords in STATE_ASSERTIONS:
            if not any(keyword in text for keyword in keywords):
                continue
            mode = self._assertion_mode(text)
            assertions.append(ExtractedStateAssertion(
                assertion_id=f"ST_{len(assertions) + 1:03d}", state_key=state_key,
                from_state=from_state, to_state=to_state, mode=mode,
                narrative_role="derived",
                evidence_event_ids=[event.event_id for event in events[:1]]))
        # primary 选择：transition 模式优先、且位置最靠近本章目标
        primaries = [item for item in assertions if item.mode == "transition"]
        if primaries:
            rank = {tuple(row[:3]): index for index, row in enumerate(STATE_ASSERTIONS)}
            primaries.sort(key=lambda item: rank.get((item.state_key, item.from_state,
                                                      item.to_state), -1))
            primaries[-1].narrative_role = "primary"
            for item in primaries[:-1]:
                item.narrative_role = "secondary"
        return assertions

    @staticmethod
    def _assertion_mode(text: str) -> str:
        if FUTURE_PATTERN.search(text):
            return "future_intention"
        if EXPECTATION_PATTERN.search(text):
            return "expectation"
        if HYPOTHESIS_PATTERN.search(text):
            return "hypothesis"
        if HISTORICAL_PATTERN.search(text):
            return "historical_reference"
        if OBSERVATION_PATTERN.search(text):
            return "observation"
        return "transition"

    # ---- decisions / turns ------------------------------------------------
    @staticmethod
    def _decisions(events: Sequence[ExtractedEvent]) -> list[ExtractedDecision]:
        rows: list[ExtractedDecision] = []
        for event in events:
            if not event.decision_action:
                continue
            rows.append(ExtractedDecision(
                decision_id=f"DEC_{len(rows) + 1:03d}",
                actor_id=next((item for item in event.actor_ids), ""),
                choice=event.selected_action, alternatives=list(event.alternatives),
                selected_action=event.selected_action,
                changes_followup_path=event.changes_followup_path,
                evidence_event_ids=[event.event_id]))
        return rows

    @staticmethod
    def _turns(assertions: Sequence[ExtractedStateAssertion],
               effects: Sequence[ExtractedEffect]) -> list[ExtractedTurn]:
        rows: list[ExtractedTurn] = []
        for item in assertions:
            if item.narrative_role == "primary":
                rows.append(ExtractedTurn(turn_id=f"TURN_{len(rows) + 1:03d}",
                                          turn_type="state_transition",
                                          transition_id=item.assertion_id,
                                          summary=f"{item.state_key}:{item.to_state}"))
        if not rows:
            for effect in effects:
                if effect.is_narrative_pivot:
                    rows.append(ExtractedTurn(turn_id=f"TURN_{len(rows) + 1:03d}",
                                              turn_type="strategic_reversal",
                                              effect_id=effect.effect_id,
                                              summary=effect.after_state))
        return rows

    # ---- dog --------------------------------------------------------------
    def _dog(self, chapter: Mapping[str, Any],
             events: Sequence[ExtractedEvent]) -> tuple[ExtractedDog, list[str], list[str]]:
        dog_events = [event for event in events if self.dog_entity_id in event.actor_ids]
        dog_actions = [event.action_text for event in dog_events]
        presence = bool(dog_events)
        ambiguity: list[str] = []
        if not presence and re.search(r"(?:它|那只狗|荒原犬|编号犬|同类)", " ".join(
                event.action_text for event in events)):
            other_dogs = self._other_dog_aliases()
            if other_dogs:
                ambiguity.append(AMBIGUOUS_ENTITY)
        if presence:
            autonomous = any(event.agency == "autonomous" for event in dog_events)
            # 被困 / 被救 / 受伤 / 被讨论 / 被交易 / 被识别编号 → 不是 supportive
            passive = any(re.search(r"(?:被困|被救|受伤|被讨论|被拿来|被交易|被识别|被扣|被运)",
                                    event.action_text) for event in dog_events)
            help_action = any(re.search(r"(?:刨|嗅|叼|扑|拖|拉|救|挖|找|带路|挡|拦|咬|顶|送|"
                                        r"拱|扒|盯|按|守)",
                                        event.action_text) for event in dog_events)
            autonomous = autonomous and not passive
            if passive and not help_action:
                role = "involved"
            else:
                role = "independent" if autonomous else ("supportive" if help_action
                                                         else "involved")
        elif self.dog_entity_id in set(self.entity_aliases.values()) and any(
                alias in str(chapter.get("goal") or "") + " ".join(
                    event.action_text for event in events)
                for alias, entity in self.entity_aliases.items() if entity == self.dog_entity_id):
            role = "offscreen_effect"
        else:
            role = "absent"
        absence_effect = ""
        if role == "offscreen_effect":
            absence_effect = str(chapter.get("turn") or chapter.get("end_state") or "")[:120]
        return (ExtractedDog(dog_entity_id=self.dog_entity_id, physical_presence=presence,
                             role=role, evidence_event_ids=[event.event_id for event in dog_events],
                             effect_ids=[], absence_effect=absence_effect,
                             affects_decision_or_state=bool(
                                 role in ("offscreen_effect", "involved", "supportive",
                                          "independent"))),
                dog_actions, ambiguity)

    # ---- proposal → IR ----------------------------------------------------
    def to_ir(self, proposal: ExtractedChapterIRProposal,
              chapter: Mapping[str, Any]) -> ChapterSemanticIR:
        events = [ChapterEventFrame(
            event_id=item.event_id, actor_ids=list(item.actor_ids),
            mentioned_entity_ids=list(item.mentioned_entity_ids),
            action_type=item.action_type, action_text=item.action_text,
            decision_action=item.decision_action, changes_followup_path=item.changes_followup_path,
            has_alternative=bool(item.alternatives), temporal_order=item.temporal_order,
            agency=item.agency, physical_presence=item.physical_presence,
            confidence=item.confidence, provenance="imported") for item in proposal.events]
        effects = [ChapterEffect(
            effect_id=item.effect_id, effect_type=item.effect_type, target_id=item.target_id,
            after_state=item.after_state,
            polarity=item.polarity, caused_by_event_ids=list(item.caused_by_event_ids),
            is_narrative_pivot=item.is_narrative_pivot, confidence=item.confidence)
            for item in proposal.effects]
        transitions = [ChapterStateTransition(
            transition_id=item.assertion_id, state_key=item.state_key,
            from_state=item.from_state, to_state=item.to_state,
            caused_by_event_ids=list(item.evidence_event_ids),
            prerequisite_state=item.from_state, assertion_mode=item.mode,
            narrative_role=item.narrative_role,
            transition_kind="irreversible" if item.to_state in
            ("permanently_sealed", "signed") else
            ("acquisition" if item.mode == "transition" else "progression"),
            effective_at=chapter.get("display_number") or chapter.get("index"))
            for item in proposal.state_assertions]
        dog = DogRoleBinding(
            role=proposal.dog_presence.role,
            evidence_event_ids=list(proposal.dog_presence.evidence_event_ids),
            effect_ids=list(proposal.dog_presence.effect_ids),
            physical_presence=proposal.dog_presence.physical_presence,
            autonomous=proposal.dog_presence.role == "independent",
            affects_decision_or_state=proposal.dog_presence.role in
            ("offscreen_effect", "involved", "supportive", "independent"))
        decision_events = [item.event_id for item in proposal.events if item.decision_action]
        primary = next((item.transition_id for item in transitions
                        if item.narrative_role == "primary"), "")
        if not primary:
            live = [item for item in transitions if item.assertion_mode == "transition"]
            if len(live) == 1:
                live[0].narrative_role = "primary"
                primary = live[0].transition_id
        evidence = [
            FieldEvidence(field_name="decision", event_ids=decision_events,
                          evidence_type="direct", confidence=0.6),
            FieldEvidence(field_name="cost", effect_ids=[effect.effect_id for effect in effects
                                                         if effect.polarity in ("negative", "mixed")],
                          evidence_type="derived", confidence=0.6),
            FieldEvidence(field_name="loss", effect_ids=[effect.effect_id for effect in effects
                                                         if effect.polarity in ("negative", "mixed")],
                          evidence_type="derived", confidence=0.6),
            FieldEvidence(field_name="turn",
                          transition_ids=[primary] if primary else [],
                          effect_ids=[effect.effect_id for effect in effects
                                      if effect.is_narrative_pivot],
                          evidence_type="derived", confidence=0.6),
            FieldEvidence(field_name="payoff", effect_ids=[effect.effect_id for effect in effects
                                                           if effect.polarity in ("positive",
                                                                                  "mixed")],
                          evidence_type="derived", confidence=0.6),
            FieldEvidence(field_name="world_state_change",
                          transition_ids=[primary] if primary else [],
                          evidence_type="derived", confidence=0.6),
            FieldEvidence(field_name="information_release",
                          event_ids=[item.event_id for item in proposal.events
                                     if item.action_type in ("discover", "negotiate", "open")],
                          evidence_type="derived", confidence=0.5),
            FieldEvidence(field_name="dog_role",
                          event_ids=list(proposal.dog_presence.evidence_event_ids),
                          effect_ids=list(proposal.dog_presence.effect_ids),
                          evidence_type="direct", confidence=0.6),
        ]
        return ChapterSemanticIR(
            # 章节身份永远来自 chapter 记录；proposal 的 uuid 不得替代 machine identity
            chapter_uuid=str(chapter.get("chapter_uuid") or proposal.chapter_uuid),
            novel_id=self.novel_id,
            volume_id=f"V{chapter.get('volume')}" if chapter.get("volume") else "",
            arc_id=str(chapter.get("arc") or ""),
            temporal_position=chapter.get("display_number") or chapter.get("index"),
            participant_ids=sorted({actor for event in events for actor in event.actor_ids}),
            event_frames=events, effects=effects, state_transitions=transitions,
            field_evidence=evidence, dog=dog, provenance="imported",
            legacy_chapter_label=str(chapter.get("id") or ""),
            goal=str(chapter.get("goal") or ""),
            focal_decision_owner_id=self._focal_decision_owner(str(chapter.get("goal") or "")),
            ambiguous_entity_ids=list(proposal.ambiguous_entity_ids),
            not_applicable_fields=[
                field_name for field_name, legacy in
                (("cost", chapter.get("cost")), ("loss", chapter.get("loss")),
                 ("information_release", chapter.get("information_release")),
                 ("world_state_change", chapter.get("world_state_change")))
                if not str(legacy or "").strip()])


ACTION_RULESET: tuple[tuple[tuple[str, ...], str], ...] = (
    (("拒绝", "不签", "不肯", "回绝", "不接"), "refuse"),
    (("决定", "选择", "定下", "拍板", "裁定", "议定", "宣布", "主持"), "decision"),
    (("签署", "署名", "刻下", "落笔", "签下"), "sign"),
    (("谈", "交涉", "条件", "换取"), "negotiate"),
    (("伏击", "交火", "袭击", "突围", "扑咬"), "fight"),
    (("撤", "退", "离开", "出塔", "封"), "flee"),
    (("离开", "离队", "出走"), "depart"),
    (("回来", "归队", "返回"), "return"),
    (("发现", "找到", "核对", "比对", "证实"), "discover"),
    (("救", "护住", "拖", "拉起"), "rescue"),
    (("守", "看住", "盯"), "protect"),
    (("封死", "爆破", "炸塌", "永久封闭"), "seal"),
    (("打开", "开门", "开启", "推门"), "open"),
    (("交换", "换成", "换取"), "trade"),
    (("挖", "刨", "拆", "起出", "拓印"), "search"),
    (("观察", "隐蔽", "探"), "observe"),
)

STATE_ASSERTIONS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("salt_route_control", "uncontrolled", "contested", ("伏击", "公开争夺", "争夺盐路")),
    ("salt_route_control", "contested", "controlled_by_rust_settlement",
     ("按趟结算", "拿到控制权", "谈成")),
    ("zero_layer_access", "closed", "first_opened", ("第一次打开", "第七次", "门开")),
    ("zero_layer_access", "first_opened", "emergency_locked", ("紧急锁闭", "撤销开放权限")),
    ("zero_layer_access", "emergency_locked", "permanently_sealed",
     ("永久封死", "爆破主通道", "封层")),
    ("common_rules_status", "idea", "draft", ("草案",)),
    ("common_rules_status", "draft", "consulted", ("征求意见", "批注", "带回修订")),
    ("common_rules_status", "consulted", "voted", ("表决", "投票")),
    ("common_rules_status", "voted", "revised", ("修订",)),
    ("common_rules_status", "approved", "signed",
     ("正式签署", "并列署名", "共守规矩正式", "正式生效")),
    ("dog_departure_status", "present", "considering", ("引诱", "招揽", "同类气味")),
    ("dog_departure_status", "considering", "voluntarily_departed",
     ("跟着那只同类", "随外部队伍离开", "自己跟着")),
    ("dog_departure_status", "voluntarily_departed", "absent_waiting",
     ("第一夜", "没有脚印回来", "等它自己")),
    ("dog_departure_status", "absent_waiting", "voluntarily_returned",
     ("自己走回", "主动回来", "自己回来")),
    ("archive_publication_level", "unpublished", "partial_release", ("前一份档案", "部分档案")),
    ("archive_publication_level", "partial_release", "second_archive_verified",
     ("第二份", "验证者名单")),
    ("archive_publication_level", "second_archive_verified", "third_archive_pending",
     ("第三份档案", "第三份在")),
    ("archive_publication_level", "third_archive_pending", "third_archive_released",
     ("第三份档案公开", "交叉验证")),
    ("gray_wall_observation_status", "unobserved", "observed_on_page",
     ("整体东移", "实测", "旧路标注作废")),
)
