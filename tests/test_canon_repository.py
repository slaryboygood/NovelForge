"""C02：SQLite repository / 稳定映射 / 重编号不影响 identity。"""

from __future__ import annotations

import json

from novelforge.story_engine.canon import (
    CanonEvent,
    CanonFact,
    CanonRenderRef,
    CanonSourceMapping,
)
from novelforge.story_engine.canon.repository import CANON_SCHEMA_VERSION, CanonRepository
from novelforge.story_engine.canon.service import CanonService, CanonServiceError


def test_sqlite_roundtrip_and_schema_version(tmp_path) -> None:
    repo = CanonRepository(tmp_path / "canon.sqlite")
    assert repo.schema_version == CANON_SCHEMA_VERSION
    repo.save_fact(CanonFact(fact_id="FACT_ALPHA", canonical_key="ALPHA", novel_id="n1",
                             status="happened", canonical_description="第一件事"))
    repo.save_event(CanonEvent(event_id="EVENT_ALPHA", canonical_key="ALPHA", novel_id="n1",
                               status="occurred", narrative_role="canonical"))
    repo.close()
    repo2 = CanonRepository(tmp_path / "canon.sqlite")
    facts = repo2.facts("n1")
    events = repo2.events("n1")
    assert [f.fact_id for f in facts] == ["FACT_ALPHA"]
    assert facts[0].immutable is True
    assert [e.event_id for e in events] == ["EVENT_ALPHA"]
    repo2.close()


def test_source_mapping_is_persistent_across_restart(tmp_path) -> None:
    repo = CanonRepository(tmp_path / "canon.sqlite")
    repo.save_mapping(CanonSourceMapping(novel_id="n1", source_type="story_state",
                                         source_stable_key="effect:runtime_action:act_scavenge",
                                         canon_type="fact", canon_id="FACT_SCRAP"))
    repo.close()
    repo2 = CanonRepository(tmp_path / "canon.sqlite")
    found = repo2.find_mapping("n1", "story_state", "effect:runtime_action:act_scavenge", "fact")
    assert found is not None and found.canon_id == "FACT_SCRAP"
    repo2.close()


def test_chapter_renumber_keeps_canon_identity(tmp_path) -> None:
    """P0：删除前方章节导致重编号时，事实 identity 与 source 追踪不变。"""

    repo = CanonRepository(tmp_path / "canon.sqlite")
    repo.save_fact(CanonFact(fact_id="FACT_ZERO_LAYER_GATE_FIRST_OPEN",
                             canonical_key="ZERO_LAYER_GATE_FIRST_OPEN", novel_id="n1",
                             status="happened", canonical_description="第一次打开第零层门禁"))
    repo.add_render_ref(novel_id="n1", canon_id="FACT_ZERO_LAYER_GATE_FIRST_OPEN",
                        ref=CanonRenderRef(chapter_uuid="uuid-a", display_number=325))
    repo.save_mapping(CanonSourceMapping(novel_id="n1", source_type="outline",
                                         source_stable_key="uuid-a",
                                         canon_type="fact",
                                         canon_id="FACT_ZERO_LAYER_GATE_FIRST_OPEN"))
    changed = repo.renumber_render_refs(novel_id="n1", mapping={325: 318})
    assert changed == 1
    refs = repo.render_refs("n1", canon_id="FACT_ZERO_LAYER_GATE_FIRST_OPEN")
    assert refs[0]["display_number"] == 318 and refs[0]["chapter_uuid"] == "uuid-a"
    fact = [f for f in repo.facts("n1") if f.fact_id == "FACT_ZERO_LAYER_GATE_FIRST_OPEN"][0]
    assert fact.fact_id == "FACT_ZERO_LAYER_GATE_FIRST_OPEN"
    assert repo.find_mapping("n1", "outline", "uuid-a", "fact").canon_id == fact.fact_id
    repo.close()


def test_happened_fact_is_immutable_and_planned_is_mutable(tmp_path) -> None:
    repo = CanonRepository(tmp_path / "canon.sqlite")
    service = CanonService(repo)
    service.repository.save_fact(CanonFact(fact_id="FACT_LOCKED", canonical_key="LOCKED",
                                           novel_id="n1", status="happened",
                                           canonical_description="历史事件"))
    with pytest_raises(CanonServiceError) as excinfo:
        service.update_fact("FACT_LOCKED", {"canonical_description": "被改写"})
    assert excinfo.value.code == "HAPPENED_FACT_IMMUTABLE"
    repo.save_fact(CanonFact(fact_id="FACT_PLAN", canonical_key="PLAN", novel_id="n1",
                             status="planned", canonical_description="计划事件"))
    updated = service.update_fact("FACT_PLAN", {"canonical_description": "计划事件（改写）"})
    assert updated.canonical_description.endswith("（改写）")
    repo.close()


def test_export_import_roundtrip(tmp_path) -> None:
    repo = CanonRepository(tmp_path / "a.sqlite")
    repo.save_fact(CanonFact(fact_id="FACT_X", canonical_key="X", novel_id="n1",
                             status="planned", canonical_description="X 事实"))
    payload = repo.export_json("n1")
    repo.close()
    other = CanonRepository(tmp_path / "b.sqlite")
    count = other.import_json(payload)
    assert count >= 1
    assert [f.fact_id for f in other.facts("n1")] == ["FACT_X"]
    other.close()


def test_v1_database_upgrades_to_current_version_without_data_loss(tmp_path) -> None:
    """v1 DB（无 canon_constraints）升级到当前版本：不 DROP、不丢 identity。"""

    import sqlite3

    from novelforge.story_engine.canon.repository import CANON_SCHEMA_VERSION, MIGRATIONS

    path = tmp_path / "legacy.sqlite"
    connection = sqlite3.connect(str(path))
    connection.executescript(MIGRATIONS[1])
    connection.execute("CREATE TABLE IF NOT EXISTS canon_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    connection.execute("INSERT OR REPLACE INTO canon_meta(key, value) VALUES('canon_schema_version','1')")
    connection.execute(
        "INSERT INTO canon_facts(fact_id, novel_id, status, canonical_key, payload) VALUES (?,?,?,?,?)",
        ("FACT_LEGACY", "n1", "happened", "LEGACY",
         json.dumps({"fact_id": "FACT_LEGACY", "canonical_key": "LEGACY", "novel_id": "n1",
                     "status": "happened", "canonical_description": "旧库事实"})))
    connection.commit()
    connection.close()

    repo = CanonRepository(path)
    assert repo.schema_version == CANON_SCHEMA_VERSION
    assert "canon_constraints" in repo.table_names()
    assert [f.fact_id for f in repo.facts("n1")] == ["FACT_LEGACY"]
    summary = repo.schema_summary()
    assert summary["canon_schema_version"] == CANON_SCHEMA_VERSION
    assert len(summary["tables"]) >= 12
    repo.close()


def pytest_raises(exc_type):
    import pytest
    return pytest.raises(exc_type)
