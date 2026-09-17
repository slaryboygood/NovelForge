"""C10：CanonBootstrap / 原子 rebuild / 既有 Outline 适配器 / 只读 API。"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from novelforge.api.canon_routes import install_canon_api
from novelforge.story_engine.canon.bootstrap import CanonBootstrap
from novelforge.story_engine.canon.models import CanonEvent, CanonFact
from novelforge.story_engine.canon.outline_adapter import (
    OutlineRepositoryAdapter,
    item_payload_from_chapter,
)
from novelforge.story_engine.canon.repository import CanonRepository


def _state() -> dict:
    return {
        "schema_version": 1, "novel_id": "n1",
        "characters": {"protagonist": {"name": "主角"}},
        "factions": {}, "relationships": [],
        "knowledge": [{"id": "clue", "holders": ["protagonist"], "tick": 2,
                       "source": "action:probe", "source_event": ""}],
        "flags": {"foreshadows": {"fs_tag": {"status": "planted", "reason": "旧物"}}},
        "effect_log": [{"op": "add_knowledge", "entity": "protagonist", "target": "clue",
                        "value": None, "source": "action:probe", "data": {"tick": 1}}],
    }


def test_bootstrap_priority_and_coverage(tmp_path) -> None:
    repo = CanonRepository(tmp_path / "canon.sqlite")
    bootstrap = CanonBootstrap(repo)
    result = bootstrap.bootstrap("n1", state=_state(),
                                 content_pack={"foreshadows": [{"id": "fs_pack", "title": "内容包伏笔"}]},
                                 profile={"future_plan": {"stages": [{"id": "s1", "title": "阶段一"}]}})
    assert result.created["story_state"] >= 1
    assert result.created["content_pack"] == 1 and result.created["profile"] == 1
    fact_ids = {f.fact_id for f in repo.facts("n1")}
    assert any(f.startswith("FACT_") for f in fact_ids)
    # StoryState 导入标 confirmed；pack/profile 标 imported（低置信）
    provenances = {f.provenance for f in repo.facts("n1")}
    assert "story_state" in provenances or "confirmed" in provenances
    assert "imported" in provenances
    assert result.report.partial is True
    assert "CANON_PARTIAL" in result.report.note
    repo.close()


def test_rebuild_is_atomic_and_keeps_identity(tmp_path) -> None:
    repo = CanonRepository(tmp_path / "canon.sqlite")
    repository = CanonBootstrap(repo).bootstrap("n1", state=_state()).created
    before = sorted(f.fact_id for f in repo.facts("n1"))
    assert repository["story_state"] >= 1
    second = CanonBootstrap(repo).rebuild("n1", state=_state())
    after = sorted(f.fact_id for f in repo.facts("n1"))
    assert before == after                      # rebuild 幂等：identity 不变
    assert "REBUILD" not in second.report.note
    repo.close()


def test_rebuild_keeps_original_on_failure(tmp_path) -> None:
    repo = CanonRepository(tmp_path / "canon.sqlite")
    CanonBootstrap(repo).bootstrap("n1", state=_state())
    before = sorted(f.fact_id for f in repo.facts("n1"))
    broken = CanonBootstrap(repo)
    broken._validate_candidate = staticmethod(lambda repository, novel_id: ["KNOWLEDGE_BEFORE_FACT"])
    result = broken.rebuild("n1", state=_state())
    assert "REBUILD_REJECTED" in result.report.note
    assert sorted(f.fact_id for f in repo.facts("n1")) == before   # 原 Canon 保留
    repo.close()


def test_outline_adapter_maps_to_existing_item_fields() -> None:
    chapter = {"chapter_uuid": "uuid_a", "title": "门后的第一层", "goal": "打开门禁",
               "concrete_events": ["他把铭牌按进凹槽等待回应"], "start_state": "站在门前",
               "end_state": "门已打开", "hook": "长廊传来第二种脚步", "location": "gate",
               "participants": ["protagonist"], "canon_fact_ids": ["FACT_GATE_OPEN"],
               "canon_event_ids": [], "canon_source_refs": [{"source_uuid": "uuid_gate"}],
               "context_manifest_id": "CTX_1", "cost": "消耗备用晶体"}
    payload = item_payload_from_chapter(chapter)
    from novelforge.story_builder.models import OutlineItem
    item = OutlineItem.model_validate(payload)          # 复用既有模型，不另造
    assert item.chapter_uuid == "uuid_a" and item.canon_fact_ids == ["FACT_GATE_OPEN"]
    assert item.context_manifest_id == "CTX_1"
    assert "FACT_" not in item.summary and "ch" not in item.title
    assert OutlineRepositoryAdapter(".").level == "CHAPTER"


def test_canon_api_read_endpoints(tmp_path) -> None:
    repo = CanonRepository(tmp_path / "novel/authoring/story_engine/canon/novel_01.sqlite")
    repo.save_fact(CanonFact(fact_id="FACT_A", canonical_key="A", novel_id="novel_01",
                             status="happened", canonical_description="事实 A"))
    repo.save_event(CanonEvent(event_id="EVENT_A", canonical_key="A", novel_id="novel_01",
                               status="occurred", narrative_role="canonical"))
    repo.close()
    app = FastAPI()
    install_canon_api(app, tmp_path)
    client = TestClient(app)
    assert client.get("/api/story-builder/canon/facts?novel_id=novel_01").json()["total"] == 1
    assert client.get("/api/story-builder/canon/events?novel_id=novel_01").json()["items"][0]["event_id"] == "EVENT_A"
    graph = client.get("/api/story-builder/canon/graph?novel_id=novel_01").json()
    assert graph["node_count"] >= 2
    validate = client.get("/api/story-builder/canon/validate?novel_id=novel_01").json()
    assert "schema" in validate and validate["schema"]["canon_schema_version"] >= 3
    listed = client.get("/api/story-builder/canon/knowledge?novel_id=novel_01").json()
    assert listed["total"] == 0
