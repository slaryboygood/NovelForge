"""检索行为：确定性、排序稳定、结果带 provenance（V4-03 §9、§30）。"""

from __future__ import annotations

from pathlib import Path

from novelforge.memory import MemoryQuery, RetrievalPolicy
from support import build_novel, service_for


def test_search_returns_structured_items_with_provenance(tmp_path: Path) -> None:
    build_novel(tmp_path, "novel_alpha", title="阿尔法计划", fact_text="主角不会使用枪械")
    service = service_for(tmp_path, "novel_alpha")
    result = service.search(MemoryQuery(novel_id="novel_alpha", task="枪械 规则",
                                        entities=("hero",),
                                        policy=RetrievalPolicy(top_k=5)))
    assert result.items, "至少应检索到 canon / story_state 条目"
    for item in result.items:
        assert item.source.source_id
        assert item.source.source_type
        assert item.selection_reason
    assert result.provenance
    assert all(row["source_id"] and row["retrieval_reason"]
               for row in result.provenance)
    assert result.memory_schema_version >= 1


def test_same_query_is_deterministic(tmp_path: Path) -> None:
    build_novel(tmp_path, "novel_alpha", title="阿尔法计划", fact_text="主角不会使用枪械")
    service = service_for(tmp_path, "novel_alpha")
    query = MemoryQuery(novel_id="novel_alpha", task="枪械", entities=("hero",),
                        policy=RetrievalPolicy(top_k=6))
    first = service.search(query)
    second = service.search(query)
    assert [item.memory_id for item in first.items] == \
        [item.memory_id for item in second.items]
    assert first.digest == second.digest, "同一 query 必须得到同一 digest"


def test_ranking_tie_break_is_stable(tmp_path: Path) -> None:
    """同分条目按 (source_type, source_id) 稳定排序。"""

    from novelforge.memory import MemoryService
    from novelforge.memory.retrieval import static_items

    service = MemoryService("novel_tie")
    service.add_items(static_items("novel_tie", [
        {"source_type": "canon_entity", "source_id": "bbb", "text": "同じ内容",
         "metadata": {"entities": ["aaa"]}},
        {"source_type": "canon_entity", "source_id": "aaa", "text": "同じ内容",
         "metadata": {"entities": ["aaa"]}},
    ]))
    result = service.search(MemoryQuery(novel_id="novel_tie", entities=("aaa",)))
    assert [item.source.source_id for item in result.items] == ["aaa", "bbb"]


def test_search_can_restrict_source_types(tmp_path: Path) -> None:
    build_novel(tmp_path, "novel_alpha", title="阿尔法计划", fact_text="主角不会使用枪械")
    service = service_for(tmp_path, "novel_alpha")
    result = service.search(MemoryQuery(novel_id="novel_alpha",
                                        source_types=("canon_fact",)))
    assert result.items
    assert {item.source.source_type for item in result.items} == {"canon_fact"}


def test_max_per_source_type_and_top_k(tmp_path: Path) -> None:
    build_novel(tmp_path, "novel_alpha", title="阿尔法计划", fact_text="主角不会使用枪械")
    service = service_for(tmp_path, "novel_alpha")
    result = service.search(MemoryQuery(
        novel_id="novel_alpha",
        policy=RetrievalPolicy(top_k=2, max_per_source_type=1)))
    assert len(result.items) <= 2
    counts: dict[str, int] = {}
    for item in result.items:
        counts[item.source.source_type] = counts.get(item.source.source_type, 0) + 1
    assert all(value <= 1 for value in counts.values())
    assert any(row["reason"] == "top_k_cutoff" for row in result.dropped)


def test_required_source_ids_are_never_dropped(tmp_path: Path) -> None:
    build_novel(tmp_path, "novel_alpha", title="阿尔法计划", fact_text="主角不会使用枪械")
    service = service_for(tmp_path, "novel_alpha")
    result = service.search(MemoryQuery(
        novel_id="novel_alpha", required_source_ids=("FACT_WEAPON_RULE",),
        policy=RetrievalPolicy(top_k=1)))
    assert any(item.source.source_id == "FACT_WEAPON_RULE" for item in result.items)

