"""C05：CanonContextBuilder —— 决定「LLM 到底看到什么」。

三种视图：

- PlannerContext：happened immutable canon + planned + constraints + possibilities（明确分层）；
- CharacterContext：只有该 holder 已知 / 怀疑 / 误信的内容（Knowledge Leak 第二道防线）；
- WriterContext：自然语言，隐藏全部内部 ID / 章节号 / Arc，planned 不得写成已发生。
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import Field

from novelforge.models import StrictModel

from .repository import CanonRepository

ContextType = Literal["HAPPENED", "PLANNED", "CONSTRAINT", "POSSIBILITY"]
Purpose = Literal["planner", "character", "writer"]

ID_PATTERN = re.compile(r"\b(?:FACT|EVENT|KNW|REL|FS|CON)_[A-Z0-9_]+")
CHAPTER_PATTERN = re.compile(r"\bch\d{3}\b")
ARC_PATTERN = re.compile(r"\bV\d+-A\d|\bArc\s*[A-Z0-9]+|\b第\d+卷")
# 内部字段名（规划器语言）：出现在 writer-visible 文本里就是元数据泄漏
INTERNAL_FIELD_PATTERN = re.compile(
    r"\b(?:source_ref|source_refs|context_manifest_id|chapter_uuid|arc_ref|volume_ref|"
    r"canon_fact_ids|canon_event_ids|canon_source_refs)\b", re.I)

# 裁剪优先级（数字越小越先保留）；P0/P1 与 constraint / knowledge boundary 永不裁剪
P0, P1, P2, P3, P4 = 0, 1, 2, 3, 4
NEVER_TRIM = {P0, P1}

# 伏笔真相锁定时的占位描述：writer / planner 可见，但不泄漏 intended_payoff
LOCKED_FORESHADOW_TEXT = "（未揭示的伏笔，具体内容锁定）"


class ContextEntry(StrictModel):
    canon_id: str = Field(min_length=3, max_length=160)
    type: ContextType
    status: str = Field(default="", max_length=32)
    canonical_description: str = Field(default="", max_length=400)
    provenance: str = Field(default="", max_length=32)
    temporal_position: int | None = Field(default=None, ge=0)
    relevance_reason: str = Field(default="", max_length=200)
    priority: int = Field(default=P2, ge=0, le=9)
    payload: dict[str, Any] = Field(default_factory=dict)


class ContextManifest(StrictModel):
    context_id: str = Field(min_length=3, max_length=80)
    novel_id: str = Field(min_length=1, max_length=96)
    purpose: Purpose
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    included_fact_ids: list[str] = Field(default_factory=list)
    included_event_ids: list[str] = Field(default_factory=list)
    included_knowledge_ids: list[str] = Field(default_factory=list)
    included_relationship_ids: list[str] = Field(default_factory=list)
    included_foreshadow_ids: list[str] = Field(default_factory=list)
    excluded_future_ids: list[str] = Field(default_factory=list)
    relevance_rules: list[str] = Field(default_factory=list)
    temporal_cutoff: int | None = Field(default=None, ge=0)
    character_scope: str = Field(default="", max_length=96)
    token_budget: int = Field(default=0, ge=0)
    context_digest: str = Field(default="", max_length=64)
    trimmed_ids: list[str] = Field(default_factory=list)
    coverage: dict[str, Any] = Field(default_factory=dict)


class ContextBundle(StrictModel):
    purpose: Purpose
    entries: list[ContextEntry] = Field(default_factory=list)
    manifest: ContextManifest
    rendered: list[str] = Field(default_factory=list)


def sanitize_writer_text(text: str) -> str:
    """移除 writer-visible 元数据：内部 ID、章节号、Arc / 卷号。"""

    cleaned = ID_PATTERN.sub("", text or "")
    cleaned = CHAPTER_PATTERN.sub("", cleaned)
    cleaned = ARC_PATTERN.sub("", cleaned)
    cleaned = INTERNAL_FIELD_PATTERN.sub("", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip(" ，、,;；")


def contains_writer_metadata(text: str) -> bool:
    """判断 writer-visible 文本里是否真的含有内部元数据（避免把空白规范化误判为泄漏）。"""

    value = text or ""
    return bool(ID_PATTERN.search(value) or CHAPTER_PATTERN.search(value)
                or ARC_PATTERN.search(value) or INTERNAL_FIELD_PATTERN.search(value))


class CanonContextBuilder:
    def __init__(self, repository: CanonRepository) -> None:
        self.repository = repository

    # ---- 公共入口 ---------------------------------------------------------
    def planner_context(self, novel_id: str, *, arc_intent: str = "",
                        focus_entity_ids: tuple[str, ...] = (),
                        focus_location_ids: tuple[str, ...] = (),
                        temporal_cutoff: int | None = None, max_items: int = 40,
                        max_chars: int = 6000) -> ContextBundle:
        entries: list[ContextEntry] = []
        excluded: list[str] = []
        relevant_rules = ["happened", "planned", "constraint", "possibility"]
        for fact in self.repository.facts(novel_id):
            position = self._fact_position(fact)
            if temporal_cutoff is not None and position is not None and position > temporal_cutoff:
                excluded.append(fact.fact_id)
                continue
            priority = P0 if fact.status == "happened" else P2
            if focus_entity_ids and set(fact.subjects) & set(focus_entity_ids):
                priority = min(priority, P1)
            entries.append(ContextEntry(
                canon_id=fact.fact_id,
                type="HAPPENED" if fact.status == "happened" else "PLANNED",
                status=fact.status, canonical_description=fact.canonical_description,
                provenance=fact.provenance, temporal_position=position,
                relevance_reason="focus entity" if priority <= P1 else "canon fact",
                priority=priority, payload={"prerequisites": fact.prerequisites,
                                            "consequences": fact.consequences}))
        for event in self.repository.events(novel_id):
            position = event.temporal_position
            if temporal_cutoff is not None and position is not None and position > temporal_cutoff:
                excluded.append(event.event_id)
                continue
            entries.append(ContextEntry(
                canon_id=event.event_id,
                type="HAPPENED" if event.status in ("occurred", "resolved") else "PLANNED",
                status=event.status, canonical_description=event.semantic_summary or event.canonical_name,
                provenance=event.provenance, temporal_position=position,
                relevance_reason=f"narrative_role={event.narrative_role}", priority=P1
                if event.prerequisites else P3,
                payload={"prerequisites": event.prerequisites,
                         "canonical_event_id": event.canonical_event_id}))
        for relationship in self.repository.relationships(novel_id):
            entries.append(ContextEntry(
                canon_id=relationship.relationship_id, type="HAPPENED", status="known",
                canonical_description=f"{relationship.source_id} → {relationship.target_id}"
                                      f" {relationship.kind} {relationship.state}".strip(),
                provenance="story_state", relevance_reason="active relationship", priority=P2))
        for foreshadow in self.repository.foreshadows(novel_id):
            if foreshadow.status in ("abandoned", "paid_off"):
                continue
            # intended_payoff 属于规划器私有信息：绝不进入任何可渲染描述（C11 加固）
            entries.append(ContextEntry(
                canon_id=foreshadow.foreshadow_id, type="PLANNED", status=foreshadow.status,
                canonical_description=foreshadow.subject or LOCKED_FORESHADOW_TEXT,
                provenance="planner", relevance_reason="active foreshadow", priority=P2,
                payload={"payoff_locked": True}))
        entries.sort(key=lambda item: (item.priority, item.temporal_position if
                                       item.temporal_position is not None else 10 ** 9, item.canon_id))
        kept, trimmed, chars = self._apply_budget(entries, max_items=max_items, max_chars=max_chars)
        manifest = self._manifest(novel_id, "planner", kept, excluded, temporal_cutoff,
                                  arc_intent=arc_intent, trimmed=trimmed)
        return ContextBundle(purpose="planner", entries=kept, manifest=manifest)

    def character_context(self, novel_id: str, character_id: str, *,
                          temporal_cutoff: int | None = None,
                          max_items: int = 30) -> ContextBundle:
        """只包含该角色 known / suspected / confirmed / false_belief 的内容。"""

        entries: list[ContextEntry] = []
        excluded: list[str] = []
        knowledge_rows = self.repository.knowledge(novel_id)
        fact_index = {f.fact_id: f for f in self.repository.facts(novel_id)}
        for entry in knowledge_rows:
            if entry.holder_id != character_id:
                continue
            if entry.state == "unknown":
                # C11 加固：unknown ≠ holder 视角内容（否则等于把真相塞进角色上下文）
                excluded.append(entry.knowledge_id)
                continue
            fact = fact_index.get(entry.fact_id)
            description = fact.canonical_description if fact else ""
            if entry.state == "false_belief":
                description = f"（误信）{description}"
            elif entry.state == "suspected":
                description = f"（怀疑）{description}"
            if temporal_cutoff is not None and entry.learned_at is not None \
                    and entry.learned_at > temporal_cutoff:
                excluded.append(entry.knowledge_id)
                continue
            entries.append(ContextEntry(
                canon_id=entry.knowledge_id, type="HAPPENED", status=entry.state,
                canonical_description=description, provenance=entry.learned_from or "unknown",
                temporal_position=entry.learned_at, relevance_reason="holder knowledge",
                priority=P0 if entry.state in ("known", "confirmed") else P2))
        entries.sort(key=lambda item: (item.priority, item.temporal_position if
                                       item.temporal_position is not None else 10 ** 9,
                                       item.canon_id))
        kept, trimmed, _ = self._apply_budget(entries, max_items=max_items, max_chars=10 ** 6)
        manifest = self._manifest(novel_id, "character", kept, excluded, temporal_cutoff,
                                  character_scope=character_id, trimmed=trimmed)
        return ContextBundle(purpose="character", entries=kept, manifest=manifest)

    def writer_context(self, novel_id: str, *, character_scope: str = "",
                       temporal_cutoff: int | None = None, max_items: int = 30) -> ContextBundle:
        """自然语言视图：不暴露内部 ID；planned 明确标注未发生。"""

        base = (self.character_context(novel_id, character_scope,
                                       temporal_cutoff=temporal_cutoff, max_items=max_items)
                if character_scope else
                self.planner_context(novel_id, temporal_cutoff=temporal_cutoff,
                                     max_items=max_items, max_chars=10 ** 6))
        rendered: list[str] = []
        entries: list[ContextEntry] = []
        for entry in base.entries:
            if entry.type == "HAPPENED":
                line = f"已经发生：{entry.canonical_description}"
            elif entry.type == "CONSTRAINT":
                line = f"必须遵守：{entry.canonical_description}"
            elif entry.type == "POSSIBILITY":
                line = f"可能方向：{entry.canonical_description}"
            else:
                line = f"尚未发生（计划方向）：{entry.canonical_description}"
            rendered.append(sanitize_writer_text(line))
            entries.append(entry.model_copy(update={"payload": {}}))
        manifest = base.manifest.model_copy(update={"purpose": "writer"})
        return ContextBundle(purpose="writer", entries=entries, manifest=manifest,
                             rendered=rendered)

    # ---- 内部 -------------------------------------------------------------
    @staticmethod
    def _fact_position(fact) -> int | None:
        if fact.first_occurrence_ref and fact.first_occurrence_ref.display_number is not None:
            return fact.first_occurrence_ref.display_number
        return None

    def _apply_budget(self, entries: list[ContextEntry], *, max_items: int,
                      max_chars: int) -> tuple[list[ContextEntry], list[str], int]:
        kept: list[ContextEntry] = []
        trimmed: list[str] = []
        chars = 0
        for entry in entries:
            size = len(entry.canonical_description) + len(entry.relevance_reason)
            if (len(kept) >= max_items or chars + size > max_chars) \
                    and entry.priority not in NEVER_TRIM:
                trimmed.append(entry.canon_id)
                continue
            kept.append(entry)
            chars += size
        return kept, trimmed, chars

    def _manifest(self, novel_id: str, purpose: str, entries: list[ContextEntry],
                  excluded: list[str], cutoff: int | None, *, arc_intent: str = "",
                  character_scope: str = "", trimmed: list[str] | None = None,
                  coverage: dict[str, Any] | None = None) -> ContextManifest:
        ids = [entry.canon_id for entry in entries]
        digest = hashlib.sha1(json.dumps(
            {"purpose": purpose, "ids": ids, "cutoff": cutoff, "intent": arc_intent},
            ensure_ascii=False).encode("utf-8")).hexdigest()[:16]
        return ContextManifest(
            context_id=f"CTX_{digest}", novel_id=novel_id, purpose=purpose,
            included_fact_ids=[i for i in ids if i.startswith("FACT_")],
            included_event_ids=[i for i in ids if i.startswith("EVENT_")],
            included_knowledge_ids=[i for i in ids if i.startswith("KNW_")],
            included_relationship_ids=[i for i in ids if i.startswith("REL_")],
            included_foreshadow_ids=[i for i in ids if i.startswith("FS_")],
            excluded_future_ids=sorted(set(excluded)), temporal_cutoff=cutoff,
            character_scope=character_scope, token_budget=8000,
            context_digest=digest, trimmed_ids=sorted(trimmed or []),
            coverage=coverage or {})
