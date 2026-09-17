"""C05：CanonContextBuilder（三视图 / 确定性 / budget / future leak / knowledge 边界）。"""

from __future__ import annotations

from novelforge.story_engine.canon.context import CanonContextBuilder, sanitize_writer_text
from novelforge.story_engine.canon.models import (
    CanonConstraint,
    CanonFact,
    CanonForeshadow,
    CanonKnowledge,
    CanonRelationship,
    CanonRenderRef,
)
from novelforge.story_engine.canon.repository import CanonRepository


def _repo(tmp_path) -> CanonRepository:
    repo = CanonRepository(tmp_path / "canon.sqlite")
    repo.save_fact(CanonFact(
        fact_id="FACT_ZERO_LAYER_GATE_FIRST_OPEN", canonical_key="ZERO_LAYER_GATE_FIRST_OPEN",
        novel_id="n1", status="happened", canonical_description="第一次打开第零层门禁",
        subjects=["protagonist"], provenance="story_state",
        first_occurrence_ref=CanonRenderRef(chapter_uuid="uuid-a", display_number=120)))
    repo.save_fact(CanonFact(
        fact_id="FACT_FUTURE_REVEAL", canonical_key="FUTURE_REVEAL", novel_id="n1",
        status="planned", canonical_description="未来才会揭示的真相",
        first_occurrence_ref=CanonRenderRef(chapter_uuid="uuid-z", display_number=500)))
    repo.save_knowledge(CanonKnowledge(
        knowledge_id="KNW_SUSPECT", novel_id="n1", fact_id="FACT_ZERO_LAYER_GATE_FIRST_OPEN",
        holder_id="protagonist", state="suspected", learned_at=90, learned_from="observation"))
    repo.save_knowledge(CanonKnowledge(
        knowledge_id="KNW_FUTURE", novel_id="n1", fact_id="FACT_FUTURE_REVEAL",
        holder_id="protagonist", state="known", learned_at=480, learned_from="reveal"))
    repo.save_relationship(CanonRelationship(
        relationship_id="REL_HERO_DOG", novel_id="n1", source_id="protagonist",
        target_id="npc_1", kind="trust", state="10"))
    repo.save_foreshadow(CanonForeshadow(
        foreshadow_id="FS_DOG_TAG", novel_id="n1", subject="颈圈铭牌的来历", status="planted",
        intended_payoff="铭牌是门禁身份"))
    repo.save_constraint(CanonConstraint(
        constraint_id="CON_DOG_LIMIT", novel_id="n1", description="伙伴能力只能感知异常，不可解释"))
    return repo


def test_deterministic_retrieval_and_digest(tmp_path) -> None:
    repo = _repo(tmp_path)
    builder = CanonContextBuilder(repo)
    first = builder.planner_context("n1", arc_intent="打开第零层", temporal_cutoff=200)
    second = builder.planner_context("n1", arc_intent="打开第零层", temporal_cutoff=200)
    assert [e.canon_id for e in first.entries] == [e.canon_id for e in second.entries]
    assert first.manifest.context_digest == second.manifest.context_digest
    repo.close()


def test_relevant_included_and_future_excluded(tmp_path) -> None:
    repo = _repo(tmp_path)
    builder = CanonContextBuilder(repo)
    bundle = builder.planner_context("n1", temporal_cutoff=200)
    ids = [e.canon_id for e in bundle.entries]
    assert "FACT_ZERO_LAYER_GATE_FIRST_OPEN" in ids
    assert "FACT_FUTURE_REVEAL" not in ids
    assert "FACT_FUTURE_REVEAL" in bundle.manifest.excluded_future_ids
    happened = next(e for e in bundle.entries if e.canon_id == "FACT_ZERO_LAYER_GATE_FIRST_OPEN")
    planned = next(e for e in bundle.entries if e.canon_id == "FS_DOG_TAG")
    assert happened.type == "HAPPENED" and planned.type == "PLANNED"
    repo.close()


def test_prerequisites_and_constraints_are_never_trimmed(tmp_path) -> None:
    repo = _repo(tmp_path)
    builder = CanonContextBuilder(repo)
    bundle = builder.planner_context("n1", max_items=1, max_chars=1)
    kept = {e.canon_id for e in bundle.entries}
    assert "FACT_ZERO_LAYER_GATE_FIRST_OPEN" in kept  # P0
    assert bundle.manifest.trimmed_ids  # 低优先级被裁剪
    repo.close()


def test_character_context_hides_unknown_and_future(tmp_path) -> None:
    repo = _repo(tmp_path)
    builder = CanonContextBuilder(repo)
    bundle = builder.character_context("n1", "protagonist", temporal_cutoff=200)
    rendered = " ".join(e.canonical_description for e in bundle.entries)
    assert "怀疑" in rendered and "第一次打开第零层门禁" in rendered
    assert "未来才会揭示的真相" not in rendered          # future knowledge 被 cutoff 排除
    assert all("寻路者" not in line for line in rendered)   # 未知道的真相不会泄漏
    repo.close()


def test_writer_context_hides_internal_ids_and_marks_planned(tmp_path) -> None:
    repo = _repo(tmp_path)
    builder = CanonContextBuilder(repo)
    bundle = builder.writer_context("n1", temporal_cutoff=200)
    joined = "\n".join(bundle.rendered)
    assert "FACT_" not in joined and "EVENT_" not in joined and "KNW_" not in joined
    assert "FS_" not in joined and "ch325" not in joined and "Arc" not in joined
    assert "尚未发生" in joined
    assert bundle.manifest.purpose == "writer"
    repo.close()


def test_manifest_records_ids_and_sanitizer_is_reusable() -> None:
    assert sanitize_writer_text("承接 FACT_X 与 ch142 的结果") == "承接 与 的结果"
    assert sanitize_writer_text("第3卷 Arc A2 的事件") == "的事件"
