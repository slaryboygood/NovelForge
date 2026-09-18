"""C10：CanonBootstrap / 原子 rebuild / 只读 API。

post-release cleanup：`canon/outline_adapter.py`（把 Canon-aware 章纲写进 V2
`StoryOutlineRepository`）随 V2 outline 存储一并退休 —— 那个适配器没有 current
消费者，且会重新引入第二套 outline 存储。对应断言随能力删除。
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from novelforge.api.canon_routes import install_canon_api
from novelforge.story_engine.canon.bootstrap import CanonBootstrap
from novelforge.story_engine.canon.models import CanonEvent, CanonFact
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
