"""S04：legacy ChapterPlan → provisional Chapter Semantic IR。

只做可解释的结构化抽取：provenance 一律 imported / inferred，
不得把 legacy 文本自动升格为 confirmed Canon。
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from novelforge.story_engine.canon.prose import (
    DOG_ACTION_VERBS,
    DOG_INDEPENDENT_PATTERN,
    DOG_PASSIVE_PATTERN,
)

from .models import (
    DECISION_ACTIONS,
    ChapterEffect,
    ChapterEventFrame,
    ChapterSemanticIR,
    ChapterStateTransition,
    DogRoleBinding,
    FieldEvidence,
)

# DecisionAction taxonomy：关键词 → 结构化 decision 动作
DECISION_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("不追", "没有追", "没追", "放弃追", "没有阻拦", "没有呼唤", "没有拦"), "withdraw"),
    (("拒绝", "不签", "不肯", "回绝", "不接", "拒绝交出", "当场拒绝"), "refuse"),
    (("接受", "接下", "同意"), "accept"),
    (("担下", "承担", "扛下"), "commit"),
    (("往后压", "暂缓", "推迟", "留到"), "defer"),
    (("放行", "允许", "让队伍"), "allow"),
    (("禁止", "不许", "不准"), "forbid"),
    (("派", "交给", "指派"), "assign"),
    (("留在", "留下", "保留", "自己留下"), "retain"),
    (("放弃", "弃", "丢弃"), "abandon"),
    (("不交", "扣下", "封存", "没交出"), "withhold"),
    (("先", "优先", "次序"), "prioritize"),
    (("换", "以", "用一个"), "trade_off"),
    (("签", "署名", "落笔", "刻下"), "sign"),
    (("通过", "批准", "表决通过"), "approve"),
    (("驳回", "否掉", "否决"), "reject"),
    (("按住", "等一个", "等下一次", "暂不"), "wait"),
    (("撤回", "收回原议"), "withdraw"),
    (("决定", "选择", "定下", "拍板", "裁定", "议定"), "decide"),
)

# StateAssertionMode：判断状态迁移语句是「现场推进」还是回指 / 观察 / 预期 / 假设
ASSERTION_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("如果", "要是", "将会", "准备", "即将"), "expectation"),
    (("怀疑", "可能", "似乎", "也许"), "hypothesis"),
    (("已经", "此前", "早已", "之后", "后来", "留下的", "记录里"), "historical_reference"),
    (("仍", "被确认", "显示", "表明", "看得出"), "observation"),
)
TRANSITION_ACTION_MARKERS: dict[str, tuple[str, ...]] = {
    "permanently_sealed": ("爆破", "炸塌", "封死", "封层"),
    "emergency_locked": ("紧急锁闭", "撤销", "锁死"),
    "first_opened": ("第一次打开", "第七次", "推门", "门开"),
    "signed": ("签署", "署名", "落笔", "刻下", "正式成立", "共守规矩成立", "新秩序成立"),
    "voted": ("表决", "投票"),
    "consulted": ("征求意见", "批注", "带回修订"),
    "controlled_by_rust_settlement": ("按趟结算", "谈成", "拿到控制权"),
    "contested": ("伏击", "争夺", "公开争夺", "进入公开"),
    "voluntarily_departed": ("跟着那只同类", "随外部队伍离开", "自主离开", "跨过旧路钉"),
    "absent_waiting": ("第一夜", "没有脚印回来"),
    "voluntarily_returned": ("自己走回", "主动回来", "自己回来"),
    "partial_release": ("前一份档案", "部分档案"),
    "second_archive_verified": ("第二份", "验证者名单"),
    "third_archive_released": ("第三份档案公开", "交叉验证"),
    "observed_on_page": ("整体东移", "实测", "旧路标注作废"),
}

ACTION_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("拒绝", "不签", "不肯", "回绝", "不接", "交还", "拒绝交出", "当场拒绝"), "refuse"),
    (("决定", "选择", "定下", "拍板", "裁定", "议定", "宣布", "主持", "要求先"), "decision"),
    (("只签", "只保留", "只同意", "坚持", "改为", "改成"), "decision"),
    (("签", "署名", "刻下", "落笔"), "sign"),
    (("谈", "交涉", "开价", "条件"), "negotiate"),
    (("打", "交火", "伏击", "袭击", "突围", "拦"), "fight"),
    (("撤", "退", "离开", "出塔", "封"), "flee"),
    (("离开", "离队", "出走"), "depart"),
    (("回来", "归队", "返回"), "return"),
    (("发现", "找到", "查", "核对", "比对", "验"), "discover"),
    (("救", "护", "拖", "拉起"), "rescue"),
    (("守", "看住", "盯"), "protect"),
    (("封死", "爆破", "炸", "永久封闭"), "seal"),
    (("开", "开门", "开启"), "open"),
    (("交易", "交换", "换"), "trade"),
    (("挖", "刨", "拆", "起出", "拓"), "search"),
)

STATE_RULES: tuple[tuple[tuple[str, ...], str, str, str], ...] = (
    (("伏击", "公开争夺", "争夺盐路"), "salt_route_control", "uncontrolled", "contested"),
    (("按趟结算", "归铁锈集", "控制权", "掌握盐路"), "salt_route_control", "contested",
     "controlled_by_rust_settlement"),
    (("第零层",), "zero_layer_access", "closed", "operational"),
    (("第一次打开", "第七次", "门开"), "zero_layer_access", "operational", "first_opened"),
    (("紧急锁闭", "撤销开放权限", "锁死"), "zero_layer_access", "first_opened",
     "emergency_locked"),
    (("永久封死", "彻底封死", "爆破主通道"), "zero_layer_access", "emergency_locked",
     "permanently_sealed"),
    (("草案",), "common_rules_status", "idea", "draft"),
    (("征求意见", "批注"), "common_rules_status", "draft", "consulted"),
    (("表决", "投票"), "common_rules_status", "consulted", "voted"),
    (("修订",), "common_rules_status", "voted", "revised"),
    (("正式签署", "并列署名", "正式生效"), "common_rules_status", "approved", "signed"),
    (("共守规矩成立", "新秩序成立", "共守规矩正式"), "common_rules_status", "approved", "signed"),
    (("阿灰", "它"), "dog_departure_status", "present", "considering"),
    (("跟着那只同类", "随外部队伍离开", "自主离开"), "dog_departure_status", "considering",
     "voluntarily_departed"),
    (("第一夜", "没有脚印回来", "留在据点"), "dog_departure_status", "voluntarily_departed",
     "absent_waiting"),
    (("自己走回", "主动回来", "自己回来"), "dog_departure_status", "absent_waiting",
     "voluntarily_returned"),
    (("部分档案", "前一份档案"), "archive_publication_level", "unpublished", "partial_release"),
    (("第二份", "验证者名单"), "archive_publication_level", "partial_release",
     "second_archive_verified"),
    (("第三份",), "archive_publication_level", "second_archive_verified",
     "third_archive_pending"),
    (("第三份档案公开", "交叉验证"), "archive_publication_level", "third_archive_pending",
     "third_archive_released"),
    (("灰墙",), "gray_wall_observation_status", "unobserved", "observed_on_page"),
    (("旧路", "旧地图", "旧路标"), "gray_wall_observation_status", "observed_on_page", "mapped"),
)


AMBIGUOUS_ENTITY = "AMBIGUOUS_ENTITY"


class LegacyChapterMigration:
    """把 legacy chapter dict 解析成 provisional IR（Pilot 使用）。"""

    def __init__(self, *, novel_id: str, dog_id: str = "", dog_name: str = "阿灰",
                 protagonist_id: str = "", actor_names: dict[str, str] | None = None) -> None:
        self.novel_id = novel_id
        self.dog_id = dog_id
        self.dog_name = dog_name
        self.protagonist_id = protagonist_id
        self.actor_names = dict(actor_names or {})

    # ---- 入口 -------------------------------------------------------------
    def migrate(self, chapter: Mapping[str, Any], *, name_to_id: dict[str, str] | None = None,
                index: int = 0) -> ChapterSemanticIR:
        names = name_to_id or {}
        events = self._events(chapter, names)
        effects = self._effects(chapter, events)
        transitions = self._transitions(chapter, events)
        dog = self._dog(chapter, events)
        ir = ChapterSemanticIR(
            chapter_uuid=str(chapter.get("chapter_uuid") or ""),
            novel_id=self.novel_id,
            volume_id=f"V{chapter.get('volume')}" if chapter.get("volume") else "",
            arc_id=str(chapter.get("arc") or ""),
            temporal_position=chapter.get("display_number") or chapter.get("index") or index,
            location_ids=[str(chapter.get("location"))] if chapter.get("location") else [],
            participant_ids=sorted({actor for event in events for actor in event.actor_ids}),
            event_frames=events, effects=effects, state_transitions=transitions,
            dog=dog, provenance="imported",
            legacy_chapter_label=str(chapter.get("id") or ""),
            goal=str(chapter.get("goal") or ""))
        ir.field_evidence = self._field_evidence(chapter, ir)
        return ir

    # ---- events -----------------------------------------------------------
    def _events(self, chapter: Mapping[str, Any],
                names: dict[str, str]) -> list[ChapterEventFrame]:
        frames: list[ChapterEventFrame] = []
        for order, raw in enumerate(chapter.get("events") or [], start=1):
            text = str(raw)
            actors = [entity for name, entity in names.items() if name and name in text]
            action_type = self._action_type(text)
            decision_action = self._decision_action(text, order, total=len(chapter.get("events") or []))
            frames.append(ChapterEventFrame(
                event_id=f"CE_{order:03d}",
                actor_ids=sorted(set(actors)),
                action_type=action_type,
                decision_action=decision_action,
                changes_followup_path=bool(decision_action),
                has_alternative=any(token in text for token in
                                    ("不", "还是", "两者", "或", "否则", "换", "改")),
                action_text=text,
                temporal_order=order,
                agency=self._agency(text),
                intent="",
                physical_presence=self.dog_name in text,
                confidence=0.6, provenance="imported"))
        return frames

    @staticmethod
    def _action_type(text: str) -> str:
        for keywords, action_type in ACTION_RULES:
            if any(keyword in text for keyword in keywords):
                return action_type
        return "action"

    @staticmethod
    def _decision_action(text: str, order: int, *, total: int) -> str:
        """decision 必须同时满足：actor（由调用方提供）、alternative/commitment、改变后续路径。"""

        has_alternative = any(token in text for token in
                              ("不", "还是", "两者", "或", "否则", "换", "改", "拒绝", "放弃"))
        has_commitment = any(token in text for token in
                             ("决定", "签", "担", "接受", "定下", "通过", "驳回"))
        for keywords, action in DECISION_RULES:
            if any(keyword in text for keyword in keywords):
                if has_alternative or has_commitment or order >= max(1, total - 1):
                    return action
        return ""

    @staticmethod
    def _assertion_mode(text: str, state_key: str, to_state: str) -> str:
        for keywords, mode in ASSERTION_RULES:
            if any(keyword in text for keyword in keywords):
                return mode
        markers = TRANSITION_ACTION_MARKERS.get(to_state, ())
        if markers and any(marker in text for marker in markers):
            return "transition"
        return "transition" if any(
            verb in text for verb in ("封死", "爆破", "签署", "表决", "离开", "回来", "打开",
                                      "锁闭", "谈成", "生效")) else "observation"

    @staticmethod
    def _agency(text: str) -> str:
        if DOG_INDEPENDENT_PATTERN.search(text):
            return "autonomous"
        if any(keyword in text for keyword in ("被迫", "被逼", "只能")):
            return "forced"
        if any(keyword in text for keyword in ("系统", "门禁", "潮", "规则")):
            return "systemic"
        return "reactive"

    # ---- effects ----------------------------------------------------------
    def _effects(self, chapter: Mapping[str, Any],
                 events: Sequence[ChapterEventFrame]) -> list[ChapterEffect]:
        effects: list[ChapterEffect] = []
        counter = 1
        loss_text = str(chapter.get("loss") or "")
        cost_text = str(chapter.get("cost") or "")
        injury = str(chapter.get("injury_delta") or "")
        resources = chapter.get("resource_delta") or {}
        negative_text = " ".join([loss_text, cost_text])
        if negative_text.strip() or injury or resources:
            polarity = "negative"
            after = loss_text or cost_text or injury or "资源减少"
            effects.append(ChapterEffect(
                effect_id=f"EF_{counter:03d}", effect_type="cost",
                target_type="party", target_id=self.actor_names.get(self.protagonist_id, "本方"),
                before_state="", after_state=after[:120], polarity=polarity,
                caused_by_event_ids=[event.event_id for event in events[:2]],
                resource_delta=resources if isinstance(resources, dict) else {},
                injury_delta=[injury] if injury else [], reversible=True,
                is_narrative_pivot=bool(injury) or "暴露" in negative_text,
                confidence=0.6))
            counter += 1
        payoff_text = str(chapter.get("payoff") or "")
        if payoff_text.strip():
            effects.append(ChapterEffect(
                effect_id=f"EF_{counter:03d}", effect_type="gain", target_type="goal",
                target_id="chapter_goal", after_state=payoff_text[:120], polarity="positive",
                caused_by_event_ids=[events[-1].event_id] if events else [],
                reversible=True, is_narrative_pivot=False, confidence=0.6))
            counter += 1
        turn_text = str(chapter.get("turn") or "")
        if turn_text and any(marker in turn_text for marker in
                             ("翻", "反转", "暴露", "确认", "交出", "易手", "被夺", "夺回",
                              "发现", "真相", "身份", "权限", "改写")):
            effects.append(ChapterEffect(
                effect_id=f"EF_{counter:03d}", effect_type="narrative_pivot",
                target_type="situation", target_id="chapter_turn", after_state=turn_text[:120],
                polarity="mixed", caused_by_event_ids=[events[-1].event_id] if events else [],
                reversible=True, is_narrative_pivot=True, confidence=0.6))
            counter += 1
        if not effects and events:
            effects.append(ChapterEffect(
                effect_id="EF_001", effect_type="state_change", target_type="situation",
                target_id="chapter", after_state=events[-1].action_text[:120],
                polarity="neutral", caused_by_event_ids=[events[-1].event_id],
                reversible=True, confidence=0.5))
        return effects

    # ---- transitions ------------------------------------------------------
    def _transitions(self, chapter: Mapping[str, Any],
                     events: Sequence[ChapterEventFrame]) -> list[ChapterStateTransition]:
        text = " ".join([str(chapter.get("goal") or ""),
                         *[str(item) for item in (chapter.get("events") or [])],
                         str(chapter.get("world_state_change") or ""),
                         str(chapter.get("end_state") or "")])
        transitions: list[ChapterStateTransition] = []
        current: dict[str, str] = {}
        events_text = " ".join(str(item) for item in (chapter.get("events") or []))
        for keywords, state_key, from_state, to_state in STATE_RULES:
            if any(keyword in text for keyword in keywords):
                # 不可逆推进必须在本章 events 里真的有动作，回指不算
                if to_state == "permanently_sealed" and not any(
                        verb in events_text for verb in ("爆破", "封死", "炸塌", "封层")):
                    continue
                mode = self._assertion_mode(text, state_key, to_state)
                chain_from = current.get(state_key, from_state)
                if chain_from == to_state:
                    continue
                transitions.append(ChapterStateTransition(
                    transition_id=f"ST_{len(transitions) + 1:03d}", state_key=state_key,
                    subject_id=self.actor_names.get(self.protagonist_id, ""),
                    from_state=chain_from, to_state=to_state,
                    caused_by_event_ids=[event.event_id for event in events[:1]],
                    prerequisite_state=chain_from,
                    transition_kind="irreversible" if to_state in
                    ("permanently_sealed", "signed") else "progression",
                    effective_at=chapter.get("display_number") or chapter.get("index"),
                    canonical_event_id="", assertion_mode=mode))
                current[state_key] = to_state
        return transitions

    # ---- dog --------------------------------------------------------------
    def _dog(self, chapter: Mapping[str, Any],
             events: Sequence[ChapterEventFrame]) -> DogRoleBinding:
        text = " ".join([str(chapter.get("goal") or ""),
                         *[str(item) for item in (chapter.get("events") or [])],
                         str(chapter.get("dog_note") or "")])
        mentions = [event for event in events if self.dog_name in event.action_text]
        performed = any(verb in event.action_text for event in mentions
                        for verb in DOG_ACTION_VERBS)
        autonomous = any(event.agency == "autonomous" for event in mentions)
        passive_only = bool(mentions) and all(
            DOG_PASSIVE_PATTERN.search(event.action_text) for event in mentions)
        presence = bool(mentions) and not passive_only
        legacy_role = str(chapter.get("dog_role") or "")
        if not mentions and self.dog_name not in text:
            role = "absent"
        elif autonomous and presence:
            role = "independent"
        elif performed and presence:
            role = "supportive"
        elif not presence and self.dog_name in text:
            role = "offscreen_effect"
        elif mentions:
            role = "involved"
        else:
            role = legacy_role or "absent"
        return DogRoleBinding(
            role=role, evidence_event_ids=[event.event_id for event in mentions],
            effect_ids=[], physical_presence=presence, autonomous=autonomous,
            affects_decision_or_state=bool(mentions) or role == "offscreen_effect")

    # ---- field evidence ----------------------------------------------------
    def _field_evidence(self, chapter: Mapping[str, Any],
                        ir: ChapterSemanticIR) -> list[FieldEvidence]:
        evidence: list[FieldEvidence] = []
        negative = [effect.effect_id for effect in ir.effects
                    if effect.polarity in ("negative", "mixed")]
        positive = [effect.effect_id for effect in ir.effects
                    if effect.polarity in ("positive", "mixed")]
        transitions = [item.transition_id for item in ir.state_transitions]
        # decision evidence 只看结构化的 decision_action（taxonomy），不看 action_type 分类
        decision_events = [event.event_id for event in ir.event_frames if event.decision_action]
        evidence.append(FieldEvidence(field_name="decision", event_ids=decision_events,
                                      evidence_type="direct", confidence=0.6))
        evidence.append(FieldEvidence(field_name="cost", effect_ids=negative,
                                      evidence_type="derived", confidence=0.6))
        evidence.append(FieldEvidence(field_name="loss", effect_ids=negative,
                                      evidence_type="derived", confidence=0.6))
        evidence.append(FieldEvidence(field_name="turn", transition_ids=transitions,
                                      effect_ids=[effect.effect_id for effect in ir.effects
                                                  if effect.is_narrative_pivot],
                                      event_ids=[event.event_id for event in ir.event_frames][-1:],
                                      evidence_type="derived", confidence=0.6))
        evidence.append(FieldEvidence(field_name="payoff", effect_ids=positive,
                                      evidence_type="derived", confidence=0.6))
        evidence.append(FieldEvidence(field_name="world_state_change",
                                      transition_ids=transitions, evidence_type="direct",
                                      confidence=0.6))
        evidence.append(FieldEvidence(
            field_name="information_release",
            event_ids=[event.event_id for event in ir.event_frames
                       if event.action_type in ("discover", "negotiate", "open")],
            evidence_type="derived", confidence=0.5))
        evidence.append(FieldEvidence(field_name="dog_role",
                                      event_ids=list(ir.dog.evidence_event_ids),
                                      effect_ids=list(ir.dog.effect_ids),
                                      evidence_type="direct", confidence=0.6))
        return evidence

    # ---- disposition / pollution -------------------------------------------
    def finalize(self, ir: ChapterSemanticIR, chapter: Mapping[str, Any],
                 findings_codes: Sequence[str]) -> ChapterSemanticIR:
        """标 disposition 与 legacy 字段污染计数；不自动补事实。"""

        code_set = set(findings_codes)
        ir.legacy_field_copy_removed = self.legacy_field_copy_count(chapter, ir)
        ir.migration_disposition = self.disposition(ir, code_set)
        return ir

    @staticmethod
    def disposition(ir: ChapterSemanticIR, code_set: set[str],
                    *, blocked_fields: Sequence[str] = ()) -> str:
        """READY_TO_COMPILE 收紧：任何 blocked / 歧义实体 / 状态冲突都不算 ready。"""

        if ir.ambiguous_entity_ids or AMBIGUOUS_ENTITY in code_set:
            return "MIGRATION_AMBIGUOUS"
        if {"PREMATURE_STATE_TRANSITION", "REPEATED_IRREVERSIBLE_TRANSITION",
                "ILLEGAL_STATE_EDGE", "UNKNOWN_STATE_KEY"} & code_set:
            return "NEEDS_CONTENT_REPAIR"
        if blocked_fields:
            return "NEEDS_CONTENT_REPAIR"
        if {"DOG_BINDING_PLUMBING_ERROR", "DOG_ROLE_PRESENCE_MISMATCH"} & code_set:
            return "PRODUCT_RULE_REVIEW"
        if {"DOG_ROLE_WITHOUT_EVIDENCE", "MIGRATION_AMBIGUOUS"} & code_set:
            return "MIGRATION_AMBIGUOUS"
        if {"DECISION_WITHOUT_DECISION_EVENT", "TURN_WITHOUT_TRANSITION",
                "PAYOFF_WITHOUT_EFFECT", "WORLD_STATE_WITHOUT_TRANSITION",
                "COST_WITHOUT_NEGATIVE_EFFECT", "LOSS_WITHOUT_NEGATIVE_EFFECT"} & code_set:
            return "NEEDS_CONTENT_REPAIR"
        return "READY_TO_COMPILE"

    def legacy_field_copy_count(self, chapter: Mapping[str, Any],
                               ir: ChapterSemanticIR) -> int:
        event_texts = {event.action_text.strip().rstrip("。") for event in ir.event_frames}
        count = 0
        for field_name in ("decision", "cost", "loss", "turn", "payoff"):
            value = str(chapter.get(field_name) or "").strip().rstrip("。")
            if value and value in event_texts:
                count += 1
        return count
