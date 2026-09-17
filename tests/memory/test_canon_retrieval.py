"""Canon retrieval（V4-03 §5）。"""

from __future__ import annotations

from pathlib import Path

from novelforge.memory import MemoryQuery, MemoryService
from novelforge.memory.sources import CanonMemorySource
from novelforge.persistence.paths import canon_db_path
from support import build_novel, service_for


def test_canon_source_projects_facts_and_entities(tmp_path: Path) -> None:
    build_novel(tmp_path, "novel_alpha", title="阿尔法计划", fact_text="主角不会使用枪械")
    source = CanonMemorySource(tmp_path)
    items = list(source.provide("novel_alpha"))
    types = {item.source.source_type for item in items}
    assert types == {"canon_fact", "canon_entity"}
    fact = next(item for item in items if item.source.source_type == "canon_fact")
    assert "枪械" in fact.text
    assert fact.source.revision is not None


def test_canon_source_is_read_only(tmp_path: Path) -> None:
    """检索不得写入 Canon（fingerprint 前后一致）。"""

    build_novel(tmp_path, "novel_alpha", title="阿尔法计划", fact_text="主角不会使用枪械")
    db = canon_db_path(tmp_path, "novel_alpha")
    before = (db.stat().st_size, db.stat().st_mtime_ns)
    service = service_for(tmp_path, "novel_alpha")
    service.search(MemoryQuery(novel_id="novel_alpha", task="枪械"))
    service.rebuild()
    after = (db.stat().st_size, db.stat().st_mtime_ns)
    assert before == after, "Canon 是权威事实，retrieval 不得修改它"


def test_canon_memory_missing_db_returns_empty(tmp_path: Path) -> None:
    source = CanonMemorySource(tmp_path)
    assert source.available("novel_without_canon") is False
    assert list(source.provide("novel_without_canon")) == []


def test_canon_fact_is_retrievable_by_task_keyword(tmp_path: Path) -> None:
    build_novel(tmp_path, "novel_alpha", title="阿尔法计划", fact_text="主角不会使用枪械")
    service = MemoryService("novel_alpha", project_root=tmp_path,
                            sources=[CanonMemorySource(tmp_path)])
    service.rebuild()
    result = service.search(MemoryQuery(novel_id="novel_alpha", task="枪械"))
    assert any("枪械" in item.text for item in result.items)
    assert all(item.source.source_type.startswith("canon") for item in result.items)


def test_canon_retrieval_is_novel_scoped(tmp_path: Path) -> None:
    from support import build_two_novels

    alpha, beta = build_two_novels(tmp_path)
    service = service_for(tmp_path, alpha)
    result = service.search(MemoryQuery(novel_id=alpha, task="枪械"))
    assert result.items
    blob = str(result.as_dict())
    assert beta not in blob
    assert "novel_beta" not in blob
    assert all(item.source.source_id != "FACT_WEAPON_RULE_FOR_BETA"
               for item in result.items)

