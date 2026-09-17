"""Cache 测试（V4-02 §20–21、§28）。"""

from __future__ import annotations

from fake_provider import build_harness
from pydantic import BaseModel, ConfigDict

from novelforge.ai import InMemoryCache, build_cache_key, cache_allowed


class Labels(BaseModel):
    model_config = ConfigDict(extra="forbid")
    labels: list[str]


def test_cache_key_is_stable_and_sensitive_to_inputs() -> None:
    base = dict(provider="p", model="m", contract_id="c", contract_version=1,
                context={"a": 1}, policy_fields={"profile": "cost_first"})
    key = build_cache_key(**base).as_string()
    assert build_cache_key(**base).as_string() == key

    variants = {
        "provider": {**base, "provider": "p2"},
        "model": {**base, "model": "m2"},
        "contract": {**base, "contract_id": "c2"},
        "contract_version": {**base, "contract_version": 2},
        "context": {**base, "context": {"a": 2}},
        "policy": {**base, "policy_fields": {"profile": "quality_first"}},
        "revision": {**base, "revision": 7},
    }
    for name, payload in variants.items():
        assert build_cache_key(**payload).as_string() != key, \
            f"{name} 变化必须改变 cache key"


def test_cache_key_contains_no_raw_content() -> None:
    key = build_cache_key(provider="p", model="m", contract_id="c",
                          contract_version=1,
                          context={"text": "极其敏感的正文内容"},
                          policy_fields={}).as_string()
    assert "极其敏感" not in key
    assert len(key) < 200


def test_cache_hit_and_miss() -> None:
    harness = build_harness(script=['{"labels": ["a"]}'], output_model=Labels,
                            cacheable=True)
    first = harness.generate()
    second = harness.generate()
    assert first.cache["hit"] is False
    assert second.cache["hit"] is True
    assert second.output.labels == ["a"]
    assert harness.provider.call_count == 1, "命中缓存时不再调用 provider"
    assert harness.cache.hits == 1 and harness.cache.misses == 1


def test_context_change_invalidates_cache() -> None:
    harness = build_harness(script=['{"labels": ["a"]}', '{"labels": ["b"]}'],
                            output_model=Labels, cacheable=True)
    harness.generate(context={"text": "第一个上下文"})
    second = harness.generate(context={"text": "第二个上下文"})
    assert second.cache["hit"] is False
    assert harness.provider.call_count == 2


def test_creative_contract_is_not_cached_by_default() -> None:
    assert cache_allowed(contract_cacheable=False,
                         generation_mode="structured_json") is False
    harness = build_harness(script=['{"labels": ["a"]}', '{"labels": ["a"]}'],
                            output_model=Labels, cacheable=False)
    harness.generate()
    second = harness.generate()
    assert second.cache["allowed"] is False
    assert second.cache["hit"] is False
    assert harness.provider.call_count == 2, "不可缓存的 contract 必须每次调用"


def test_in_memory_cache_eviction_and_stats() -> None:
    cache = InMemoryCache(max_entries=2)
    keys = [build_cache_key(provider="p", model="m", contract_id=f"c{i}",
                            contract_version=1, context={}, policy_fields={})
            for i in range(3)]
    for index, key in enumerate(keys):
        cache.put(key, index)
    stats = cache.stats()
    assert stats["entries"] == 2, "超过上限时按插入顺序淘汰"
    assert cache.get(keys[0]) is None
    assert cache.get(keys[2]) == 2

