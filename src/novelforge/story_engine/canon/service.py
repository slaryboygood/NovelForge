"""C02：CanonService —— 稳定身份生命周期（immutable happened / planned promotion / source mapping）。"""

from __future__ import annotations

from typing import Any

from .ids import new_canon_id
from .models import (
    CanonEvent,
    CanonFact,
    CanonRenderRef,
    CanonSourceMapping,
)
from .repository import CanonRepository

PROTECTED_FACT_FIELDS = {"fact_id", "canonical_key", "category", "canonical_description",
                         "status", "immutable"}
REPEATABLE_EVENT_TYPES = {"patrol", "trade", "daily_work", "recurring_attack"}


class CanonServiceError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class CanonService:
    """业务层：只通过 repository 访问 SQL；不引入第二套 runtime truth。"""

    def __init__(self, repository: CanonRepository) -> None:
        self.repository = repository

    # ---- facts ------------------------------------------------------------
    def import_fact(self, fact: CanonFact, *, source_type: str, source_stable_key: str) -> CanonFact:
        """幂等导入：同一 source 永远复用同一个 fact_id。"""

        existing = self.repository.find_mapping(
            fact.novel_id, source_type, source_stable_key, "fact")
        if existing is not None:
            for row in self.repository.facts(fact.novel_id):
                if row.fact_id == existing.canon_id:
                    return row
            return fact
        self.repository.save_fact(fact)
        self.repository.save_mapping(CanonSourceMapping(
            novel_id=fact.novel_id, source_type=source_type,
            source_stable_key=source_stable_key, canon_type="fact", canon_id=fact.fact_id))
        return fact

    def new_fact(self, *, novel_id: str, category: str, description: str,
                 status: str = "planned") -> CanonFact:
        key = new_canon_id("fact").split("_", 1)[1]
        return CanonFact(fact_id=f"FACT_{key}", canonical_key=key, novel_id=novel_id,
                         category=category, canonical_description=description, status=status,
                         provenance="generated")

    def update_fact(self, fact_id: str, changes: dict[str, Any]) -> CanonFact:
        current = next((f for f in self.repository.facts(
            self._novel_of(fact_id)) if f.fact_id == fact_id), None)
        if current is None:
            raise CanonServiceError("FACT_NOT_FOUND", f"找不到事实 {fact_id}")
        if current.status == "happened":
            illegal = sorted(set(changes) & PROTECTED_FACT_FIELDS)
            if illegal:
                raise CanonServiceError(
                    "HAPPENED_FACT_IMMUTABLE",
                    f"已发生事实不可改写：{', '.join(illegal)}；请用新事实 + SUPERSEDES 链表达")
        updated = current.model_copy(update=changes)
        self.repository.save_fact(updated)
        return updated

    def _novel_of(self, canon_id: str) -> str:
        rows = self.repository._connection.execute(
            "SELECT novel_id FROM canon_facts WHERE fact_id = ?", (canon_id,)).fetchone()
        return rows["novel_id"] if rows else ""

    # ---- events -----------------------------------------------------------
    def promote_event(self, event_id: str, *, render_ref: CanonRenderRef | None = None,
                      novel_id: str = "") -> CanonEvent:
        """planned → occurred：保留 event_id，不产生第二个逻辑相同事件。"""

        rows = [e for e in self.repository.events(novel_id) if e.event_id == event_id]
        if not rows:
            raise CanonServiceError("EVENT_NOT_FOUND", f"找不到事件 {event_id}")
        event = rows[0]
        if event.status == "occurred":
            return event
        if event.status not in ("planned",):
            raise CanonServiceError("EVENT_NOT_PROMOTABLE",
                                    f"{event_id} 当前状态 {event.status} 不能升级为 occurred")
        updated = event.model_copy(update={
            "status": "occurred",
            "first_occurrence_ref": render_ref or event.first_occurrence_ref,
            "can_repeat": event.can_repeat or event.event_type in REPEATABLE_EVENT_TYPES})
        self.repository.save_event(updated)
        return updated

    def match_promotion(self, planned: CanonEvent, candidate: CanonEvent) -> bool:
        """Promotion Matcher：显式 id → 类型/参与者/地点 → 时间邻域；不确定就不合并。"""

        if planned.canonical_key == candidate.canonical_key:
            return True
        if planned.event_id == candidate.event_id:
            return True
        same_type = planned.event_type == candidate.event_type
        same_place = bool(planned.location) and planned.location == candidate.location
        shared = set(planned.subjects) & set(candidate.subjects)
        near = (planned.temporal_position is not None
                and candidate.temporal_position is not None
                and abs(planned.temporal_position - candidate.temporal_position) <= 3)
        strong = same_type and same_place and bool(shared)
        return bool(strong and near)

    def new_event(self, *, novel_id: str, name: str, summary: str, event_type: str = "major",
                  narrative_role: str = "canonical", canonical_event_id: str = "",
                  status: str = "planned") -> CanonEvent:
        key = new_canon_id("event").split("_", 1)[1]
        return CanonEvent(event_id=f"EVENT_{key}", canonical_key=key, novel_id=novel_id,
                          canonical_name=name, semantic_summary=summary,
                          event_type=event_type, narrative_role=narrative_role,
                          canonical_event_id=canonical_event_id, status=status,
                          can_repeat=event_type in REPEATABLE_EVENT_TYPES,
                          provenance="generated")
