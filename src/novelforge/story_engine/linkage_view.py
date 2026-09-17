"""大纲联动面板视图（V2-I-07）。

链路：StoryState → 实际路线 → 全书 → 卷 → 篇章 → 章节。

- happened / planned / suggested / unresolved 严格分开，已发生历史不可被改写。
- 未来重规划只生成预览（调用 `replan_long_line`），不写回任何文件、不改历史。
- 大纲来源校验复用 `verify_outline_sources`，无来源的条目保持 unresolved。
"""

from __future__ import annotations

from typing import Any

from .linkage import FuturePlan, assert_history_immutable
from .narrative import (
    build_route,
    outline_items_from_route,
    replan_long_line,
    split_long_line,
    verify_outline_sources,
)
from .state import StoryState


def _outline_packages(root, blueprint_id: str, version: int) -> list[dict[str, Any]]:
    """已存在的大纲包摘要（只读），用于把路线与已有大纲对照。"""

    from novelforge.story_builder.outlines import StoryOutlineRepository

    repository = StoryOutlineRepository(root)
    rows: list[dict[str, Any]] = []
    try:
        for package in repository.latest_chain(blueprint_id):
            rows.append({
                "package_id": package.package_id,
                "level": getattr(package.level, "value", package.level),
                "status": getattr(package.status, "value", package.status),
                "version": package.version,
                "parent_package_id": package.parent_package_id,
                "items": [{"item_id": item.item_id, "title": item.title, "summary": item.summary}
                          for item in package.items],
                "pending_questions": list(package.pending_questions),
                "route_source": dict(package.route_source),
                "blueprint_version": package.blueprint_version,
            })
    except Exception:  # noqa: BLE001 - 没有大纲包或读取失败时只是空对照
        return []
    del version
    return rows


def _plan_from_profile(context) -> FuturePlan:
    """未来规划：只接受作者声明的目标阶段；没有声明时给空计划。"""

    payload = context.profile.future_plan
    if isinstance(payload, dict) and payload:
        try:
            return FuturePlan.model_validate(payload)
        except Exception:  # noqa: BLE001 - 格式错误时退回空计划
            return FuturePlan()
    return FuturePlan()


def linkage_snapshot(context, *, changed_stage: str = "", note: str = "",
                     preview: bool = False) -> dict[str, Any]:
    """大纲联动面板数据；预览重规划只返回预览结果，不写回。"""

    state: StoryState = context.state
    plan = _plan_from_profile(context)
    package = build_route(state, plan=plan)
    long_line = split_long_line(package)
    items = outline_items_from_route(package)
    trace = verify_outline_sources(items, package)
    payload: dict[str, Any] = {
        "meta": context.meta(),
        "story_state": {
            "tick": state.timeline.tick,
            "current_time": state.timeline.current_time,
            "current_location": state.location.current,
            "effect_log": len(state.effect_log),
            "plots": len(state.plots),
            "active_events": len(state.active_events),
        },
        "route": {
            "happened": [item.as_dict() for item in package.happened],
            "planned": [item.as_dict() for item in package.planned],
            "suggested": [item.as_dict() for item in package.suggested],
        },
        "counts": {"happened": len(package.happened), "planned": len(package.planned),
                   "suggested": len(package.suggested)},
        "long_line": long_line.as_dict(),
        "outline_preview": items,
        "trace": trace.as_dict(),
        "unresolved": [item["item_id"] for item in trace.unsourced],
        "plans": [{"id": stage.id, "title": stage.title, "goal": stage.goal,
                   "status": stage.status, "note": stage.note} for stage in plan.stages],
        "existing_outlines": _outline_packages(context.project_root, context.blueprint_id,
                                               context.blueprint_version),
        "history_immutable": True,
    }
    if preview:
        updated_plan, replanned = replan_long_line(plan, state, package,
                                                   changed_stage=changed_stage, note=note)
        assert_history_immutable(state, state)
        payload["replan_preview"] = {
            "changed_stage": changed_stage,
            "note": note,
            "plan": [{"id": stage.id, "title": stage.title, "goal": stage.goal,
                      "status": stage.status, "note": stage.note} for stage in updated_plan.stages],
            "plan_revision": updated_plan.revision,
            "happened_unchanged": replanned.happened == package.happened,
            "planned": [item.as_dict() for item in replanned.planned],
            "suggested": [item.as_dict() for item in replanned.suggested],
        }
    return payload
