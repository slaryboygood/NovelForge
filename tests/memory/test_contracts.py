"""Memory 契约测试（V4-03 §9–§10）。"""

from __future__ import annotations

import pytest

from novelforge.memory import (
    MEMORY_SCHEMA_VERSION,
    MemoryIsolationError,
    MemoryItem,
    MemoryQuery,
    MemoryScope,
    MemorySource,
    RetrievalPolicy,
)


def test_public_contract_stays_small() -> None:
    import novelforge.memory as memory

    assert len(memory.__all__) <= 30, "Public Contract 必须保持精简（§10）"
    for name in ("MemoryService", "MemoryQuery", "MemoryResult", "ContextBuilder",
                 "ContextRequest", "ContextBundle", "AuthorPreferenceService"):
        assert name in memory.__all__
    for internal in ("MemoryIndex", "EpisodicStore", "SemanticIndex",
                     "LocalHashEmbedding"):
        assert internal not in memory.__all__, f"{internal} 属于内部实现，不应公开"


def test_scope_and_query_require_novel_id() -> None:
    with pytest.raises(MemoryIsolationError):
        MemoryScope(novel_id="")
    with pytest.raises(MemoryIsolationError):
        MemoryQuery(novel_id="   ")


def test_source_and_item_carry_provenance() -> None:
    source = MemorySource(source_type="canon_fact", source_id="FACT_1", revision=3)
    assert source.ref == "FACT_1@3"
    assert source.memory_type == "canon"
    item = MemoryItem(memory_id="canon_fact:FACT_1", memory_type="canon",
                      text="主角不会使用枪械", source=source, token_estimate=0)
    payload = item.as_dict()
    assert payload["source"]["revision"] == 3
    assert payload["memory_id"] == "canon_fact:FACT_1"


def test_retrieval_policy_validation() -> None:
    with pytest.raises(Exception):
        RetrievalPolicy(top_k=0)
    with pytest.raises(Exception):
        RetrievalPolicy(min_relevance=2.0)
    policy = RetrievalPolicy(top_k=3, include_stale=True)
    assert policy.as_dict()["top_k"] == 3


def test_memory_schema_version_is_declared() -> None:
    assert MEMORY_SCHEMA_VERSION >= 1

