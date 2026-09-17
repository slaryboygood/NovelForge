"""确定性相关性打分（V4-03 §30）。

排序规则（**固定**，不允许随机）：

```text
1. novel_id 过滤在打分之前（由 index 保证）
2. relevance 降序
3. source_type 字典序（tie-break）
4. source_id 字典序（tie-break）
```

分数构成（可解释，写进 provenance）：

```text
source_type 基础分（SOURCE_TYPE_PRIORITY）
+ required_source_ids 命中 0.40
+ entity 命中 0.15/个（上限 0.45）
+ location 命中 0.12/个（上限 0.24）
+ task 关键词命中 0.05/个（上限 0.20）
+ episode 时效加成（最近 0.10 → 最旧 0.00）
```
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping, Sequence

from .contracts import MemoryItem, SOURCE_TYPE_PRIORITY

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]{2,}|[\u4e00-\u9fff]{2,}")


def tokenize(text: str) -> tuple[str, ...]:
    """最小 tokenizer：ASCII 词 + 连续中文片段（确定性、无第三方依赖）。"""

    return tuple(match.group(0).lower() for match in _TOKEN_RE.finditer(str(text or "")))


def _keyword_hits(text: str, task: str) -> int:
    if not task:
        return 0
    tokens = set(tokenize(text))
    if not tokens:
        return 0
    wanted = set(tokenize(task))
    if not wanted:
        return 0
    hits = 0
    for token in wanted:
        if token in tokens:
            hits += 1
        elif any(token in item or item in token for item in tokens if len(item) >= 2):
            hits += 1
    return hits


def score_item(item: MemoryItem, *, task: str = "", entities: Sequence[str] = (),
               locations: Sequence[str] = (),
               required_source_ids: Sequence[str] = (),
               recency_rank: int | None = None,
               recency_total: int = 0) -> tuple[float, tuple[str, ...]]:
    """返回 (relevance, reasons)。"""

    reasons: list[str] = []
    score = float(SOURCE_TYPE_PRIORITY.get(item.source.source_type, 0.10))
    reasons.append(f"source_type={item.source.source_type}")

    ref = item.source.ref
    if ref in set(required_source_ids) or item.source.source_id in set(required_source_ids):
        score += 0.40
        reasons.append("required_source")

    entity_set = {str(value) for value in entities if str(value)}
    if entity_set:
        matched = entity_set & {str(value) for value in (item.metadata.get("entities") or ())}
        matched |= {value for value in entity_set if value and value in item.text}
        if matched:
            score += min(0.15 * len(matched), 0.45)
            reasons.append("entity_match:" + ",".join(sorted(matched)))

    location_set = {str(value) for value in locations if str(value)}
    if location_set:
        matched_locations = location_set & {str(value) for value in
                                            (item.metadata.get("locations") or ())}
        if matched_locations:
            score += min(0.12 * len(matched_locations), 0.24)
            reasons.append("location_match:" + ",".join(sorted(matched_locations)))

    hits = _keyword_hits(item.text, task)
    if hits:
        score += min(0.05 * hits, 0.20)
        reasons.append(f"keyword_hits={hits}")

    if item.source.source_type == "episode" and recency_rank is not None and recency_total > 0:
        bonus = 0.10 * (1.0 - (recency_rank / max(1, recency_total)))
        if bonus > 0:
            score += bonus
            reasons.append(f"recency_bonus={round(bonus, 4)}")

    if item.stale:
        score -= 0.50
        reasons.append("stale_penalty")

    return (max(0.0, min(1.0, round(score, 6))), tuple(reasons))


def rank_items(items: Iterable[MemoryItem], *, task: str = "",
               entities: Sequence[str] = (), locations: Sequence[str] = (),
               required_source_ids: Sequence[str] = ()) -> list[MemoryItem]:
    """按确定性规则排序并写回 relevance / selection_reason。"""

    rows = list(items)
    episode_ids = [row.memory_id for row in rows if row.source.source_type == "episode"]
    total = len(episode_ids)
    scored: list[MemoryItem] = []
    for row in rows:
        rank = episode_ids.index(row.memory_id) if row.memory_id in episode_ids else None
        relevance, reasons = score_item(row, task=task, entities=entities,
                                        locations=locations,
                                        required_source_ids=required_source_ids,
                                        recency_rank=rank, recency_total=total)
        scored.append(row.with_relevance(relevance, reason=";".join(reasons)))
    return sorted(scored, key=lambda item: (-item.relevance, item.source.source_type,
                                            item.source.source_id))


def relatedness(left: Mapping[str, Any], right: Mapping[str, Any]) -> float:
    """两个 metadata 的确定性相似度（关键词 Jaccard），仅用于 hybrid 打分。"""

    left_tokens = set(tokenize(str(left.get("text", ""))))
    right_tokens = set(tokenize(str(right.get("text", ""))))
    if not left_tokens or not right_tokens:
        return 0.0
    inter = left_tokens & right_tokens
    union = left_tokens | right_tokens
    return round(len(inter) / len(union), 6)


__all__ = ["rank_items", "relatedness", "score_item", "tokenize"]

