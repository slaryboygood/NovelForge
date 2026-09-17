"""导演面板视图（V2-I-06）。

投影导演结果：候选事件排序、chosen、逐维得分、加分 / 扣分原因、why_chosen / why_not、
当前权重，以及权重调整入口。

- 排序与评分只调用 director.py 的 `score_events` / `decide`，前端不重新实现评分算法。
- 权重来自 Novel Profile 的 `director_weights`（数据）；调整权重只改配置，不改算法。
"""

from __future__ import annotations

from typing import Any

from .content import ContentPack
from .director import (
    DirectorWeights,
    candidate_events,
    decide,
    score_events,
    weights_from_config,
)
from .events import EventCard, EventCardCatalog
from .journey import actor_for
from .state import StoryState


def _catalog(pack: ContentPack | None) -> EventCardCatalog | None:
    if pack is None:
        return None
    return EventCardCatalog(catalog_id=f"{pack.pack_id}_events", cards=list(pack.events))


def _card(catalog: EventCardCatalog | None, event_id: str) -> EventCard | None:
    if catalog is None or not event_id:
        return None
    try:
        return catalog.by_id(event_id)
    except KeyError:
        return None


def last_choice(state: StoryState) -> str:
    for record in reversed(state.effect_log):
        if record.op == "choice":
            return record.target
    return ""


def weights_payload(context) -> dict[str, float]:
    return weights_from_config(context.profile.director_weights).as_config()


def director_snapshot(context, *, actor: str = "", limit: int = 5) -> dict[str, Any]:
    """导演面板数据；没有合法事件时给出空排序与说明，不编造事件。"""

    state = context.state
    catalog = _catalog(context.pack)
    resolved_actor = actor or actor_for(state)
    weights = weights_from_config(context.profile.director_weights)
    last = last_choice(state)
    if catalog is None:
        return {
            "meta": context.meta(),
            "actor": resolved_actor,
            "weights": weights.as_config(),
            "weights_config": dict(context.profile.director_weights),
            "available_events": [],
            "ranked": [],
            "chosen": "",
            "why_chosen": [],
            "why_not": {},
            "note": "当前小说没有可读取的内容包，无法给出导演建议。",
        }
    available = candidate_events(catalog, state, actor=resolved_actor)
    scores = score_events(catalog, state, weights=weights, actor=resolved_actor, last_choice=last)
    decision = decide(catalog, state, weights=weights, actor=resolved_actor,
                      last_choice=last, limit=limit)
    ranked = []
    for item in decision.ranked:
        card = _card(catalog, item.event_id)
        ranked.append({
            "event_id": item.event_id,
            "title": (card.title if card is not None else "") or item.event_id,
            "kind": card.kind if card is not None else "",
            "scope": card.scope if card is not None else "",
            "priority": card.priority if card is not None else 0,
            "score": item.score,
            "dimensions": dict(item.dimensions),
            "reasons": list(item.reasons),
            "deductions": list(item.deductions),
            "is_chosen": item.event_id == decision.chosen,
        })
    return {
        "meta": context.meta(),
        "actor": resolved_actor,
        "last_choice": last,
        "weights": weights.as_config(),
        "weights_config": dict(context.profile.director_weights),
        "weights_keys": list(weights.as_config()),
        "available_events": [item.as_dict() for item in available],
        "scored": [item.as_dict() for item in scores],
        "ranked": ranked,
        "chosen": decision.chosen,
        "chosen_title": (_card(catalog, decision.chosen).title if _card(catalog, decision.chosen)
                         else decision.chosen),
        "why_chosen": list(decision.why_chosen),
        "why_not": {key: list(value) for key, value in decision.why_not.items()},
        "note": "" if available else "当前状态没有合法事件可以排序。",
    }


def apply_director_weights(context, payload: dict[str, Any]):
    """只把权重写进 Novel Profile 配置，返回更新后的 profile；算法不变。"""

    from .profile import NovelProfileRepository

    current = DirectorWeights.model_validate({**context.profile.director_weights, **payload})
    profile = context.profile.model_copy(update={"director_weights": current.as_config()})
    return NovelProfileRepository(context.project_root).save(profile)
