"""W1-03：设定自检与起点世界事实。

这一层只做一件事：把 W1-02 生成的内容包骨架真的装进引擎跑一遍，回答
“这套设定现在能不能开局”——而不是新增规则。

检查全部复用既有实现：

- 起点事实：`journey.initial_journey_state`（内容包 `initial_*` 声明 → StoryState）
- 候选行动：`driver.candidates_for`（同一套 Condition / ActionResolver 判定）
- 事件可触发性：`conditions.evaluate` 对起点状态求值
- 成长树 / 伏笔 / 关系：既有 Pydantic schema 已负责结构校验，这里只查引用完整性

设定一旦不可运行，允许做**数据层修补**（补默认地点 / 兜底行动 / 触发事件），
但修补只改内容包草稿，不新增规则、不写 StoryState 事实。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from novelforge.models import StrictModel

from .conditions import Condition, evaluate
from .content import ContentPack
from .creator import preview_state
from .driver import candidates_for, runtime_candidates
from .events import EventCard
from .profile import NovelProfileRepository
from .settings_gen import (
    SETTINGS_KEY,
    SettingSeed,
    SettingsGenError,
    content_pack_draft,
    load_pack_draft,
    load_setting_seed,
    default_pack_id,
    saved_pack_id,
    validate_pack_draft,
    write_content_pack,
)

Severity = Literal["error", "warning"]


class CheckFinding(StrictModel):
    """一条自检结论：代码 / 严重级别 / 说明 / 修补建议 / 目标字段。"""

    code: str = Field(min_length=1, max_length=64)
    severity: Severity = "error"
    message: str = Field(default="", max_length=300)
    hint: str = Field(default="", max_length=300)
    target: str = Field(default="", max_length=128)

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class SettingsCheckReport(StrictModel):
    novel_id: str = Field(default="", max_length=96)
    pack_id: str = Field(default="", max_length=96)
    ok: bool = False
    repairable: bool = False
    findings: list[CheckFinding] = Field(default_factory=list)
    applied_fixes: list[str] = Field(default_factory=list)
    story_state: dict[str, Any] = Field(default_factory=dict)
    available_candidates: list[str] = Field(default_factory=list)
    blocked_candidates: list[dict[str, Any]] = Field(default_factory=list)

    def errors(self) -> list[CheckFinding]:
        return [item for item in self.findings if item.severity == "error"]

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def _finding(code: str, message: str, *, severity: Severity = "error", hint: str = "",
             target: str = "") -> CheckFinding:
    return CheckFinding(code=code, severity=severity, message=message, hint=hint, target=target)


def _check_locations(payload: Mapping[str, Any], findings: list[CheckFinding]) -> None:
    locations = payload.get("initial_locations") or {}
    current = str(payload.get("initial_current_location", "") or "")
    if not locations:
        findings.append(_finding("LOCATION_EMPTY", "起点没有任何地点",
                                 hint="至少声明一个开局可进入的地点", target="initial_locations"))
        return
    if not current or current not in locations:
        findings.append(_finding("START_LOCATION_MISSING", "当前所在地点不在地点表里",
                                 hint="把 initial_current_location 指向一个真实地点",
                                 target="initial_current_location"))
    moved = _movable_locations(payload)
    for location_id in locations:
        if location_id == current or location_id in moved:
            continue
        findings.append(_finding(
            "LOCATION_UNREACHABLE", f"没有任何行动能到达地点 {location_id}",
            severity="warning", hint="为它补一条可以移动过去的行动，或删掉这个地点",
            target=location_id))


def _movable_locations(payload: Mapping[str, Any]) -> set[str]:
    moved: set[str] = set()
    effects = [effect for action in payload.get("actions") or []
               for effect in (action.get("immediate_effects") or []) + (action.get("costs") or [])]
    for event in payload.get("events") or []:
        effects.extend(event.get("consequences") or [])
    for effect in effects:
        if isinstance(effect, Mapping) and effect.get("op") in ("change_location",
                                                               "update_location"):
            value = str(effect.get("value", "") or "")
            target = str(effect.get("target", "") or "")
            if value:
                moved.add(value)
            if target:
                moved.add(target)
    return moved


def _check_characters(payload: Mapping[str, Any], findings: list[CheckFinding]) -> None:
    characters = payload.get("initial_characters") or {}
    if not characters:
        findings.append(_finding("CHARACTER_EMPTY", "起点没有任何角色",
                                 hint="至少声明主角与一个 NPC", target="initial_characters"))
        return
    if not any(str(entry.get("kind", "")) == "player" for entry in characters.values()
               if isinstance(entry, Mapping)):
        findings.append(_finding("PROTAGONIST_MISSING", "没有 kind=player 的主角条目",
                                 hint="把主角标记为 player", target="initial_characters"))
    for character_id, entry in characters.items():
        if not isinstance(entry, Mapping):
            continue
        goals = (entry.get("data") or {}).get("goals") or []
        if not goals:
            findings.append(_finding("CHARACTER_GOAL_MISSING", f"{character_id} 没有目标",
                                     severity="warning",
                                     hint="长期 / 阶段目标至少要有一个",
                                     target=character_id))


def _check_factions(payload: Mapping[str, Any], findings: list[CheckFinding]) -> None:
    factions = payload.get("initial_factions") or {}
    if not factions:
        findings.append(_finding("FACTION_EMPTY", "起点没有任何势力",
                                 hint="至少声明一个势力，长期冲突才有来源",
                                 target="initial_factions"))
        return
    referenced = set()
    for location in (payload.get("initial_locations") or {}).values():
        if isinstance(location, Mapping):
            control = str((location.get("data") or {}).get("control", "") or "")
            if control:
                referenced.add(control)
    for plot in payload.get("initial_plots") or []:
        if isinstance(plot, Mapping):
            referenced.update(str(item) for item in (plot.get("factions") or []))
    for faction_id, entry in factions.items():
        if faction_id not in referenced:
            findings.append(_finding("FACTION_UNUSED", f"势力 {faction_id} 没有被任何地点或支线引用",
                                     severity="warning",
                                     hint="把它挂到一个地点或一条支线上",
                                     target=faction_id))
        if isinstance(entry, Mapping):
            influence = (entry.get("data") or {}).get("influence")
            if isinstance(influence, (int, float)) and not 0 <= float(influence) <= 10:
                findings.append(_finding("FACTION_INFLUENCE_RANGE",
                                         f"势力 {faction_id} 的 influence 超出 0～10",
                                         severity="warning", target=faction_id))


def _check_resources(payload: Mapping[str, Any], findings: list[CheckFinding]) -> None:
    resources = payload.get("initial_resources") or {}
    if not resources:
        findings.append(_finding("RESOURCE_EMPTY", "起点没有任何资源",
                                 hint="至少给一份开局资源，成本判定才有意义",
                                 target="initial_resources"))
    for resource_id, amount in resources.items():
        if not isinstance(amount, (int, float)) or amount < 0:
            findings.append(_finding("RESOURCE_INVALID", f"资源 {resource_id} 的数量不合法",
                                     target=resource_id))
    known = set(resources)
    for action in payload.get("actions") or []:
        if not isinstance(action, Mapping):
            continue
        for cost in action.get("costs") or []:
            if not isinstance(cost, Mapping) or cost.get("op") not in (
                    "remove_resource", "set_resource"):
                continue
            resource_id = str(cost.get("target") or cost.get("key") or "")
            if resource_id and resource_id not in known:
                findings.append(_finding(
                    "ACTION_COST_UNKNOWN_RESOURCE",
                    f"行动 {action.get('id', '')} 消耗了未声明的资源 {resource_id}",
                    severity="warning", hint="把资源补进 initial_resources，或改掉这条成本",
                    target=str(action.get("id", ""))))


def _check_relationships(payload: Mapping[str, Any], findings: list[CheckFinding]) -> None:
    characters = set((payload.get("initial_characters") or {}).keys())
    rows = payload.get("initial_relationships") or []
    covered: set[str] = set()
    for entry in rows:
        if not isinstance(entry, Mapping):
            continue
        source = str(entry.get("source_id", "") or "")
        target = str(entry.get("target_id", "") or "")
        for endpoint in (source, target):
            if endpoint and endpoint not in characters:
                findings.append(_finding(
                    "RELATION_TARGET_MISSING", f"关系引用了不存在的角色 {endpoint}",
                    hint="关系两端必须是 initial_characters 里的 id", target=endpoint))
        covered.update(item for item in (source, target) if item)
        for dimension, value in (entry.get("dimensions") or {}).items():
            if not isinstance(value, (int, float)) or abs(float(value)) > 10:
                findings.append(_finding(
                    "RELATION_DIMENSION_RANGE", f"关系维度 {dimension} 的取值超出 -10～10",
                    severity="warning", target=target or source))
    for character_id in characters:
        if character_id in covered:
            continue
        findings.append(_finding("RELATION_MISSING", f"角色 {character_id} 没有任何初始关系",
                                 severity="warning",
                                 hint="至少给一条初始关系，后续变化才有起点",
                                 target=character_id))


def _check_progression(payload: Mapping[str, Any], findings: list[CheckFinding]) -> None:
    trees = payload.get("progressions") or []
    if not trees:
        findings.append(_finding("PROGRESSION_EMPTY", "没有任何成长树",
                                 hint="至少给一条成长线", target="progressions"))
        return
    for tree in trees:
        if not isinstance(tree, Mapping):
            continue
        nodes = tree.get("nodes") or []
        ids = [str(node.get("id", "")) for node in nodes if isinstance(node, Mapping)]
        if len(ids) != len(set(ids)):
            findings.append(_finding("PROGRESSION_DUPLICATE", "同一成长树存在重复节点 id",
                                     target=str(tree.get("tree_id", ""))))
        known = set(ids)
        for node in nodes:
            if not isinstance(node, Mapping):
                continue
            for requirement in node.get("requires") or []:
                if str(requirement) not in known:
                    findings.append(_finding(
                        "PROGRESSION_REQUIRES_MISSING",
                        f"节点 {node.get('id', '')} 的前置 {requirement} 不在同一棵树里",
                        target=str(node.get("id", ""))))


def _check_actions(payload: Mapping[str, Any], state, findings: list[CheckFinding],
                   pack: ContentPack) -> list[str]:
    actions = payload.get("actions") or []
    if not actions:
        findings.append(_finding("ACTION_EMPTY", "没有任何行动",
                                 hint="至少给一条开局可执行的行动", target="actions"))
        return []
    rows = candidates_for(state, pack)
    available = [row.action_id for row in rows if row.available]
    if not available:
        findings.append(_finding(
            "ACTION_NO_AVAILABLE", "开局没有任何满足条件的行动",
            hint="降低至少一条行动的前置条件，或补一份开局资源",
            target="actions"))
    events_actions = {str(item) for event in payload.get("events") or []
                      if isinstance(event, Mapping)
                      for item in (event.get("available_actions") or [])}
    known = {str(action.get("id", "")) for action in actions if isinstance(action, Mapping)}
    for action_id in sorted(events_actions - known):
        findings.append(_finding("EVENT_ACTION_MISSING",
                                 f"事件引用了不存在的行动 {action_id}",
                                 severity="warning", target=action_id))
    return available


def _check_events(payload: Mapping[str, Any], state, findings: list[CheckFinding]) -> None:
    events = payload.get("events") or []
    if not events:
        findings.append(_finding("EVENT_EMPTY", "没有任何事件卡",
                                 hint="至少给一个可触发事件，世界才有推进来源",
                                 target="events"))
        return
    triggerable: list[str] = []
    for raw in events:
        if not isinstance(raw, Mapping):
            continue
        try:
            card = EventCard.model_validate(dict(raw))
        except Exception as exc:  # noqa: BLE001 - schema 已在 ContentPack 校验过，这里是兜底
            findings.append(_finding("EVENT_INVALID", f"事件格式不合法：{exc}",
                                     target=str(raw.get("event_id", ""))))
            continue
        if evaluate(card.trigger, state).ok:
            triggerable.append(card.event_id)
    if not triggerable:
        findings.append(_finding("EVENT_NOT_TRIGGERABLE", "开局没有任何事件满足触发条件",
                                 hint="至少让一个事件的触发条件在起点就成立",
                                 target="events"))


def _check_foreshadows(payload: Mapping[str, Any], findings: list[CheckFinding]) -> None:
    rows = payload.get("foreshadows") or []
    if not rows:
        findings.append(_finding("FORESHADOW_EMPTY", "没有任何伏笔",
                                 severity="warning", hint="至少埋一个可以回收的伏笔",
                                 target="foreshadows"))
    for raw in rows:
        if not isinstance(raw, Mapping):
            continue
        condition = raw.get("payoff_condition")
        if condition is None:
            findings.append(_finding("FORESHADOW_CONDITION_MISSING",
                                     f"伏笔 {raw.get('id', '')} 没有回收条件",
                                     severity="warning", target=str(raw.get("id", ""))))


def _check_plots(payload: Mapping[str, Any], findings: list[CheckFinding]) -> None:
    plots = payload.get("initial_plots") or []
    if not plots:
        findings.append(_finding("PLOT_EMPTY", "没有任何支线轨道",
                                 severity="warning",
                                 hint="支线是长篇的骨架，至少给一条", target="initial_plots"))
        return
    characters = set((payload.get("initial_characters") or {}).keys())
    for plot in plots:
        if not isinstance(plot, Mapping):
            continue
        for character_id in plot.get("characters") or []:
            if str(character_id) not in characters:
                findings.append(_finding(
                    "PLOT_CHARACTER_MISSING",
                    f"支线 {plot.get('id', '')} 引用了不存在的角色 {character_id}",
                    severity="warning", target=str(plot.get("id", ""))))


def run_settings_check(project_root: Path, novel_id: str, *,
                       pack: ContentPack | None = None) -> SettingsCheckReport:
    """对一本小说的内容包做可运行性自检，并返回起点世界事实。"""

    resolved_pack = pack
    if resolved_pack is None:
        pack_id = saved_pack_id(project_root, novel_id)
        resolved_pack = load_pack_draft(project_root, pack_id) if pack_id else None
    if resolved_pack is None:
        raise SettingsGenError("SETTINGS_PACK_REQUIRED", "请先生成并保存设定草图（W1-02）",
                               novel_id=novel_id)
    payload = resolved_pack.model_dump(mode="json")
    findings: list[CheckFinding] = []
    _check_locations(payload, findings)
    _check_characters(payload, findings)
    _check_factions(payload, findings)
    _check_resources(payload, findings)
    _check_relationships(payload, findings)
    _check_progression(payload, findings)
    _check_plots(payload, findings)
    _check_foreshadows(payload, findings)
    profile = NovelProfileRepository(project_root).ensure(novel_id)
    state = preview_state(profile, resolved_pack)
    available = _check_actions(payload, state, findings, resolved_pack)
    _check_events(payload, state, findings)
    snapshot = runtime_candidates(state, resolved_pack)
    blocked = [{"action": row["action_id"], "code": row.get("code", ""),
                "reason": row.get("reason", "")}
               for row in snapshot["candidates"] if not row["available"]]
    return SettingsCheckReport(
        novel_id=novel_id, pack_id=resolved_pack.pack_id,
        ok=not any(item.severity == "error" for item in findings),
        repairable=all(item.code in REPAIRABLE_CODES for item in findings
                       if item.severity == "error"),
        findings=findings, story_state=snapshot["summary"],
        available_candidates=available or list(snapshot["available"]),
        blocked_candidates=blocked)


REPAIRABLE_CODES = frozenset({
    "START_LOCATION_MISSING", "LOCATION_EMPTY", "ACTION_NO_AVAILABLE", "ACTION_EMPTY",
    "EVENT_NOT_TRIGGERABLE", "EVENT_EMPTY", "RESOURCE_EMPTY", "PLOT_EMPTY",
})


def repair_pack_draft(payload: Mapping[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """对可修补的缺项做数据层兜底；返回 (修补后的草稿, 修补记录)。"""

    working = json.loads(json.dumps(dict(payload)))
    fixes: list[str] = []
    locations = working.get("initial_locations")
    if not isinstance(locations, Mapping) or not locations:
        locations = {"start_place": {"name": "起点场所", "kind": "site",
                                     "access": "主角当前可以进入",
                                     "data": {"control": "", "danger": 0}}}
        working["initial_locations"] = dict(locations)
        fixes.append("ADD_START_LOCATION")
    if not str(working.get("initial_current_location", "") or ""):
        working["initial_current_location"] = next(iter(locations))
        fixes.append("SET_CURRENT_LOCATION")
    elif working["initial_current_location"] not in locations:
        working["initial_current_location"] = next(iter(locations))
        fixes.append("FIX_CURRENT_LOCATION")
    if not working.get("initial_resources"):
        working["initial_resources"] = {"supplies": 3}
        fixes.append("ADD_START_RESOURCES")
    flags = working.get("initial_flags")
    if not isinstance(flags, Mapping) or not flags:
        working["initial_flags"] = {"seeded": True}
        fixes.append("ADD_START_FLAGS")
    actions = list(working.get("actions") or [])
    if not actions or not any(not action.get("requirements") for action in actions
                              if isinstance(action, Mapping)):
        actions.append({"id": "act_wait", "kind": "wait", "name": "先观察，不急着介入",
                        "data": {"cost_text": "不消耗资源，但世界会推进一格"}})
        working["actions"] = actions
        fixes.append("ADD_FALLBACK_ACTION")
    events = list(working.get("events") or [])
    reference_flag = next((str(key) for key, value in (working.get("initial_flags") or {}).items()
                           if value), "")
    if not events:
        events.append({"event_id": "ev_world_pressure", "title": "局面出现新的压力",
                       "kind": "world", "priority": 2, "scope": "world",
                       "trigger": {"op": "flag", "key": reference_flag or "seeded",
                                   "value": True},
                       "data": {"world": True, "event_type": "world_pressure"}})
        working["events"] = events
        fixes.append("ADD_FALLBACK_EVENT")
    if not working.get("initial_plots"):
        working["initial_plots"] = [{"id": "main_track", "title": "主线",
                                     "status": "active", "priority": 3, "progress": 0,
                                     "characters": list((working.get("initial_characters")
                                                         or {}).keys())[:1]}]
        fixes.append("ADD_MAIN_TRACK")
    return working, fixes


def repair_and_save(project_root: Path, novel_id: str, *, pack_id: str = "") -> dict[str, Any]:
    """修补缺项 → 重新校验 → 落盘（同时更新 NovelProfile 里的内容包草稿记录）。"""

    resolved_pack_id = pack_id or saved_pack_id(project_root, novel_id)
    if not resolved_pack_id:
        raise SettingsGenError("SETTINGS_PACK_REQUIRED", "请先生成并保存设定草图（W1-02）",
                               novel_id=novel_id)
    current = load_pack_draft(project_root, resolved_pack_id)
    if current is None:
        raise SettingsGenError("SETTINGS_PACK_REQUIRED", "找不到已保存的内容包草稿",
                               novel_id=novel_id)
    repaired, fixes = repair_pack_draft(current.model_dump(mode="json"))
    pack = validate_pack_draft(repaired)
    path = write_content_pack(project_root, pack)
    profile = NovelProfileRepository(project_root).ensure(novel_id)
    world_profile = dict(profile.world_profile)
    payload = world_profile.get(SETTINGS_KEY)
    if isinstance(payload, Mapping):
        updated = dict(payload)
        updated["pack_id"] = pack.pack_id
        updated["pack_path"] = str(path.relative_to(project_root)) if \
            path.is_relative_to(project_root) else str(path)
        updated["repairs"] = fixes
        world_profile[SETTINGS_KEY] = updated
        profile = profile.model_copy(update={"world_profile": world_profile,
                                             "content_pack_id": pack.pack_id})
        NovelProfileRepository(project_root).save(profile)
    return {"pack": pack, "fixes": fixes, "pack_path": path}


def seed_settings_from_pack(project_root: Path, novel_id: str) -> SettingSeed | None:
    """读取设定种子（自检报告里要引用原始创意时用）。"""

    return load_setting_seed(project_root, novel_id)


def check_seed(project_root: Path, novel_id: str, seed: SettingSeed) -> SettingsCheckReport:
    """不落盘自检：用当前种子现场生成骨架后直接跑检查（作者保存前就能看到问题）。"""

    from .creative import load_creative_brief

    brief = load_creative_brief(project_root, novel_id)
    if brief is None:
        raise SettingsGenError("CREATIVE_BRIEF_REQUIRED", "请先完成创意简报（W1-01）",
                               novel_id=novel_id)
    pack = validate_pack_draft(content_pack_draft(seed, pack_id=default_pack_id(novel_id),
                                                  brief=brief))
    return run_settings_check(project_root, novel_id, pack=pack)
