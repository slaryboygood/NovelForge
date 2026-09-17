"""C02：StoryState → Canon 单向同步（幂等，source mapping 持久化）。"""

from __future__ import annotations

import hashlib
from typing import Any

from .ids import new_canon_id
from .models import (
    CanonEntity,
    CanonFact,
    CanonForeshadow,
    CanonKnowledge,
    CanonRelationship,
    CanonSourceMapping,
)
from .repository import CanonRepository

SOURCE_TYPE = "story_state"


def source_stable_key(record: dict[str, Any]) -> str:
    """稳定 source locator：来自事实本身，不使用 effect_log order / route order。"""

    payload = "|".join(str(record.get(key, "")) for key in
                       ("op", "entity", "target", "source", "value"))
    tick = str((record.get("data") or {}).get("tick", ""))
    digest = hashlib.sha1(f"{payload}|{tick}".encode("utf-8")).hexdigest()[:16]
    return f"effect:{record.get('op', '')}:{record.get('target', '')}:{digest}"


class StoryStateCanonSync:
    """只允许 StoryState → Canon；不反向覆盖 runtime truth。"""

    def __init__(self, repository: CanonRepository) -> None:
        self.repository = repository

    def sync(self, novel_id: str, state: dict[str, Any]) -> dict[str, Any]:
        created = {"entities": 0, "facts": 0, "knowledge": 0, "foreshadows": 0, "relationships": 0}
        created["entities"] += self._sync_entities(novel_id, state)
        created["facts"] += self._sync_effect_log(novel_id, state)
        created["knowledge"] += self._sync_knowledge(novel_id, state)
        created["foreshadows"] += self._sync_foreshadows(novel_id, state)
        created["relationships"] += self._sync_relationships(novel_id, state)
        self.repository.record_version(
            novel_id=novel_id, version=self.repository.schema_version,
            note=f"story_state sync revision={state.get('schema_version', '')}")
        return created

    # ---- 内部 -------------------------------------------------------------
    def _mapped_id(self, novel_id: str, key: str, canon_type: str, prefix: str) -> tuple[str, bool]:
        existing = self.repository.find_mapping(novel_id, SOURCE_TYPE, key, canon_type)
        if existing is not None:
            return existing.canon_id, False
        canon_id = f"{prefix}_{new_canon_id(canon_type).split('_', 1)[1]}"
        self.repository.save_mapping(CanonSourceMapping(
            novel_id=novel_id, source_type=SOURCE_TYPE, source_stable_key=key,
            canon_type=canon_type, canon_id=canon_id))
        return canon_id, True

    def _sync_entities(self, novel_id: str, state: dict[str, Any]) -> int:
        added = 0
        for kind, table in (("character", state.get("characters") or {}),
                            ("faction", state.get("factions") or {})):
            for entity_id, payload in table.items():
                key = f"{kind}:{entity_id}"
                canon_id, created = self._mapped_id(novel_id, key, "entity", "ENT")
                if not created:
                    continue
                self.repository.save_entity(CanonEntity(
                    entity_id=canon_id, canonical_key=canon_id.split("_", 1)[1],
                    novel_id=novel_id, kind=kind,
                    display_name=str((payload or {}).get("name", "") or entity_id),
                    data={"source_id": entity_id}))
                added += 1
        return added

    def _sync_effect_log(self, novel_id: str, state: dict[str, Any]) -> int:
        added = 0
        seen_events: set[str] = set()
        for record in state.get("effect_log") or []:
            if record.get("op") in ("fire_event", "world_event"):
                event_id = str(record.get("target", ""))
                if event_id in seen_events:
                    continue
                seen_events.add(event_id)
            key = source_stable_key(record)
            canon_id, created = self._mapped_id(novel_id, key, "fact", "FACT")
            if not created:
                continue
            self.repository.save_fact(CanonFact(
                fact_id=canon_id, canonical_key=canon_id.split("_", 1)[1], novel_id=novel_id,
                category=str(record.get("op", "event")), status="happened",
                canonical_description=f"{record.get('op', '')} {record.get('target', '')}".strip(),
                source_type="story_state", provenance="story_state",
                subjects=[str(record.get("entity", ""))] if record.get("entity") else [],
                objects=[str(record.get("target", ""))] if record.get("target") else [],
                knowledge_effects=[]))
            added += 1
        return added

    def _sync_knowledge(self, novel_id: str, state: dict[str, Any]) -> int:
        added = 0
        for entry in state.get("knowledge") or []:
            knowledge_source = f"knowledge:{entry.get('id', '')}"
            fact_id, fact_created = self._mapped_id(novel_id, knowledge_source, "fact", "FACT")
            if fact_created:
                self.repository.save_fact(CanonFact(
                    fact_id=fact_id, canonical_key=fact_id.split("_", 1)[1], novel_id=novel_id,
                    category="knowledge", status="happened",
                    canonical_description=f"知识对象 {entry.get('id', '')}",
                    source_type="story_state", provenance="story_state"))
            for holder in entry.get("holders") or []:
                key = f"knowledge:{entry.get('id', '')}:{holder}"
                knowledge_id, created = self._mapped_id(novel_id, key, "knowledge", "KNW")
                if not created:
                    continue
                self.repository.save_knowledge(CanonKnowledge(
                    knowledge_id=knowledge_id, novel_id=novel_id, fact_id=fact_id,
                    holder_type="character", holder_id=str(holder), state="known",
                    learned_at=int(entry.get("tick") or 0),
                    learned_from=str(entry.get("source", "")),
                    source_event_id=str(entry.get("source_event", ""))))
                added += 1
        return added

    def _sync_foreshadows(self, novel_id: str, state: dict[str, Any]) -> int:
        added = 0
        registry = (state.get("flags") or {}).get("foreshadows") or {}
        for foreshadow_id, payload in registry.items():
            key = f"foreshadow:{foreshadow_id}"
            canon_id, created = self._mapped_id(novel_id, key, "foreshadow", "FS")
            if not created:
                continue
            status = str((payload or {}).get("status", "planned"))
            canon_status = {"planned": "planned", "planted": "planted", "reinforced": "reinforced",
                            "revealed": "revealed", "resolved": "paid_off",
                            "abandoned": "abandoned"}.get(status, "planned")
            self.repository.save_foreshadow(CanonForeshadow(
                foreshadow_id=canon_id, novel_id=novel_id,
                subject=str((payload or {}).get("reason", "")),
                status=canon_status))
            added += 1
        return added

    def _sync_relationships(self, novel_id: str, state: dict[str, Any]) -> int:
        added = 0
        for entry in state.get("relationships") or []:
            source = str(entry.get("source_id", ""))
            target = str(entry.get("target_id", ""))
            key = f"relationship:{source}:{target}"
            canon_id, created = self._mapped_id(novel_id, key, "relationship", "REL")
            if not created:
                continue
            self.repository.save_relationship(CanonRelationship(
                relationship_id=canon_id, novel_id=novel_id, source_id=source, target_id=target,
                kind="trust", state=str((entry.get("dimensions") or {}).get("trust", "")),
                data={"dimensions": entry.get("dimensions") or {}}))
            added += 1
        return added
