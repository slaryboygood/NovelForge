"""派生记忆失效（V4-03 §13–§14）。"""

from __future__ import annotations

from pathlib import Path

from novelforge.memory import MemoryQuery, RetrievalPolicy
from support import build_novel, service_for


def test_source_revision_drift_marks_stale(tmp_path: Path) -> None:
    build_novel(tmp_path, "novel_alpha", title="阿尔法计划", fact_text="主角不会使用枪械")
    service = service_for(tmp_path, "novel_alpha")
    before = service.stats()["stale"]
    assert before == 0

    # 模拟 canonical 侧 revision 前进（新事实导入）
    from novelforge.story_engine.canon.models import CanonFact
    from novelforge.story_engine.canon.repository import CanonRepository
    from novelforge.persistence.paths import canon_db_path

    repository = CanonRepository(canon_db_path(tmp_path, "novel_alpha"))
    try:
        repository.save_fact(CanonFact(fact_id="FACT_NEW_ONE", canonical_key="NEW_ONE",
                                       novel_id="novel_alpha", status="happened",
                                       canonical_description="一条新事实"))
    finally:
        repository.close()

    marked = service.refresh_staleness()
    assert marked >= 1, "canonical revision 变化后旧派生记忆必须被标记 stale"
    report = service.stale_report()
    assert any(row["reason"] == "source_revision_changed" for row in report)


def test_stale_items_are_excluded_by_default(tmp_path: Path) -> None:
    build_novel(tmp_path, "novel_alpha", title="阿尔法计划", fact_text="主角不会使用枪械")
    service = service_for(tmp_path, "novel_alpha")
    service.index.mark_stale("novel_alpha", source_id="FACT_WEAPON_RULE",
                             reason="manual_test")
    excluded = service.search(MemoryQuery(novel_id="novel_alpha", task="枪械"))
    assert all(item.source.source_id != "FACT_WEAPON_RULE" for item in excluded.items)
    assert any(row["reason"] == "stale_excluded" for row in excluded.stale)

    included = service.search(MemoryQuery(
        novel_id="novel_alpha", task="枪械",
        policy=RetrievalPolicy(include_stale=True, top_k=50)))
    assert any(item.source.source_id == "FACT_WEAPON_RULE" for item in included.items)
    stale_item = next(item for item in included.items
                      if item.source.source_id == "FACT_WEAPON_RULE")
    assert stale_item.stale is True, "stale 条目必须带标记（调用方可见）"
    assert included.items[-1].source.source_id == "FACT_WEAPON_RULE", (
        "stale 条目即使被包含也必须排在最后（惩罚项）")


def test_stale_items_are_penalized_in_ranking(tmp_path: Path) -> None:
    from novelforge.memory import MemoryService
    from novelforge.memory.retrieval import static_items

    service = MemoryService("novel_stale")
    service.add_items(static_items("novel_stale", [
        {"source_type": "canon_fact", "source_id": "FACT_A", "text": "旧事实",
         "revision": 1},
        {"source_type": "canon_fact", "source_id": "FACT_B", "text": "新事实",
         "revision": 2},
    ]))
    service.index.mark_stale("novel_stale", source_id="FACT_A")
    result = service.search(MemoryQuery(
        novel_id="novel_stale", policy=RetrievalPolicy(include_stale=True)))
    order = [item.source.source_id for item in result.items]
    assert order.index("FACT_B") < order.index("FACT_A")


def test_rebuild_restores_freshness(tmp_path: Path) -> None:
    build_novel(tmp_path, "novel_alpha", title="阿尔法计划", fact_text="主角不会使用枪械")
    service = service_for(tmp_path, "novel_alpha")
    service.index.mark_stale("novel_alpha", source_id="FACT_WEAPON_RULE")
    assert service.stats()["stale"] >= 1
    service.rebuild()
    assert service.stats()["stale"] == 0, "重建后索引应与 canonical 一致"


def test_rebuild_is_idempotent(tmp_path: Path) -> None:
    build_novel(tmp_path, "novel_alpha", title="阿尔法计划", fact_text="主角不会使用枪械")
    service = service_for(tmp_path, "novel_alpha")
    first = service.rebuild()
    second = service.rebuild()
    assert first["counts"] == second["counts"]
    assert first["digest"] == second["digest"], "重建必须幂等（同一 canonical 状态）"
