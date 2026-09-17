"""M5：Planning 内部排序工具（timeline sequence_order 是唯一时间真相）。"""

from __future__ import annotations

from .models import StoryPlanningIR, TimelineEntry


def timeline_entries(plan: StoryPlanningIR) -> list[TimelineEntry]:
    timeline = plan.timeline
    if timeline is None:
        return []
    rows = list(timeline.world_history) + list(timeline.story_timeline)
    for entries in timeline.character_timeline.values():
        rows.extend(entries)
    return rows


def node_sequence_order(plan: StoryPlanningIR) -> dict[str, int]:
    """PlotNode → 最早的 timeline sequence_order（没有锚点的节点不在表里）。"""

    rows: dict[str, int] = {}
    for entry in timeline_entries(plan):
        if not entry.anchor_node_id:
            continue
        current = rows.get(entry.anchor_node_id)
        if current is None or entry.sequence_order < current:
            rows[entry.anchor_node_id] = entry.sequence_order
    return rows


def order_of(plan: StoryPlanningIR, node_id: str) -> int | None:
    return node_sequence_order(plan).get(node_id) if node_id else None


def entry_order(plan: StoryPlanningIR, entry_id: str) -> int | None:
    for entry in timeline_entries(plan):
        if entry.entry_id == entry_id:
            return entry.sequence_order
    return None


def sequence_order_map(plan: StoryPlanningIR) -> dict[str, int]:
    """时间线条目 / 节点 → sequence_order，用于"谁先谁后"的通用比较。"""

    rows = {entry.entry_id: entry.sequence_order for entry in timeline_entries(plan)}
    for node_id, order in node_sequence_order(plan).items():
        rows.setdefault(node_id, order)
    return rows


__all__ = [
    "entry_order",
    "node_sequence_order",
    "order_of",
    "sequence_order_map",
    "timeline_entries",
]
