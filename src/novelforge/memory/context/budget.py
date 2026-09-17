"""Token 预算与优先级裁剪（V4-03 §21）。

优先级（从高到低，**固定**）：

```text
required.canon > required.story_state > required.target >
relevant.characters > recent.episodes > relevant.setup_payoff >
relevant.locations > relevant.semantic > preferences > relevant.background
```

超预算时：先删低优先级 block 的条目，再压缩（§21 / §22）。
**永不静默删除** required.canon / required.story_state / required.target；
如果保护块自己就超预算，报告 overflow 而不是丢弃。
"""

from __future__ import annotations

import math
from typing import Protocol, Sequence

from ..contracts import MemoryItem

#: block 优先级（数值越小越先保留）
BLOCK_PRIORITY: dict[str, int] = {
    "required.canon": 0,
    "required.story_state": 1,
    "required.target": 2,
    "relevant.characters": 3,
    "recent.episodes": 4,
    "relevant.setup_payoff": 5,
    "relevant.locations": 6,
    "relevant.semantic": 7,
    "preferences": 8,
    "relevant.background": 9,
}

#: 不允许被预算裁剪掉的 block
PROTECTED_BLOCKS: frozenset[str] = frozenset(
    {"required.canon", "required.story_state", "required.target"})

BLOCK_PRIORITY_ORDER: tuple[str, ...] = tuple(
    sorted(BLOCK_PRIORITY, key=lambda key: (BLOCK_PRIORITY[key], key)))


class TokenEstimator(Protocol):
    def estimate(self, text: str) -> int: ...


class DeterministicTokenEstimator:
    """确定性估算：ASCII 约 4 字符/token，非 ASCII 约 1.5 字符/token（保守）。"""

    def estimate(self, text: str) -> int:
        value = str(text or "")
        if not value:
            return 0
        ascii_chars = sum(1 for char in value if ord(char) < 128)
        other_chars = len(value) - ascii_chars
        return max(1, int(math.ceil(ascii_chars / 4.0 + other_chars / 1.5)))


def estimate_tokens(text: str, *, estimator: TokenEstimator | None = None) -> int:
    return (estimator or DeterministicTokenEstimator()).estimate(text)


def item_tokens(item: MemoryItem, *, estimator: TokenEstimator | None = None) -> int:
    return item.token_estimate or estimate_tokens(item.text, estimator=estimator)


def block_priority(block_id: str) -> int:
    return BLOCK_PRIORITY.get(block_id, BLOCK_PRIORITY["relevant.background"])


def trim_to_budget(blocks: Sequence[tuple[str, Sequence[MemoryItem]]], *,
                   budget: int, estimator: TokenEstimator | None = None
                   ) -> tuple[dict[str, list[MemoryItem]], list[dict[str, object]],
                              dict[str, int]]:
    """按优先级裁剪到预算内；返回 (kept_by_block, dropped_rows, budget_report)。"""

    if int(budget) <= 0:
        raise ValueError("token budget 必须 > 0")
    ordered = sorted(blocks, key=lambda row: (block_priority(row[0]), row[0]))
    kept: dict[str, list[MemoryItem]] = {block_id: [] for block_id, _ in ordered}
    dropped: list[dict[str, object]] = []
    used = 0

    # 第一遍：保护块优先占用预算（永不裁剪）
    for block_id, items in ordered:
        if block_id not in PROTECTED_BLOCKS:
            continue
        for item in items:
            kept[block_id].append(item)
            used += item_tokens(item, estimator=estimator)

    # 第二遍：其余 block 按优先级填充，装不下就记录 dropped
    for block_id, items in ordered:
        if block_id in PROTECTED_BLOCKS:
            continue
        for item in items:
            tokens = item_tokens(item, estimator=estimator)
            if used + tokens > int(budget):
                dropped.append({"block_id": block_id, "memory_id": item.memory_id,
                                "token_estimate": tokens,
                                "reason": "budget_exceeded"})
                continue
            kept[block_id].append(item)
            used += tokens

    protected_tokens = sum(item_tokens(item, estimator=estimator)
                           for block_id in PROTECTED_BLOCKS
                           for item in kept.get(block_id, []))
    report = {"limit": int(budget), "used": int(used),
              "protected_tokens": int(protected_tokens),
              "overflow": max(0, protected_tokens - int(budget)),
              "dropped_count": len(dropped)}
    return kept, dropped, report


__all__ = [
    "BLOCK_PRIORITY", "BLOCK_PRIORITY_ORDER", "DeterministicTokenEstimator",
    "PROTECTED_BLOCKS", "TokenEstimator", "block_priority", "estimate_tokens",
    "item_tokens", "trim_to_budget",
]

