"""C08：SemanticIndex —— 只负责找 candidate 与分类关系，不做事实裁判。"""

from __future__ import annotations

import re
from typing import Literal, Protocol

from pydantic import Field

from novelforge.models import StrictModel

Relation = Literal["duplicate", "legitimate_recurrence", "consequence", "escalation",
                   "reinterpretation", "payoff", "unrelated", "uncertain"]
REPEATABLE_TYPES = {"patrol", "trade", "daily_work", "recurring_attack"}


class EventSemanticSignature(StrictModel):
    event_id: str = Field(min_length=3, max_length=160)
    canonical_event_id: str = Field(default="", max_length=160)
    subjects: list[str] = Field(default_factory=list)
    action: str = Field(default="", max_length=200)
    objects: list[str] = Field(default_factory=list)
    location: str = Field(default="", max_length=120)
    decision: str = Field(default="", max_length=200)
    reveal: str = Field(default="", max_length=200)
    consequence: str = Field(default="", max_length=200)
    event_type: str = Field(default="major", max_length=48)
    narrative_role: str = Field(default="canonical", max_length=32)
    temporal_role: str = Field(default="", max_length=32)
    can_repeat: bool = False
    repeat_rule: str = Field(default="", max_length=200)
    status: str = Field(default="planned", max_length=32)
    semantic_summary: str = Field(default="", max_length=400)

    @classmethod
    def from_event(cls, event) -> "EventSemanticSignature":
        return cls(event_id=event.event_id, canonical_event_id=event.canonical_event_id,
                   subjects=list(event.subjects), objects=list(event.objects),
                   action=event.canonical_name or event.semantic_summary,
                   location=event.location, event_type=event.event_type,
                   narrative_role=event.narrative_role, can_repeat=event.can_repeat,
                   repeat_rule=event.repeat_rule, status=event.status,
                   semantic_summary=event.semantic_summary)


class SemanticCandidate(StrictModel):
    event_id: str
    score: float = Field(ge=0, le=1)
    relation: Relation = "uncertain"
    reasons: list[str] = Field(default_factory=list)


class SemanticIndex(Protocol):  # pragma: no cover - 接口
    def index_event(self, signature: EventSemanticSignature) -> None: ...
    def remove_event(self, event_id: str) -> None: ...
    def get_event(self, event_id: str) -> EventSemanticSignature | None: ...
    def candidates(self, signature: EventSemanticSignature, *, top_k: int = 5,
                   threshold: float = 0.3) -> list[SemanticCandidate]: ...
    def compare_signature(self, a: EventSemanticSignature,
                          b: EventSemanticSignature) -> float: ...
    def classify_relation(self, a: EventSemanticSignature,
                          b: EventSemanticSignature) -> Relation: ...
    def clear(self) -> None: ...
    def rebuild(self, signatures: list[EventSemanticSignature]) -> None: ...


def _tokens(text: str) -> set[str]:
    clean = re.sub(r"[^\w\u4e00-\u9fff]+", " ", (text or "").lower())
    words = {w for w in clean.split() if len(w) > 1}
    grams = {clean[i:i + 2].strip() for i in range(max(0, len(clean) - 1))}
    return {t for t in words | grams if t}


def _jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


class LocalSemanticIndex:
    """零外部依赖的默认 backend：token / n-gram + 结构化字段重叠。"""

    backend = "local"

    def __init__(self) -> None:
        self._rows: dict[str, EventSemanticSignature] = {}

    # ---- 基础 -------------------------------------------------------------
    def index_event(self, signature: EventSemanticSignature) -> None:
        self._rows[signature.event_id] = signature

    def remove_event(self, event_id: str) -> None:
        self._rows.pop(event_id, None)

    def get_event(self, event_id: str) -> EventSemanticSignature | None:
        return self._rows.get(event_id)

    def clear(self) -> None:
        self._rows.clear()

    def rebuild(self, signatures: list[EventSemanticSignature]) -> None:
        self.clear()
        for signature in signatures:
            self.index_event(signature)

    def events(self) -> list[EventSemanticSignature]:
        return [self._rows[key] for key in sorted(self._rows)]

    # ---- 相似度与分类 -----------------------------------------------------
    def compare_signature(self, a: EventSemanticSignature, b: EventSemanticSignature) -> float:
        text = _jaccard(_tokens(a.semantic_summary or a.action),
                        _tokens(b.semantic_summary or b.action))
        subjects = _jaccard(set(a.subjects), set(b.subjects))
        objects = _jaccard(set(a.objects), set(b.objects))
        same_place = 1.0 if a.location and a.location == b.location else 0.0
        same_type = 1.0 if a.event_type and a.event_type == b.event_type else 0.0
        shared_action = 1.0 if a.action and a.action == b.action else \
            _jaccard(_tokens(a.action), _tokens(b.action))
        score = (0.3 * text + 0.2 * subjects + 0.15 * objects + 0.15 * shared_action
                 + 0.1 * same_place + 0.1 * same_type)
        return round(min(1.0, score), 4)

    def classify_relation(self, a: EventSemanticSignature,
                          b: EventSemanticSignature) -> Relation:
        """规则优先级：显式 canonical 关系 > 结构化签名 > 语义相似度。"""

        if b.canonical_event_id and b.canonical_event_id == a.event_id:
            return {"consequence": "consequence", "escalation": "escalation",
                    "reinterpretation": "reinterpretation", "payoff": "payoff",
                    "recurrence": "legitimate_recurrence"}.get(b.narrative_role, "uncertain")
        if a.canonical_event_id and a.canonical_event_id == b.event_id:
            return "consequence"
        repeatable = (a.can_repeat or b.can_repeat
                      or a.event_type in REPEATABLE_TYPES or b.event_type in REPEATABLE_TYPES
                      or a.narrative_role == "recurrence" or b.narrative_role == "recurrence")
        score = self.compare_signature(a, b)
        same_action = a.action and a.action == b.action
        same_subjects = bool(set(a.subjects) & set(b.subjects))
        same_location = bool(a.location) and a.location == b.location
        if repeatable and score >= 0.3:
            return "legitimate_recurrence"
        if score >= 0.72 and same_subjects and (same_action or same_location):
            return "duplicate"
        if score >= 0.5:
            return "uncertain"
        return "unrelated"

    def candidates(self, signature: EventSemanticSignature, *, top_k: int = 5,
                   threshold: float = 0.3) -> list[SemanticCandidate]:
        rows: list[SemanticCandidate] = []
        for event_id in sorted(self._rows):
            if event_id == signature.event_id:
                continue
            other = self._rows[event_id]
            score = self.compare_signature(signature, other)
            if score < threshold:
                continue
            rows.append(SemanticCandidate(event_id=event_id, score=score,
                                          relation=self.classify_relation(other, signature)))
        rows.sort(key=lambda item: (-item.score, item.event_id))
        return rows[:top_k]
