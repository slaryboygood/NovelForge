"""C02：Canon SQLite 持久层（唯一允许写 SQL 的地方）。"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .models import (
    CanonConstraint,
    CanonDependency,
    CanonEntity,
    CanonEvent,
    CanonFact,
    CanonForeshadow,
    CanonKnowledge,
    CanonRelationship,
    CanonRenderRef,
    CanonSourceMapping,
)

CANON_SCHEMA_VERSION = 3


def _with_renumbered_refs(record: Any, mapping: dict[int, int], fields: tuple[str, ...]) -> Any | None:
    """把 payload 内联的 CanonRenderRef display_number 按 mapping 重编号（identity 不动）。

    返回 None 表示无需变更（调用方不做额外写入）。
    """

    changes: dict[str, Any] = {}
    for field in fields:
        value = getattr(record, field, None)
        if value is None:
            continue
        if isinstance(value, list):
            updated: list[Any] = []
            touched = False
            for item in value:
                if item.display_number in mapping:
                    updated.append(item.model_copy(update={"display_number": mapping[item.display_number]}))
                    touched = True
                else:
                    updated.append(item)
            if touched:
                changes[field] = updated
        elif value.display_number in mapping:
            changes[field] = value.model_copy(update={"display_number": mapping[value.display_number]})
    if not changes:
        return None
    return record.model_copy(update=changes)

MIGRATIONS: dict[int, str] = {
    1: """
    CREATE TABLE IF NOT EXISTS canon_meta (
        key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS canon_entities (
        entity_id TEXT PRIMARY KEY, novel_id TEXT NOT NULL, payload TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS canon_facts (
        fact_id TEXT PRIMARY KEY, novel_id TEXT NOT NULL, status TEXT NOT NULL,
        canonical_key TEXT NOT NULL, payload TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS canon_events (
        event_id TEXT PRIMARY KEY, novel_id TEXT NOT NULL, status TEXT NOT NULL,
        narrative_role TEXT NOT NULL, canonical_event_id TEXT NOT NULL, payload TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS canon_knowledge (
        knowledge_id TEXT PRIMARY KEY, novel_id TEXT NOT NULL, fact_id TEXT NOT NULL,
        holder_type TEXT NOT NULL, holder_id TEXT NOT NULL, payload TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS canon_relationships (
        relationship_id TEXT PRIMARY KEY, novel_id TEXT NOT NULL, payload TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS canon_foreshadows (
        foreshadow_id TEXT PRIMARY KEY, novel_id TEXT NOT NULL, status TEXT NOT NULL,
        payload TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS canon_dependencies (
        id INTEGER PRIMARY KEY AUTOINCREMENT, novel_id TEXT NOT NULL, from_id TEXT NOT NULL,
        to_id TEXT NOT NULL, relation TEXT NOT NULL, note TEXT NOT NULL DEFAULT '');
    CREATE TABLE IF NOT EXISTS canon_render_refs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, novel_id TEXT NOT NULL, canon_id TEXT NOT NULL,
        chapter_uuid TEXT NOT NULL, display_number INTEGER, field TEXT NOT NULL DEFAULT '');
    CREATE TABLE IF NOT EXISTS canon_versions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, novel_id TEXT NOT NULL, version INTEGER NOT NULL,
        created_at TEXT NOT NULL, digest TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '');
    CREATE TABLE IF NOT EXISTS canon_source_mappings (
        novel_id TEXT NOT NULL, source_type TEXT NOT NULL, source_stable_key TEXT NOT NULL,
        canon_type TEXT NOT NULL, canon_id TEXT NOT NULL, created_at TEXT NOT NULL,
        PRIMARY KEY (novel_id, source_type, source_stable_key, canon_type));
    CREATE TABLE IF NOT EXISTS canon_constraints (
        constraint_id TEXT PRIMARY KEY, novel_id TEXT NOT NULL, payload TEXT NOT NULL);
    """,
    2: """
    CREATE TABLE IF NOT EXISTS canon_constraints (
        constraint_id TEXT PRIMARY KEY, novel_id TEXT NOT NULL, payload TEXT NOT NULL);
    """,
    3: """
    CREATE TABLE IF NOT EXISTS canon_chapter_lineage (
        chapter_uuid TEXT PRIMARY KEY, novel_id TEXT NOT NULL, display_number INTEGER,
        status TEXT NOT NULL DEFAULT 'active', superseded_by TEXT NOT NULL DEFAULT '',
        merged_into TEXT NOT NULL DEFAULT '', context_manifest_id TEXT NOT NULL DEFAULT '',
        title TEXT NOT NULL DEFAULT '');
    CREATE TABLE IF NOT EXISTS canon_context_manifests (
        context_id TEXT PRIMARY KEY, novel_id TEXT NOT NULL, purpose TEXT NOT NULL,
        payload TEXT NOT NULL);
    """,
}


class CanonRepository:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(str(self.path))
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self.migrate()

    # ---- 基础 -------------------------------------------------------------
    def close(self) -> None:
        self._connection.close()

    @property
    def schema_version(self) -> int:
        row = self._connection.execute(
            "SELECT value FROM canon_meta WHERE key = 'canon_schema_version'").fetchone()
        return int(row["value"]) if row else 0

    def table_names(self) -> list[str]:
        rows = self._connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE 'canon_%' "
            "ORDER BY name").fetchall()
        return [row["name"] for row in rows]

    def schema_summary(self) -> dict[str, Any]:
        """供报告 / API 引用 schema 事实，避免文档手写版本号漂移。"""

        return {"canon_schema_version": self.schema_version,
                "migrations": sorted(MIGRATIONS),
                "tables": self.table_names()}

    def migrate(self) -> int:
        current = 0
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS canon_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        row = self._connection.execute(
            "SELECT value FROM canon_meta WHERE key = 'canon_schema_version'").fetchone()
        current = int(row["value"]) if row else 0
        for version in sorted(MIGRATIONS):
            if version <= current:
                continue
            with self.transaction():
                self._connection.executescript(MIGRATIONS[version])
                self._connection.execute(
                    "INSERT INTO canon_meta(key, value) VALUES('canon_schema_version', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (str(version),))
            current = version
        return current

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        try:
            yield self._connection
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise

    # ---- 写入 -------------------------------------------------------------
    def _upsert(self, table: str, key_column: str, key: str, columns: dict[str, Any],
                payload: Any) -> None:
        names = [key_column, *columns.keys(), "payload"]
        values = [key, *columns.values(), json.dumps(payload, ensure_ascii=False)]
        placeholders = ",".join("?" for _ in names)
        updates = ",".join(f"{name}=excluded.{name}" for name in names if name != key_column)
        self._connection.execute(
            f"INSERT INTO {table} ({','.join(names)}) VALUES ({placeholders}) "
            f"ON CONFLICT({key_column}) DO UPDATE SET {updates}", values)

    def save_entity(self, entity: CanonEntity) -> None:
        with self.transaction():
            self._upsert("canon_entities", "entity_id", entity.entity_id,
                         {"novel_id": entity.novel_id}, entity.model_dump(mode="json"))

    def save_fact(self, fact: CanonFact) -> None:
        with self.transaction():
            self._upsert("canon_facts", "fact_id", fact.fact_id,
                         {"novel_id": fact.novel_id, "status": fact.status,
                          "canonical_key": fact.canonical_key}, fact.model_dump(mode="json"))

    def save_event(self, event: CanonEvent) -> None:
        with self.transaction():
            self._upsert("canon_events", "event_id", event.event_id,
                         {"novel_id": event.novel_id, "status": event.status,
                          "narrative_role": event.narrative_role,
                          "canonical_event_id": event.canonical_event_id},
                         event.model_dump(mode="json"))

    def save_knowledge(self, entry: CanonKnowledge) -> None:
        with self.transaction():
            self._upsert("canon_knowledge", "knowledge_id", entry.knowledge_id,
                         {"novel_id": entry.novel_id, "fact_id": entry.fact_id,
                          "holder_type": entry.holder_type, "holder_id": entry.holder_id},
                         entry.model_dump(mode="json"))

    def save_relationship(self, entry: CanonRelationship) -> None:
        with self.transaction():
            self._upsert("canon_relationships", "relationship_id", entry.relationship_id,
                         {"novel_id": entry.novel_id}, entry.model_dump(mode="json"))

    def save_foreshadow(self, entry: CanonForeshadow) -> None:
        with self.transaction():
            self._upsert("canon_foreshadows", "foreshadow_id", entry.foreshadow_id,
                         {"novel_id": entry.novel_id, "status": entry.status},
                         entry.model_dump(mode="json"))

    def save_constraint(self, entry: CanonConstraint) -> None:
        with self.transaction():
            self._upsert("canon_constraints", "constraint_id", entry.constraint_id,
                         {"novel_id": entry.novel_id}, entry.model_dump(mode="json"))

    def add_dependency(self, dependency: CanonDependency, *, novel_id: str) -> None:
        with self.transaction():
            self._connection.execute(
                "INSERT INTO canon_dependencies(novel_id, from_id, to_id, relation, note) "
                "VALUES (?,?,?,?,?)",
                (novel_id, dependency.from_id, dependency.to_id, dependency.relation,
                 dependency.note))

    def add_render_ref(self, *, novel_id: str, canon_id: str, ref: CanonRenderRef) -> None:
        with self.transaction():
            self._connection.execute(
                "INSERT INTO canon_render_refs(novel_id, canon_id, chapter_uuid, display_number, field) "
                "VALUES (?,?,?,?,?)",
                (novel_id, canon_id, ref.chapter_uuid, ref.display_number, ref.field))

    def renumber_render_refs(self, *, novel_id: str, mapping: dict[int, int]) -> int:
        """章节重编号：只更新 display_number，canon_id / chapter_uuid 不变。"""

        changed = 0
        with self.transaction():
            rows = self._connection.execute(
                "SELECT id, display_number FROM canon_render_refs WHERE novel_id = ?",
                (novel_id,)).fetchall()
            for row in rows:
                old = row["display_number"]
                if old in mapping:
                    self._connection.execute(
                        "UPDATE canon_render_refs SET display_number = ? WHERE id = ?",
                        (mapping[old], row["id"]))
                    changed += 1
        # C11 加固：fact / event payload 内联的渲染位置必须与 canon_render_refs 同步，
        # 否则 future-leak / context 判定会继续使用过期章节号。
        for fact in self._load("canon_facts", CanonFact, novel_id):
            updated = _with_renumbered_refs(fact, mapping, ("first_occurrence_ref",
                                                            "current_render_refs"))
            if updated is not None:
                self.save_fact(updated)
                changed += 1
        for event in self._load("canon_events", CanonEvent, novel_id):
            updated = _with_renumbered_refs(event, mapping, ("first_occurrence_ref",))
            if updated is not None:
                self.save_event(updated)
                changed += 1
        return changed

    # ---- 读取 -------------------------------------------------------------
    def _load(self, table: str, model, novel_id: str, where: str = "",
              params: tuple = ()) -> list[Any]:
        sql = f"SELECT payload FROM {table} WHERE novel_id = ?"
        if where:
            sql += f" AND {where}"
        rows = self._connection.execute(sql, (novel_id, *params)).fetchall()
        return [model.model_validate(json.loads(row["payload"])) for row in rows]

    def facts(self, novel_id: str, *, status: str = "") -> list[CanonFact]:
        return self._load("canon_facts", CanonFact, novel_id,
                          "status = ?" if status else "", (status,) if status else ())

    def events(self, novel_id: str, *, role: str = "") -> list[CanonEvent]:
        return self._load("canon_events", CanonEvent, novel_id,
                          "narrative_role = ?" if role else "", (role,) if role else ())

    def knowledge(self, novel_id: str) -> list[CanonKnowledge]:
        return self._load("canon_knowledge", CanonKnowledge, novel_id)

    def foreshadows(self, novel_id: str) -> list[CanonForeshadow]:
        return self._load("canon_foreshadows", CanonForeshadow, novel_id)

    def entities(self, novel_id: str) -> list[CanonEntity]:
        return self._load("canon_entities", CanonEntity, novel_id)

    def relationships(self, novel_id: str) -> list[CanonRelationship]:
        return self._load("canon_relationships", CanonRelationship, novel_id)

    def dependencies(self, novel_id: str) -> list[CanonDependency]:
        rows = self._connection.execute(
            "SELECT from_id, to_id, relation, note FROM canon_dependencies WHERE novel_id = ?",
            (novel_id,)).fetchall()
        return [CanonDependency(from_id=r["from_id"], to_id=r["to_id"],
                                relation=r["relation"], note=r["note"]) for r in rows]

    def render_refs(self, novel_id: str, *, canon_id: str = "") -> list[dict[str, Any]]:
        sql = "SELECT canon_id, chapter_uuid, display_number, field FROM canon_render_refs " \
              "WHERE novel_id = ?"
        params: tuple = (novel_id,)
        if canon_id:
            sql += " AND canon_id = ?"
            params = (novel_id, canon_id)
        return [dict(row) for row in self._connection.execute(sql, params).fetchall()]

    # ---- source mapping ---------------------------------------------------
    def find_mapping(self, novel_id: str, source_type: str, source_stable_key: str,
                     canon_type: str) -> CanonSourceMapping | None:
        row = self._connection.execute(
            "SELECT * FROM canon_source_mappings WHERE novel_id = ? AND source_type = ? "
            "AND source_stable_key = ? AND canon_type = ?",
            (novel_id, source_type, source_stable_key, canon_type)).fetchone()
        if row is None:
            return None
        return CanonSourceMapping(novel_id=row["novel_id"], source_type=row["source_type"],
                                  source_stable_key=row["source_stable_key"],
                                  canon_type=row["canon_type"], canon_id=row["canon_id"],
                                  created_at=row["created_at"])

    def save_mapping(self, mapping: CanonSourceMapping) -> None:
        with self.transaction():
            self._connection.execute(
                "INSERT INTO canon_source_mappings(novel_id, source_type, source_stable_key, "
                "canon_type, canon_id, created_at) VALUES (?,?,?,?,?,?) "
                "ON CONFLICT(novel_id, source_type, source_stable_key, canon_type) "
                "DO UPDATE SET canon_id = excluded.canon_id",
                (mapping.novel_id, mapping.source_type, mapping.source_stable_key,
                 mapping.canon_type, mapping.canon_id, mapping.created_at.isoformat()))

    # ---- 版本 / 导出 -------------------------------------------------------
    def record_version(self, *, novel_id: str, version: int, digest: str = "",
                       note: str = "") -> None:
        from datetime import datetime, timezone
        with self.transaction():
            self._connection.execute(
                "INSERT INTO canon_versions(novel_id, version, created_at, digest, note) "
                "VALUES (?,?,?,?,?)",
                (novel_id, version, datetime.now(timezone.utc).isoformat(), digest, note))

    def export_json(self, novel_id: str) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "novel_id": novel_id,
            "facts": [f.model_dump(mode="json") for f in self.facts(novel_id)],
            "events": [e.model_dump(mode="json") for e in self.events(novel_id)],
            "knowledge": [k.model_dump(mode="json") for k in self.knowledge(novel_id)],
            "foreshadows": [f.model_dump(mode="json") for f in self.foreshadows(novel_id)],
            "entities": [e.model_dump(mode="json") for e in self.entities(novel_id)],
            "relationships": [r.model_dump(mode="json") for r in self.relationships(novel_id)],
            "dependencies": [d.model_dump(mode="json") for d in self.dependencies(novel_id)],
            "render_refs": self.render_refs(novel_id),
            "source_mappings": [
                {"novel_id": row["novel_id"], "source_type": row["source_type"],
                 "source_stable_key": row["source_stable_key"], "canon_type": row["canon_type"],
                 "canon_id": row["canon_id"], "created_at": row["created_at"]}
                for row in self._connection.execute(
                    "SELECT * FROM canon_source_mappings WHERE novel_id = ?",
                    (novel_id,)).fetchall()],
        }

    def import_json(self, payload: dict[str, Any]) -> int:
        count = 0
        for fact in payload.get("facts", []):
            self.save_fact(CanonFact.model_validate(fact)); count += 1
        for event in payload.get("events", []):
            self.save_event(CanonEvent.model_validate(event)); count += 1
        for entry in payload.get("knowledge", []):
            self.save_knowledge(CanonKnowledge.model_validate(entry)); count += 1
        for entry in payload.get("foreshadows", []):
            self.save_foreshadow(CanonForeshadow.model_validate(entry)); count += 1
        for entry in payload.get("entities", []):
            self.save_entity(CanonEntity.model_validate(entry)); count += 1
        for entry in payload.get("relationships", []):
            self.save_relationship(CanonRelationship.model_validate(entry)); count += 1
        for entry in payload.get("source_mappings", []):
            self.save_mapping(CanonSourceMapping(
                novel_id=entry["novel_id"], source_type=entry["source_type"],
                source_stable_key=entry["source_stable_key"], canon_type=entry["canon_type"],
                canon_id=entry["canon_id"], created_at=entry["created_at"]))
            count += 1
        return count
