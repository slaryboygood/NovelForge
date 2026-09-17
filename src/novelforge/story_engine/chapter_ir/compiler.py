"""S03：ChapterFieldCompiler —— 由 IR 渲染 Writer-ready 字段（两层：语义编译 + 文本渲染）。

事实只来自 IR；渲染层只做语言变化，不得引入 IR 中不存在的 event / effect / transition。
"""

from __future__ import annotations

from typing import Iterable

from .models import (
    ChapterEffect,
    ChapterEventFrame,
    ChapterSemanticIR,
    ChapterStateTransition,
    CompiledChapter,
    CompiledField,
    compile_ir_ref,
)

ACTION_LABELS: dict[str, str] = {
    "choice": "做出选择", "decision": "定下做法", "commit": "承担", "refuse": "拒绝",
    "accept": "接受", "order": "下令", "trade": "交换", "fight": "交手", "flee": "撤退",
    "search": "搜索", "observe": "观察", "rescue": "救人", "negotiate": "谈判",
    "protect": "护住", "seal": "封死", "open": "打开", "sign": "署名", "speak": "开口",
    "depart": "离开", "return": "回来", "discover": "发现", "investigate": "查证",
}

# 渲染层变体（只改语言，不改 IR 事实）
DECISION_RENDERERS: dict[str, str] = {
    "choose": "{actor}在两条路里选了后面那条：{detail}",
    "decide": "{actor}当场定下做法：{detail}",
    "refuse": "{actor}没有答应：{detail}",
    "accept": "{actor}接下了条件：{detail}",
    "commit": "{actor}把这件事担了下来：{detail}",
    "defer": "{actor}把决定往后压：{detail}",
    "allow": "{actor}放行：{detail}",
    "forbid": "{actor}当场禁止：{detail}",
    "assign": "{actor}把差事派了下去：{detail}",
    "retain": "{actor}选择留下：{detail}",
    "abandon": "{actor}放弃原路：{detail}",
    "withhold": "{actor}没有交出：{detail}",
    "prioritize": "{actor}把次序改了：{detail}",
    "trade_off": "{actor}用一个代价换一个条件：{detail}",
    "sign": "{actor}落笔签下：{detail}",
    "approve": "{actor}点头通过：{detail}",
    "reject": "{actor}驳回：{detail}",
    "wait": "{actor}按住不动，等一个更合适的时机：{detail}",
    "withdraw": "{actor}撤回原议：{detail}",
}
STATE_LABELS: dict[str, str] = {
    "salt_route_control": "盐路控制权",
    "zero_layer_access": "第零层门禁",
    "common_rules_status": "共守规矩",
    "dog_departure_status": "阿灰的去留",
    "archive_publication_level": "档案公开程度",
    "gray_wall_observation_status": "灰墙观测",
}
STATE_VALUE_LABELS: dict[str, str] = {
    "uncontrolled": "无人控制", "contested": "进入争夺",
    "controlled_by_rust_settlement": "落到铁锈集手里",
    "closed": "封闭", "first_opened": "第一次打开", "operational": "可用",
    "emergency_locked": "紧急锁闭", "inaccessible": "无法进入",
    "permanently_sealed": "永久封死",
    "idea": "只有想法", "draft": "形成草案", "consulted": "征求意见", "voted": "完成表决",
    "revised": "完成修订", "approved": "通过", "signed": "正式签署", "enacted": "生效执行",
    "present": "在场", "considering": "动摇", "voluntarily_departed": "自己离开",
    "absent_waiting": "不在、等它回来", "voluntarily_returned": "自己回来",
    "unpublished": "未公开", "partial_release": "部分公开",
    "second_archive_verified": "第二份档案已核对", "third_archive_pending": "第三份尚未公开",
    "third_archive_released": "第三份已公开",
    "cross_validation_established": "建立交叉验证", "full_public_truth": "真相全公开",
    "unobserved": "未被观测", "recorded_historically": "只有历史记录",
    "observed_on_page": "现场实测到", "mapped": "已测绘",
}
NEGATIVE_RENDERERS: dict[str, str] = {
    "cost": "为了这一步，{subject}付出：{detail}",
    "injury": "{subject}在代价里受了伤：{detail}",
    "exposure": "{subject}因此暴露了位置：{detail}",
    "loss": "{subject}失去了{detail}",
}
PAYOFF_RENDERERS: dict[str, str] = {
    "gain": "这一步换回了{target}：{detail}",
    "resolution": "目标走到头：{detail}",
    "state_change": "局面落定：{detail}",
}


def _label(event: ChapterEventFrame) -> str:
    return ACTION_LABELS.get(event.action_type, "行动")


def _first(events: Iterable[ChapterEventFrame]) -> ChapterEventFrame | None:
    return next(iter(events), None)


class ChapterFieldCompiler:
    """确定性编译：同一 IR 编译两次必须得到同一语义输出。"""

    def __init__(self, *, actor_names: dict[str, str] | None = None,
                 dog_id: str = "", shadow: bool = True) -> None:
        self.actor_names = dict(actor_names or {})
        self.dog_id = dog_id
        self.shadow = shadow

    # ---- 入口 -------------------------------------------------------------
    def compile(self, ir: ChapterSemanticIR) -> CompiledChapter:
        fields: list[CompiledField] = []
        seen_negative_evidence: set[tuple[str, ...]] = set()
        for name in ("decision", "cost", "turn", "payoff", "loss", "information_release",
                     "world_state_change"):
            compiled = self._compile_field(ir, name)
            # cost / loss 去重：同一 negative effect 只能渲染一次
            if compiled is not None and name in ("cost", "loss") and compiled.status == "OK":
                key = tuple(sorted(compiled.compiled_from_effect_ids))
                if key and key in seen_negative_evidence:
                    compiled = CompiledField(field_name=name, text="",
                                             status="NOT_APPLICABLE",
                                             compiled_from_effect_ids=list(key))
                else:
                    seen_negative_evidence.add(key)
            if compiled is not None:
                fields.append(compiled)
        dog_payload = self._compile_dog_payload(ir)
        if dog_payload is not None:
            fields.append(dog_payload)
        return CompiledChapter(chapter_uuid=ir.chapter_uuid,
                               semantic_ir_ref=compile_ir_ref(ir.chapter_uuid),
                               fields=fields, dog_role=ir.dog, dog_payload=dog_payload,
                               shadow=self.shadow)

    # ---- 单字段 -----------------------------------------------------------
    def _compile_field(self, ir: ChapterSemanticIR, field_name: str) -> CompiledField | None:
        evidence = ir.evidence_for(field_name)
        if evidence is None:
            return None
        if field_name == "decision":
            return self._render_decision(ir, evidence.event_ids)
        if field_name in ("cost", "loss"):
            return self._render_negative(ir, field_name, evidence.effect_ids)
        if field_name == "turn":
            return self._render_turn(ir, evidence.transition_ids, evidence.event_ids)
        if field_name == "payoff":
            return self._render_payoff(ir, evidence.effect_ids)
        if field_name == "world_state_change":
            return self._render_world_state(ir, evidence.transition_ids)
        if field_name == "information_release":
            return self._render_information(ir, evidence.event_ids, evidence.effect_ids)
        return None

    def _render_decision(self, ir: ChapterSemanticIR, event_ids: list[str]) -> CompiledField:
        event = next((ir.event(item) for item in event_ids
                      if ir.event(item) and ir.event(item).decision_action), None)
        if event is None:
            return CompiledField(field_name="decision", text="",
                                 status=("NOT_APPLICABLE"
                                         if "decision" in ir.not_applicable_fields
                                         else "BLOCKED_MISSING_EVIDENCE"))
        text = ""
        if event is not None:
            actor = self._name(event.actor_ids[0] if event.actor_ids else "")
            template = DECISION_RENDERERS.get(event.decision_action,
                                              "{actor}{label}：{detail}")
            text = template.format(actor=actor, label=_label(event),
                                   detail=event.intent or event.action_text)
        preview = event.action_text[:200]
        return CompiledField(field_name="decision", text=text.strip("：")[:200],
                             writer_text=preview, compiled_from_event_ids=[event.event_id])

    def _render_negative(self, ir: ChapterSemanticIR, field_name: str,
                         effect_ids: list[str]) -> CompiledField:
        effect = self._first_effect(ir, effect_ids, ("negative", "mixed"))
        if effect is None:
            return CompiledField(field_name=field_name, text="",
                                 status=("NOT_APPLICABLE"
                                         if field_name in ir.not_applicable_fields
                                         else "BLOCKED_MISSING_EVIDENCE"))
        subject = self._name(effect.target_id) if effect.target_id in self.actor_names \
            else (effect.target_id or "本方")
        template = NEGATIVE_RENDERERS.get(effect.effect_type, "{subject}付出代价：{detail}")
        text = template.format(subject=subject, detail=effect.after_state)
        return CompiledField(field_name=field_name, text=text[:200],
                             writer_text=effect.after_state[:200],
                             compiled_from_effect_ids=[effect.effect_id])

    def _render_turn(self, ir: ChapterSemanticIR, transition_ids: list[str],
                     event_ids: list[str]) -> CompiledField:
        transition = self._first_transition(ir, transition_ids)
        if transition is not None:
            text = (f"局势在{transition.state_key}上翻转："
                    f"{transition.from_state} → {transition.to_state}")
            return CompiledField(field_name="turn", text=text[:200],
                                 writer_text=(f"{STATE_LABELS.get(transition.state_key, '局势')}"
                                              f"从{STATE_VALUE_LABELS.get(transition.from_state, transition.from_state)}"
                                              f"变为{STATE_VALUE_LABELS.get(transition.to_state, transition.to_state)}"),
                                 compiled_from_transition_ids=[transition.transition_id])
        pivot = next((ir.effect(item) for item in (ir.evidence_for("turn").effect_ids
                                                   if ir.evidence_for("turn") else [])
                      if ir.effect(item) and ir.effect(item).is_narrative_pivot), None)
        if pivot is None:
            return CompiledField(field_name="turn", text="",
                                 status=("NOT_APPLICABLE"
                                         if "turn" in ir.not_applicable_fields
                                         else "BLOCKED_MISSING_EVIDENCE"))
        return CompiledField(field_name="turn",
                             text=f"局面从此不同：{pivot.after_state}"[:200],
                             writer_text=pivot.after_state[:200],
                             compiled_from_effect_ids=[pivot.effect_id])

    def _render_payoff(self, ir: ChapterSemanticIR, effect_ids: list[str]) -> CompiledField:
        effect = self._first_effect(ir, effect_ids, ("positive", "mixed"))
        if effect is None:
            return CompiledField(field_name="payoff", text="",
                                 status=("NOT_APPLICABLE"
                                         if "payoff" in ir.not_applicable_fields
                                         else "BLOCKED_MISSING_EVIDENCE"))
        target = effect.target_id or "本章目标"
        if target in self.actor_names:
            target = self.actor_names[target]
        text = PAYOFF_RENDERERS.get(effect.effect_type,
                                    "{target}达成：{detail}").format(
            target=target, detail=effect.after_state)
        return CompiledField(field_name="payoff", text=text[:200],
                             writer_text=effect.after_state[:200],
                             compiled_from_effect_ids=[effect.effect_id])

    def _render_world_state(self, ir: ChapterSemanticIR,
                            transition_ids: list[str]) -> CompiledField:
        transition = self._first_transition(ir, transition_ids)
        if transition is None:
            return CompiledField(field_name="world_state_change", text="",
                                 status=("NOT_APPLICABLE"
                                         if "world_state_change" in ir.not_applicable_fields
                                         else "BLOCKED_MISSING_EVIDENCE"))
        if transition.assertion_mode != "transition" or transition.narrative_role == "derived":
            return CompiledField(field_name="world_state_change", text="",
                                 status="BLOCKED_MISSING_EVIDENCE")
        text = (f"{self._state_text(transition.state_key, transition.from_state)}"
                f"→{self._state_text(transition.state_key, transition.to_state)}")
        return CompiledField(field_name="world_state_change", text=text[:200],
                             compiled_from_transition_ids=[transition.transition_id])

    @staticmethod
    def _state_text(state_key: str, state: str) -> str:
        label = STATE_LABELS.get(state_key, state_key)
        value = STATE_VALUE_LABELS.get(state, state)
        return f"{label}{value}" if value and not label.endswith(value) else label

    def _render_information(self, ir: ChapterSemanticIR, event_ids: list[str],
                            effect_ids: list[str]) -> CompiledField:
        event = next((ir.event(item) for item in event_ids if ir.event(item)), None)
        effect = self._first_effect(ir, effect_ids, ("positive", "neutral", "mixed"))
        text = ""
        if event is not None and event.fact_refs:
            text = f"信息释放：{event.fact_refs[0]}"
        elif effect is not None and effect.knowledge_delta:
            text = f"信息释放：{effect.knowledge_delta[0]}"
        if not text:
            return CompiledField(field_name="information_release", text="",
                                 status=("NOT_APPLICABLE"
                                         if "information_release" in ir.not_applicable_fields
                                         else "BLOCKED_MISSING_EVIDENCE"))
        return CompiledField(field_name="information_release", text=text[:200],
                             compiled_from_event_ids=[event.event_id] if event else [],
                             compiled_from_effect_ids=[effect.effect_id] if effect else [])

    def _compile_dog_payload(self, ir: ChapterSemanticIR) -> CompiledField | None:
        dog = ir.dog
        if dog.role == "absent":
            return CompiledField(field_name="dog_action", text="",
                                 compiled_from_event_ids=list(dog.evidence_event_ids))
        event = next((ir.event(item) for item in dog.evidence_event_ids if ir.event(item)), None)
        if event is None:
            return CompiledField(field_name="dog_action", text="",
                                 status=("NOT_APPLICABLE"
                                         if dog.role in ("absent", "offscreen_effect")
                                         else "BLOCKED_MISSING_EVIDENCE"))
        text = event.action_text
        if dog.role == "supportive":
            text = f"{event.action_text}，直接帮上了本章目标"
        elif dog.role == "independent":
            text = f"{event.action_text}（它自己的选择）"
        elif dog.role == "offscreen_effect":
            text = f"它不在场，但{event.action_text}改变了当前的取舍"
        return CompiledField(field_name="dog_action", text=text[:200],
                             compiled_from_event_ids=[event.event_id],
                             compiled_from_effect_ids=list(dog.effect_ids))

    # ---- 工具 -------------------------------------------------------------
    def _name(self, actor_id: str) -> str:
        if not actor_id:
            return "主角"
        if actor_id in self.actor_names:
            return self.actor_names[actor_id]
        # 绝不把 machine id 写进 writer 文本
        return "对方势力" if actor_id.startswith("ENTITY_FACTION_") else (
            "对方" if actor_id.startswith("ENTITY_") else actor_id)

    @staticmethod
    def _first_effect(ir: ChapterSemanticIR, effect_ids: list[str],
                      polarities: tuple[str, ...]) -> ChapterEffect | None:
        for effect_id in effect_ids:
            effect = ir.effect(effect_id)
            if effect is not None and effect.polarity in polarities:
                return effect
        return None

    @staticmethod
    def _first_transition(ir: ChapterSemanticIR,
                          transition_ids: list[str]) -> ChapterStateTransition | None:
        for transition_id in transition_ids:
            transition = next((item for item in ir.state_transitions
                               if item.transition_id == transition_id), None)
            if transition is not None:
                return transition
        return None
