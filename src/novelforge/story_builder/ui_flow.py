"""M13 Game UI P0 的只读应用层投影（W6-01 / W6-03 / W6-04 / W6-05）。

分层（AGENTS：UI 不得直接解析 Canon / StoryState）：

```text
Domain / Story Engine（profile / settings / runtime / outline）
        ↓
Application / Query Layer（本模块：只读投影）
        ↓
UI ViewModel / DTO（story_builder_routes 的 JSON 响应）
        ↓
Game UI（ui/src）
```

硬边界：

* 只读：不写 NovelProfile / StoryState / 内容包 / repair artifacts；
  UI 的写操作继续走既有 API（creative/* / settings/* / runtime/*）。
* 事实分层必须显式：`occurred`（StoryState / runtime）≠ `planned`（设定 / 内容包 /
  路线 / 大纲）≠ `historical_repair`（M11/M12 frozen）≠ `ui_derived`（本投影）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from novelforge.story_engine.creator import CreatorContextError, resolve_creator_context
from novelforge.story_engine.character_view import character_snapshot_payload
from novelforge.story_engine.memory_view import memory_snapshot
from novelforge.story_engine.settings_check import run_settings_check
from novelforge.story_engine.settings_gen import (
    SELECTABLE_GROUPS,
    load_creative_brief,
    load_pack_draft,
    load_setting_seed,
    saved_pack_id,
)
from novelforge.story_engine.world_view import world_snapshot

FACT_LAYERS: dict[str, str] = {
    "occurred": "StoryState / runtime（已发生事实）",
    "planned": "设定种子 / 内容包 / 路线 / 大纲（未来规划）",
    "historical_repair": "M11/M12 frozen repair lineage（历史修复，只读）",
    "ui_derived": "M13 UI 只读投影（不成为 truth source）",
}

# W6-07：设定总览的卡片构成（世界 / 主角 / 核心伙伴 / 势力 / 关系）。
OVERVIEW_CARDS: tuple[dict[str, str], ...] = (
    {"card_id": "world", "title": "世界", "truth_layer": "planned",
     "source_group": "world_rules"},
    {"card_id": "protagonist", "title": "主角", "truth_layer": "planned",
     "source_group": "protagonist"},
    {"card_id": "companion", "title": "核心伙伴（狗）", "truth_layer": "planned",
     "source_group": "characters"},
    {"card_id": "factions", "title": "势力", "truth_layer": "planned",
     "source_group": "factions"},
    {"card_id": "relationships", "title": "关系", "truth_layer": "planned",
     "source_group": "relationships"},
)

# W6-08：区域卡字段（未探索区域保持未知）。
REGION_FIELDS: tuple[str, ...] = (
    "danger", "known_resources", "known_information", "entry_conditions")

# W6-01：一条引导流的步骤顺序（与 W6 规划一致：创意 → 设定 → 自检 → 开始推演）。
GUIDED_STEPS: tuple[dict[str, str], ...] = (
    {"step_id": "idea", "title": "创意", "stage": "design",
     "detail": "一句创意 → 题材 / 基调 / 卖点（W1-01）"},
    {"step_id": "settings", "title": "设定与起点", "stage": "design",
     "detail": "世界 / 主角 / 角色 / 势力 / 关系 / 成长 / 矛盾 / 主线 / 伏笔（W1-02）"},
    {"step_id": "check", "title": "设定自检", "stage": "design",
     "detail": "起点可运行性、候选行动非空（W1-03）"},
    {"step_id": "runtime", "title": "开始推演", "stage": "occurred",
     "detail": "把起点事实落盘，成为 StoryState（W1-04）"},
)

STAGE_LABELS: dict[str, str] = {
    "design": "设计（故事构筑）",
    "occurred": "事实与推演",
    "output": "产出（路线 / 大纲）",
}

GROUP_LABELS: dict[str, str] = {
    "world_rules": "世界规则",
    "protagonist": "主角",
    "characters": "重要角色",
    "factions": "势力",
    "relationships": "初始关系网",
    "progression": "成长体系",
    "conflicts": "核心矛盾",
    "main_line": "主线方向",
    "foreshadows": "初始伏笔",
}

# W6-04：每条候选 / 已选设定「进入 NovelProfile 的哪些字段」。
# 与 `settings_gen.save_setting_seed` 的落盘映射一一对应（不在 UI 层复制业务判断）。
GROUP_PROFILE_FIELDS: dict[str, tuple[str, ...]] = {
    "world_rules": ("story_rules", "world_profile.settings.seed"),
    "protagonist": ("cast.protagonist", "world_profile.settings.seed"),
    "characters": ("cast.npc_*", "world_profile.settings.seed"),
    "factions": ("factions", "world_profile.settings.seed"),
    "relationships": ("world_profile.settings.seed",),
    "progression": ("world_profile.settings.seed",),
    "conflicts": ("world_profile.settings.seed",),
    "main_line": ("future_plan.stages", "world_profile.settings.seed"),
    "foreshadows": ("world_profile.settings.seed",),
}

# W6-04：每条候选 / 已选设定「进入内容包的哪些段」（与 content_pack_draft 的结构一致）。
GROUP_PACK_SECTIONS: dict[str, tuple[str, ...]] = {
    "world_rules": ("events", "actions"),
    "protagonist": ("characters", "plots", "progression"),
    "characters": ("characters", "relationships", "autonomous"),
    "factions": ("factions", "locations", "plots"),
    "relationships": ("relationships", "actions"),
    "progression": ("progression",),
    "conflicts": ("plots", "events"),
    "main_line": ("plots",),
    "foreshadows": ("foreshadow",),
}

# W6-04：候选行动解锁口径——内容包 action.requirements 的 op 与设定组的关系。
# 这是一条**展示口径**（应用层投影），不是新的事实来源：只对已保存内容包里真实存在的
# action 生效，并在响应里回传 requirement op 供 UI 结构化断言。
GROUP_UNLOCK_OPS: dict[str, tuple[str, ...]] = {
    "world_rules": ("knowledge", "flag"),
    "protagonist": ("identity", "resource"),
    "characters": ("relationship", "resource"),
    "factions": ("location", "resource"),
    "relationships": ("relationship", "resource"),
    "progression": ("resource",),
    "conflicts": ("flag",),
    "main_line": ("flag",),
    "foreshadows": ("flag",),
}

# W6-05：设定自检失败项 → 对应候选组（深链接目标）。
FINDING_GROUPS: dict[str, str] = {
    "RESOURCE_EMPTY": "progression",
    "RESOURCE_INVALID": "progression",
    "PROGRESSION_EMPTY": "progression",
    "PROGRESSION_DUPLICATE": "progression",
    "PROTAGONIST_MISSING": "protagonist",
    "CHARACTER_EMPTY": "characters",
    "CHARACTER_GOAL_MISSING": "protagonist",
    "FACTION_EMPTY": "factions",
    "FACTION_UNUSED": "factions",
    "FACTION_INFLUENCE_RANGE": "factions",
    "RELATION_MISSING": "relationships",
    "LOCATION_EMPTY": "world_rules",
    "START_LOCATION_MISSING": "world_rules",
    "ACTION_EMPTY": "world_rules",
    "EVENT_EMPTY": "conflicts",
    "EVENT_INVALID": "conflicts",
    "EVENT_NOT_TRIGGERABLE": "conflicts",
    "EVENT_ACTION_MISSING": "world_rules",
    "PLOT_EMPTY": "main_line",
    "FORESHADOW_EMPTY": "foreshadows",
    "FORESHADOW_CONDITION_MISSING": "foreshadows",
}


def _group_impact(group: str) -> dict[str, Any]:
    return {
        "group": group,
        "label": GROUP_LABELS.get(group, group),
        "profile_fields": list(GROUP_PROFILE_FIELDS.get(group, ())),
        "pack_sections": list(GROUP_PACK_SECTIONS.get(group, ())),
        "unlock_ops": list(GROUP_UNLOCK_OPS.get(group, ())),
    }


def _action_requirements(action: dict[str, Any]) -> list[str]:
    ops: list[str] = []
    for row in action.get("requirements") or []:
        if isinstance(row, dict) and row.get("op"):
            ops.append(str(row["op"]))
    return ops


def setting_impact(project_root: Path | str, novel_id: str, *, group: str = ""
                   ) -> dict[str, Any]:
    """W6-04：候选 / 已选设定的只读影响范围投影（NovelProfile 字段 / 内容包段 / 解锁行动）。"""

    seed = load_setting_seed(project_root, novel_id)
    pack_id = saved_pack_id(project_root, novel_id)
    pack = load_pack_draft(project_root, pack_id) if pack_id else None
    pack_payload: dict[str, Any] = pack.model_dump(mode="json") if pack else {}
    actions = [row for row in pack_payload.get("actions") or [] if isinstance(row, dict)]
    groups = [group] if group else list(SELECTABLE_GROUPS)
    rows: list[dict[str, Any]] = []
    for name in groups:
        impact = _group_impact(name)
        candidates = list(getattr(seed, name, []) or []) if seed is not None else []
        selected_ids = list((seed.selected or {}).get(name, [])) if seed is not None else []
        unlocks = []
        for action in actions:
            ops = _action_requirements(action)
            matched = sorted(set(ops) & set(impact["unlock_ops"]))
            if matched:
                unlocks.append({"action_id": str(action.get("id") or ""),
                                "name": str(action.get("name") or ""),
                                "requirement_ops": ops,
                                "matched_ops": matched})
        rows.append({
            **impact,
            "selected_ids": selected_ids,
            "candidates": [{
                "id": item.id, "label": item.label, "summary": item.summary,
                "reason": item.reason, "selected": item.id in selected_ids,
                "impact": {
                    "profile_fields": impact["profile_fields"],
                    "pack_sections": impact["pack_sections"],
                    "unlock_action_ids": [row["action_id"] for row in unlocks],
                },
            } for item in candidates],
            "section_presence": {section: bool(pack_payload.get(section))
                                 for section in impact["pack_sections"]},
            "unlocks": unlocks,
        })
    return {
        "novel_id": novel_id,
        "pack_id": pack_id,
        "pack_ready": bool(pack_payload),
        "groups": rows,
        "finding_groups": dict(FINDING_GROUPS),
        "fact_layers": dict(FACT_LAYERS),
        "note": ("" if pack_payload else
                 "尚未保存设定：解锁行动需要先保存内容包（settings/seed PUT）。"),
        "read_only": True,
        "non_authoritative": True,
    }


def guided_flow_state(project_root: Path | str, novel_id: str) -> dict[str, Any]:
    """W6-01 / W6-03：引导流状态、当前阶段与下一步（只读）。"""

    brief = load_creative_brief(project_root, novel_id)
    seed = load_setting_seed(project_root, novel_id)
    pack_id = saved_pack_id(project_root, novel_id)
    pack = load_pack_draft(project_root, pack_id) if pack_id else None
    check = None
    check_error = ""
    if pack is not None:
        try:
            check = run_settings_check(project_root, novel_id)
        except Exception as exc:  # noqa: BLE001 - 自检失败不允许打断引导流
            check_error = str(exc)
    runtime_started = False
    runtime_error = ""
    branch_id = ""
    try:
        context = resolve_creator_context(project_root, novel_id)
        runtime_started = bool(context.persisted)
        branch_id = context.branch_id
    except CreatorContextError as exc:
        runtime_error = exc.code
    check_ok = bool(check is not None and check.ok)

    done_map: dict[str, bool] = {
        "idea": brief is not None,
        "settings": seed is not None and pack is not None,
        "check": check_ok,
        "runtime": runtime_started,
    }
    block_map: dict[str, bool] = {
        "check": bool(check is not None and not check.ok)}
    order = [row["step_id"] for row in GUIDED_STEPS]
    current = next((step_id for step_id in order if not done_map[step_id]), "")
    if not current:
        current = order[-1]
    current_index = order.index(current)
    statuses: dict[str, str] = {}
    for index, step_id in enumerate(order):
        if done_map[step_id] and index <= current_index:
            statuses[step_id] = "done"
        elif index == current_index:
            statuses[step_id] = "blocked" if block_map.get(step_id) else "current"
        else:
            statuses[step_id] = "pending"

    steps: list[dict[str, Any]] = []
    for step in GUIDED_STEPS:
        step_id = step["step_id"]
        deep_link = {"panel": "builder", "step": step_id, "group": "", "hash": ""}
        if step_id == "settings":
            deep_link = {"panel": "builder", "step": "settings",
                         "group": "", "hash": ""}
        if step_id == "check" and check is not None and not check.ok:
            first = next((row for row in check.findings
                          if row.severity == "error"), None)
            if first is not None:
                deep_link = {"panel": "builder", "step": "settings",
                             "group": FINDING_GROUPS.get(first.code, ""),
                             "hash": ""}
        if step_id == "runtime":
            deep_link = {"panel": "world", "step": "runtime", "group": "", "hash": ""}
        steps.append({
            **step,
            "stage_label": STAGE_LABELS.get(step["stage"], step["stage"]),
            "status": statuses[step_id],
            "deep_link": deep_link,
        })

    next_step = next((row for row in steps
                      if row["status"] in ("current", "blocked", "pending")), None)
    if all(row["status"] == "done" for row in steps):
        next_step = {"step_id": "outline", "title": "路线 / 大纲", "stage": "output",
                     "stage_label": STAGE_LABELS["output"],
                     "detail": "推演已开始：可进入路线实验室与大纲锻造（产出阶段）",
                     "status": "current",
                     "deep_link": {"panel": "route", "step": "output",
                                   "group": "", "hash": ""}}
    # V4-01（ADR-004）：阶段不再由本模块自己推导 —— 引导流只保留"四步 onboarding 进度"，
    # canonical 阶段 / 下一步统一来自 JourneyService（= v3_projection.journey_projection）。
    from novelforge.application.services.journey import JourneyService

    journey_service = JourneyService(project_root, novel_id)
    journey = journey_service.projection()
    journey_stage = (journey.get("journey") or {}).get("current_stage", "")
    display_group = journey_service.display_group(journey)
    return {
        "novel_id": novel_id,
        "current_stage": display_group,
        "current_stage_label": STAGE_LABELS.get(display_group, STAGE_LABELS["design"]),
        "journey_stage": journey_stage,
        "journey_stage_label": (journey.get("journey") or {}).get(
            "current_stage_label", ""),
        "journey_next_action": journey.get("next_action") or {},
        "current_step": current,
        "next_step": next_step,
        "steps": steps,
        "context": {"novel_id": novel_id, "pack_id": pack_id, "branch_id": branch_id},
        "facts": {
            "creative_brief_saved": brief is not None,
            "setting_seed_saved": seed is not None,
            "content_pack_ready": pack is not None,
            "settings_check_ok": check_ok,
            "settings_check_findings": ([row.as_dict() for row in check.findings]
                                        if check is not None else []),
            "settings_check_error": check_error,
            "runtime_started": runtime_started,
            "runtime_error": runtime_error,
        },
        "fact_layers": dict(FACT_LAYERS),
        "read_only": True,
        "non_authoritative": True,
    }


def _context(project_root: Path | str, novel_id: str):
    try:
        return resolve_creator_context(project_root, novel_id)
    except CreatorContextError:
        return None


def setting_overview(project_root: Path | str, novel_id: str) -> dict[str, Any]:
    """W6-07：设定总览卡（世界 / 主角 / 核心伙伴（狗）/ 势力 / 关系），只读 planned 层。"""

    context = _context(project_root, novel_id)
    seed = load_setting_seed(project_root, novel_id)
    profile = context.profile if context is not None else None
    pack = context.pack if context is not None else None
    pack_payload = pack.model_dump(mode="json") if pack is not None else {}

    def chosen(group: str, *, limit: int = 4) -> list[dict[str, Any]]:
        rows = list(getattr(seed, group, []) or []) if seed is not None else []
        selected = set((seed.selected or {}).get(group, [])) if seed is not None else set()
        picked = [row for row in rows if row.id in selected] or rows
        return [{"id": row.id, "label": row.label, "summary": row.summary,
                 "reason": row.reason, "selected": row.id in selected}
                for row in picked[:limit]]

    cast = dict((profile.cast if profile is not None else {}) or {})
    companion_rows = []
    for character_id, entry in (pack_payload.get("initial_characters") or {}).items():
        if character_id == "protagonist":
            continue
        name = str(entry.get("name") or "")
        kind = str(entry.get("kind") or "")
        data = entry.get("data") or {}
        role = str(data.get("role") or "")
        companion_rows.append({
            "id": character_id, "label": name or character_id, "summary": role,
            "reason": "", "selected": True,
            "core_companion": ("狗" in name or kind in ("companion", "pet")
                               or "伙伴" in role)})
    if not companion_rows:
        companion_rows = chosen("characters")

    cards: list[dict[str, Any]] = []
    for spec in OVERVIEW_CARDS:
        card_id = spec["card_id"]
        if card_id == "world":
            items = chosen("world_rules") or [
                {"id": f"rule_{index}", "label": str(text), "summary": "",
                 "reason": "", "selected": True}
                for index, text in enumerate(
                    (profile.story_rules if profile is not None else []) or [], start=1)]
        elif card_id == "protagonist":
            items = chosen("protagonist") or [
                {"id": key, "label": str(entry.name), "summary": "",
                 "reason": "", "selected": True}
                for key, entry in cast.items() if key == "protagonist"]
        elif card_id == "companion":
            items = companion_rows
        elif card_id == "factions":
            items = chosen("factions") or [
                {"id": key, "label": str(entry.name), "summary": str(entry.stance),
                 "reason": "", "selected": True}
                for key, entry in ((profile.factions if profile is not None else {})
                                   or {}).items()]
        else:
            items = chosen("relationships") or [
                {"id": str(row.get("id") or f"rel_{index}"),
                 "label": f"{row.get('source')} → {row.get('target')}",
                 "summary": ", ".join(f"{k}={v}" for k, v in
                                      (row.get("dimensions") or {}).items()),
                 "reason": "", "selected": True}
                for index, row in enumerate(
                    pack_payload.get("initial_relationships") or [], start=1)]
        cards.append({**spec, "items": items,
                      "item_count": len(items),
                      "note": ("" if items else "尚未保存设定：先完成引导流的设定步骤。")})
    return {
        "novel_id": novel_id,
        "pack_id": (pack.pack_id if pack is not None else ""),
        "cards": cards,
        "fact_layers": dict(FACT_LAYERS),
        "read_only": True, "non_authoritative": True,
    }


def region_cards(project_root: Path | str, novel_id: str) -> dict[str, Any]:
    """W6-08：区域与地图卡片（与 StoryState location / world 一致；未探索保持未知）。"""

    context = _context(project_root, novel_id)
    if context is None:
        return {"novel_id": novel_id, "regions": [], "note": "小说尚未开始推演",
                "read_only": True, "non_authoritative": True}
    world = world_snapshot(context)
    known = {str(row.get("id")): row for row in world["location"]["known"]}
    visited = {str(item) for item in world["location"]["visited"]}
    declared = dict((context.pack.initial_locations if context.pack is not None
                     else {}) or {})
    actions = list((context.pack.actions if context.pack is not None else []) or [])
    resources = list(world.get("resources") or [])

    def region_resources(region_id: str, data: Mapping[str, Any]) -> list[str]:
        declared_resources = list((data.get("data") or {}).get("known_resources") or [])
        holders = [row["id"] for row in resources
                   if region_id in (row.get("holders") or [])]
        return declared_resources or holders

    rows: list[dict[str, Any]] = []
    for region_id in sorted(set(declared) | set(known) | visited):
        declared_row = dict(declared.get(region_id) or {})
        state_row = known.get(region_id) or {}
        explored = bool(region_id in known or region_id in visited)
        entry_actions = [
            action.id for action in actions
            if any(str(getattr(req, "op", "")) == "location"
                   and str(getattr(req, "value", "")) == region_id
                   for req in (action.requirements or []))]
        access = str(state_row.get("access") or declared_row.get("access") or "")
        danger = state_row.get("danger")
        rows.append({
            "region_id": region_id,
            "name": str(state_row.get("name") or declared_row.get("name") or region_id),
            "kind": str(state_row.get("kind") or declared_row.get("kind") or ""),
            "explored": explored,
            "current": bool(state_row.get("current")),
            "truth_layer": "occurred" if explored else "planned",
            "danger": danger if explored else None,
            "danger_label": ("未知" if not explored else
                             (str(danger) if danger is not None else "未标注")),
            "known_resources": (region_resources(region_id, declared_row)
                                if explored else ["未知"]),
            "known_information": (
                list((declared_row.get("data") or {}).get("known_information") or [])
                if explored else ["未知"]),
            "entry_conditions": (([] if not explored else
                                  ([access] if access else []))
                                 + ([f"行动 {action_id}" for action_id in entry_actions]
                                    if entry_actions else [])
                                 or (["未知"] if not explored else [])),
        })
    return {
        "novel_id": novel_id, "branch_id": world["meta"]["branch_id"],
        "current_location": world["location"]["current"],
        "regions": rows,
        "region_fields": list(REGION_FIELDS),
        "visited": sorted(visited),
        "unknown_count": sum(1 for row in rows if not row["explored"]),
        "fact_layers": dict(FACT_LAYERS),
        "read_only": True, "non_authoritative": True,
    }


def relationship_graph(project_root: Path | str, novel_id: str,
                       character_id: str = "") -> dict[str, Any]:
    """W6-09：人物—势力—伙伴关系网 + 数值来源与变更记录（relationships + effect log）。"""

    context = _context(project_root, novel_id)
    if context is None:
        return {"novel_id": novel_id, "nodes": [], "edges": [],
                "note": "小说尚未开始推演", "read_only": True,
                "non_authoritative": True}
    payload = character_snapshot_payload(context, character_id, include_reactions=False)
    memory = memory_snapshot(context)
    nodes: list[dict[str, Any]] = []
    for row in payload["characters"]:
        nodes.append({"node_id": row["id"], "label": row["name"],
                      "kind": "player" if row["is_player"] else row["kind"],
                      "status": row["status"], "tags": list(row["tags"]),
                      "truth_layer": "occurred"})
    for faction_id, faction in (context.state.factions or {}).items():
        nodes.append({"node_id": faction_id, "label": faction.name,
                      "kind": "faction", "status": "", "tags": [],
                      "truth_layer": "occurred"})
    changes: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in memory.get("hostility") or []:
        changes.setdefault((str(row["source_id"]), str(row["target_id"])), []).extend(
            {"order": item.get("order"), "delta": item.get("delta"),
             "source": item.get("source"), "reason": item.get("reason"),
             "tick": item.get("tick")} for item in row.get("sources") or [])
    edges: list[dict[str, Any]] = []
    for row in payload["characters"]:
        detail = character_snapshot_payload(context, row["id"],
                                            include_reactions=False)["detail"] or {}
        for relation in detail.get("relationships") or []:
            key = (row["id"], str(relation["other_id"]))
            edges.append({
                "source": row["id"], "source_label": row["name"],
                "target": str(relation["other_id"]),
                "target_label": str(relation["other_label"]),
                "direction": str(relation["direction"]),
                "dimensions": dict(relation["dimensions"] or {}),
                "tags": list(relation["tags"] or []), "stage": str(relation["stage"]),
                "change_records": changes.get(key, []),
                "truth_layer": "occurred"})
    return {
        "novel_id": novel_id, "selected": payload["selected"],
        "nodes": nodes, "edges": edges,
        "note": ("" if nodes else "小说尚未开始推演：关系数据来自 StoryState。"),
        "fact_layers": dict(FACT_LAYERS),
        "read_only": True, "non_authoritative": True,
    }


__all__ = [
    "FACT_LAYERS", "FINDING_GROUPS", "GROUP_LABELS", "GROUP_PACK_SECTIONS",
    "GROUP_PROFILE_FIELDS", "GROUP_UNLOCK_OPS", "GUIDED_STEPS", "STAGE_LABELS",
    "OVERVIEW_CARDS", "REGION_FIELDS", "guided_flow_state", "region_cards",
    "relationship_graph", "setting_impact", "setting_overview",
]
