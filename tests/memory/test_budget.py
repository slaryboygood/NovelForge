"""Token 预算与优先级（V4-03 §21）。"""

from __future__ import annotations

import pytest

from novelforge.memory import MemoryItem, MemorySource
from novelforge.memory.context.budget import (
    BLOCK_PRIORITY_ORDER,
    PROTECTED_BLOCKS,
    DeterministicTokenEstimator,
    estimate_tokens,
    trim_to_budget,
)


def _item(memory_id: str, text: str) -> MemoryItem:
    return MemoryItem(memory_id=memory_id, memory_type="canon", text=text,
                      source=MemorySource(source_type="canon_fact",
                                          source_id=memory_id, revision=1))


def test_token_estimator_is_deterministic_and_monotonic() -> None:
    estimator = DeterministicTokenEstimator()
    assert estimator.estimate("") == 0
    short = estimator.estimate("abcd")
    long = estimator.estimate("abcd" * 10)
    assert 0 < short < long
    assert estimate_tokens("中文内容") == estimator.estimate("中文内容")


def test_priority_order_is_fixed() -> None:
    assert BLOCK_PRIORITY_ORDER[0] == "required.canon"
    assert BLOCK_PRIORITY_ORDER[1] == "required.story_state"
    assert BLOCK_PRIORITY_ORDER[2] == "required.target"
    assert BLOCK_PRIORITY_ORDER[-1] == "relevant.background"
    assert PROTECTED_BLOCKS == {"required.canon", "required.story_state",
                                "required.target"}


def test_low_priority_is_dropped_first() -> None:
    blocks = [
        ("required.canon", [_item("c1", "必须保留的 Canon")]),
        ("required.story_state", [_item("s1", "当前状态")]),
        ("relevant.semantic", [_item("m1", "背景语义信息" * 20)]),
    ]
    kept, dropped, report = trim_to_budget(blocks, budget=20)
    assert kept["required.canon"] and kept["required.story_state"]
    assert not kept["relevant.semantic"], "低优先级内容先被裁剪"
    assert dropped and dropped[0]["reason"] == "budget_exceeded"
    assert report["limit"] == 20 and report["overflow"] == 0


def test_protected_blocks_are_never_dropped() -> None:
    blocks = [
        ("required.canon", [_item(f"c{i}", "很长的必填事实" * 10) for i in range(3)]),
        ("relevant.semantic", [_item("m1", "语义")]),
    ]
    kept, dropped, report = trim_to_budget(blocks, budget=10)
    assert len(kept["required.canon"]) == 3, "保护块不得被静默删除"
    assert report["overflow"] > 0, "超预算必须显式报告 overflow"
    assert dropped and dropped[0]["block_id"] == "relevant.semantic"


def test_invalid_budget_rejected() -> None:
    with pytest.raises(ValueError):
        trim_to_budget([("required.canon", [])], budget=0)

