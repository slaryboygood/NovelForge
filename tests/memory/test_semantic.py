"""Semantic Memory（V4-03 §8、§23–§24）。"""

from __future__ import annotations

from pathlib import Path

from novelforge.memory.embedding import (
    LocalHashEmbedding,
    NullEmbeddingProvider,
    cosine,
)
from novelforge.memory.semantic import SemanticEntry, SemanticIndex
from novelforge.memory import MemoryQuery
from support import build_novel, service_for


def test_structured_and_keyword_retrieval() -> None:
    index = SemanticIndex()
    index.add(SemanticEntry(entry_id="e1", novel_id="novel_a",
                            text="主角不会使用枪械",
                            entities=("hero",), keywords=("主角", "枪械")))
    index.add(SemanticEntry(entry_id="e2", novel_id="novel_a",
                            text="中转站备用电源被破坏",
                            entities=("station",), keywords=("中转站", "电源")))
    assert [row[0].entry_id for row in index.search("novel_a", entities=("hero",))] \
        == ["e1"]
    assert [row[0].entry_id for row in index.search("novel_a", task="电源")] == ["e2"]


def test_semantic_index_is_novel_scoped() -> None:
    index = SemanticIndex()
    index.add(SemanticEntry(entry_id="e1", novel_id="novel_a", text="同名角色",
                            entities=("hero",)))
    index.add(SemanticEntry(entry_id="e2", novel_id="novel_b", text="同名角色",
                            entities=("hero",)))
    rows = index.search("novel_a", entities=("hero",))
    assert [row[0].entry_id for row in rows] == ["e1"]


def test_null_embedding_is_default_and_offline() -> None:
    provider = NullEmbeddingProvider()
    assert provider.dimensions == 0
    assert provider.embed(["任意文本"]) == [()]
    index = SemanticIndex()  # 默认无 embedding
    assert index.embedder.provider_id == "null"
    index.add(SemanticEntry(entry_id="e1", novel_id="novel_a", text="x",
                            entities=("hero",)))
    assert index.entries("novel_a")[0].embedding == ()


def test_local_hash_embedding_is_deterministic_and_hybrid_scoring_works() -> None:
    provider = LocalHashEmbedding(dimensions=16)
    first = provider.embed(["同一段文本"])[0]
    second = provider.embed(["同一段文本"])[0]
    assert first == second and len(first) == 16
    assert cosine(first, second) > 0.99

    index = SemanticIndex(embedder=provider)
    index.add(SemanticEntry(entry_id="e1", novel_id="novel_a",
                            text="中转站备用电源被破坏",
                            keywords=("中转站", "电源")))
    without = index.search("novel_a", task="备用电源", allow_embeddings=False)
    with_embeddings = index.search("novel_a", task="备用电源", allow_embeddings=True)
    assert without and with_embeddings
    assert with_embeddings[0][1] >= without[0][1]
    assert "embedding_similarity" in with_embeddings[0][2]


def test_semantic_entries_can_be_built_from_retrieval_items(tmp_path: Path) -> None:
    build_novel(tmp_path, "novel_alpha", title="阿尔法计划", fact_text="主角不会使用枪械")
    service = service_for(tmp_path, "novel_alpha")
    from novelforge.memory.retrieval import semantic_entries_from_items

    items = service.index.items("novel_alpha", source_types=("canon_fact",))
    assert service.add_semantic(semantic_entries_from_items("novel_alpha", items)) >= 1
    assert service.semantic.count("novel_alpha") >= 1
    result = service.search(MemoryQuery(novel_id="novel_alpha", task="枪械",
                                        source_types=("semantic",)))
    assert result.items, "semantic 索引应可被检索"
