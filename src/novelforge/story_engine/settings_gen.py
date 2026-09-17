"""W1-02：设定候选生成。

输入 `creative_brief`，产出**这本小说专属**的候选：

    世界规则 → 主角 → 重要角色 → 势力 → 初始关系网 → 成长体系 → 核心矛盾 → 主线方向 → 初始伏笔

并据此生成符合既有 `ContentPack` schema 的骨架（落盘为可直接被 Runtime 消费的内容包）。

设计约束：

- 复用 NovelProfile / ContentPack / Condition / Effect / ProgressionTree / Foreshadow 既有模型。
- 差异只通过数据表达；代码里没有题材分支，所有内容都从 brief 的创意文本与已选方向派生。
- AI 只允许补充文案；结构、id、schema 与合法性由本模块生成与校验。
- 不写任何 StoryState 事实：本阶段产出的是设计态数据。
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import Field

from novelforge.models import StrictModel

from .content import DEFAULT_CONTENT_DIR, ContentPack
from .creative import CreativeBrief, load_creative_brief
from .entities import Character, Faction

SETTINGS_KEY = "setting_seed"
MAX_RULE_CANDIDATES = 5
MAX_CHARACTER_CANDIDATES = 4
MAX_FACTION_CANDIDATES = 4
MAX_FORESHADOW_CANDIDATES = 4

SELECTABLE_GROUPS: tuple[str, ...] = (
    "world_rules", "protagonist", "characters", "factions", "relationships",
    "progression", "conflicts", "main_line", "foreshadows",
)

# 通用叙事要素词表：只用于给候选命名与打标签，不参与任何分支判断。
CONFLICT_MARKERS = ("其实", "背后", "秘密", "隐藏", "真相", "阴谋", "系统", "规则")
RESOURCE_MARKERS = ("资源", "能源", "灵石", "钱", "物资", "补给", "算力", "矿石")
FACTION_MARKERS = ("公司", "宗门", "势力", "组织", "阵营", "议会", "管理局", "行会")
RELATION_MARKERS = ("同门", "同事", "同伴", "搭档", "师傅", "上司", "家人", "房东")

RULE_TEMPLATES: tuple[tuple[str, str], ...] = (
    ("世界表层规则", "日常秩序按公开规则运行，违规会立刻被看见"),
    ("隐藏层规则", "存在一套只在特定条件下显露的底层机制"),
    ("代价规则", "任何超出常规的收益都要付出可追溯的代价"),
    ("信息规则", "知道得越多，能接触的范围越大，风险也越高"),
    ("身份规则", "身份决定可进入的场所与可调用的资源"),
)

PROTAGONIST_ROLES: tuple[str, ...] = ("普通执行者", "边缘技术员", "被误解的当事人",
                                      "刚入行的新人", "背债的中间人")

SUPPORT_ROLES: tuple[str, ...] = ("掌握线索的同行者", "立场摇摆的上位者",
                                  "利益冲突的旧识", "规则内外的中间人")

FACTION_SHAPES: tuple[str, ...] = ("资源控制方", "秩序维护方", "灰色中间方")

# 七类成长：与引擎的 ProgressionCategory 对齐（"progression" 只是缺省值，不单独出节点）。
PROGRESSION_CATEGORIES: tuple[str, ...] = ("ability", "identity", "relationship", "faction",
                                           "information", "equipment", "skill")

CATEGORY_LABELS: dict[str, str] = {
    "progression": "综合成长",
    "ability": "能力",
    "identity": "身份",
    "relationship": "关系",
    "faction": "势力",
    "information": "信息",
    "equipment": "装备",
    "skill": "非战斗技能",
}

ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def _default_provider() -> Any | None:
    """V4-04 §14：默认 provider 经 `novelforge.ai` 的 Gateway 桥（函数内惰性 import）。"""

    from novelforge.ai import default_structured_provider

    return default_structured_provider()


class SettingsGenError(ValueError):
    def __init__(self, code: str, message: str, *, novel_id: str = "") -> None:
        self.code = code
        self.message = message
        self.novel_id = novel_id
        super().__init__(message)

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message, "novel_id": self.novel_id}


class Candidate(StrictModel):
    """一个可被作者挑选 / 改写的设定候选；`data` 承载结构化字段。"""

    id: str = Field(min_length=1, max_length=64)
    label: str = Field(default="", max_length=80)
    summary: str = Field(default="", max_length=300)
    reason: str = Field(default="", max_length=300)
    data: dict[str, Any] = Field(default_factory=dict)


class SettingSeed(StrictModel):
    """W1-02 的设定种子：每一组都是候选集，作者可挑可改可跳过。"""

    novel_id: str = Field(default="", max_length=96)
    original_idea: str = Field(default="", max_length=1000)
    genre: str = Field(default="", max_length=64)
    tone: str = Field(default="", max_length=64)
    selling_points: list[str] = Field(default_factory=list)
    world_rules: list[Candidate] = Field(default_factory=list)
    protagonist: list[Candidate] = Field(default_factory=list)
    characters: list[Candidate] = Field(default_factory=list)
    factions: list[Candidate] = Field(default_factory=list)
    relationships: list[Candidate] = Field(default_factory=list)
    progression: list[Candidate] = Field(default_factory=list)
    conflicts: list[Candidate] = Field(default_factory=list)
    main_line: list[Candidate] = Field(default_factory=list)
    foreshadows: list[Candidate] = Field(default_factory=list)
    selected: dict[str, list[str]] = Field(default_factory=dict)
    source: str = "rule"
    notes: list[str] = Field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def _slug(text: str, *, prefix: str) -> str:
    """把中文 / 英文摘要转成稳定且唯一的 slug id。

    中文没有 ASCII 词干，因此始终附加内容摘要（sha1 前 8 位）：
    同一个输入在任何进程、任何时间都得到同一个 id，不同输入不会撞 id。
    """

    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
    ascii_part = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    if ascii_part.startswith(prefix):
        ascii_part = ascii_part[len(prefix):].strip("_")
    stem = f"{prefix}_{ascii_part}" if ascii_part else prefix
    return f"{stem[:54]}_{digest}"[:64]


def _clauses(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"[，。；、！？!?;,\n]+", text or "") if part.strip()]


def _core_phrase(idea: str) -> str:
    """从创意里取一小段“这本书专属”的描述，用于候选文案与内容包标题。"""

    parts = _clauses(idea)
    if not parts:
        return "当前的局面"
    for part in parts:
        if any(marker in part for marker in CONFLICT_MARKERS):
            return part[:40]
    return parts[0][:40]


def _first_marker(text: str, markers: tuple[str, ...], default: str) -> str:
    for marker in markers:
        if marker in text:
            return marker
    return default


def _short_title(idea: str, *, limit: int = 18, fallback: str = "未命名作品") -> str:
    """作品名候选：取创意的第一个完整短句，不在词中间截断，也不带状态后缀。

    内容包的 `title` 会出现在作者可见的位置（高级工具的作品下拉、导出清单），
    所以这里只取「作者自己写下的第一个短句」，状态用 badge 表达而不是写进名字。
    """

    text = " ".join(str(idea or "").split()).strip()
    if not text:
        return fallback
    for separator in ("。", "！", "？", "；", "\n", "，", "、"):
        head, found, _ = text.partition(separator)
        if found and head.strip():
            text = head.strip()
            break
    text = text.strip(" 　·；;，,。:：\"'“”")
    if len(text) > limit:
        text = text[:limit].rstrip(" 　·；;，,。:：")
    return text or fallback


def deterministic_seed(brief: CreativeBrief, *, offset: int = 0) -> SettingSeed:
    """确定性降级路径：只依据 brief 的创意文本派生候选，不调用任何模型。"""

    idea = brief.original_idea.strip()
    tone = brief.tone or "冷峻写实"
    genre = brief.selected_genre or ""
    focus = _core_phrase(idea)
    text = " ".join([idea, tone, genre, brief.reader_experience, *brief.selling_points])
    conflict_word = _first_marker(text, CONFLICT_MARKERS, "隐患")
    resource_word = _first_marker(text, RESOURCE_MARKERS, "关键资源")
    faction_word = _first_marker(text, FACTION_MARKERS, "既有秩序")
    relation_word = _first_marker(text, RELATION_MARKERS, "身边人")
    subject = idea[:16] or "主角"

    rules = [Candidate(
        id=_slug(label, prefix="rule"), label=label, summary=f"{summary}（围绕「{focus}」）",
        reason=f"创意里出现“{conflict_word}”方向的张力，需要一条可被事件触发的规则",
        data={"kind": "world_rule"})
        for label, summary in RULE_TEMPLATES[:MAX_RULE_CANDIDATES]]
    protagonist = [Candidate(
        id=_slug(f"{role}|{idea}", prefix="hero"), label=role,
        summary=f"{role}：以普通身份切入「{focus}」的局面",
        reason="主角需要与世界观存在落差，才能持续产生选择与代价",
        data={"kind": "protagonist", "goal": f"查清与「{focus}」有关的真相"})
        for role in PROTAGONIST_ROLES[:3]]
    characters = [Candidate(
        id=_slug(f"{role}|{idea}", prefix="npc"), label=role,
        summary=f"{role}：与主角的目标部分重叠、部分冲突（{subject}的局面里）",
        reason=f"围绕“{relation_word}”关系制造立场摩擦",
        data={"kind": "character", "role": role, "desire": "推进自己的目标",
              "fear": "失去已有的位置"})
        for role in SUPPORT_ROLES[:MAX_CHARACTER_CANDIDATES]]
    factions = [Candidate(
        id=_slug(f"{shape}|{faction_word}|{idea}", prefix="faction"),
        label=f"{faction_word}·{shape}",
        summary=f"{shape}：掌握“{resource_word}”与通行权限",
        reason="势力决定资源与场所的开放程度，是长期冲突的来源",
        data={"kind": "faction", "stance": shape, "influence": 5 - index})
        for index, shape in enumerate(FACTION_SHAPES[:MAX_FACTION_CANDIDATES], start=1)]
    relationships = [Candidate(
        id=_slug(f"{role}|{idea}", prefix="rel"), label=f"主角 ↔ {role}",
        summary=f"初始关系：互相需要但彼此保留（{role}）",
        reason="先给一层可被事件改变的初始关系，不预设感情数值",
        data={"kind": "relationship", "from": "protagonist", "to": role,
              "dimensions": {"trust": 1, "affection": 0, "respect": 1, "fear": 0,
                             "debt": 0, "hostility": 0, "dependency": 0}})
        for role in SUPPORT_ROLES[:3]]
    progression = [Candidate(
        id=_slug(category, prefix="tree"), label=f"{CATEGORY_LABELS.get(category, category)}成长线",
        summary=f"覆盖「{CATEGORY_LABELS.get(category, category)}」的成长节点，解锁条件与代价全部数据化",
        reason="七类成长共用同一套 Progression，避免为单本小说写专用逻辑",
        data={"kind": "progression", "category": category})
        for category in PROGRESSION_CATEGORIES]
    conflicts = [Candidate(
        id=_slug(f"{label}|{idea}", prefix="conflict"), label=label, summary=summary,
        reason=f"与创意中“{conflict_word}”直接相关", data={"kind": "conflict"})
        for label, summary in (
            ("表层问题", f"主角必须先处理眼前的实际问题，再触及「{focus}」"),
            ("立场冲突", f"{faction_word}与主角对「{resource_word}」的分配要求相反"),
            ("代价压力", "每次接近真相都要付出可被追踪的代价"))]
    main_line = [Candidate(
        id=_slug(f"{label}|{idea}", prefix="main"), label=label, summary=summary,
        reason="主线只描述目标与阶段，不规定具体事件顺序",
        data={"kind": "main_line", "scope": scope})
        for label, summary, scope in (
            # 主线候选的 label 会同时成为 future_plan 的阶段名与章节标题素材，
            # 因此必须是**内容**（这本小说要做什么），不能是「阶段目标」这类字段标签。
            (_short_title(f"查清{focus}", limit=16, fallback="查清真相"),
             f"查清「{focus}」并把证据整理到可呈报的程度", "stage"),
            (_short_title(f"在{faction_word}中立足", limit=16,
                          fallback="取得自主行动的位置"),
             f"在「{faction_word}」的秩序里取得可以自主行动的位置", "long_term"))]
    foreshadows = [Candidate(
        id=_slug(f"{label}|{idea}", prefix="fs"), label=label, summary=summary,
        reason="伏笔只登记状态与回收条件，不规定回收方式",
        data={"kind": "foreshadow", "planted_in": planted, "payoff_condition": condition})
        for label, summary, planted, condition in (
            ("缺失的一环", f"「{focus}」有一条被刻意抹去的记录", "开篇",
             {"op": "knowledge", "entity": "protagonist", "target": "core_record"}),
            ("被忽略的警告", "有人早就提醒过主角，但当时没被当真", "第二章",
             {"op": "flag", "key": "clue", "value": True}),
            ("代价的来处", f"主角获得的「{resource_word}」来源并不干净", "第三章",
             {"op": "relationship", "entity": "protagonist", "target": "npc_1",
              "key": "trust", "value": 2, "comparator": ">="}),
            ("站不住的身份", "主角赖以行动的凭证随时可能失效", "第四章",
             {"op": "identity", "entity": "protagonist", "value": "acting_permit"}))]
    groups = (rules, protagonist, characters, factions, relationships, progression, conflicts,
              main_line, foreshadows)
    if offset:
        for group in groups:
            if group:
                pivot = offset % len(group)
                group[:] = group[pivot:] + group[:pivot]
    return SettingSeed(novel_id="", original_idea=idea, genre=genre, tone=tone,
                       selling_points=list(brief.selling_points),
                       world_rules=rules[:MAX_RULE_CANDIDATES], protagonist=protagonist,
                       characters=characters, factions=factions, relationships=relationships,
                       progression=progression, conflicts=conflicts, main_line=main_line,
                       foreshadows=foreshadows[:MAX_FORESHADOW_CANDIDATES],
                       source="rule", notes=[])


class SettingsProvider:
    """可选 AI 补全：只允许在既有候选 id 上补充文案，不能新增结构。"""

    def __init__(self, provider: Any | None) -> None:
        self.provider = provider if provider is not None else _default_provider()

    def enrich(self, seed: SettingSeed) -> tuple[SettingSeed, list[str]]:
        notes: list[str] = []
        if self.provider is None:
            return seed, ["AI_UNAVAILABLE"]
        allowed = {group: {item.id for item in getattr(seed, group)} for group in SELECTABLE_GROUPS}
        try:
            _, draft = self.provider.generate_structured(
                chapter_id="setting_seed", stage="setting_seed_suggestions", skill_name=None,
                prompt=self._prompt(seed),
                context={"brief": {"original_idea": seed.original_idea, "genre": seed.genre,
                                   "tone": seed.tone}}, output_model=None, workspace=None)
        except Exception as exc:  # noqa: BLE001 - AI 失败退回确定性种子
            return seed, [f"AI_ERROR:{exc}"]
        parsed = draft if isinstance(draft, Mapping) else getattr(draft, "__dict__", {})
        if not isinstance(parsed, Mapping):
            return seed, ["AI_DRAFT_INVALID"]
        updates: dict[str, list[Candidate]] = {}
        for group in SELECTABLE_GROUPS:
            rows: list[Candidate] = []
            for raw in parsed.get(group, []) or []:
                if not isinstance(raw, Mapping):
                    continue
                item_id = str(raw.get("id", "") or "")
                if item_id not in allowed[group]:
                    notes.append(f"AI_CANDIDATE_OUTSIDE_CATALOG:{group}:{item_id}")
                    continue
                base = next(item for item in getattr(seed, group) if item.id == item_id)
                rows.append(base.model_copy(update={
                    "label": str(raw.get("label", "") or base.label)[:80],
                    "summary": str(raw.get("summary", "") or base.summary)[:300],
                    "reason": str(raw.get("reason", "") or base.reason)[:300]}))
            if rows:
                merged = rows + [item for item in getattr(seed, group) if item not in rows]
                updates[group] = merged
        if not updates:
            return seed.model_copy(update={"notes": notes}), notes
        enriched = seed.model_copy(update={**updates, "source": "ai", "notes": notes})
        return enriched, notes

    @staticmethod
    def _prompt(seed: SettingSeed) -> str:
        lines = ["你只能改写下面候选项的文案，禁止新增、删除或改名 id，禁止发明新的结构。",
                 f"创意：{seed.original_idea}", f"题材：{seed.genre} 基调：{seed.tone}"]
        for group in SELECTABLE_GROUPS:
            items = [{"id": item.id, "label": item.label} for item in getattr(seed, group)]
            lines.append(f"{group}: {items}")
        lines.append("输出 JSON：{world_rules:[{id,label,summary,reason}], ...其余同理}")
        return "\n".join(lines)


def apply_selection(seed: SettingSeed, selected: Mapping[str, list[str]] | None
                    ) -> tuple[SettingSeed, list[str]]:
    """把作者选择写进种子；越界 id 直接丢弃并记录，不抛异常。"""

    notes: list[str] = []
    allowed = {group: {item.id for item in getattr(seed, group)} for group in SELECTABLE_GROUPS}
    resolved: dict[str, list[str]] = {}
    for group, ids in (selected or {}).items():
        if group not in SELECTABLE_GROUPS:
            notes.append(f"SELECTION_GROUP_UNKNOWN:{group}")
            continue
        kept: list[str] = []
        for item_id in ids or []:
            if item_id not in allowed[group]:
                notes.append(f"SELECTION_OUTSIDE_CATALOG:{group}:{item_id}")
                continue
            if item_id not in kept:
                kept.append(item_id)
        resolved[group] = kept
    return seed.model_copy(update={"selected": resolved}), notes


def build_setting_seed(project_root: Path, novel_id: str, *, regenerate: bool = False,
                       provider: Any | None = None, brief: CreativeBrief | None = None,
                       selected: Mapping[str, list[str]] | None = None) -> SettingSeed:
    """生成（或重新生成）设定候选；不落盘，保存由 save_setting_seed 负责。

    重新生成不会丢掉作者已经确认（或人工改写）的候选项：
    这些候选按 id 保留在结果里，并继续标记为已选。
    """

    current = brief or load_creative_brief(project_root, novel_id)
    if current is None:
        raise SettingsGenError("CREATIVE_BRIEF_REQUIRED",
                               "请先完成创意简报（W1-01），再生成设定候选", novel_id=novel_id)
    if not current.original_idea.strip():
        raise SettingsGenError("CREATIVE_BRIEF_EMPTY", "创意简报缺少原始创意", novel_id=novel_id)
    previous = load_setting_seed(project_root, novel_id)
    seed = deterministic_seed(current, offset=1 if regenerate else 0)
    seed = seed.model_copy(update={"novel_id": novel_id})
    if previous is not None:
        seed = _keep_confirmed(seed, previous)
    seed, selection_notes = apply_selection(
        seed, selected if selected is not None else seed.selected)
    seed, notes = SettingsProvider(provider).enrich(seed)
    merged_notes = list(notes) + selection_notes + [
        note for note in seed.notes if note not in notes]
    return seed.model_copy(update={"notes": merged_notes})


def _keep_confirmed(seed: SettingSeed, previous: SettingSeed) -> SettingSeed:
    """重新生成时保留作者已确认 / 已改写的候选（按 id 合并）。"""

    updates: dict[str, Any] = {"selected": dict(previous.selected or {})}
    for group in SELECTABLE_GROUPS:
        kept_ids = set(previous.selected.get(group, []) or [])
        if not kept_ids:
            continue
        rows = list(getattr(seed, group))
        known = {item.id for item in rows}
        for item in getattr(previous, group):
            if item.id in kept_ids and item.id not in known:
                rows.append(item)
                known.add(item.id)
        updates[group] = rows
    return seed.model_copy(update=updates)


def _action_payload(action_id: str, *, kind: str, name: str, cost_text: str = "",
                    requirements: list[dict[str, Any]] | None = None,
                    costs: list[dict[str, Any]] | None = None,
                    immediate_effects: list[dict[str, Any]] | None = None,
                    risks: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"id": action_id, "kind": kind, "name": name,
                               "data": {"cost_text": cost_text or "不消耗资源"}}
    if requirements:
        payload["requirements"] = requirements
    if costs:
        payload["costs"] = costs
    if immediate_effects:
        payload["immediate_effects"] = immediate_effects
    if risks:
        payload["risks"] = risks
    return payload


def _chosen(seed: SettingSeed, group: str, *, limit: int) -> list[Candidate]:
    """作者选中的候选优先；没选（可跳过）时回退到前 N 个候选。"""

    rows = list(getattr(seed, group))
    selected_ids = list(seed.selected.get(group) or [])
    picked = [item for item_id in selected_ids for item in rows if item.id == item_id]
    if not picked:
        picked = rows[:limit]
    return picked[:limit]


def content_pack_draft(seed: SettingSeed, *, pack_id: str, brief: CreativeBrief,
                       selected: Mapping[str, list[str]] | None = None) -> dict[str, Any]:
    """把设定种子转成符合 ContentPack schema 的骨架（未落盘）。"""

    working = seed if selected is None else seed.model_copy(update={
        "selected": {group: list(ids) for group, ids in (selected or {}).items()}})
    focus = _core_phrase(working.original_idea)
    rules = _chosen(working, "world_rules", limit=1)
    protagonist = (_chosen(working, "protagonist", limit=1) or [None])[0]
    characters = _chosen(working, "characters", limit=3)
    factions = _chosen(working, "factions", limit=3)
    conflicts = _chosen(working, "conflicts", limit=1)
    main_line = _chosen(working, "main_line", limit=2)
    foreshadows = _chosen(working, "foreshadows", limit=MAX_FORESHADOW_CANDIDATES)
    context_word = rules[0].label if rules else focus
    protagonist_name = protagonist.label if protagonist else "主角"

    characters_payload: dict[str, Any] = {
        "protagonist": {
            "name": protagonist_name, "kind": "player",
            "data": {
                "role": protagonist_name,
                "premise": focus,
                "goal": ((protagonist.data.get("goal") if protagonist else "") or
                         f"查清「{focus}」"),
                "desire": "把局面看清楚",
                "fear": "被卷进更大的代价",
                "bottom_line": ["不拿身边人挡灾"],
                "goals": [
                    {"id": "goal_long", "scope": "long_term",
                     "title": (main_line[1].label if len(main_line) > 1 else "长期方向"),
                     "priority": 3, "weight": 2},
                    {"id": "goal_stage", "scope": "stage",
                     "title": (main_line[0].label if main_line else "阶段目标"),
                     "priority": 3, "weight": 2},
                    {"id": "goal_now", "scope": "current",
                     "title": f"处理{context_word}", "priority": 2, "weight": 2}]}}}
    for index, item in enumerate(characters, start=1):
        characters_payload[f"npc_{index}"] = {
            "name": item.label, "kind": "npc",
            "data": {"role": item.label, "desire": item.data.get("desire", "推进自己的目标"),
                     "fear": item.data.get("fear", "失去已有的位置"),
                     "bottom_line": ["不损自己的根基"],
                     "goals": [
                         {"id": "goal_long", "scope": "long_term",
                          "title": f"{item.label}的长期目标", "priority": 3, "weight": 2},
                         {"id": "goal_stage", "scope": "stage",
                          "title": f"{item.label}的当前盘算", "priority": 2, "weight": 2}]}}
    factions_payload = {
        f"faction_{index}": {
            "name": item.label, "kind": "faction", "stance": item.data.get("stance", ""),
            "data": {"influence": item.data.get("influence", 5 - index), "resources": [],
                     "internal_conflicts": ["内部分配存在分歧"]}}
        for index, item in enumerate(factions, start=1)}
    locations_payload = {
        "start_place": {"name": "起点场所", "kind": "site", "access": "主角当前可以进入",
                        "data": {"control": "faction_1" if factions_payload else "",
                                 "danger": 0}},
        "work_place": {"name": "工作场所", "kind": "site", "access": "需要身份或通行条件",
                       "data": {"control": "faction_2" if len(factions_payload) > 1 else "",
                                "danger": 1}},
        "hidden_place": {"name": "隐藏节点", "kind": "site", "access": "需要情报或关系才能进入",
                         "data": {"control": "unknown", "danger": 2}},
    }
    actions_payload = [
        _action_payload("act_investigate", kind="investigate",
                        name=f"查证与「{focus}」有关的记录",
                        immediate_effects=[{"op": "add_knowledge", "entity": "protagonist",
                                            "target": "core_record", "value": 1,
                                            "source": "act_investigate"}]),
        _action_payload("act_ask", kind="negotiate", name="向身边人打听",
                        cost_text="消耗 1 份人情",
                        costs=[{"op": "remove_resource", "target": "favors", "value": 1}],
                        requirements=[{"op": "resource", "key": "favors", "value": 1,
                                       "comparator": ">="}],
                        immediate_effects=[{"op": "set_flag", "key": "asked_around",
                                            "value": True}]),
        _action_payload("act_wait", kind="wait", name="先观察，不急着介入",
                        cost_text="不消耗资源，但世界会推进一格"),
        _action_payload("act_open_hidden", kind="investigate",
                        name="进入需要情报才能找到的节点",
                        requirements=[{"op": "knowledge", "entity": "protagonist",
                                       "target": "core_record"},
                                      {"op": "location", "value": "start_place"}],
                        costs=[{"op": "advance_time", "value": 1}],
                        risks=[{"id": "risk_exposure", "data": {"kind": "exposure"},
                                "description": "进入后会被控制方注意到"}]),
        _action_payload("act_call_favor", kind="negotiate",
                        name="请关系对象帮一次忙",
                        requirements=[{"op": "relationship", "entity": "protagonist",
                                       "target": "npc_1", "key": "trust", "value": 2,
                                       "comparator": ">="}],
                        costs=[{"op": "change_relationship", "entity": "protagonist",
                                "target": "npc_1", "key": "debt", "value": 1}],
                        immediate_effects=[{"op": "set_flag", "key": "ally", "value": True}]),
        _action_payload("act_use_permit", kind="use",
                        name="使用仍在有效期内的凭证",
                        requirements=[{"op": "identity", "entity": "protagonist",
                                       "value": "acting_permit"}]),
        _action_payload("act_go_work", kind="move", name="去工作场所",
                        immediate_effects=[{"op": "change_location", "entity": "protagonist",
                                            "value": "work_place"}]),
        _action_payload("act_go_hidden", kind="move", name="前往隐藏节点",
                        cost_text="需要情报；进入后风险上升",
                        requirements=[{"op": "knowledge", "entity": "protagonist",
                                       "target": "core_record"}],
                        costs=[{"op": "advance_time", "value": 1}],
                        immediate_effects=[{"op": "change_location", "entity": "protagonist",
                                            "value": "hidden_place"}]),
    ]
    relationships_payload = _relationship_payload(working, characters)
    events_payload = [
        {"event_id": "ev_first_pressure", "title": f"{context_word}的压力落到主角身上",
         "kind": "main", "priority": 4, "once_only": True, "scope": "scene",
         "trigger": {"op": "flag", "key": "seeded", "value": True},
         "participants": ["protagonist"],
         "scene_goal": f"让作者看清「{focus}」的第一层压力",
         "conflict": "主角想先弄清情况，但局面要求他立刻表态",
         "available_actions": ["act_investigate", "act_ask", "act_wait"],
         "data": {"main_line": True, "pacing": "rise", "event_type": "pressure",
                  "conflict": 1, "crisis": 1}},
        {"event_id": "ev_world_shift", "title": f"{context_word}的分配方式被单方面调整",
         "kind": "world", "priority": 3, "once_only": False, "cooldown": 4, "scope": "world",
         "trigger": {"op": "flag", "key": "seeded", "value": True},
         "reader_visible": True,
         "data": {"world": True, "pacing": "wave", "event_type": "world_pressure",
                  "conflict": 2}},
    ]
    plots_payload = [
        {"id": "main_track", "title": (conflicts[0].label if conflicts else "主线"),
         "status": "active", "priority": 4, "progress": 0,
         "characters": ["protagonist"], "factions": list(factions_payload)[:1],
         "locations": ["start_place"],
         "trigger": {"op": "flag", "key": "seeded", "value": True}},
    ]
    for index, item in enumerate(working.main_line or [], start=1):
        plots_payload.append({"id": f"stage_track_{index}", "title": item.label,
                              "status": "inactive", "priority": 3 - (index - 1), "progress": 0,
                              "characters": ["protagonist"]})
    for index, item in enumerate(working.conflicts or [], start=1):
        plots_payload.append({"id": f"conflict_track_{index}", "title": item.label,
                              "status": "inactive", "priority": 2, "progress": 0,
                              "characters": ["protagonist"],
                              "factions": [f"faction_{index + 2}"]
                              if f"faction_{index + 2}" in factions_payload else []})
    progression_payload = _progression_payload(working)
    foreshadow_payload = [
        {"id": item.id, "title": item.label, "status": "planned",
         "planted_in": item.data.get("planted_in", "开篇"), "payoff_in": "后续篇章",
         "payoff_condition": item.data.get("payoff_condition") or
         {"op": "flag", "key": "seeded", "value": True},
         "data": {"level": "book", "author_note": item.summary}}
        for item in foreshadows]
    autonomous_payload = [
        {"actor_id": f"npc_{index}", "action_id": "act_wait",
         "label": f"{item.label}按自己的目标行动", "priority": 2, "once": False,
         "data": {"source": "settings_seed"}}
        for index, item in enumerate(characters, start=1)]
    return {
        "schema_version": 1,
        "pack_id": pack_id,
        # 作者可见的作品名：不在词中间截断，也不用「（设定草稿）」表达状态
        # （状态由界面 badge / 就绪度表达，不是名字的一部分）。
        "title": _short_title(brief.original_idea),
        "genre": working.genre,
        "initial_flags": {"journey_revision": 0, "seeded": True, "clue": False, "ally": False},
        "initial_resources": {"supplies": 3, "favors": 2},
        "initial_current_location": "start_place",
        "initial_locations": locations_payload,
        "initial_factions": factions_payload,
        "initial_characters": characters_payload,
        "initial_relationships": relationships_payload,
        "initial_plots": plots_payload,
        # 世界事件密度：两次世界事件至少间隔 2 tick（作者可在内容包里调）。
        "world_event_gap": 2,
        "progressions": progression_payload,
        "foreshadows": foreshadow_payload,
        "autonomous_rules": autonomous_payload,
        "actions": actions_payload,
        "events": events_payload,
    }


def _relationship_payload(seed: SettingSeed, characters: list[Candidate]) -> list[dict[str, Any]]:
    """起点关系网：把候选里的关系映射到真实角色 id；每个 NPC 至少有一条关系。"""

    label_to_id = {item.label: f"npc_{index}"
                   for index, item in enumerate(characters, start=1)}
    rows: list[dict[str, Any]] = []
    for item in _chosen(seed, "relationships", limit=MAX_CHARACTER_CANDIDATES):
        target_id = label_to_id.get(str(item.data.get("to", "")))
        if not target_id:
            continue
        dimensions = dict(item.data.get("dimensions") or {})
        dimensions.setdefault("trust", 1)
        rows.append({"source_id": "protagonist", "target_id": target_id,
                     "dimensions": dimensions,
                     "data": {"kind": "initial", "note": item.reason}})
    covered = {row["target_id"] for row in rows}
    for index, item in enumerate(characters, start=1):
        character_id = f"npc_{index}"
        if character_id in covered:
            continue
        rows.append({"source_id": "protagonist", "target_id": character_id,
                     "dimensions": {"trust": 1, "respect": 1},
                     "data": {"kind": "initial", "note": f"{item.label}：初始互相观察"}})
    return rows


def _progression_payload(seed: SettingSeed) -> list[dict[str, Any]]:
    """七类成长：每类一个节点，前置与成本数据化。"""

    nodes: list[dict[str, Any]] = []
    for index, item in enumerate(seed.progression or [], start=1):
        category = str(item.data.get("category", "progression"))
        kind = category if category in ("ability", "identity", "skill") else "progression"
        nodes.append({
            "id": item.id, "tree_id": "core", "kind": kind, "category": category,
            "level": index, "name": item.label, "summary": item.summary,
            "story_impact": "解锁后会出现新的可行动作",
            "recommendation": item.reason,
            "unlock": {"op": "flag", "key": "seeded", "value": True},
            "costs": [{"op": "advance_time", "value": 1}]})
    return [{"tree_id": "core", "name": "通用成长", "nodes": nodes}]


def validate_pack_draft(payload: Mapping[str, Any]) -> ContentPack:
    """骨架必须能通过既有 ContentPack schema 校验。"""

    try:
        return ContentPack.model_validate(dict(payload))
    except Exception as exc:  # noqa: BLE001 - 校验失败按生成错误返回
        raise SettingsGenError("SETTINGS_PACK_INVALID", f"设定骨架不符合内容包格式：{exc}") from exc


def pack_path_for(project_root: Path, pack_id: str) -> Path:
    return Path(project_root) / DEFAULT_CONTENT_DIR / f"{pack_id}.json"


def default_pack_id(novel_id: str) -> str:
    """由 novel_id 派生内容包 id：规范化成合法 slug，大小写与符号都不会让保存失败。"""

    slug = re.sub(r"[^a-z0-9_]+", "_", f"{novel_id}_pack".lower()).strip("_")
    if not slug or not slug[0].isalpha():
        slug = f"pack_{slug}"
    return slug[:64]


def write_content_pack(project_root: Path, pack: ContentPack) -> Path:
    """把生成的内容包写进项目内容目录（单包文件），供 Runtime 直接按 pack_id 载入。"""

    if not ID_PATTERN.match(pack.pack_id or ""):
        raise SettingsGenError("PACK_ID_INVALID", f"内容包 id 不合法：{pack.pack_id}")
    path = pack_path_for(project_root, pack.pack_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(pack.model_dump(mode="json"), ensure_ascii=False, indent=2)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(path)
    return path


def load_pack_draft(project_root: Path, pack_id: str) -> ContentPack | None:
    path = pack_path_for(project_root, pack_id)
    if not path.is_file():
        return None
    return validate_pack_draft(json.loads(path.read_text(encoding="utf-8")))


def save_setting_seed(project_root: Path, novel_id: str, *, seed: SettingSeed,
                      selected: Mapping[str, list[str]] | None = None,
                      pack_id: str = "") -> dict[str, Any]:
    """保存作者确认后的设定种子与内容包骨架（设计态），不写 StoryState。"""

    from .profile import NovelProfileRepository

    for group in SELECTABLE_GROUPS:
        for item in getattr(seed, group):
            if not ID_PATTERN.match(item.id):
                raise SettingsGenError("CANDIDATE_ID_INVALID", f"候选 id 不合法：{item.id}",
                                       novel_id=novel_id)
    brief = load_creative_brief(project_root, novel_id)
    if brief is None:
        raise SettingsGenError("CREATIVE_BRIEF_REQUIRED", "请先完成创意简报（W1-01）",
                               novel_id=novel_id)
    working, selection_notes = apply_selection(
        seed, selected if selected is not None else seed.selected)
    resolved_pack_id = pack_id or default_pack_id(novel_id)
    payload = content_pack_draft(working, pack_id=resolved_pack_id, brief=brief)
    pack = validate_pack_draft(payload)
    path = write_content_pack(project_root, pack)

    repository = NovelProfileRepository(project_root)
    profile = repository.ensure(novel_id)
    world_profile = dict(profile.world_profile)
    world_profile[SETTINGS_KEY] = {
        "seed": working.as_dict(),
        "pack_id": resolved_pack_id,
        "pack_path": str(path.relative_to(project_root)) if path.is_relative_to(project_root)
        else str(path),
        "notes": selection_notes,
    }
    rules = _chosen(working, "world_rules", limit=MAX_RULE_CANDIDATES)
    cast: dict[str, Any] = {}
    for item in _chosen(working, "protagonist", limit=1):
        cast["protagonist"] = Character(id="protagonist", kind="player", name=item.label,
                                        data={"role": item.label,
                                              "goal": item.data.get("goal", "")})
    for index, item in enumerate(_chosen(working, "characters", limit=3), start=1):
        cast[f"npc_{index}"] = Character(id=f"npc_{index}", kind="npc", name=item.label,
                                         data={"role": item.label})
    factions = {f"faction_{index}": Faction(id=f"faction_{index}", kind="faction",
                                            name=item.label, stance=item.data.get("stance", ""),
                                            data={"influence": item.data.get("influence", 0)})
                for index, item in enumerate(_chosen(working, "factions", limit=3), start=1)}
    stages = [{"id": item.id, "title": item.label, "goal": item.summary, "status": "planned",
               "is_goal": True, "note": "来自 W1-02 设定候选"}
              for item in _chosen(working, "main_line", limit=2)]
    saved = repository.save(profile.model_copy(update={
        "world_profile": world_profile,
        "content_pack_id": resolved_pack_id,
        "story_rules": [f"{item.label}：{item.summary}" for item in rules],
        "cast": cast,
        "factions": factions,
        "future_plan": {"plan_id": f"{novel_id}_plan", "stages": stages, "revision": 0},
    }))
    return {"profile": saved, "pack": pack, "pack_path": path, "pack_id": resolved_pack_id,
            "selected": dict(working.selected), "notes": selection_notes}


def load_setting_seed(project_root: Path, novel_id: str) -> SettingSeed | None:
    from .profile import NovelProfileRepository

    profile = NovelProfileRepository(project_root).ensure(novel_id)
    payload = profile.world_profile.get(SETTINGS_KEY)
    if not isinstance(payload, Mapping):
        return None
    seed_payload = payload.get("seed")
    if not isinstance(seed_payload, Mapping):
        return None
    seed = SettingSeed.model_validate(dict(seed_payload))
    return seed.model_copy(update={"novel_id": seed.novel_id or novel_id})


def saved_pack_id(project_root: Path, novel_id: str) -> str:
    from .profile import NovelProfileRepository

    profile = NovelProfileRepository(project_root).ensure(novel_id)
    payload = profile.world_profile.get(SETTINGS_KEY)
    if isinstance(payload, Mapping):
        return str(payload.get("pack_id", "") or "")
    return profile.content_pack_id or ""
