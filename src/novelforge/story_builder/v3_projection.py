"""NovelForge Product V3 —— 作者旅程 / 目标 / 下一步 的应用层投影（只读）。

分层（沿用 AGENTS：UI 不得自行解析 StoryState / Canon）：

    Domain / Story Engine（profile / settings / runtime / outline / repair）
            ↓
    Application（本模块：AuthorJourney / AuthorObjective / NextBestAction）
            ↓
    ViewModel / DTO（story_builder_routes 的 /api/story-builder/v3/* JSON）
            ↓
    V3 Game UI（ui/src/v3）

硬边界：

* 只读：不写 NovelProfile / 内容包 / StoryState / Canon / repair artifact；
  写操作仍走既有 V2 API（creative/* / settings/* / runtime/* / outline/*）。
* 不伪造：每个 stage / objective / risk 都必须带 evidence（真实状态引用）；
  没有真实数据时返回“尚未开始”，而不是演示数字。
* 确定性：全部规则为规则函数（无随机、无 LLM）；LLM 只允许润色解释文案。
* 事实分层显式：occurred（StoryState）≠ planned（设定 / 内容包 / 大纲）。
"""

from __future__ import annotations

import datetime as _dt
import json
import re as _re
from pathlib import Path
from typing import Any, Mapping, Sequence

from novelforge.story_engine.creator import (
    DEFAULT_BRANCH,
    CreatorContextError,
    resolve_creator_context,
)
from novelforge.story_engine.character_view import character_snapshot_payload
from novelforge.story_engine.driver import runtime_candidates
from novelforge.story_engine.outline_forge import OutlineForgeError, load_forge_chain
from novelforge.story_engine.profile import NovelProfile, NovelProfileRepository
from novelforge.story_engine.settings_check import run_settings_check
from novelforge.story_engine.world_view import world_snapshot
from novelforge.story_engine.route_lab import list_branches
from novelforge.story_engine.settings_gen import (
    load_creative_brief,
    load_pack_draft,
    load_setting_seed,
    saved_pack_id,
)
from novelforge.story_builder.ui_flow import relationship_graph

from novelforge.author_language import (
    ACTION_KIND_LABEL,
    IDENTITY_LABEL,
    KNOWLEDGE_LABEL,
    OP_LABEL,
    RESOURCE_LABEL,
    TRACK_LABEL,
    content_labels,
    label_table,
    translate,
)
from .inspector import repair_diagnosis
from .ui_flow import FINDING_GROUPS, setting_overview

# --------------------------------------------------------------------- stages
# 与 UI 视觉标准一致：左侧导航与阶段条使用同一套 stage 语义。
V3_STAGES: tuple[dict[str, str], ...] = (
    {"stage_id": "creation", "label": "创意", "icon": "creation",
     "goal": "把想法变成可发展的核心设定"},
    {"stage_id": "world", "label": "世界", "icon": "world",
     "goal": "定下世界规则与故事发生的地方"},
    {"stage_id": "characters", "label": "角色", "icon": "character",
     "goal": "让主角与关系网立起来"},
    {"stage_id": "story", "label": "故事", "icon": "story",
     "goal": "定下主线、矛盾与伏笔"},
    {"stage_id": "simulation", "label": "推演", "icon": "simulation",
     "goal": "让故事从起点开始真的跑起来"},
    {"stage_id": "outline", "label": "大纲", "icon": "outline",
     "goal": "把推演结果整理成可写的大纲"},
    {"stage_id": "review", "label": "检查", "icon": "review",
     "goal": "确认没有自相矛盾的设定"},
    {"stage_id": "export", "label": "导出", "icon": "export",
     "goal": "把作品交给写作环节"},
)

STAGE_INDEX: dict[str, int] = {row["stage_id"]: index
                               for index, row in enumerate(V3_STAGES)}

FACT_LAYERS: dict[str, str] = {
    "occurred": "StoryState（已经发生的事实）",
    "planned": "设定 / 内容包 / 大纲（还没发生）",
    "ui_derived": "V3 界面推导（不是事实来源）",
}

# 设定组 → 作者语言目标（UI 不出现内部字段名）。
GROUP_OBJECTIVES: tuple[dict[str, str], ...] = (
    {"objective_id": "obj_world_rules", "stage_id": "world", "group": "world_rules",
     "title": "建立世界规则", "icon": "world",
     "description": "这个世界靠什么运转？先定下 1 条以上规则。",
     "why_it_matters": "世界规则决定后面哪些行动、资源与冲突说得通。",
     "unlock_effects": "解锁：与世界观一致的行动与事件候选"},
    {"objective_id": "obj_factions", "stage_id": "world", "group": "factions",
     "title": "定下势力", "icon": "faction",
     "description": "哪些组织在争夺资源与话语权。",
     "why_it_matters": "势力给故事提供外部压力。",
     "unlock_effects": "解锁：势力相关的支线与事件"},
    {"objective_id": "obj_protagonist", "stage_id": "characters", "group": "protagonist",
     "title": "完善主角", "icon": "character",
     "description": "主角是谁、想要什么、底线在哪里。",
     "why_it_matters": "主角的目标决定剧情推进方向。",
     "unlock_effects": "解锁：以主角视角展开的推演"},
    {"objective_id": "obj_cast", "stage_id": "characters", "group": "characters",
     "title": "安排重要角色", "icon": "relationship",
     "description": "除主角之外，故事里还有谁。",
     "why_it_matters": "有人才有冲突，也才有关系变化。",
     "unlock_effects": "解锁：关系冲突与支线候选"},
    {"objective_id": "obj_relationships", "stage_id": "characters", "group": "relationships",
     "title": "建立关系网", "icon": "relationship",
     "description": "谁和谁站在一起、谁和谁对立。",
     "why_it_matters": "关系决定冲突升级的速度。",
     "unlock_effects": "解锁：更稳定的推演与路线选择"},
    {"objective_id": "obj_progression", "stage_id": "story", "group": "progression",
     "title": "设计成长与代价", "icon": "progression",
     "description": "角色怎么变强，变强要付出什么。",
     "why_it_matters": "成长线让长故事有持续回报。",
     "unlock_effects": "解锁：成长节点与资源消耗"},
    {"objective_id": "obj_conflicts", "stage_id": "story", "group": "conflicts",
     "title": "确立核心矛盾", "icon": "conflict",
     "description": "故事最根本的对抗是什么。",
     "why_it_matters": "没有矛盾，推演会停在原地。",
     "unlock_effects": "解锁：可推进的事件链"},
    {"objective_id": "obj_main_line", "stage_id": "story", "group": "main_line",
     "title": "确定主线方向", "icon": "story",
     "description": "整本书大致走向哪里。",
     "why_it_matters": "主线决定大纲与章节取舍。",
     "unlock_effects": "解锁：分层大纲生成"},
    {"objective_id": "obj_foreshadows", "stage_id": "story", "group": "foreshadows",
     "title": "埋下伏笔", "icon": "foreshadow", "optional": "1",
     "description": "先埋下可以回收的线索。",
     "why_it_matters": "伏笔让后面的高潮有铺垫。",
     "unlock_effects": "解锁：伏笔回收检查"},
)

GROUP_LABELS: dict[str, str] = {
    "world_rules": "世界规则",
    "protagonist": "主角",
    "characters": "重要角色",
    "factions": "势力",
    "relationships": "关系网",
    "progression": "成长体系",
    "conflicts": "核心矛盾",
    "main_line": "主线方向",
    "foreshadows": "伏笔",
}

# 设定组 → 作者应该去的工作区（深链接目标）。与 GROUP_OBJECTIVES 同源，不重复定义。
GROUP_VIEWS: dict[str, str] = {row["group"]: row["stage_id"] for row in GROUP_OBJECTIVES}

# 自检 / 修复 finding 的专业码 → 作者语言标题（细节仍可在高级信息里看到）。
FINDING_TITLES: dict[str, str] = {
    "LOCATION_EMPTY": "还没有故事发生的地方",
    "START_LOCATION_MISSING": "起点地点不在已设定的地点里",
    "CHARACTER_EMPTY": "还没有任何角色",
    "PROTAGONIST_MISSING": "还没有确定主角",
    "CHARACTER_GOAL_MISSING": "有角色还没有目标",
    "FACTION_EMPTY": "还没有势力",
    "FACTION_UNUSED": "有势力没有参与任何地点或支线",
    "FACTION_INFLUENCE_RANGE": "势力影响力数值超出范围",
    "RESOURCE_EMPTY": "还没有可用的资源",
    "RESOURCE_INVALID": "资源数量不合法",
    "ACTION_EMPTY": "起点没有任何可执行的行动",
    "EVENT_EMPTY": "还没有可以触发的事件",
    "EVENT_INVALID": "事件配置不完整",
    "EVENT_NOT_TRIGGERABLE": "事件在起点无法触发",
    "EVENT_ACTION_MISSING": "事件缺少可执行行动",
    "PLOT_EMPTY": "还没有主线",
    "FORESHADOW_EMPTY": "还没有伏笔",
    "FORESHADOW_CONDITION_MISSING": "伏笔缺少回收条件",
    "RELATION_MISSING": "有角色还没有关系",
    "PROGRESSION_EMPTY": "还没有成长体系",
    "PROGRESSION_DUPLICATE": "成长节点有重复",
}

# 每个目标至少需要选中多少项才算完成（可选项范围由引擎的真实候选决定）。
GROUP_REQUIRED: dict[str, int] = {
    "world_rules": 1, "protagonist": 1, "characters": 1, "factions": 1,
    "relationships": 1, "progression": 1, "conflicts": 1, "main_line": 1,
    "foreshadows": 1,
}

CHECKLIST_LIMIT = 5

ACTION_LABELS: dict[str, str] = {
    "brief": "开始一句创意",
    "settings": "开始设定",
    "group": "继续完善",
    "check": "开始检查",
    "runtime": "开始推演",
    "outline": "生成大纲",
    "review": "继续检查",
    "export": "继续创作",
}


# ------------------------------------------------------------------- helpers
def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None


def _mtime(path: Path) -> str:
    try:
        stamp = path.stat().st_mtime
    except OSError:
        return ""
    return _dt.datetime.fromtimestamp(stamp, tz=_dt.timezone.utc).isoformat()


def _profile_path(project_root: Path | str, novel_id: str) -> Path:
    return NovelProfileRepository(Path(project_root)).path_for(novel_id)


def _pack_path(project_root: Path | str, pack_id: str) -> Path:
    return Path(project_root) / "novel" / "config" / "story_engine" / f"{pack_id}.json"


def _writer_drafts(project_root: Path | str, novel_id: str) -> list[dict[str, Any]]:
    """只读读取 writer 草稿（preview 层），不创建任何目录。

    路径唯一来源是 `writer_integration.read_writer_drafts`——投影与
    WriterDraftService 写入路径同源（V3 验收 NF-002 的验收条件）。
    """

    from .writer_integration import read_writer_drafts

    return read_writer_drafts(project_root, novel_id)


def _group_rows(seed: Any, group: str) -> list[Any]:
    if seed is None:
        return []
    return list(getattr(seed, group, []) or [])


def _group_selected(seed: Any, group: str) -> list[str]:
    if seed is None:
        return []
    selected = (seed.selected or {}).get(group) or []
    return [str(item) for item in selected]


def _checklist(seed: Any, group: str) -> list[dict[str, Any]]:
    rows = _group_rows(seed, group)[:CHECKLIST_LIMIT]
    selected = set(_group_selected(seed, group))
    return [{"item_id": str(getattr(row, "id", "")),
             "label": str(getattr(row, "label", "") or getattr(row, "id", "")),
             "done": str(getattr(row, "id", "")) in selected}
            for row in rows]


def _pack_group_present(pack: Any, group: str) -> bool:
    """内容包里是否已经真的含有这一组设计内容（设计态事实，不是 UI 推断）。"""

    if pack is None:
        return False
    characters = dict(getattr(pack, "initial_characters", {}) or {})
    if group == "world_rules":
        return bool(pack.initial_locations or pack.events or pack.actions)
    if group == "factions":
        return bool(pack.initial_factions)
    if group == "protagonist":
        return any(str((entry or {}).get("kind", "")) == "player"
                   for entry in characters.values())
    if group == "characters":
        return bool(characters)
    if group == "relationships":
        return bool(pack.initial_relationships)
    if group == "progression":
        return bool(pack.progressions)
    if group == "conflicts":
        return bool(pack.events or pack.initial_plots)
    if group == "main_line":
        return bool(pack.initial_plots)
    if group == "foreshadows":
        return bool(pack.foreshadows)
    return False


def _stage_progress(stage_id: str, objectives: Sequence[Mapping[str, Any]]
                    ) -> dict[str, int]:
    rows = [row for row in objectives
            if row["stage_id"] == stage_id
            and row["status"] not in ("not_applicable", "optional")]
    done = sum(1 for row in rows if row["status"] == "complete")
    total = len(rows)
    return {"done": done, "total": total,
            "percent": round(100 * done / total) if total else 0}


def _author_finding(row: Mapping[str, Any]) -> dict[str, Any]:
    def field(name: str, default: str = "") -> str:
        if isinstance(row, Mapping):
            return str(row.get(name, default) or default)
        return str(getattr(row, name, default) or default)

    code = field("code")
    severity = field("severity", "warning")
    group = FINDING_GROUPS.get(code, "")
    view = GROUP_VIEWS.get(group, "creation")
    return {
        "finding_id": f"finding_{code}_{field('target')}",
        "level": "BLOCKING" if severity == "error" else "WARNING",
        "title": FINDING_TITLES.get(code, field("message") or code),
        "detail": field("message"),
        "hint": field("hint"),
        "source": "settings_check",
        "evidence": {"code": code, "target": field("target"),
                     "severity": severity},
        "deep_link": {"view": view, "step": "settings", "group": group},
        "action_label": "去修补",
    }


REPAIR_APPROVAL_LABEL: dict[str, str] = {
    "AUTO_SAFE": "可以自动修复（不改变故事事实）",
    "MANUAL_REVIEW": "需要你确认后再修复",
    "AUTHOR_DECISION": "需要作者决定怎么改",
    "NOT_SAFE": "暂时不能自动修复",
}


def _repair_view(repair: Mapping[str, Any]) -> dict[str, Any]:
    """P5：把修复诊断翻成作者语言（问题是什么 / 为什么重要 / 能不能自动修）。

    只做投影：修复能力仍来自既有 repair 子系统——V3 不建立第二套修复逻辑，
    也不在 Primary UI 暴露 raw patch / payload / repair opcode。
    """

    issues = []
    for row in list(repair.get("issues") or [])[:12]:
        # 既有 repair 诊断的字段：requires_approval / approval_note / hint / target。
        # 这里只做作者语言化，不改变「谁能修、是否需要作者确认」的判定。
        requires_approval = bool(row.get("requires_approval", True))
        approval = str(row.get("approval") or row.get("approval_class") or "")
        source = str(row.get("source") or "")
        source_label = ("设定自检" if source == "settings_check"
                        else "大纲质量" if source == "outline_quality"
                        else "历史冲突")
        issues.append({
            "issue_id": str(row.get("issue_id") or ""),
            "title": str(row.get("message") or "有一处需要确认的旧设定"),
            "why": str(row.get("hint") or row.get("approval_note") or ""),
            "note": str(row.get("approval_note") or ""),
            "target": str(row.get("target") or ""),
            "source_label": source_label,
            "approval_label": (REPAIR_APPROVAL_LABEL.get(approval)
                               or ("需要你确认后再修复" if requires_approval
                                   else "可以自动修复（不改变故事事实）")),
            "reversible": bool(row.get("reversible", True)),
            "auto_safe": approval == "AUTO_SAFE" or (not approval and not requires_approval),
            # 只有会改变「已经发生的事实」的问题才真的阻塞导出；
            # 大纲质量属于规划内容（作者可以重新锻造），不阻塞把作品交给写作环节。
            "blocks_export": source_label != "大纲质量",
        })
    count = int(repair.get("issue_count") or len(issues))
    blocking = sum(1 for row in issues if not row["auto_safe"])
    return {
        "available": count > 0,
        "issue_count": count,
        "blocking_count": blocking,
        "issues": issues,
        "reason": "" if count else "目前没有需要修复的历史冲突。",
    }


def _export_view(*, pack: Any, check: Any, outline: Mapping[str, Any],
                 outline_view: Mapping[str, Any], runtime: Mapping[str, Any],
                 repair: Mapping[str, Any],
                 drafts: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
    """P5：导出就绪度——作者必须知道「还缺什么才能交给写作环节」。"""

    started = bool(runtime.get("started"))
    check_ok = bool(check is not None and getattr(check, "ok", False))
    book = outline.get("book")
    confirmed = bool(book is not None
                     and _enum_value(getattr(book, "status", "")) == "CONFIRMED")
    chapter_count = int(outline_view.get("chapter_count") or 0)
    stale = bool(outline_view.get("stale"))
    draft_count = len(list(drafts))

    steps = [
        {"step_id": "content_pack", "label": "内容包已经生成", "done": pack is not None,
         "why": "没有内容包就没有可写的事实、事件与行动。", "view": "creation"},
        {"step_id": "runtime_started", "label": "起点事实已经落盘", "done": started,
         "why": "写作草稿必须基于已经发生的事实，而不是规划。", "view": "simulation"},
        {"step_id": "settings_check_ok", "label": "设定自检通过", "done": check_ok,
         "why": "自检通过说明设定之间没有相互矛盾的硬伤。", "view": "review"},
        {"step_id": "outline_confirmed", "label": "大纲已确认", "done": confirmed,
         "why": "确认后的大纲才是这本书的正式结构。", "view": "outline"},
        {"step_id": "chapters_ready", "label": "已经有可写的章节", "done": chapter_count > 0,
         "why": "导出的是章节与事实，没有章节就没有可导出的内容。", "view": "outline"},
        {"step_id": "writer_drafts", "label": "已有写作草稿", "done": draft_count > 0,
         "why": "写作草稿是「这本书真的开始写了」的证据；它在导出工作区里创建。",
         "view": "export"},
    ]
    missing = [row for row in steps if not row["done"]]
    blockers: list[str] = []
    if check is not None and not check_ok:
        blockers.append("设定自检还有必须处理的问题。")
    if stale:
        blockers.append("故事推进过，大纲需要重新锻造后才能导出。")
    # 只有「会改变已经发生事实」的问题才阻塞导出；规划层面的质量问题不阻塞。
    if any(row["blocks_export"] for row in _repair_view(repair)["issues"]):
        blockers.append("还有需要你决定的历史冲突没有处理。")
    ready = not missing and not blockers
    # N-12：文案必须优先说清真正的阻塞原因——存在 blocker 时不能再写「还差 0 步」。
    if blockers:
        headline = blockers[0]
    elif missing:
        headline = f"还差 {len(missing)} 步就可以导出"
    else:
        headline = "可以导出给写作环节了"
    return {
        "ready": ready,
        "headline": headline,
        "steps": steps,
        "missing": missing,
        "blockers": blockers,
        "chapter_count": chapter_count,
        "writer_drafts": draft_count,
        "bundle": [
            {"label": "故事状态与事实", "detail": "已经发生的记录与当前局面"},
            {"label": "大纲与章节", "detail": f"当前 {chapter_count} 章的结构与目标"},
            {"label": "设定与内容包", "detail": getattr(pack, "title", "") or "尚未生成"},
            {"label": "写作草稿", "detail": (f"已有 {draft_count} 份写作草稿"
                                             if draft_count else "还没有写作草稿")},
        ],
    }


# --------------------------------------------------------------- objectives
def _objective_payload(project_root: Path, novel_id: str, *, profile: Any,
                       brief: Any, seed: Any, pack_id: str, pack: Any,
                       check: Any,
                       runtime: Mapping[str, Any], outline: Mapping[str, Any],
                       repair: Mapping[str, Any], drafts: Sequence[Mapping[str, Any]],
                       spec: Mapping[str, str]) -> dict[str, Any]:
    group = spec.get("group", "")
    kind = "group" if group else spec.get("kind", "")
    pack_ready = pack is not None
    optional = spec.get("optional") == "1"
    evidence: list[dict[str, Any]] = []
    checklist: list[dict[str, Any]] = []
    required = 1
    done_count = 0
    total_count = 1

    if kind == "brief":
        saved = brief is not None
        evidence.append({"source": "creative_brief",
                         "ref": f"profiles/{novel_id}.json",
                         "summary": "创意简报已保存" if saved else "还没有创意简报"})
        checklist = [{"item_id": "idea", "label": "一句话创意", "done": saved},
                     {"item_id": "genre", "label": "题材方向",
                      "done": bool(getattr(brief, "selected_genre", "") or "")}]
        done_count = sum(1 for row in checklist if row["done"])
        total_count = len(checklist)
        status = ("complete" if saved and done_count == total_count
                  else "active")
    elif kind == "group":
        rows = _group_rows(seed, group)
        selected = _group_selected(seed, group)
        required = GROUP_REQUIRED.get(group, 1)
        checklist = _checklist(seed, group)
        in_pack = _pack_group_present(pack, group)
        done_count = max(len(selected), 1 if in_pack else 0)
        total_count = max(required, min(len(rows), CHECKLIST_LIMIT) if rows else required)
        evidence.append({"source": f"setting_seed.{group}",
                         "ref": f"profiles/{novel_id}.json",
                         "summary": f"已确认 {done_count} 项 / 候选 {len(rows)} 项"})
        if in_pack:
            evidence.append({"source": f"content_pack.{group}", "ref": pack_id,
                             "summary": "内容包已经包含这一组内容"})
            if not selected:
                checklist = [{"item_id": f"{group}_default",
                              "label": "按默认值生成的骨架", "done": True}]
        if brief is None:
            status = "locked"
        elif done_count >= required and (selected or in_pack):
            status = "complete"
        elif seed is None:
            # 还没生成这一组的候选：作者下一步就是生成它。
            status = "available"
        elif rows:
            status = "active"
        else:
            # 引擎没有给出这一组的候选：这一步对这本小说不适用，不再计数。
            status = "not_applicable"
    elif kind == "check":
        ok = bool(check is not None and check.ok)
        findings = list(getattr(check, "findings", []) or []) if check is not None else []
        checklist = [{"item_id": "check_ran", "label": "自检已执行",
                      "done": check is not None},
                     {"item_id": "check_ok", "label": "没有阻塞问题", "done": ok}]
        done_count = sum(1 for row in checklist if row["done"])
        total_count = len(checklist)
        evidence.append({"source": "settings_check", "ref": pack_id or "",
                         "summary": ("自检通过" if ok else
                                     f"自检有 {len(findings)} 个待处理项"
                                     if check is not None else "还没有执行自检")})
        status = ("complete" if ok
                  else "blocked" if check is not None
                  else "available" if pack_ready else "locked")
    elif kind == "runtime":
        started = bool(runtime.get("started"))
        checklist = [{"item_id": "runtime_started", "label": "起点事实已落盘",
                      "done": started}]
        done_count = 1 if started else 0
        total_count = 1
        evidence.append({"source": "story_state",
                         "ref": str(runtime.get("runtime_id") or ""),
                         "summary": (f"revision {runtime.get('revision')}" if started
                                     else "还没有开始推演")})
        check_ok = bool(check is not None and check.ok)
        status = ("complete" if started
                  else "active" if check_ok
                  else "available" if pack_ready else "locked")
    elif kind == "outline":
        book = outline.get("book")
        chapters = list(outline.get("chapters") or [])
        checklist = [{"item_id": "book", "label": "全书大纲", "done": book is not None},
                     {"item_id": "chapters", "label": "章节大纲", "done": bool(chapters)}]
        done_count = sum(1 for row in checklist if row["done"])
        total_count = len(checklist)
        evidence.append({"source": "outline_chain",
                         "ref": str(getattr(book, "package_id", "") or ""),
                         "summary": f"{len(chapters)} 个章节大纲" if chapters else "还没有大纲"})
        status = ("complete" if done_count == total_count
                  else "active" if done_count
                  else "available" if runtime.get("started") else "locked")
    elif kind == "review":
        ok = bool(check is not None and check.ok)
        issues = int(repair.get("issue_count") or 0)
        checklist = [{"item_id": "check_ok", "label": "设定自检通过", "done": ok},
                     {"item_id": "repair", "label": "没有待处理冲突",
                      "done": check is not None and issues == 0}]
        done_count = sum(1 for row in checklist if row["done"])
        total_count = len(checklist)
        evidence.append({"source": "repair_diagnosis", "ref": novel_id,
                         "summary": f"{issues} 个待处理冲突"})
        status = ("complete" if done_count == total_count and check is not None
                  else "active" if check is not None
                  else "locked")
    elif kind == "export":
        book = outline.get("book")
        confirmed = str(getattr(book, "status", "") or "") == "CONFIRMED"
        checklist = [{"item_id": "outline_confirmed", "label": "大纲已确认",
                      "done": confirmed},
                     {"item_id": "drafts", "label": "已有写作草稿", "done": bool(drafts)}]
        done_count = sum(1 for row in checklist if row["done"])
        total_count = len(checklist)
        evidence.append({"source": "writer_drafts", "ref": novel_id,
                         "summary": f"{len(drafts)} 份写作草稿"})
        status = ("complete" if done_count == total_count
                  else "active" if done_count
                  else "available" if book is not None else "locked")
    else:  # pragma: no cover - 防御分支
        status = "locked"

    if optional and status != "complete":
        status = "optional"
    action_label = ACTION_LABELS.get(kind, "继续完善")
    if status == "available":
        action_label = {"group": "开始设定", "check": "开始检查",
                        "runtime": "开始推演", "outline": "生成大纲",
                        "export": "开始导出"}.get(kind, action_label)
    progress_percent = round(100 * done_count / total_count) if total_count else 0
    deep_link: dict[str, Any] = {"view": spec["stage_id"]}
    if spec.get("step"):
        deep_link["step"] = spec["step"]
    if group:
        deep_link["group"] = group
    return {
        "objective_id": spec["objective_id"],
        "stage_id": spec["stage_id"],
        "title": spec["title"],
        "description": spec["description"],
        "why_it_matters": spec["why_it_matters"],
        "icon": spec.get("icon", "objective"),
        "optional": optional,
        "blocking": spec.get("blocking") == "1",
        "status": status,
        "progress": {"done": done_count, "total": total_count,
                     "percent": progress_percent},
        "checklist": checklist,
        "completion_evidence": evidence,
        "unlock_effects": spec["unlock_effects"],
        "target_view": spec["stage_id"],
        "deep_link": deep_link,
        "action_label": action_label,
        "truth_layer": "ui_derived",
        "read_only": True,
    }


OBJECTIVE_SPECS: tuple[dict[str, str], ...] = (
    {"objective_id": "obj_creative_idea", "stage_id": "creation", "kind": "brief",
     "title": "确定一句话创意", "icon": "creation", "blocking": "1", "step": "idea",
     "description": "把这本小说想写什么写成一句话，并选定题材方向。",
     "why_it_matters": "题材与基调决定后面世界、角色与主线的候选范围。",
     "unlock_effects": "解锁：世界与角色候选"},
    *GROUP_OBJECTIVES,
    {"objective_id": "obj_settings_check", "stage_id": "simulation", "kind": "check",
     "title": "让起点可以运行", "icon": "review", "blocking": "1", "step": "check",
     "description": "检查起点地点、角色与可执行行动是否齐全。",
     "why_it_matters": "起点不完整时，推演会立刻停住。",
     "unlock_effects": "解锁：开始剧情推演"},
    {"objective_id": "obj_runtime", "stage_id": "simulation", "kind": "runtime",
     "title": "开始剧情推演", "icon": "simulation", "blocking": "1", "step": "runtime",
     "description": "把起点事实落盘，让故事真的开始。",
     "why_it_matters": "推演之后，所有面板读的都是同一份已发生事实。",
     "unlock_effects": "解锁：路线推演与大纲生成"},
    {"objective_id": "obj_outline", "stage_id": "outline", "kind": "outline",
     "title": "生成大纲", "icon": "outline", "step": "forge",
     "description": "把已经发生的推演整理成可写的大纲。",
     "why_it_matters": "大纲让写作有稳定的章节结构。",
     "unlock_effects": "解锁：导出与写作"},
    {"objective_id": "obj_review", "stage_id": "review", "kind": "review",
     "title": "检查故事一致性", "icon": "review", "step": "check",
     "description": "确认没有互相矛盾的设定与待处理冲突。",
     "why_it_matters": "矛盾越晚发现，返工代价越高。",
     "unlock_effects": "解锁：放心导出"},
    {"objective_id": "obj_export", "stage_id": "export", "kind": "export",
     "title": "导出并开始写作", "icon": "export", "step": "bundle",
     "description": "把设定、事实与大纲交给写作环节。",
     "why_it_matters": "这是从设计走向成稿的最后一步。",
     "unlock_effects": "解锁：写作草稿与事实回填"},
)


# ---------------------------------------------------------------- main build
def _runtime_facts(project_root: Path | str, novel_id: str) -> dict[str, Any]:
    try:
        context = resolve_creator_context(project_root, novel_id)
    except CreatorContextError:
        return {"started": False, "runtime_id": "", "revision": 0, "tick": 0,
                "branch_id": "", "reason": "NOT_STARTED", "state": None, "context": None}
    state = context.state
    return {
        "started": bool(context.persisted),
        "runtime_id": getattr(state, "runtime_id", "") or context.runtime_id,
        "revision": int(getattr(state, "revision", 0) or 0),
        "tick": int(getattr(state, "tick", 0) or 0),
        "branch_id": context.branch_id,
        "reason": "" if context.persisted else "PREVIEW_ONLY",
        "state": state,
        "context": context,
    }


def _outline_facts(project_root: Path | str, novel_id: str,
                   runtime: Mapping[str, Any]) -> dict[str, Any]:
    if not runtime.get("started"):
        return {"book": None, "volumes": [], "arcs": [], "chapters": [],
                "fresh": False, "quality": None, "error": "NOT_STARTED"}
    try:
        chain = load_forge_chain(project_root, novel_id)
    except OutlineForgeError as exc:
        return {"book": None, "volumes": [], "arcs": [], "chapters": [],
                "fresh": False, "quality": None, "error": str(exc)}
    return {"book": chain.get("book"), "volumes": list(chain.get("volumes") or []),
            "arcs": list(chain.get("arcs") or []),
            "chapters": list(chain.get("chapters") or []),
            "fresh": bool(chain.get("fresh")), "quality": chain.get("quality"),
            "error": ""}


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "")


def _author_time(text: Any) -> str:
    """引擎时间字段 → 作者语言（`tick 3` 是引擎说法，作者看到的是「第 3 回合」）。"""

    out = str(text or "")
    if not out:
        return ""
    return _TICK_PATTERN.sub(lambda match: f"第 {match.group(1)} 回合", out)


_TICK_PATTERN = _re.compile(r"tick\s*(\d+)")


def _outline_package_row(package: Any) -> dict[str, Any] | None:
    """把一层 OutlinePackage 投影成作者可读的一行（不含内部 enum / provenance）。"""

    if package is None:
        return None
    status = _enum_value(getattr(package, "status", ""))
    items = list(getattr(package, "items", []) or [])
    # OutlinePackage 本身没有 title 字段：作者可读的名字来自它这一层的条目
    # （例如卷包的 items[0].title 就是「第一卷」）。
    title = str(getattr(package, "title", "") or "")
    if not title and items:
        title = str(getattr(items[0], "title", "") or "")
    return {
        "package_id": str(getattr(package, "package_id", "")),
        "parent_package_id": str(getattr(package, "parent_package_id", "") or ""),
        "level": _enum_value(getattr(package, "level", "")),
        "title": title,
        "status": status,
        "confirmed": status == "CONFIRMED" or bool(
            getattr(package, "confirmed_by_author", False)),
        "version": int(getattr(package, "version", 0) or 0),
        "item_count": len(items),
        "pending_questions": list(getattr(package, "pending_questions", []) or [])[:3],
    }


def _chapter_rows(outline: Mapping[str, Any],
                  character_labels: Mapping[str, str] | None = None) -> list[dict[str, Any]]:
    """把 outline chain 的章级包摊平成章节条目。

    章节不是新的 Domain：它来自既有 outline forge 的 chain（book → volumes → arcs → chapters），
    每个章级包（level=CHAPTER）的 items 就是这本书的真实章节。这里只做只读投影。
    """

    labels = dict(character_labels or {})
    # 篇章名用于「这一章属于哪个篇章」——章节不该只知道自己叫第几章。
    # package 本身没有 title：标题在它的 items 里（既有 outline 数据结构）。
    arcs = {str(getattr(row, "package_id", "")):
            str(getattr((getattr(row, "items", []) or [None])[0], "title", "") or "")
            for row in (outline.get("arcs") or [])}
    rows: list[dict[str, Any]] = []
    for package in outline.get("chapters") or []:
        status = _enum_value(getattr(package, "status", ""))
        package_id = str(getattr(package, "package_id", ""))
        parent_id = str(getattr(package, "parent_package_id", "") or "")
        version = int(getattr(package, "version", 0) or 0)
        for item in getattr(package, "items", []) or []:
            participants = [labels.get(str(entry), str(entry))
                            for entry in (getattr(item, "participants", []) or [])]
            # 大纲摘要 / 目标 / 冲突里会出现引擎原文（行动 id、事件 id…）：
            # 这里只按真实名称表翻译，缺失保留原文，不编造。
            title = _simulation_reason(str(getattr(item, "title", "") or ""), labels)
            summary = _simulation_reason(str(getattr(item, "summary", "") or ""), labels)
            goals = [_simulation_reason(str(entry), labels)
                     for entry in (getattr(item, "goals", []) or [])][:3]
            conflicts = [_simulation_reason(str(entry), labels)
                         for entry in (getattr(item, "conflicts", []) or [])][:3]
            # 地点与时间同样是引擎字段：进入作者界面之前必须翻译（NF-004）。
            location = _simulation_reason(str(getattr(item, "location", "") or ""), labels)
            rows.append({
                "item_id": str(getattr(item, "item_id", "")),
                "package_id": package_id,
                "parent_package_id": parent_id,
                "arc_title": arcs.get(parent_id, ""),
                "order": len(rows) + 1,
                "title": title,
                "summary": summary,
                "pov": str(getattr(item, "pov", "") or ""),
                "time": _author_time(getattr(item, "time", "")),
                "location": location,
                "ending_hook": _simulation_reason(
                    str(getattr(item, "ending_hook", "") or ""), labels),
                "goals": goals,
                "conflicts": conflicts,
                "participants": participants[:6],
                "status": status,
                "confirmed": status == "CONFIRMED",
                "package_version": version,
            })
    return rows


def _outline_questions(rows: Sequence[Any]) -> list[dict[str, str]]:
    """把大纲包里真实存在的待办问题整理成作者可读告警（不改写、不补造）。"""

    warnings: list[dict[str, str]] = []
    for row in rows:
        label = str(getattr(row, "title", "") or "")
        for question in list(getattr(row, "pending_questions", []) or []):
            text = str(question or "").strip()
            if not text:
                continue
            code, _, message = text.partition(": ")
            warnings.append({"code": (code or "OUTLINE_QUESTION").strip(),
                             "message": (message or text).strip(), "target": label})
    return warnings[:8]


def _outline_view(outline: Mapping[str, Any],
                  character_labels: Mapping[str, str] | None = None,
                  element_labels: Mapping[str, str] | None = None) -> dict[str, Any]:
    """V3 只读投影：作者可读的大纲层级 + 章节列表（唯一数据源仍是 outline chain）。"""

    chapters = _chapter_rows(outline, character_labels)
    book = _outline_package_row(outline.get("book"))
    volumes = [row for row in (_outline_package_row(item)
                               for item in outline.get("volumes") or []) if row][:60]
    arcs = [row for row in (_outline_package_row(item)
                            for item in outline.get("arcs") or []) if row][:120]
    packages = [row for row in (_outline_package_row(item)
                                for item in outline.get("chapters") or []) if row][:120]
    started = bool(book is not None or chapters)

    # 缺口：只描述真实缺失的层级与真实存在的草稿状态，不制造进度数字。
    gaps: list[str] = []
    if not started:
        gaps.append("还没有任何大纲：这本小说还没有把故事方向锻造成大纲。")
    else:
        if book is None:
            gaps.append("缺少全书主线：推进方向必须来自「全书主线」。")
        if not volumes:
            gaps.append("缺少卷纲：全书主线还没有拆成卷。")
        if not arcs:
            gaps.append("缺少篇章纲：卷纲还没有拆成篇章。")
        if not chapters:
            gaps.append("缺少详细章纲：篇章还没有拆成可写的章节。")
    drafts = [row for row in [book, *volumes, *arcs, *packages] if row and not row["confirmed"]]
    if drafts:
        gaps.append(f"{len(drafts)} 个大纲层级还是草稿：确认后才算这本书的正式结构。")

    # 警告：大纲包自己的待办问题 + 真实的「来源已过期」状态。
    warnings = _outline_questions([outline.get("book"), *(outline.get("volumes") or []),
                                   *(outline.get("arcs") or []),
                                   *(outline.get("chapters") or [])])
    labels = dict(element_labels or {})
    if warnings and labels:
        for row in warnings:
            row["message"] = _simulation_reason(row["message"], labels)
    # 只有链**明确**报告来源已过期时才算过期；缺字段不等于过期。
    stale = bool(started and outline.get("fresh") is False)
    if stale:
        warnings.append({"code": "OUTLINE_STALE",
                         "message": "故事已经推进过，这份大纲是推进之前的版本，需要重新锻造才能与当前事实一致。",
                         "target": ""})

    quality = outline.get("quality")
    quality_rows = []
    if isinstance(quality, Mapping):
        for finding in quality.get("findings") or []:
            if not isinstance(finding, Mapping):
                continue
            message = _simulation_reason(str(finding.get("message") or ""), labels)
            if message:
                quality_rows.append({"severity": str(finding.get("severity") or ""),
                                     "message": message})
    return {
        "started": started,
        "error": str(outline.get("error") or ""),
        "book": book,
        "volumes": volumes,
        "arcs": arcs,
        "chapter_packages": packages,
        "chapters": chapters[:400],
        "chapter_count": len(chapters),
        "gaps": gaps[:6],
        "warnings": warnings[:8],
        "quality": quality_rows[:6],
        "stale": stale,
    }


CHARACTER_ROLE_LABEL: dict[str, str] = {
    "protagonist": "主角",
    "companion": "核心伙伴",
    "npc": "配角",
    "antagonist": "对手",
    "pet": "伙伴",
}

RELATION_DIMENSION_LABEL: dict[str, str] = {
    "trust": "信任",
    "affection": "亲近",
    "respect": "尊重",
    "fear": "忌惮",
    "debt": "亏欠",
    "hostility": "敌意",
    "dependency": "依赖",
}


def _relationship_edge(source: Any, source_label: Any, target: Any, target_label: Any,
                       dimensions: Any, tags: Any, truth_label: str) -> dict[str, Any]:
    """把一条真实关系归一化成作者可读的一行（不新增关系模型）。"""

    rows = []
    for key, value in (dimensions or {}).items():
        label = RELATION_DIMENSION_LABEL.get(str(key), str(key))
        rows.append({"label": label, "value": value})
    return {
        "source_id": str(source or ""),
        "source_label": str(source_label or source or ""),
        "target_id": str(target or ""),
        "target_label": str(target_label or target or ""),
        "dimension_labels": [row["label"] for row in rows],
        "dimension_rows": rows,
        "tags": [str(tag) for tag in (tags or [])][:4],
        "truth_label": truth_label,
    }


def relationship_edges(project_root: Path | str, novel_id: str) -> list[dict[str, Any]]:
    """真实关系边：已发生（StoryState，复用 W6-09 关系网）+ 设计中（内容包 initial_relationships）。

    同一对实体同时存在两种来源时，保留「已发生」——事实优先于设计。
    """

    root = Path(project_root)
    edges: list[dict[str, Any]] = []
    labels: dict[str, str] = {}
    try:
        graph = relationship_graph(root, novel_id)
    except Exception:  # noqa: BLE001 - 关系网不可用不应打断 Command Center
        graph = {}
    for node in graph.get("nodes") or []:
        if str(node.get("node_id") or ""):
            labels[str(node["node_id"])] = str(node.get("label") or "")
    for row in graph.get("edges") or []:
        edges.append(_relationship_edge(
            row.get("source"), row.get("source_label"), row.get("target"),
            row.get("target_label"), row.get("dimensions"), row.get("tags"), "已发生"))

    pack_id = saved_pack_id(root, novel_id)
    pack = load_pack_draft(root, pack_id) if pack_id else None
    if pack is not None:
        for character_id, entry in (getattr(pack, "initial_characters", {}) or {}).items():
            name = str((entry or {}).get("name") or "")
            if name and not labels.get(str(character_id)):
                labels[str(character_id)] = name
        for faction_id, entry in (getattr(pack, "initial_factions", {}) or {}).items():
            name = str((entry or {}).get("name") or "")
            if name and not labels.get(str(faction_id)):
                labels[str(faction_id)] = name
        for row in getattr(pack, "initial_relationships", []) or []:
            source = str((row or {}).get("source") or "")
            target = str((row or {}).get("target") or "")
            if not source or not target:
                continue
            edges.append(_relationship_edge(
                source, labels.get(source, source), target, labels.get(target, target),
                (row or {}).get("dimensions"), (row or {}).get("tags"), "设计中"))

    occurred = {(row["source_id"], row["target_id"]) for row in edges
                if row["truth_label"] == "已发生"}
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in edges:
        key = (row["source_id"], row["target_id"])
        if key in seen:
            continue
        if row["truth_label"] == "设计中" and key in occurred:
            continue
        seen.add(key)
        merged.append(row)
    return merged


def relationships_view(project_root: Path | str, novel_id: str,
                       edges: Sequence[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """V3-P2 CLOSEOUT：关系投影（只做投影，不新增关系 Domain）。"""

    rows = list(edges) if edges is not None else relationship_edges(project_root, novel_id)
    return {
        "available": True,
        "edge_count": len(rows),
        "occurred_count": sum(1 for row in rows if row["truth_label"] == "已发生"),
        "planned_count": sum(1 for row in rows if row["truth_label"] == "设计中"),
        "edges": rows,
    }

LOCATION_KIND_LABEL: dict[str, str] = {
    "site": "地点",
    "region": "区域",
    "city": "城市",
}

# 引擎用这些值表示「控制方未知 / 未确定」；它们是哨兵值而不是势力 id。
LOCATION_UNKNOWN_CONTROL: frozenset[str] = frozenset({"", "unknown", "none", "null"})

# NF-016：设定候选给的是「原型名」（角色定位 / 势力形态），不是真实姓名。
# 这些名字可以区分实体，但必须让作者一眼看出它还是占位，而不是已经命名好的人物。
PLACEHOLDER_NAME_LABELS: frozenset[str] = frozenset({
    "普通执行者", "边缘技术员", "被误解的当事人", "掌握线索的同行者", "立场摇摆的上位者",
    "资源控制方", "秩序维护方", "灰色中间方", "起点场所", "工作场所", "隐藏节点",
    "主角", "角色",
})


def _is_placeholder_name(name: Any) -> bool:
    value = str(name or "").strip()
    return bool(value) and value in PLACEHOLDER_NAME_LABELS


def _location_control_label(raw: Any, faction_names: Mapping[str, str]) -> str:
    """把地点的「控制方」翻成作者语言。

    引擎给的是势力 id（`faction_1`）或未知哨兵（`unknown`）。
    能对上真实势力就显示势力名；对不上且不是哨兵时给出可读描述（不编造）。

    NF-013：返回值只描述「谁在控制」，不加「控制方」前缀——UI 已经把标签写成
    「控制方 {值}」，值里再带一次就变成「控制方 控制方未知」。
    """

    value = str(raw or "").strip()
    if value.lower() in LOCATION_UNKNOWN_CONTROL:
        return "未知"
    if value in faction_names:
        return faction_names[value]
    # 引擎 id（faction_1 / npc_1 …）没有对应真实势力时不能原样抛给作者。
    return "" if value.startswith(("faction_", "npc_", "character_")) else value


def characters_view(project_root: Path | str, novel_id: str,
                    edges: Sequence[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """V3-P2 角色投影：复用 V2 `character_snapshot_payload`，不建立第二套角色模型。

    只输出作者可读字段（名称 / 定位 / 状态 / 标签 / 事实计数）；
    内部 id 只作为 deep-link 与实体主键，不作为显示名。
    """

    try:
        context = resolve_creator_context(Path(project_root), novel_id)
    except CreatorContextError as exc:
        return {"available": False, "reason": exc.message or exc.code,
                "count": 0, "items": [], "protagonist": None}
    try:
        snapshot = character_snapshot_payload(context, "", include_reactions=False)
    except Exception:  # noqa: BLE001 - 角色投影不可用不应打断 Command Center
        return {"available": False, "reason": "角色投影暂时不可用",
                "count": 0, "items": [], "protagonist": None}

    rows = list(snapshot.get("characters") or [])
    relationship_rows = list(edges) if edges is not None else relationship_edges(
        project_root, novel_id)
    items: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        is_player = bool(row.get("is_player"))
        kind = str(row.get("kind") or "")
        name = str(row.get("name") or "").strip()
        tags = [str(tag) for tag in (row.get("tags") or [])][:4]
        character_id = str(row.get("id") or f"character_{index}")
        mine = [edge for edge in relationship_rows
                if edge["source_id"] == character_id or edge["target_id"] == character_id]
        items.append({
            "character_id": character_id,
            "name": name or f"角色 {index}",
            "name_placeholder": _is_placeholder_name(name),
            # 主角优先用真实身份判定（is_player / kind），否则按 kind 映射。
            "role_label": ("主角" if is_player
                           else CHARACTER_ROLE_LABEL.get(kind, "角色")),
            "kind": kind,
            "is_protagonist": is_player,
            "status_label": str(row.get("status") or ""),
            "tags": tags,
            "active_goals": int(row.get("active_goals") or 0),
            "memories": int(row.get("memories") or 0),
            # 关系只给真实可推导的信息：数量 + 前 3 条真实边。
            "relationship_count": len(mine),
            "has_relationships": bool(mine),
            "key_relationships": mine[:3],
        })
    # 稳定排序：主角置顶，其余保持投影原有顺序（不引入随机 / 无规则重排）。
    items.sort(key=lambda item: 0 if item["is_protagonist"] else 1)
    protagonist = next((item for item in items if item["is_protagonist"]), None)
    return {"available": True, "reason": "", "count": len(items), "items": items,
            "protagonist": protagonist,
            "selected_id": str(snapshot.get("selected") or "")}


def world_view(project_root: Path | str, novel_id: str) -> dict[str, Any]:
    """V3-P2 世界投影：复用 V2 `world_snapshot`，只输出真实存在的地点与势力。"""

    try:
        context = resolve_creator_context(Path(project_root), novel_id)
    except CreatorContextError as exc:
        return {"available": False, "reason": exc.message or exc.code,
                "locations": [], "factions": [], "current_location": None,
                "location_count": 0, "faction_count": 0}
    try:
        snapshot = world_snapshot(context)
    except Exception:  # noqa: BLE001 - 世界投影不可用不应打断 Command Center
        return {"available": False, "reason": "世界投影暂时不可用",
                "locations": [], "factions": [], "current_location": None,
                "location_count": 0, "faction_count": 0}

    location_block = snapshot.get("location") or {}
    # 势力名表先行：地点的「控制方」是势力 id，必须在角色/地点循环之前就能翻译。
    faction_names = {str(row.get("id") or ""): str(row.get("name") or "").strip()
                     for row in list(snapshot.get("factions") or [])}
    faction_names = {key: value for key, value in faction_names.items() if key and value}
    locations: list[dict[str, Any]] = []
    for index, row in enumerate(list(location_block.get("known") or []), start=1):
        kind = str(row.get("kind") or "")
        name = str(row.get("name") or "").strip()
        locations.append({
            "location_id": str(row.get("id") or f"location_{index}"),
            "name": name or f"地点 {index}",
            "kind_label": LOCATION_KIND_LABEL.get(kind, "地点"),
            "access_label": str(row.get("access") or ""),
            "control_label": _location_control_label(row.get("control"), faction_names),
            "name_placeholder": _is_placeholder_name(row.get("name")),
            "danger": int(row.get("danger") or 0),
            "current": bool(row.get("current")),
            "visited": bool(row.get("visited")),
        })
    current_location = next((row for row in locations if row["current"]), None)
    if current_location is None and str(location_block.get("name") or "").strip():
        current_location = {"location_id": str(location_block.get("current") or ""),
                            "name": str(location_block.get("name") or "").strip(),
                            "kind_label": LOCATION_KIND_LABEL.get(
                                str(location_block.get("kind") or ""), "地点"),
                            "access_label": str(location_block.get("access") or ""),
                            "control_label": _location_control_label(
                                location_block.get("control"), faction_names),
                            "danger": int(location_block.get("danger") or 0),
                            "current": True,
                            "visited": bool(location_block.get("visited"))}

    factions: list[dict[str, Any]] = []
    for index, row in enumerate(list(snapshot.get("factions") or []), start=1):
        name = str(row.get("name") or "").strip()
        factions.append({
            "faction_id": str(row.get("id") or f"faction_{index}"),
            "name": name or f"势力 {index}",
            "name_placeholder": _is_placeholder_name(name),
            "stance_label": str(row.get("stance") or ""),
            "influence": int(row.get("influence") or 0),
            "active_plot_count": len(list(row.get("active_plots") or [])),
            "conflict_count": len(list(row.get("internal_conflicts") or [])),
        })
    return {"available": True, "reason": "", "locations": locations,
            "factions": factions, "current_location": current_location,
            "location_count": len(locations), "faction_count": len(factions)}


# 展示层映射只有一份（src/novelforge/story_builder/author_language.py）：
# 投影 / 导出 / API 错误文案共用，避免同一个 id 在不同位置一半被翻译。
SIMULATION_ACTION_KIND_LABEL = ACTION_KIND_LABEL
SIMULATION_OP_LABEL = OP_LABEL
SIMULATION_RESOURCE_LABEL = RESOURCE_LABEL
SIMULATION_TRACK_LABEL = TRACK_LABEL
SIMULATION_KNOWLEDGE_LABEL = KNOWLEDGE_LABEL
SIMULATION_IDENTITY_LABEL = IDENTITY_LABEL


def _simulation_element_labels(pack: Any) -> dict[str, str]:
    """真实故事元素 id → 作者语言名称（事件 / 行动 / 伏笔 / 支线 / 地点 / 势力）。

    只收录内容包里真的有名字的元素；缺失时调用方按类型兜底，不回落原始 id。
    """

    return content_labels(pack)


def _action_name_labels(pack: Any) -> dict[str, str]:
    """行动 id → 作者可读行动名（大纲摘要里会出现行动 id 的原文）。"""

    return {key: value for key, value in content_labels(pack).items()
            if key.startswith("act_")}


def _simulation_reason(text: str, labels: Mapping[str, str]) -> str:
    """把引擎给出的作者可读原因里的真实 id 换成名称。

    引擎 reason 的句子结构本身已经可读（例如「需要 protagonist 已知 core_record」），
    这里只做 id → 真实名称的替换，不改写句子结构、不新增解释。
    """

    return translate(text, label_table(extra=labels))


# 每条 op 的「被作用对象」放在哪个字段：引擎 op 行形状不统一，这里显式声明，
# 不靠猜字段。
SIMULATION_OP_SUBJECT_FIELD: dict[str, str] = {
    "relationship": "target",
    "location": "value",
    "knowledge": "target",
    "resource": "key",
    "identity": "key",
    "flag": "key",
    "remove_resource": "target",
    "add_resource": "target",
    "change_relationship": "target",
    "change_location": "value",
    "update_location": "key",
    "set_flag": "key",
    "add_knowledge": "target",
}


def _simulation_op_label(row: Any, labels: Mapping[str, str] | None = None) -> str:
    """把引擎 op 行翻成作者读得懂的一句；不认识的 op 不猜，交给 Advanced。"""

    # 引擎里 risks 可能是字符串，也可能是一条 op；两种都直接沿用真实文本。
    if isinstance(row, str):
        return row.strip()
    if not isinstance(row, Mapping):
        return ""
    op = str(row.get("op") or "")
    label = SIMULATION_OP_LABEL.get(op, "")
    if not label:
        return ""
    field = SIMULATION_OP_SUBJECT_FIELD.get(op, "")
    subject = str(row.get(field) or "").strip() if field else ""
    dimension = ""
    known = dict(labels or {})
    if subject and subject in known:
        subject = known[subject]
    elif subject and op in ("resource", "remove_resource", "add_resource"):
        subject = SIMULATION_RESOURCE_LABEL.get(subject, subject)
    elif subject and op in ("knowledge", "add_knowledge"):
        subject = SIMULATION_KNOWLEDGE_LABEL.get(subject, subject)
    elif subject and op in ("identity", "add_identity"):
        subject = SIMULATION_IDENTITY_LABEL.get(subject, subject)
    if op in ("relationship", "change_relationship"):
        # 维度（信任 / 亏欠…）是作者真正需要知道的，必须一起显示。
        raw_dimension = str(row.get("key") or "").strip()
        dimension = SIMULATION_TRACK_LABEL.get(raw_dimension, raw_dimension)
    value = row.get("value")
    comparator = str(row.get("comparator") or "")
    parts = [label]
    if dimension:
        parts.append(dimension)
    if subject:
        parts.append(f"（{subject}）" if dimension else subject)
    # subject 本身就是 value 的 op（location / change_location）不再重复显示同一个值。
    if field != "value" and value not in (None, "", 0):
        parts.append(f"{comparator} {value}".strip() if comparator else f"×{value}")
    return " ".join(parts)


def _simulation_op_refs(row: Any) -> list[str]:
    """一条 op 行里真实承载 entity id 的字段值（不猜测、不做关键词匹配）。

    引擎 op 行的形状并不统一：`relationship` 把对象放在 `target`，
    `change_location` / `location` 把地点 id 放在 `value`，
    `update_location` 放在 `key`。只认这些结构化字段里的**原文 id**，
    匹配不到真实实体就不绑定。
    """

    if not isinstance(row, Mapping):
        return []
    refs: list[str] = []
    for field in ("entity", "target", "value", "key"):
        value = row.get(field)
        if isinstance(value, str) and value.strip():
            refs.append(value.strip())
    return refs


def _simulation_candidate(row: Mapping[str, Any], character_labels: Mapping[str, str],
                          location_labels: Mapping[str, str] | None = None,
                          faction_labels: Mapping[str, str] | None = None,
                          event_labels: Mapping[str, str] | None = None,
                          ) -> dict[str, Any]:
    kind = str(row.get("kind") or "")
    # 作者可读化用的真实实体名表：角色 / 地点 / 势力 / 事件与伏笔（故事元素）。
    # 只做 id → 真实名称的翻译，缺失就保留原文，绝不编造。
    known_labels: dict[str, str] = {}
    known_labels.update(dict(character_labels))
    known_labels.update(dict(location_labels or {}))
    known_labels.update(dict(faction_labels or {}))
    known_labels.update(dict(event_labels or {}))
    known_labels.update(SIMULATION_KNOWLEDGE_LABEL)
    requirements = [text for text in (_simulation_op_label(item, known_labels)
                                      for item in row.get("requirements") or []) if text]
    costs = [text for text in (_simulation_op_label(item, known_labels)
                               for item in row.get("costs") or []) if text]
    risks = [text for text in (_simulation_op_label(item, known_labels)
                               for item in row.get("risks") or []) if text]
    related = [character_labels.get(str(item), str(item))
               for item in row.get("related_characters") or []]
    # 受影响的角色：除引擎给出的 related_characters，再补「op 行里以 id 直接点名的角色」
    # （例如 `relationship.target = npc_1`）。同样只认真实角色 id，不做关键词猜测。
    for bucket in ("requirements", "costs", "risks"):
        for op in row.get(bucket) or []:
            for ref in _simulation_op_refs(op):
                name = character_labels.get(ref, "")
                if name and name not in related:
                    related.append(name)
    # 受影响的非角色对象：只认「op 行里出现的真实实体 id」与 P2 世界投影的交集，
    # 不做关键词猜测；匹配不到就不绑定（宁可只保留「世界变化」）。
    location_hits: list[str] = []
    faction_hits: list[str] = []
    locations = dict(location_labels or {})
    factions = dict(faction_labels or {})
    for bucket in ("requirements", "costs", "risks"):
        for op in row.get(bucket) or []:
            for ref in _simulation_op_refs(op):
                if ref in locations and locations[ref] not in location_hits:
                    location_hits.append(locations[ref])
                if ref in factions and factions[ref] not in faction_hits:
                    faction_hits.append(factions[ref])
    return {
        "candidate_id": str(row.get("action_id") or ""),
        "title": str(row.get("name") or "").strip() or "未命名行动",
        "kind_label": SIMULATION_ACTION_KIND_LABEL.get(kind, kind or "行动"),
        "reason": _simulation_reason(str(row.get("reason") or ""), known_labels),
        "available": bool(row.get("available")),
        "blocked_reason": str(row.get("code") or ""),
        "requirements": requirements[:4],
        "costs": costs[:4],
        "risks": risks[:4],
        "related_characters": related[:6],
        "affected_locations": location_hits[:6],
        "affected_factions": faction_hits[:6],
        "goal_notes": [str(item) for item in (row.get("goal_notes") or [])][:3],
        "visibility": str(row.get("visibility") or ""),
    }


def simulation_view(project_root: Path | str, novel_id: str,
                    runtime: Mapping[str, Any],
                    characters: Mapping[str, Any],
                    world: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """V3-P3 推演投影：当前故事状况 + 真实候选方向 + 分支。

    复用引擎自己的 `runtime_candidates` 与既有 `list_branches`：
    这里只做投影与作者可读化，不新增第二套推演 / 路线引擎。
    """

    started = bool(runtime.get("started"))
    state = runtime.get("state")
    context = runtime.get("context")
    character_labels = {row["character_id"]: row["name"]
                        for row in (characters.get("items") or [])}
    # 目的行 / 条件句里的 id 也按真实角色名翻译（主角默认叫「主角」，不硬编码作品名）。
    actor_labels = dict(character_labels)
    actor_labels["protagonist"] = next(
        (row["name"] for row in (characters.get("items") or [])
         if row.get("is_protagonist")), actor_labels.get("protagonist", "主角"))
    actor_labels["player"] = actor_labels.get("protagonist", "主角")
    world_block = world or {}
    location_labels = {row["location_id"]: row["name"]
                       for row in (world_block.get("locations") or [])}
    faction_labels = {row["faction_id"]: row["name"]
                      for row in (world_block.get("factions") or [])}
    base: dict[str, Any] = {
        "available": started,
        "tick": int(runtime.get("tick") or 0),
        "revision": int(runtime.get("revision") or 0),
        "branch_id": str(runtime.get("branch_id") or ""),
        "summary": "",
        "situation_rows": [],
        "blocked": False,
        "candidates": [],
        "branches": [],
        "runtime_id": str(runtime.get("runtime_id") or ""),
        "event_labels": {},
        "reason": "",
    }
    if not started or state is None or context is None:
        # STATE A：还不能推演——给出真实原因，而不是「暂无数据」。
        base["reason"] = "起点事实还没有落盘：先完成设定与自检，再开始推演"
        return base

    try:
        # NF-008：候选可用性必须与 `POST /runtime/advance` 用同一个 actor——
        # 否则投影会说「可执行」，点下去却是 422（需要人情的行动在资源耗尽后仍然可点）。
        actor = next(iter(state.characters), "protagonist") if state.characters else ""
        payload = runtime_candidates(state, context.pack, actor=actor)
    except Exception:  # noqa: BLE001 - 候选不可用不应打断 Command Center
        base["reason"] = "推演候选暂时不可用"
        return base
    base["summary"] = str(payload.get("summary") or "")
    base["blocked"] = bool(payload.get("blocked"))
    base["revision"] = int(payload.get("revision") or base["revision"])
    base["tick"] = int(payload.get("tick") or base["tick"])
    # 世界 / 触发事件 id → 标题（真实内容包事件卡），供 UI 用作者语言解释结果。
    pack = getattr(context, "pack", None)
    labels = _simulation_element_labels(pack)
    base["event_labels"] = labels
    base["candidates"] = [_simulation_candidate(row, actor_labels, location_labels,
                                                faction_labels, labels)
                          for row in (payload.get("candidates") or [])][:12]

    try:
        branches = list_branches(Path(project_root), novel_id).get("branches") or []
    except Exception:  # noqa: BLE001
        branches = []
    rows = []
    for index, row in enumerate(branches, start=1):
        branch_id = str(row.get("branch_id") or "")
        official = bool(row.get("official"))
        rows.append({
            "branch_id": branch_id,
            # 作者可读标签：试演分支按序号稳定命名，机器 id 只作 fallback。
            "display_label": ("正式路线" if official
                              else "主线" if branch_id == DEFAULT_BRANCH
                              else f"试演分支 {index}" if branch_id else "未命名路线"),
            "official": official,
            "revision": int(row.get("revision") or 0),
            "tick": int(row.get("tick") or 0),
        })
    base["branches"] = rows

    # 作者可读的「当前状况」：只取真实事实，不把引擎原始摘要塞进主界面。
    current_location = (world or {}).get("current_location") or {}
    situation: list[dict[str, str]] = []
    if current_location.get("name"):
        situation.append({"label": "当前地点", "value": str(current_location["name"])})
    if characters.get("count"):
        situation.append({"label": "已登场角色",
                          "value": f"{int(characters['count'])} 个"})
    if base["tick"]:
        situation.append({"label": "已推演回合", "value": f"第 {base['tick']} 回合"})
    for row in (payload.get("candidates") or []):
        if len(situation) >= 4:
            break
    base["situation_rows"] = situation
    return base


def _journey_projection(project_root: Path | str, novel_id: str) -> dict[str, Any]:
    """AuthorJourney 的唯一计算入口：阶段 / 目标 / 进度 / 下一步 / 风险。

    Landing 卡片（`novel_card`）与 Command Center（`command_center`）都只能消费
    这里的结果——V3 验收 NF-005 要求同一本书在任何入口得到同一阶段、同一进度、
    同一下一步，因此不允许存在第二套 stage / progress 公式。

    只做只读加载：不写 NovelProfile / 内容包 / StoryState / Canon。
    """

    root = Path(project_root)
    profile: NovelProfile = NovelProfileRepository(root).load(novel_id)
    brief = load_creative_brief(root, novel_id)
    seed = load_setting_seed(root, novel_id)
    pack_id = saved_pack_id(root, novel_id)
    pack = load_pack_draft(root, pack_id) if pack_id else None
    check = None
    check_error = ""
    if pack is not None:
        try:
            check = run_settings_check(root, novel_id)
        except Exception as exc:  # noqa: BLE001 - 自检失败不打断投影
            check_error = str(exc)
    runtime = _runtime_facts(root, novel_id)
    outline = _outline_facts(root, novel_id, runtime)
    try:
        repair = repair_diagnosis(root, novel_id)
    except Exception:  # noqa: BLE001 - 修复诊断不可用不影响主流程
        repair = {"issue_count": 0, "issues": []}
    drafts = _writer_drafts(root, novel_id)

    objectives = [
        _objective_payload(root, novel_id, profile=profile, brief=brief, seed=seed,
                           pack_id=pack_id, pack=pack, check=check,
                           runtime=runtime,
                           outline=outline, repair=repair, drafts=drafts, spec=spec)
        for spec in OBJECTIVE_SPECS
    ]

    stages: list[dict[str, Any]] = []
    current_stage = ""
    for index, stage in enumerate(V3_STAGES):
        progress = _stage_progress(stage["stage_id"], objectives)
        rows = [row for row in objectives if row["stage_id"] == stage["stage_id"]]
        blocked = any(row["status"] == "blocked" for row in rows)
        if not current_stage and progress["done"] < progress["total"]:
            current_stage = stage["stage_id"]
        stages.append({**stage, "progress": progress, "blocked": blocked,
                       "objective_ids": [row["objective_id"] for row in rows]})
    if not current_stage:
        current_stage = V3_STAGES[-1]["stage_id"]
    current_index = STAGE_INDEX.get(current_stage, len(V3_STAGES) - 1)
    for index, stage in enumerate(stages):
        if index < current_index:
            status = "COMPLETE"
        elif index == current_index:
            status = ("BLOCKED" if stage["blocked"]
                      else "IN_PROGRESS" if stage["progress"]["done"] else "CURRENT")
        elif index == current_index + 1:
            status = "AVAILABLE"
        else:
            status = "LOCKED"
        stage["status"] = status
        stage["current"] = index == current_index
        stage["reachable"] = status in ("COMPLETE", "CURRENT", "IN_PROGRESS",
                                        "AVAILABLE", "BLOCKED")
    recommended_next = (stages[current_index + 1]["stage_id"]
                        if current_index + 1 < len(stages) else "")

    current_objective = next(
        (row for row in objectives
         if row["stage_id"] == current_stage
         and row["status"] not in ("complete", "optional")), None)
    if current_objective is None:
        current_objective = next((row for row in objectives
                                  if row["status"] not in ("complete", "optional")), None)

    counted = [row for row in objectives
               if row["status"] not in ("not_applicable", "optional")]
    total_done = sum(row["progress"]["done"] for row in counted)
    total_items = sum(row["progress"]["total"] for row in counted)
    percent = round(100 * total_done / total_items) if total_items else 0
    risks = _risks(check, repair, seed, outline, runtime)
    return {
        "root": root, "profile": profile, "brief": brief, "seed": seed,
        "pack_id": pack_id, "pack": pack, "check": check, "check_error": check_error,
        "runtime": runtime, "outline": outline, "repair": repair, "drafts": drafts,
        "objectives": objectives, "stages": stages, "current_stage": current_stage,
        "current_index": current_index, "recommended_next": recommended_next,
        "current_objective": current_objective, "risks": risks,
        "progress": {"percent": percent, "label": "总体进度",
                     "done": total_done, "total": total_items},
        "journey": {
            "stages": stages,
            "current_stage": current_stage,
            "current_stage_label": next((row["label"] for row in stages
                                         if row["stage_id"] == current_stage), ""),
            "current_stage_goal": next((row["goal"] for row in stages
                                        if row["stage_id"] == current_stage), ""),
            "recommended_next_stage": recommended_next,
            "completed_stages": sum(1 for row in stages if row["status"] == "COMPLETE"),
            "stage_count": len(stages),
        },
        "next_action": _next_action(current_objective, objectives, current_stage, risks),
    }


def journey_projection(project_root: Path | str, novel_id: str) -> dict[str, Any]:
    """公开 Contract：唯一 JourneyProjection（V4-01）。

    `V4_ARCHITECTURE.md` ADR-004 要求 UI / REST / MCP 消费同一份阶段 / 进度 / 下一步；
    本函数是该投影的**唯一公开入口**，`_journey_projection()` 属于内部实现。
    服务层入口见 `novelforge.application.services.journey.JourneyService`。
    """

    return _journey_projection(project_root, novel_id)


def command_center(project_root: Path | str, novel_id: str) -> dict[str, Any]:
    """Novel Command Center 的完整只读投影（Landing 与 Command Center 的唯一数据源）。"""

    core = _journey_projection(project_root, novel_id)
    root = core["root"]
    profile = core["profile"]
    brief = core["brief"]
    seed = core["seed"]
    pack_id = core["pack_id"]
    pack = core["pack"]
    check = core["check"]
    check_error = core["check_error"]
    runtime = core["runtime"]
    outline = core["outline"]
    repair = core["repair"]
    drafts = core["drafts"]
    objectives = core["objectives"]
    stages = core["stages"]
    current_stage = core["current_stage"]
    risks = core["risks"]

    entity_edges = relationship_edges(project_root, novel_id)
    characters_payload = characters_view(project_root, novel_id, entity_edges)
    world_payload = world_view(project_root, novel_id)
    # 大纲里的参与者 / 伏笔是引擎 id，先按真实名称表翻译，再进入 Primary UI。
    character_labels = {row["character_id"]: row["name"]
                        for row in (characters_payload.get("items") or [])}
    character_labels["protagonist"] = next(
        (row["name"] for row in (characters_payload.get("items") or [])
         if row.get("is_protagonist")), character_labels.get("protagonist", "主角"))
    # 地点 / 势力也必须进同一张名称表：大纲章节的地点与摘要里会出现真实 id。
    entity_labels = {
        **{row["location_id"]: row["name"]
           for row in (world_payload.get("locations") or [])},
        **{row["faction_id"]: row["name"]
           for row in (world_payload.get("factions") or [])},
    }
    outline_labels = dict(character_labels)
    outline_labels.update(entity_labels)
    outline_labels.update(_action_name_labels(pack))
    outline_labels.update(_simulation_element_labels(pack))
    outline_view = _outline_view(outline, outline_labels, _simulation_element_labels(pack))

    return {
        "novel": {
            "novel_id": profile.novel_id,
            "title": profile.title or profile.novel_id,
            "genre": profile.genre,
            "themes": list(profile.themes or [])[:4],
            "premise": (str(getattr(brief, "original_idea", "") or "")
                        or str(profile.tone or "")),
            "tone": profile.tone,
            "content_pack_id": pack_id,
            "content_pack_title": getattr(pack, "title", "") if pack is not None else "",
            "updated_at": profile.updated_at.isoformat(),
        },
        "progress": core["progress"],
        "journey": core["journey"],
        "objectives": objectives,
        "current_objective": core["current_objective"],
        "next_action": core["next_action"],
        "risks": risks,
        "repair": _repair_view(repair),
        "export": _export_view(pack=pack, check=check, outline=outline,
                               outline_view=outline_view, runtime=runtime,
                               repair=repair, drafts=drafts),
        "outline": outline_view,
        "characters": characters_payload,
        "relationships": relationships_view(project_root, novel_id, entity_edges),
        "simulation": simulation_view(project_root, novel_id, runtime, characters_payload,
                                      world_payload),
        "world": world_payload,
        "content": _content_cards(project_root, novel_id, seed, runtime, outline),
        "activity": _activity(root, novel_id, brief, seed, pack_id, runtime, outline),
        "facts": {
            "truth_layers": dict(FACT_LAYERS),
            "creative_brief_saved": brief is not None,
            "setting_seed_saved": seed is not None,
            "content_pack_ready": pack is not None,
            "settings_check_ok": bool(check is not None and check.ok),
            "settings_check_error": check_error,
            "runtime_started": bool(runtime.get("started")),
            "outline_book_ready": outline.get("book") is not None,
            "writer_drafts": len(drafts),
        },
        "read_only": True,
        "non_authoritative": True,
    }


BLOCKING_TITLES: dict[str, str] = {
    "creation": "补齐起点设定",
    "world": "补齐世界设定",
    "characters": "补齐角色设定",
    "story": "补齐故事设定",
    "simulation": "让起点可以运行",
    "outline": "修正大纲",
    "review": "处理待确认的冲突",
    "export": "处理导出前的问题",
}


def _next_action(current_objective: Mapping[str, Any] | None,
                 objectives: Sequence[Mapping[str, Any]],
                 current_stage: str,
                 risks: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """全局唯一的 Next Best Action：只由真实 objective 状态决定。"""

    blocking = next((row for row in objectives
                     if row["status"] == "blocked" and row["blocking"]), None)
    blocking_risk = next((row for row in risks if row["level"] == "BLOCKING"), None)
    if blocking_risk is not None:
        view = str((blocking_risk.get("deep_link") or {}).get("view") or current_stage)
        return {
            "action_id": f"next_{blocking_risk['finding_id']}",
            "title": BLOCKING_TITLES.get(view, "处理阻塞问题"),
            "reason": str(blocking_risk["title"]),
            "impact": "处理完才能继续往下推进。",
            "action_label": str(blocking_risk.get("action_label") or "去修补"),
            "icon": "warning",
            "objective_id": blocking["objective_id"] if blocking else "",
            "stage_id": current_stage,
            "deep_link": dict(blocking_risk.get("deep_link") or {"view": view}),
            "blocking": True,
            "source": str(blocking_risk.get("source") or ""),
            "truth_layer": "ui_derived",
            "read_only": True,
        }
    target = blocking or current_objective or next(
        (row for row in objectives if row["status"] == "active"), None)
    if target is None:
        last = objectives[-1] if objectives else {"objective_id": "", "stage_id": current_stage}
        return {
            "action_id": "next_all_done",
            "title": "这一步已经完成",
            "reason": "当前所有目标都已完成，可以继续往下推进。",
            "impact": "整本书可以进入下一阶段。",
            "action_label": "继续创作",
            "icon": "next_action",
            "objective_id": last["objective_id"],
            "stage_id": current_stage,
            "deep_link": {"view": last["stage_id"]},
            "blocking": False,
            "truth_layer": "ui_derived",
            "read_only": True,
        }
    reason = str(target["description"])
    if target["status"] == "blocked":
        reason = "当前还有必须处理的问题，处理完才能继续。"
    return {
        "action_id": f"next_{target['objective_id']}",
        "title": target["title"],
        "reason": reason,
        "impact": target["unlock_effects"],
        "action_label": target["action_label"],
        "icon": target["icon"],
        "objective_id": target["objective_id"],
        "stage_id": target["stage_id"],
        "deep_link": dict(target["deep_link"]),
        # `blocking` 只表示「当前真的被挡住」：普通必做目标不标红肿，
        # 只有真实 blocked 状态或阻塞风险才使用 BLOCKING 语义。
        "blocking": target["status"] == "blocked",
        "truth_layer": "ui_derived",
        "read_only": True,
    }


def _risks(check: Any, repair: Mapping[str, Any], seed: Any,
           outline: Mapping[str, Any], runtime: Mapping[str, Any]
           ) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    if check is not None:
        for row in getattr(check, "findings", []) or []:
            risks.append(_author_finding(row))
    for row in list(repair.get("issues") or [])[:3]:
        requires_approval = bool(row.get("requires_approval", True))
        risks.append({
            "finding_id": f"repair_{row.get('issue_id', '')}",
            "level": "WARNING",
            "title": str(row.get("message") or "有一处需要确认的旧设定"),
            "detail": str(row.get("hint") or ""),
            "hint": str(row.get("approval_note") or row.get("hint") or ""),
            "source": "repair_diagnosis",
            "evidence": {"issue_id": str(row.get("issue_id") or ""),
                         "target": str(row.get("target") or "")},
            "deep_link": {"view": "review", "step": "repair"},
            "action_label": "去看看",
            # P5：作者必须知道这次修复会不会改动事实、是否可逆。
            "approval_label": ("需要你确认后再修复" if requires_approval
                               else "可以自动修复（不改变故事事实）"),
            "reversible": bool(row.get("reversible", True)),
        })
    if seed is not None and not _group_selected(seed, "foreshadows"):
        risks.append({
            "finding_id": "info_foreshadow_empty",
            "level": "INFO",
            "title": "还没有伏笔",
            "detail": "先埋下 1 条线索，后面的高潮会更自然。",
            "hint": "",
            "source": "setting_seed",
            "evidence": {"group": "foreshadows", "selected": 0},
            "deep_link": {"view": "story", "group": "foreshadows"},
            "action_label": "去安排",
        })
    if runtime.get("started") and outline.get("book") is None:
        risks.append({
            "finding_id": "info_outline_missing",
            "level": "INFO",
            "title": "还没有大纲",
            "detail": "推演已经开始，可以把它整理成可写的大纲。",
            "hint": "",
            "source": "outline_chain",
            "evidence": {"book": None, "chapters": 0},
            "deep_link": {"view": "outline", "step": "forge"},
            "action_label": "生成大纲",
        })
    return risks[:5]


def _content_cards(project_root: Path | str, novel_id: str, seed: Any,
                   runtime: Mapping[str, Any], outline: Mapping[str, Any]
                   ) -> list[dict[str, Any]]:
    try:
        overview = setting_overview(project_root, novel_id)
    except Exception:  # noqa: BLE001 - 总览不可用不影响核心卡片
        overview = {"cards": []}
    counts = {row["card_id"]: int(row.get("item_count") or 0)
              for row in overview.get("cards", [])}
    state = runtime.get("state")
    state_characters = len(getattr(state, "characters", {}) or {}) if state else 0
    location = getattr(state, "location", None) if state else None
    state_locations = len(getattr(location, "known", {}) or {}) if location else 0
    state_plots = len(getattr(state, "plots", {}) or {}) if state else 0
    chapters = len(_chapter_rows(outline))
    selected_main = len(_group_selected(seed, "main_line"))

    def card(card_id: str, label: str, icon: str, count: int, unit: str, view: str,
             hint: str, *, live: bool) -> dict[str, Any]:
        return {"card_id": card_id, "label": label, "icon": icon, "count": count,
                "unit": unit, "target_view": view, "hint": hint,
                "truth_layer": "occurred" if live else "planned", "read_only": True}

    return [
        card("characters", "角色", "character",
             state_characters or counts.get("protagonist", 0) + counts.get("companion", 0),
             "个角色", "characters", "已经登场的主角与重要角色。",
             live=bool(state_characters)),
        card("factions", "势力", "faction", counts.get("factions", 0), "个势力",
             "world", "正在争夺资源与话语权的组织。", live=bool(state)),
        card("locations", "地点", "location", state_locations or counts.get("world", 0),
             "个地点", "world", "故事已经发生或即将发生的地方。",
             live=bool(state_locations)),
        card("plots", "剧情", "story", state_plots or selected_main, "条线", "story",
             "主线与支线的当前推进情况。", live=bool(state_plots)),
        card("chapters", "大纲", "outline", chapters, "个章节", "outline",
             "已经整理出来的章节结构。", live=False),
    ]


def _activity(project_root: Path | str, novel_id: str, brief: Any, seed: Any,
              pack_id: str, runtime: Mapping[str, Any],
              outline: Mapping[str, Any]) -> list[dict[str, Any]]:
    root = Path(project_root)
    entries: list[dict[str, Any]] = []

    def add(entry_id: str, label: str, detail: str, path: Path, view: str) -> None:
        stamp = _mtime(path)
        if not stamp:
            return
        entries.append({"item_id": entry_id, "label": label, "detail": detail,
                        "updated_at": stamp, "target_view": view,
                        "truth_layer": "ui_derived", "read_only": True})

    profile_path = _profile_path(root, novel_id)
    if brief is not None:
        add("activity_idea", "一句话创意", "创意简报已保存", profile_path, "creation")
    if seed is not None:
        count = sum(len(rows or []) for rows in (seed.selected or {}).values())
        add("activity_settings", "设定草图", f"已确认 {count} 项设定", profile_path, "world")
    if pack_id:
        add("activity_pack", "内容包", f"已生成 {pack_id}", _pack_path(root, pack_id),
            "story")
    if runtime.get("started"):
        add("activity_runtime", "起点事实",
            f"tick {runtime.get('tick')} · revision {runtime.get('revision')}",
            profile_path, "simulation")
    book = outline.get("book")
    if book is not None:
        add("activity_outline", "大纲",
            f"{getattr(book, 'level', 'BOOK')} 大纲已生成", profile_path, "outline")
    entries.sort(key=lambda row: row["updated_at"], reverse=True)
    return entries[:4]


def novel_card(project_root: Path | str, profile: NovelProfile) -> dict[str, Any]:
    """Landing / 存档选择用的投影。

    NF-005：阶段 / 进度 / 下一步**不再自己算**，只裁剪 `_journey_projection()`
    的结果（与 Command Center 同源）。列表页因此不会出现「入口页说大纲 81%、
    作品内说导出 51%」这种同一本书两套数字。
    """

    root = Path(project_root)
    novel_id = profile.novel_id
    core = _journey_projection(root, novel_id)
    current_stage = core["current_stage"]
    next_action = core["next_action"]
    return {
        "novel_id": novel_id,
        "title": profile.title or novel_id,
        "genre": profile.genre,
        "themes": list(profile.themes or [])[:3],
        "updated_at": profile.updated_at.isoformat(),
        "stage_id": current_stage,
        "stage_label": core["journey"]["current_stage_label"],
        "progress_percent": core["progress"]["percent"],
        "progress_done": core["progress"]["done"],
        "progress_total": core["progress"]["total"],
        # 与 Command Center 右栏「下一步」同源：同一本书在两个入口显示同一句话。
        "next_action": str(next_action.get("title") or ""),
        "next_action_label": str(next_action.get("action_label") or ""),
        "next_action_view": str((next_action.get("deep_link") or {}).get("view") or ""),
        "runtime_started": bool(core["runtime"].get("started")),
        "content_pack_id": core["pack_id"],
        "read_only": True,
    }


def novel_cards(project_root: Path | str) -> dict[str, Any]:
    root = Path(project_root)
    cards = [novel_card(root, profile)
             for profile in NovelProfileRepository(root).list()]
    cards.sort(key=lambda row: row["updated_at"], reverse=True)
    return {"novels": cards, "count": len(cards), "read_only": True}


__all__ = [
    "FACT_LAYERS",
    "FINDING_TITLES",
    "GROUP_LABELS",
    "GROUP_OBJECTIVES",
    "GROUP_REQUIRED",
    "OBJECTIVE_SPECS",
    "STAGE_INDEX",
    "V3_STAGES",
    "command_center",
    "novel_card",
    "novel_cards",
]
