"""W3：剧情 → 高质量四级大纲。

把一条已经试演过的路线（`StoryState` 事实 + `FuturePlan` 规划）转成**既有**四级大纲：

    BOOK（全书主线）→ VOLUME（卷纲）→ ARC（篇章纲）→ CHAPTER（详细章纲）

复用 `OutlinePackage` / `OutlineItem` 模型与 `StoryOutlineRepository` 存储、版本、导出；
本模块只解决“怎么把剧情变成能直接写的章纲”，不新增第二套大纲模型。

质量原则：

- 只有 happened（已发生事实）才能写成事实；planned / suggested 必须显式标注，不得混入事实；
- 每一章都必须回答：本章目标 / 核心冲突 / 转折 / 信息释放 / 关系与成长变化 / 代价 / 结尾钩子 /
  来源事实 / 不得违反的约束；
- 结构（卷 / 篇章 / 章节数）由作者参数与路线长度共同决定，不写死模板；冲突与钩子的素材来自内容包
  与 StoryState（行动名、事件、支线、伏笔、角色目标），不是通用套话；
- AI 只是可选润色：只允许改写既有章节的标题 / 摘要 / 钩子，越界 id 直接丢弃。
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pydantic import Field

from novelforge.models import StrictModel
from novelforge.story_builder.models import (
    OutlineItem,
    OutlineLevel,
    OutlinePackage,
    OutlineStatus,
)
from novelforge.story_builder.outlines import StoryOutlineError, StoryOutlineRepository

from .content import ContentPack
from .context import DEFAULT_BRANCH, NovelContextError, resolve_novel_context
from .linkage import FuturePlan, StageGoal, plot_tracks
from .narrative import RoutePackage, RouteRecord, build_route, verify_outline_sources
from .profile import NovelProfileRepository
from .state import StoryState
from .storage import StoryStateRepository, StoryStateStorageError

DEFAULT_STRUCTURE = {"volumes": 3, "arcs_per_volume": 2, "chapters_per_arc": 5}
MAX_CHAPTERS = 180
FACT_KINDS = ("happened", "planned", "suggested")

# ------------------------------------------------------------------ 标题质量
# 章节标题必须是**内容**（本章事件 / 冲突 / 人物目标 / 变化 / 结果），不能是
# 引擎的字段标签。这些词是 UI 文案或规划字段名，出现在标题里就说明标题没有生成出来。
FIELD_LABEL_BLACKLIST: frozenset[str] = frozenset({
    "阶段目标", "长期方向", "阶段", "短期目标", "主线", "推进主线", "规划",
    "阶段目标（规划）", "长期方向（规划）",
})

# 规划章节按位置承担的叙事功能（beat sheet）。同一段规划里的章节从不同角度进入，
# 而不是复制同一个阶段名——它不是随机词，而是这一章在这一段里真正要做的事。
NARRATIVE_BEATS: tuple[str, ...] = ("试探", "布局", "交涉", "受阻", "代价", "转机",
                                    "决断", "收束")


def _clean_title_text(text: Any, *, limit: int = 36) -> str:
    """标题正文清洗：去掉字段标签残留、模板后缀与首尾标点，不改变语义。

    超长时优先在标点处收尾，避免把一个词从中间切断（NF-006 的同类问题）。
    """

    out = " ".join(str(text or "").split())
    for noise in ("（规划）", "（设定草稿）", "（planned，尚未发生）"):
        out = out.replace(noise, "")
    out = out.strip(" 　·；;，,。:：")
    if len(out) > limit:
        window = out[:limit]
        cut = max((window.rfind(sep) for sep in ("，", "、", "；", "：", " ")), default=-1)
        out = window[:cut] if cut >= max(8, limit // 3) else window
        out = out.strip(" 　·；;，,。:：")
    return out[:limit].strip()


def _is_field_label(text: str) -> bool:
    return not text or text in FIELD_LABEL_BLACKLIST


def _title_body(title: str) -> str:
    """从「第N章：正文」里取出正文（标题正文才是作者读到的内容）。"""

    text = str(title or "")
    return text.split("：", 1)[1] if "：" in text else text


class ChapterTitleLedger:
    """章级标题分配器：同一本书里不允许有两章使用同一个标题正文。

    同一行动 / 同一阶段会重复出现，因此标题正文必须靠**本章自己的内容**
    区分（代价、转折、信息释放、伏笔、人物目标…）。只有所有真实素材都用尽时，
    才使用「第 N 次」这种纯序数补充——它仍然表达了「同一件事又发生了一次」。
    """

    def __init__(self) -> None:
        self.used: set[str] = set()
        self.counts: dict[str, int] = {}

    def allocate(self, *candidates: Any, index: int = 0) -> str:
        pool: list[str] = []
        for raw in candidates:
            text = _clean_title_text(raw)
            if text and not _is_field_label(text) and text not in pool:
                pool.append(text)
        for candidate in pool:
            if candidate not in self.used:
                self.used.add(candidate)
                self.counts[candidate] = 1
                return candidate
        base = pool[0] if pool else f"第 {index} 章的推进"
        self.counts[base] = self.counts.get(base, 1) + 1
        repeated = f"{base}（第 {self.counts[base]} 次）"
        self.used.add(repeated)
        return repeated


class OutlineForgeError(ValueError):
    def __init__(self, code: str, message: str, *, novel_id: str = "") -> None:
        self.code = code
        self.message = message
        self.novel_id = novel_id
        super().__init__(message)

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message, "novel_id": self.novel_id}


class StructureSpec(StrictModel):
    """整本书的规模：卷数 / 每卷篇章数 / 每篇章章节数。"""

    volumes: int = Field(default=DEFAULT_STRUCTURE["volumes"], ge=1, le=12)
    arcs_per_volume: int = Field(default=DEFAULT_STRUCTURE["arcs_per_volume"], ge=1, le=6)
    chapters_per_arc: int = Field(default=DEFAULT_STRUCTURE["chapters_per_arc"], ge=1, le=20)

    @property
    def total_chapters(self) -> int:
        return self.volumes * self.arcs_per_volume * self.chapters_per_arc

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class ChapterBlueprint(StrictModel):
    """一章的写作蓝图：字段与既有 OutlineItem 对齐，额外标注来源种类。"""

    id: str
    index: int = 0
    volume_index: int = 1
    arc_index: int = 1
    kind: str = "planned"
    title: str = ""
    summary: str = ""
    goal: str = ""
    conflict: str = ""
    turn: str = ""
    hook: str = ""
    start_state: str = ""
    end_state: str = ""
    pov: str = ""
    time: str = ""
    location: str = ""
    participants: list[str] = Field(default_factory=list)
    information_changes: list[str] = Field(default_factory=list)
    relationship_changes: list[str] = Field(default_factory=list)
    progression_changes: list[str] = Field(default_factory=list)
    plot_changes: list[str] = Field(default_factory=list)
    foreshadow_moves: list[str] = Field(default_factory=list)
    costs: list[str] = Field(default_factory=list)
    pacing: str = "steady"
    source_ids: list[str] = Field(default_factory=list)
    must_keep: list[str] = Field(default_factory=list)
    must_avoid: list[str] = Field(default_factory=list)


class VolumeBlueprint(StrictModel):
    id: str
    index: int = 1
    title: str = ""
    goal: str = ""
    conflict: str = ""
    turn: str = ""
    arc_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)


class ArcBlueprint(StrictModel):
    id: str
    index: int = 1
    volume_id: str = ""
    title: str = ""
    question: str = ""
    closes_with: str = ""
    chapter_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)


class ForgePlan(StrictModel):
    """一次锻造的完整计划（尚未落盘）。"""

    novel_id: str = ""
    branch_id: str = DEFAULT_BRANCH
    runtime_id: str = ""
    runtime_version: int = 1
    revision: int = 0
    tick: int = 0
    structure: StructureSpec = Field(default_factory=StructureSpec)
    book_title: str = ""
    book_goal: str = ""
    book_conflict: str = ""
    book_turn: str = ""
    book_end_state: str = ""
    volumes: list[VolumeBlueprint] = Field(default_factory=list)
    arcs: list[ArcBlueprint] = Field(default_factory=list)
    chapters: list[ChapterBlueprint] = Field(default_factory=list)
    unresolved: list[dict[str, str]] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    source: str = "rule"

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class QualityFinding(StrictModel):
    code: str
    severity: str = "warning"
    message: str = ""
    target: str = ""


class OutlineQualityReport(StrictModel):
    novel_id: str = ""
    ok: bool = True
    counts: dict[str, int] = Field(default_factory=dict)
    findings: list[QualityFinding] = Field(default_factory=list)
    pacing: list[str] = Field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def state_digest(state: StoryState) -> str:
    """运行槽路线的摘要：用于判断大纲是否还符合同一份事实。"""

    payload = {
        "novel_id": state.novel_id,
        "tick": state.timeline.tick,
        "effect_log": [item.order for item in state.effect_log],
        "knowledge": sorted(item.id for item in state.knowledge),
        "plots": {key: value.get("status", "") for key, value in sorted(state.plots.items())},
        "flags": {key: value for key, value in sorted(state.flags.items()) if key != "foreshadows"},
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                     default=str).encode("utf-8")).hexdigest()


def _slug(text: str, *, prefix: str) -> str:
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:6]
    ascii_part = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    stem = f"{prefix}_{ascii_part}" if ascii_part else prefix
    return f"{stem[:40]}_{digest}"


def _chain_stem(novel_id: str, branch_id: str) -> str:
    suffix = branch_id if branch_id == DEFAULT_BRANCH else branch_id.replace("branch_", "")[-8:]
    return _slug(f"{novel_id}_{suffix}", prefix="forge")


def _package_id(label: str, novel_id: str, branch_id: str) -> str:
    """四级大纲包的统一命名：`ol_<小说+分支摘要>_<层级/序号>`。"""

    return f"ol_{_chain_stem(novel_id, branch_id)}_{label}"[:96]


def _revision(state: StoryState) -> int:
    return len([item for item in state.effect_log if item.op in ("choice", "runtime_action")])


def _action_labels(pack: ContentPack) -> dict[str, str]:
    return {item.id: (item.name or item.id) for item in pack.actions}


def _event_titles(pack: ContentPack) -> dict[str, str]:
    return {item.event_id: (item.title or item.event_id) for item in pack.events}


def _records_by_source(state: StoryState) -> dict[str, list[Any]]:
    grouped: dict[str, list[Any]] = {}
    for record in state.effect_log:
        source = record.source or ""
        grouped.setdefault(source, []).append(record)
    return grouped


def _fact_locations(state: StoryState) -> dict[int, str]:
    """按 effect_log 顺序还原“每个已发生记录发生时主角在哪里”。"""

    current = state.location.current if state.location.current else ""
    rows: dict[int, str] = {}
    for record in state.effect_log:
        if record.op == "change_location":
            current = str(record.value or (record.data or {}).get("key") or current)
        elif record.op in ("choice", "runtime_action", "world_action", "fire_event",
                           "world_event"):
            rows[record.order] = current
    return rows


def _order_of(record: RouteRecord) -> int:
    digits = record.id.rsplit("_", 1)[-1]
    return int(digits) if digits.isdigit() else 0


# 引擎 id 前缀：这些字符串是机器标识，不是作者文本（NF-004）。
ENGINE_ID_PREFIXES: tuple[str, ...] = ("act_", "ev_", "route_", "plot_", "world_",
                                       "planned_", "suggested_", "npc_", "faction_",
                                       "location_", "runtime:")


def _author_result(record: RouteRecord, action_labels: Mapping[str, str],
                   event_titles: Mapping[str, str]) -> str:
    """route 记录的「结果」→ 作者语言。

    运行态记录的 `result` 往往是行动 id（`act_ask`）或来源字符串
    （`runtime:act_ask`）：它们是引擎标识，不能出现在作者可见内容里。
    能翻成真实行动 / 事件名的就翻，翻不出来就返回空串（调用方用行动名兜底），
    绝不把 id 原样写进章节摘要。
    """

    raw = str(record.result or "").strip()
    if not raw:
        return ""
    if raw in action_labels:
        return action_labels[raw]
    if raw in event_titles:
        return event_titles[raw]
    tail = raw.split(":")[-1]
    if tail in action_labels:
        return action_labels[tail]
    if tail in event_titles:
        return event_titles[tail]
    if raw.startswith(ENGINE_ID_PREFIXES) or tail.startswith(ENGINE_ID_PREFIXES):
        return ""
    return raw


PLOT_STATUS_LABEL: dict[str, str] = {
    "inactive": "还没有启动",
    "active": "正在推进",
    "paused": "暂时搁置",
    "completed": "已经收束",
    "failed": "已经失败",
    "abandoned": "被放弃",
    "planned": "还在计划里",
    "planted": "已经埋下",
    "revealed": "已经揭开",
    "resolved": "已经回收",
}


def naming_table(state: StoryState, pack: Any) -> dict[str, str]:
    """叙事元素的作者语言名称表：角色 / 地点 / 支线 / 伏笔 / 行动 / 事件。

    只收录真实存在的名称（StoryState 与内容包），缺失由调用方按类型兜底。
    """

    from novelforge.author_language import content_labels

    labels: dict[str, str] = {}
    for character_id, character in (state.characters or {}).items():
        name = str(getattr(character, "name", "") or "")
        if name:
            labels[str(character_id)] = name
    def field_of(row: Any, *names: str) -> str:
        for name in names:
            value = (row.get(name) if isinstance(row, Mapping)
                     else getattr(row, name, None))
            text = str(value or "").strip()
            if text:
                return text
        return ""

    known = getattr(getattr(state, "location", None), "known", {}) or {}
    if isinstance(known, Mapping):
        for location_id, payload in known.items():
            name = field_of(payload, "name", "label")
            if name:
                labels[str(location_id)] = name
    for plot_id, payload in (state.plots or {}).items():
        title = field_of(payload, "title", "name")
        if title:
            labels[str(plot_id)] = title
    registry = (state.flags or {}).get("foreshadows", {}) or {}
    if isinstance(registry, Mapping):
        for foreshadow_id, payload in registry.items():
            title = field_of(payload, "title", "name")
            if title:
                labels[str(foreshadow_id)] = title
    labels.update(content_labels(pack))
    return labels


def _effect_rows(state: StoryState, source_hints: Sequence[str],
                 labels: Mapping[str, str] | None = None) -> dict[str, list[str]]:
    """把某个行动 / 事件产生的效果整理成章纲用的字段（多条来源合并，去重保序）。

    NF-004：效果文本直接面向作者与写作环节，因此这里在**生成时**就把引擎 id
    翻成作者语言（角色 / 地点 / 支线 / 伏笔 / 资源 / 状态），翻不出来时给可读兜底，
    绝不把 `favors` / `act_wait` / `npc_1` 这类内部标识写进章节内容。
    """

    from novelforge.author_language import RESOURCE_LABEL, TRACK_LABEL, resource_label

    table = {str(key): str(value) for key, value in dict(labels or {}).items() if value}

    def name(value: Any, *, kind: str = "") -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        if raw in table:
            return table[raw]
        if kind == "resource":
            return resource_label(raw)
        if kind == "track":
            return TRACK_LABEL.get(raw) or ("" if raw.isascii() else raw)
        if kind == "knowledge":
            from novelforge.author_language import KNOWLEDGE_LABEL

            return KNOWLEDGE_LABEL.get(raw, "")
        if raw.startswith(ENGINE_ID_PREFIXES) or raw in RESOURCE_LABEL:
            return ""
        return raw

    rows = {"information": [], "relationship": [], "progression": [], "plot": [],
            "foreshadow": [], "costs": []}
    hints = [hint for hint in source_hints if hint]
    for record in state.effect_log:
        source = record.source or ""
        if hints and not any(hint in source for hint in hints):
            continue
        if record.op == "add_knowledge":
            who = name(record.entity) or "主角"
            rows["information"].append(
                f"{who} 获知「{name(record.target, kind='knowledge') or '一条新线索'}」")
        elif record.op == "change_relationship":
            value = record.value or 0
            direction = "上升" if float(value) >= 0 else "下降"
            dimension = TRACK_LABEL.get(str((record.data or {}).get("key", "") or ""), "")
            rows["relationship"].append(
                f"{name(record.entity) or '主角'} → {name(record.target) or '对方'}"
                f"{f' 的 {dimension}' if dimension else ''} {direction} {abs(float(value)):g}")
        elif record.op in ("grant_ability", "acquire_progression", "add_identity"):
            rows["progression"].append(
                f"{name(record.entity) or '主角'} 获得「{name(record.target) or '新的能力'}」")
        elif record.op == "update_plot":
            status = str((record.data or {}).get("status", "") or "")
            label = PLOT_STATUS_LABEL.get(status, "有了新进展")
            rows["plot"].append(f"支线「{name(record.target) or '主线'}」{label}")
        elif record.op == "update_foreshadow":
            status = str((record.data or {}).get("status", "") or "")
            label = PLOT_STATUS_LABEL.get(status, "有了新进展")
            rows["foreshadow"].append(f"伏笔「{name(record.target) or '一条线索'}」{label}")
        elif record.op in ("remove_resource", "set_resource"):
            rows["costs"].append(
                f"{name(record.target, kind='resource')} 消耗 {record.value}")
        elif record.op == "create_promise":
            rows["costs"].append(f"新增承诺「{name(record.target) or '一个新的承诺'}」")
    return {key: list(dict.fromkeys(values)) for key, values in rows.items()}


def _character_rows(state: StoryState) -> dict[str, list[str]]:
    rows: dict[str, list[str]] = {}
    for character_id, character in state.characters.items():
        goals = character.data.get("goals") or []
        titles = [str(item.get("title", "")) for item in goals if isinstance(item, Mapping)]
        rows[character_id] = [item for item in titles if item]
    return rows


def _open_foreshadows(state: StoryState) -> list[dict[str, str]]:
    registry = state.flags.get("foreshadows", {})
    rows: list[dict[str, str]] = []
    if isinstance(registry, Mapping):
        for foreshadow_id, payload in registry.items():
            status = str((payload or {}).get("status", "planned"))
            if status in ("resolved", "abandoned"):
                continue
            rows.append({"id": str(foreshadow_id), "status": status,
                         "title": str((payload or {}).get("title", "") or "")})
    return rows


def _foreshadow_titles(pack: Any) -> dict[str, str]:
    """伏笔 id → 作者在内容包里写下的伏笔名（没有名字时保持缺失，不编造）。"""

    rows: dict[str, str] = {}
    for item in list(getattr(pack, "foreshadows", None) or [])[:200]:
        item_id = str(getattr(item, "id", "") or "")
        title = str(getattr(item, "title", "") or "")
        if item_id and title:
            rows[item_id] = title
    return rows


def _structure_for(state: StoryState, plan: FuturePlan, spec: StructureSpec | None) -> StructureSpec:
    """结构由作者参数与路线长度共同决定：路线越长，默认章节越多（有上限）。"""

    if spec is not None:
        return spec
    facts = _revision(state)
    stages = len(plan.stages) or 1
    volumes = min(12, max(1, stages if stages > 1 else max(1, (facts + 5) // 6)))
    arcs_per_volume = 2
    needed = max(1, (facts + volumes * arcs_per_volume - 1) // (volumes * arcs_per_volume))
    chapters_per_arc = min(20, max(5, needed + 1))
    if volumes * arcs_per_volume * chapters_per_arc > MAX_CHAPTERS:
        chapters_per_arc = max(1, MAX_CHAPTERS // (volumes * arcs_per_volume))
    return StructureSpec(volumes=volumes, arcs_per_volume=arcs_per_volume,
                         chapters_per_arc=chapters_per_arc)


def build_forge_plan(project_root: Path, novel_id: str, *, branch_id: str = DEFAULT_BRANCH,
                     structure: StructureSpec | Mapping[str, Any] | None = None,
                     provider: Any | None = None) -> ForgePlan:
    """把一条路线的 StoryState 变成四级大纲计划（不落盘）。"""

    try:
        context = resolve_novel_context(project_root, novel_id)
    except NovelContextError as exc:
        raise OutlineForgeError(exc.code, exc.message, novel_id=novel_id) from exc
    if context.pack is None:
        raise OutlineForgeError("CONTENT_PACK_REQUIRED", "当前小说没有可用的内容包",
                                novel_id=novel_id)
    states = StoryStateRepository(project_root)
    try:
        state = states.load(context.runtime_id, context.runtime_version, branch_id)
    except StoryStateStorageError as exc:
        raise OutlineForgeError("ROUTE_NOT_STARTED",
                                f"分支 {branch_id} 还没有可用的已发生路线，请先试演或开始推演",
                                novel_id=novel_id) from exc
    profile = NovelProfileRepository(project_root).ensure(novel_id)
    plan = _future_plan_from_profile(profile)
    spec = structure if isinstance(structure, StructureSpec) else (
        StructureSpec.model_validate(dict(structure)) if structure else None)
    resolved = _structure_for(state, plan, spec)
    route = build_route(state, plan=plan)
    forge = _compose(project_root, novel_id, branch_id, context, state, plan, route, resolved,
                     profile)
    if provider is not None:
        forge = OutlineProvider(provider).enrich(forge)
    return forge


def _future_plan_from_profile(profile) -> FuturePlan:
    payload = profile.future_plan
    if isinstance(payload, Mapping) and payload:
        try:
            return FuturePlan.model_validate(dict(payload))
        except Exception:  # noqa: BLE001 - 作者计划格式错误时退回空计划
            return FuturePlan()
    return FuturePlan()


def _compose(project_root: Path, novel_id: str, branch_id: str, context, state: StoryState,
             plan: FuturePlan, route: RoutePackage, spec: StructureSpec, profile) -> ForgePlan:
    pack: ContentPack = context.pack
    action_labels = _action_labels(pack)
    event_titles = _event_titles(pack)
    tracks = plot_tracks(state)
    active_plots = [item for item in tracks if item.status == "active"]
    character_goals = _character_rows(state)
    foreshadows = _open_foreshadows(state)
    protagonist = next((item for item in state.characters.values() if item.kind == "player"),
                       None)
    protagonist_id = protagonist.id if protagonist else "protagonist"
    protagonist_goal = (character_goals.get(protagonist_id) or [""])[0]
    premise = str((protagonist.data or {}).get("premise", "") if protagonist is not None else "")

    total = spec.total_chapters
    facts = list(route.happened)
    premise_short = premise[:24]
    naming = naming_table(state, pack)
    # 一本书一个标题分配器：happened 与 planned 章节共用，保证全书标题正文唯一。
    ledger = ChapterTitleLedger()
    fact_chapters = _fact_chapters(novel_id, branch_id, state, facts, action_labels,
                                   event_titles, total, premise_short, titles=ledger,
                                   stage_purpose=protagonist_goal, labels=naming,
                                   protagonist_id=protagonist_id)
    planned_stages = list(plan.stages)
    remaining = total - len(fact_chapters)
    planned_chapters = _planned_chapters(novel_id, branch_id, state, plan, fact_chapters,
                                         remaining, active_plots, foreshadows, character_goals,
                                         action_labels, premise_short, titles=ledger,
                                         foreshadow_titles=_foreshadow_titles(pack))
    chapters = (fact_chapters + planned_chapters)[:total]
    # 卷 / 篇章分组：先按段均匀切，再把计划阶段的目标映射到卷。
    volumes: list[VolumeBlueprint] = []
    arcs: list[ArcBlueprint] = []
    per_arc = spec.chapters_per_arc
    per_volume = spec.arcs_per_volume * per_arc
    for volume_index in range(spec.volumes):
        chunk = chapters[volume_index * per_volume:(volume_index + 1) * per_volume]
        volume_id = _package_id(f"vol{volume_index + 1:02d}", novel_id, branch_id)
        stage = planned_stages[volume_index] if volume_index < len(planned_stages) else None
        volume_chapters: list[str] = []
        arc_ids: list[str] = []
        for arc_offset in range(spec.arcs_per_volume):
            start = arc_offset * per_arc
            arc_chunk = chunk[start:start + per_arc]
            if not arc_chunk:
                continue
            arc_id = _package_id(f"arc{volume_index + 1:02d}{arc_offset + 1:02d}", novel_id,
                                 branch_id)
            arc_ids.append(arc_id)
            for chapter in arc_chunk:
                chapter.arc_index = volume_index * spec.arcs_per_volume + arc_offset + 1
                volume_chapters.append(chapter.id)
            first, last = arc_chunk[0], arc_chunk[-1]
            arc_label = _title_body(first.title) or first.goal or first.title
            arcs.append(ArcBlueprint(
                id=arc_id, index=volume_index * spec.arcs_per_volume + arc_offset + 1,
                volume_id=volume_id,
                title=f"第{volume_index + 1}卷 · 篇章{arc_offset + 1}：{arc_label}",
                question=first.conflict or first.goal or "这一篇要解决什么问题",
                closes_with=last.end_state or last.summary,
                chapter_ids=[item.id for item in arc_chunk],
                source_ids=[sid for item in arc_chunk for sid in item.source_ids][:8]))
        volume_label = _clean_title_text(stage.title) if stage else ""
        if _is_field_label(volume_label):
            volume_label = _title_body(chunk[0].title) if chunk else novel_id
        volumes.append(VolumeBlueprint(
            id=volume_id, index=volume_index + 1,
            title=f"第{volume_index + 1}卷：{volume_label or novel_id}",
            goal=(stage.goal if stage else (chunk[0].goal if chunk else "")),
            conflict=(chunk[0].conflict if chunk else ""),
            turn=(chunk[-1].turn if chunk else ""),
            arc_ids=arc_ids, source_ids=[sid for item in chunk for sid in item.source_ids][:10]))
        for chapter in chunk:
            chapter.volume_index = volume_index + 1
    unresolved = [{"id": item.id, "kind": item.kind, "source": item.source,
                   "result": item.result}
                  for item in list(route.planned) + list(route.suggested)]
    notes: list[str] = []
    if not facts:
        notes.append("ROUTE_EMPTY：还没有已发生事实，当前大纲全部是 planned 章节。")
    if active_plots:
        notes.append("ACTIVE_PLOTS：" + "、".join(item.title for item in active_plots[:6]))
    if foreshadows:
        notes.append("OPEN_FORESHADOWS：" + "、".join(item["id"] for item in foreshadows[:6]))
    book_goal = protagonist_goal or (plan.stages[0].goal if plan.stages else
                                    (chapters[0].goal if chapters else ""))
    if premise and premise not in book_goal:
        # 主角目标 + 这本小说自己的前提，避免不同小说得到同一句全书目标。
        book_goal = f"{book_goal}（前提：{premise}）" if book_goal else premise
    return ForgePlan(
        novel_id=novel_id, branch_id=branch_id, runtime_id=context.runtime_id,
        runtime_version=context.runtime_version, revision=_revision(state),
        tick=state.timeline.tick, structure=spec,
        book_title=profile.title or novel_id,
        book_goal=book_goal,
        book_conflict=(active_plots[0].title if active_plots else
                       (chapters[0].conflict if chapters else "")),
        book_turn=next((chapter.turn for chapter in chapters if chapter.turn), ""),
        book_end_state=(plan.stages[-1].goal if plan.stages else
                        (chapters[-1].end_state if chapters else "")),
        volumes=volumes, arcs=arcs, chapters=chapters, unresolved=unresolved, notes=notes,
        source="rule")


def _fact_chapters(novel_id: str, branch_id: str, state: StoryState, facts: list[RouteRecord],
                   action_labels: dict[str, str], event_titles: dict[str, str],
                   total: int, premise: str = "",
                   titles: ChapterTitleLedger | None = None,
                   stage_purpose: str = "",
                   labels: Mapping[str, str] | None = None,
                   protagonist_id: str = "") -> list[ChapterBlueprint]:
    """已发生事实 → 章纲；记录数超过容量时按顺序合并，不会丢掉任何来源。"""

    if not facts:
        return []
    ledger = titles if titles is not None else ChapterTitleLedger()
    purpose = _clean_title_text(stage_purpose, limit=48)
    table = dict(labels or {})

    def name(value: Any) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        if raw in table:
            return table[raw]
        return "" if raw.startswith(ENGINE_ID_PREFIXES) else raw
    room = max(1, min(len(facts), total - max(1, total // 3)))
    group_size = max(1, (len(facts) + room - 1) // room)
    locations = _fact_locations(state)
    chapters: list[ChapterBlueprint] = []
    for index in range(0, len(facts), group_size):
        group = facts[index:index + group_size]
        head = group[0]
        tail = group[-1]
        # 标题优先用主角自己的选择（action），其次事件，最后世界自主行动。
        focus = next((item for item in group if item.origin == "action"),
                     next((item for item in group if item.origin == "event"), head))
        hints = [str(item.data.get("target", "") or "") for item in group]
        rows = _effect_rows(state, hints, labels=table)
        focus_id = str(focus.data.get("target", "") or "")
        label = (action_labels.get(focus_id) or event_titles.get(focus_id) or focus.result
                 or head.result)
        result_text = (_author_result(focus, action_labels, event_titles)
                       or _author_result(head, action_labels, event_titles) or label)
        if label and label.startswith(ENGINE_ID_PREFIXES):
            label = result_text
        number = len(chapters) + 1
        # 标题正文必须区别于其它章节：优先行动 / 事件名，其次本章真实的变化与代价。
        label_text = _clean_title_text(label)
        body = ledger.allocate(
            label_text,
            f"{label_text} · {rows['costs'][0]}" if rows["costs"] and label_text else "",
            f"{label_text} · {result_text}" if result_text and label_text
            and result_text != label_text else "",
            result_text if result_text != label_text else "",
            _clean_title_text(result_text),
            f"{label_text} · {rows['information'][0]}" if rows["information"]
            and label_text else "",
            index=number)
        title = f"第{number}章：{body}"
        conflicts = [f"立场摩擦：{label}"] if label else []
        if rows["costs"]:
            conflicts.append("代价压力：" + "；".join(rows["costs"][:2]))
        tail_result = _author_result(tail, action_labels, event_titles)
        turn = rows["plot"][0] if rows["plot"] else (
            tail_result if tail_result and tail_result != result_text else "")
        # 摘要必须让作者看出「这一章在这本书里的作用」：己方行动结果 + 这本书自己的
        # 阶段目的（来自本作的设定，不是通用模板句）。
        summary = f"已发生：{result_text}" if result_text else f"已发生：{label}"
        if purpose:
            summary = f"{summary}；这一步服务于「{purpose}」"
        # participants 必须是真实角色（不是行动 id）：只保留确实存在的角色 id，
        # 主角行动的章节回落到主角本人（UI / 导出再翻译成角色名）。
        candidate_ids = [entry for row in group for entry in row.participants]
        actors = [entry for entry in dict.fromkeys(candidate_ids)
                  if entry and entry in state.characters]
        if not actors and protagonist_id:
            actors = [protagonist_id]
        location_id = str(head.location or focus.location
                          or locations.get(_order_of(focus), "")
                          or locations.get(_order_of(head), ""))
        chapters.append(ChapterBlueprint(
            id=_package_id(f"ch{number:03d}", novel_id, branch_id),
            index=number, kind="happened",
            title=title,
            summary=summary,
            goal=f"完成 {label}",
            conflict="；".join(conflicts) or "当前局面与主角目标存在直接冲突",
            turn=turn, hook="",
            start_state=(f"承接第 {number - 1} 章的结尾局面" if number > 1
                         else "从已经落盘的起点局面开始"),
            end_state=result_text or label,
            time=f"第 {head.tick} 回合",
            location=name(location_id),
            participants=actors,
            information_changes=rows["information"],
            relationship_changes=rows["relationship"],
            progression_changes=rows["progression"],
            plot_changes=rows["plot"], foreshadow_moves=rows["foreshadow"], costs=rows["costs"],
            pacing="rise",
            source_ids=[item.id for item in group],
            # must_keep 是作者可见的约束说明：写清了来源是什么，但不含引擎 id
            # （机器可追溯的 id 在 source_ids 里，不在作者文本里）。
            must_keep=[f"来源：{label or '已发生的行动'}"
                       f"（已经发生 · 第 {head.tick} 回合）",
                       "这一章只能写已经发生的事实"],
            must_avoid=["不得把 planned / suggested 写成已发生事实"]))
    for position, chapter in enumerate(chapters):
        nxt = chapters[position + 1] if position + 1 < len(chapters) else None
        chapter.hook = (f"下一章：{nxt.goal}" if nxt else
                        (f"下一步：{chapter.turn}" if chapter.turn else "留一个未解决的问题"))
    return chapters


def _planned_chapters(novel_id: str, branch_id: str, state: StoryState, plan: FuturePlan,
                      fact_chapters: list[ChapterBlueprint], remaining: int,
                      active_plots: Sequence[Any],
                      foreshadows: Sequence[Mapping[str, str]],
                      character_goals: Mapping[str, list[str]],
                      action_labels: Mapping[str, str], premise: str = "",
                      titles: ChapterTitleLedger | None = None,
                      foreshadow_titles: Mapping[str, str] | None = None
                      ) -> list[ChapterBlueprint]:
    """未来规划 → planned 章节：只写目标与预期冲突，不伪造事实。

    NF-003：规划章节的标题来自**本章自己的内容**（要推进的支线 / 要埋设的伏笔 /
    人物目标 / 阶段目标）+ 它在这一段里承担的叙事功能，而不是把 `future_plan` 的
    阶段字段名复制 20 多次。
    """

    if remaining <= 0:
        return []
    ledger = titles if titles is not None else ChapterTitleLedger()
    foreshadow_names = dict(foreshadow_titles or {})
    stages: list[StageGoal] = list(plan.stages)
    if not stages:
        stages = [StageGoal(id="stage_default", title="推进主线",
                            goal=(fact_chapters[-1].turn if fact_chapters else "推动主线前进"))]
    chapters: list[ChapterBlueprint] = []
    for offset in range(remaining):
        stage = stages[offset % len(stages)]
        plot = active_plots[offset % len(active_plots)] if active_plots else None
        foreshadow = foreshadows[offset % len(foreshadows)] if foreshadows else None
        goals = [goal for goals_list in character_goals.values() for goal in goals_list]
        conflict = (f"支线「{plot.title}」的推进与主角当前目标冲突" if plot
                    else "新的阻力让主角必须在两个目标之间取舍")
        number = len(fact_chapters) + offset + 1
        # 章节真正的内容素材（真实存在才用；字段标签一律不参与标题）。
        foreshadow_name = ""
        if foreshadow:
            foreshadow_name = (foreshadow_names.get(str(foreshadow["id"]))
                               or str(foreshadow.get("title") or ""))
        stage_summary = _clean_title_text(stage.goal or "")
        beat = NARRATIVE_BEATS[offset % len(NARRATIVE_BEATS)]
        contents = [text for text in (
            _clean_title_text(getattr(plot, "title", "") if plot else ""),
            _clean_title_text(foreshadow_name),
            _clean_title_text(goals[0] if goals else ""),
            _clean_title_text(stage.title),
            stage_summary,
        ) if text and not _is_field_label(text)]
        primary = contents[0] if contents else (stage_summary or "故事向前推进")
        body = ledger.allocate(
            f"{beat}：{primary}",
            *[f"{beat}：{text}" for text in contents[1:]],
            *[f"{other_beat}：{primary}" for other_beat in NARRATIVE_BEATS
              if other_beat != beat],
            index=number)
        information = ([f"安排释放：「{foreshadow_name or '这一条伏笔'}」指向的线索"]
                       if foreshadow is not None else [])
        stage_label = _clean_title_text(stage.title)
        if _is_field_label(stage_label):
            stage_label = primary
        chapters.append(ChapterBlueprint(
            id=_package_id(f"ch{number:03d}", novel_id, branch_id),
            index=number, kind="planned",
            title=f"第{number}章：{body}",
            summary=(f"计划：{beat}「{primary}」"
                     + (f"；阶段目标：{stage.goal}" if stage.goal and stage.goal != primary
                        else "")),
            goal=stage.goal or primary,
            conflict=conflict,
            turn=f"这次{beat}改变了「{primary}」的条件，主角必须重新选择",
            hook=f"这一段要在这里收束：{stage.goal or primary}",
            start_state="（未来章节：起点状态由实际推演决定）",
            end_state=stage.goal,
            participants=[next(iter(state.characters), "protagonist")],
            information_changes=information,
            progression_changes=[goal for goal in goals[:1]],
            plot_changes=[f"支线「{plot.title}」推进" ] if plot else [],
            foreshadow_moves=[f"埋设 / 强化「{foreshadow_name}」"] if foreshadow_name else [],
            pacing="wave" if offset % 3 == 2 else "steady",
            source_ids=[f"planned_{stage.id}"],
            must_keep=[f"来源：作者设定的未来规划「{stage_label}」（还没发生）",
                       f"阶段目标：{stage.goal}"],
            must_avoid=["不得把规划写成已经发生的事实",
                        "不得占用未确认的信息与关系"]))
    # 钩子用**下一章真正的内容**，避免所有规划章节共用同一句模板。
    for position, chapter in enumerate(chapters):
        nxt = chapters[position + 1] if position + 1 < len(chapters) else None
        chapter.hook = (f"下一章：{_title_body(nxt.title)}" if nxt
                        else "这一段在这里收束，留一个还没解决的问题")
    return chapters


class OutlineProvider:
    """可选 AI 润色：只允许改写既有章节的标题 / 摘要 / 钩子。"""

    def __init__(self, provider: Any | None) -> None:
        self.provider = provider if provider is not None else _default_provider()


def _default_provider() -> Any | None:
    """V4-04 §14：默认 provider 经 `novelforge.ai` 的 Gateway 桥（函数内惰性 import）。"""

    from novelforge.ai import default_structured_provider

    return default_structured_provider()

    def enrich(self, plan: ForgePlan) -> ForgePlan:
        if self.provider is None:
            return plan
        allowed = {item.id for item in plan.chapters}
        try:
            _, draft = self.provider.generate_structured(
                chapter_id="outline_forge", stage="outline_forge_polish", skill_name=None,
                prompt=self._prompt(plan), context={"novel_id": plan.novel_id,
                                                    "branch_id": plan.branch_id},
                output_model=None, workspace=None)
        except Exception as exc:  # noqa: BLE001 - AI 失败保留规则生成的章纲
            return plan.model_copy(update={"notes": list(plan.notes) + [f"AI_ERROR:{exc}"]})
        parsed = draft if isinstance(draft, Mapping) else getattr(draft, "__dict__", {})
        if not isinstance(parsed, Mapping):
            return plan.model_copy(update={"notes": list(plan.notes) + ["AI_DRAFT_INVALID"]})
        notes = list(plan.notes)
        rows = parsed.get("chapters") or []
        updates: dict[str, dict[str, str]] = {}
        for raw in rows:
            if not isinstance(raw, Mapping):
                continue
            item_id = str(raw.get("id", "") or "")
            if item_id not in allowed:
                notes.append(f"AI_CHAPTER_OUTSIDE_CATALOG:{item_id}")
                continue
            updates[item_id] = {key: str(raw.get(key, "") or "") for key in
                                ("title", "summary", "hook")}
        if not updates:
            return plan.model_copy(update={"notes": notes + ["AI_NO_CHANGES"]})
        chapters = [item.model_copy(update={key: value for key, value in updates[item.id].items()
                                            if value}) if item.id in updates else item
                    for item in plan.chapters]
        return plan.model_copy(update={"chapters": chapters, "source": "ai", "notes": notes})

    @staticmethod
    def _prompt(plan: ForgePlan) -> str:
        lines = ["你只能改写下面章节的 title / summary / hook，禁止新增或删除章节，禁止改动 id。",
                 f"小说：{plan.book_title}（{plan.novel_id}）",
                 f"全书目标：{plan.book_goal}",
                 "章节："]
        for item in plan.chapters:
            lines.append(json.dumps({"id": item.id, "title": item.title, "goal": item.goal,
                                     "conflict": item.conflict, "kind": item.kind},
                                    ensure_ascii=False))
        lines.append('输出 JSON：{"chapters":[{"id":..., "title":..., "summary":..., "hook":...}]}')
        return "\n".join(lines)


def assess_forge_plan(plan: ForgePlan
                      ) -> OutlineQualityReport:
    """大纲质量评估：主线清晰度 / 支线收束 / 伏笔回收 / 节奏分布 / 章节可写性。"""

    findings: list[QualityFinding] = []
    if not plan.book_goal or not plan.book_turn or not plan.book_end_state:
        findings.append(QualityFinding(code="MAIN_LINE_UNCLEAR", severity="error",
                                       message="全书主线缺少目标 / 转折 / 收束描述",
                                       target="book"))
    total = len(plan.chapters)
    if total == 0:
        findings.append(QualityFinding(code="NO_CHAPTERS", severity="error",
                                       message="没有生成任何章节", target="chapters"))
    kinds = [item.kind for item in plan.chapters]
    for kind in FACT_KINDS:
        if kind not in kinds and kind == "happened":
            findings.append(QualityFinding(code="NO_HAPPENED_CHAPTERS", severity="warning",
                                           message="还没有任何已发生事实，全书都是规划章节",
                                           target="chapters"))
    # NF-003 门禁：章节标题必须是内容——不得使用字段标签，也不得两章同标题。
    bodies: list[str] = []
    for item in plan.chapters:
        body = _title_body(item.title).strip()
        bodies.append(body)
        if _is_field_label(body):
            findings.append(QualityFinding(
                code="CHAPTER_TITLE_PLACEHOLDER", severity="error",
                message=f"章节标题是字段标签而不是内容：{item.title}",
                target=item.id))
        elif any(noise in body for noise in ("（规划）", "（设定草稿）")):
            findings.append(QualityFinding(
                code="CHAPTER_TITLE_PLACEHOLDER", severity="error",
                message=f"章节标题里残留模板后缀：{item.title}", target=item.id))
    duplicates = sorted({body for body in bodies if bodies.count(body) > 1 and body})
    if duplicates:
        findings.append(QualityFinding(
            code="CHAPTER_TITLE_DUPLICATE", severity="error",
            message=f"{len(duplicates)} 个章节标题被重复使用：" + "、".join(duplicates[:3]),
            target="chapters"))
    underspecified = [item.id for item in plan.chapters
                      if not item.goal or not item.conflict or not item.hook]
    if underspecified:
        findings.append(QualityFinding(code="CHAPTER_UNDERSPECIFIED", severity="error",
                                       message=f"{len(underspecified)} 章缺少目标 / 冲突 / 钩子",
                                       target=",".join(underspecified[:5])))
    referenced = set()
    for item in plan.chapters:
        for value in item.plot_changes:
            referenced.add(value)
        for value in item.foreshadow_moves:
            referenced.add(value)
    for value in plan.notes:
        if value.startswith("ACTIVE_PLOTS："):
            for title in value.replace("ACTIVE_PLOTS：", "").split("、"):
                if title and not any(title in row for row in referenced):
                    findings.append(QualityFinding(
                        code="PLOT_UNCLOSED", severity="warning",
                        message=f"支线「{title}」还没有对应的章节动作", target=title))
        if value.startswith("OPEN_FORESHADOWS："):
            for foreshadow_id in value.replace("OPEN_FORESHADOWS：", "").split("、"):
                if foreshadow_id and not any(foreshadow_id in row for row in referenced):
                    findings.append(QualityFinding(
                        code="FORESHADOW_UNPLACED", severity="warning",
                        message=f"伏笔 {foreshadow_id} 还没有安排在章节里",
                        target=foreshadow_id))
    pacing: list[str] = []
    flat = 0
    for item in plan.chapters:
        hook = 1 if item.hook else 0
        turn = 1 if item.turn else 0
        pacing.append("rise" if turn else "flat")
        flat = flat + 1 if not hook and not turn else 0
        if flat >= 4:
            findings.append(QualityFinding(
                code="PACING_FLAT", severity="warning",
                message="连续 4 章没有转折或钩子，节奏过平", target=item.id))
            flat = 0
    for item in plan.chapters:
        if item.kind == "happened" and not item.source_ids:
            findings.append(QualityFinding(
                code="FACT_WITHOUT_SOURCE", severity="error",
                message="已发生章节缺少来源记录", target=item.id))
        if item.kind != "happened" and item.information_changes and not item.must_avoid:
            findings.append(QualityFinding(
                code="PLANNED_LEAK_RISK", severity="warning",
                message="规划章节包含信息释放，必须标注不得违反的约束", target=item.id))
    counts = {"chapters": total, "happened": kinds.count("happened"),
              "planned": kinds.count("planned"), "suggested": kinds.count("suggested"),
              "volumes": len(plan.volumes), "arcs": len(plan.arcs)}
    return OutlineQualityReport(novel_id=plan.novel_id,
                                ok=not any(item.severity == "error" for item in findings),
                                counts=counts, findings=findings, pacing=pacing)


def _items_for_level(plan: ForgePlan, level: OutlineLevel) -> list[OutlineItem]:
    if level == OutlineLevel.BOOK:
        return [OutlineItem(
            item_id=_package_id("book_item", plan.novel_id, plan.branch_id),
            title=plan.book_title or plan.novel_id,
            summary=plan.book_goal or "全书主线",
            start_state="起点：由已发生路线决定的当前事实",
            end_state=plan.book_end_state,
            goals=[plan.book_goal] if plan.book_goal else [],
            conflicts=[plan.book_conflict] if plan.book_conflict else [],
            major_turns=[plan.book_turn] if plan.book_turn else [],
            ending_hook="全书收束由最后一卷的目标决定，不提前写成事实",
            must_keep=[f"路线：{plan.branch_id} · revision {plan.revision}",
                       "只有 happened 记录可以写成事实"],
            must_avoid=["不得把 planned / suggested 写成已发生事实",
                        "不得改写已确认的历史"],
            pov="", time=f"tick {plan.tick}", location="", participants=[])]
    if level == OutlineLevel.VOLUME:
        return [OutlineItem(
            item_id=_package_id(f"vol{row.index:02d}_item", plan.novel_id, plan.branch_id),
            title=row.title or f"第{row.index}卷",
            summary=row.goal or row.title,
            goals=[row.goal] if row.goal else [],
            conflicts=[row.conflict] if row.conflict else [],
            major_turns=[row.turn] if row.turn else [],
            ending_hook="进入下一卷前完成本卷目标",
            must_keep=[f"来源：{plan.branch_id} 路线（revision {plan.revision}）"],
            must_avoid=["本卷之外的历史不得改写"]) for row in plan.volumes]
    if level == OutlineLevel.ARC:
        return [OutlineItem(
            item_id=_package_id(f"arc{row.index:02d}_item", plan.novel_id, plan.branch_id),
            title=row.title or f"篇章{row.index}",
            summary=row.question or row.title,
            goals=[row.question] if row.question else [],
            conflicts=[row.question] if row.question else [],
            major_turns=[row.closes_with] if row.closes_with else [],
            ending_hook="这一篇以一次选择或后果收束",
            must_keep=[f"来源：{plan.branch_id} 路线（revision {plan.revision}）"],
            must_avoid=["不得越过篇章边界改写其它篇章"]) for row in plan.arcs]
    return [OutlineItem(
        item_id=row.id, title=row.title[:120] or f"第{row.index}章",
        summary=row.summary[:4000] or row.goal or row.title,
        start_state=row.start_state[:2000], end_state=row.end_state[:2000],
        goals=[row.goal] if row.goal else [],
        conflicts=[row.conflict] if row.conflict else [],
        major_turns=[row.turn] if row.turn else [],
        ending_hook=row.hook[:1000],
        must_keep=(row.must_keep or [])[:12], must_avoid=(row.must_avoid or [])[:12],
        source_ids=(row.source_ids or [])[:24],
        pov=row.pov, time=row.time, location=row.location,
        participants=row.participants,
        information_changes=row.information_changes + row.plot_changes + row.foreshadow_moves,
        costs=row.costs + row.relationship_changes + row.progression_changes)
        for row in plan.chapters]


def forge_outline(project_root: Path, novel_id: str, *, branch_id: str = DEFAULT_BRANCH,
                  structure: StructureSpec | Mapping[str, Any] | None = None,
                  provider: Any | None = None,
                  expected_revision: int | None = None) -> dict[str, Any]:
    """把路线锻造成四级大纲并落盘（复用既有大纲仓库与版本规则）。"""

    plan = build_forge_plan(project_root, novel_id, branch_id=branch_id, structure=structure,
                            provider=provider)
    if expected_revision is not None and expected_revision != plan.revision:
        raise OutlineForgeError("OUTLINE_ROUTE_STALE",
                                f"路线已经推进到 revision {plan.revision}，请刷新后重新锻造")
    report = assess_forge_plan(plan)
    repository = StoryOutlineRepository(project_root)
    profile = NovelProfileRepository(project_root).ensure(novel_id)
    digest = _digest_for_slot(project_root, plan)
    route_source = {"branch_id": plan.branch_id, "revision": str(plan.revision),
                    "runtime_id": plan.runtime_id, "runtime_version": str(plan.runtime_version),
                    "digest": digest}
    design_sections = {
        "novel": profile.title or novel_id,
        "genre": profile.genre or "",
        "tone": profile.tone or "",
        "selling_points": "；".join(profile.world_profile.get("creative_brief", {}).get(
            "selling_points", []) if isinstance(profile.world_profile.get("creative_brief"), Mapping)
            else []),
        "structure": f"{plan.structure.volumes} 卷 / "
                     f"{plan.structure.volumes * plan.structure.arcs_per_volume} 篇章 / "
                     f"{len(plan.chapters)} 章",
        "structure_spec": f"{plan.structure.volumes}/{plan.structure.arcs_per_volume}/"
                          f"{plan.structure.chapters_per_arc}",
    }
    pending = [f"{item.code}: {item.message}" for item in report.findings]
    packages: dict[str, Any] = {}
    version = 1
    book_id = _package_id("book", novel_id, branch_id)
    book = _save_package(repository, OutlinePackage(
        package_id=book_id, project_id=novel_id, blueprint_id=plan.runtime_id,
        blueprint_version=plan.runtime_version, level=OutlineLevel.BOOK, version=1,
        status=OutlineStatus.DRAFT, items=_items_for_level(plan, OutlineLevel.BOOK),
        route_source=route_source,
        route_history=[{"id": item.id, "kind": item.kind, "title": item.title}
                       for item in plan.chapters],
        design_sections=design_sections, pending_questions=pending))
    packages["book"] = book
    volume_rows = _items_for_level(plan, OutlineLevel.VOLUME)
    arc_rows = _items_for_level(plan, OutlineLevel.ARC)
    chapter_rows = _items_for_level(plan, OutlineLevel.CHAPTER)
    volume_package_by_blueprint: dict[str, Any] = {}
    for row, blueprint in zip(volume_rows, plan.volumes):
        volume_id = _package_id(f"vol{blueprint.index:02d}", novel_id, branch_id)
        package = _save_package(repository, OutlinePackage(
            package_id=volume_id, project_id=novel_id, blueprint_id=plan.runtime_id,
            blueprint_version=plan.runtime_version, level=OutlineLevel.VOLUME, version=version,
            status=OutlineStatus.DRAFT, parent_package_id=book_id, items=[row],
            source_package_versions={book_id: book.version},
            route_source=route_source, design_sections=design_sections))
        packages[f"volume_{blueprint.index}"] = package
        volume_package_by_blueprint[blueprint.id] = package
    for row, blueprint in zip(arc_rows, plan.arcs):
        arc_id = _package_id(f"arc{blueprint.index:02d}", novel_id, branch_id)
        parent = volume_package_by_blueprint.get(blueprint.volume_id)
        package = _save_package(repository, OutlinePackage(
            package_id=arc_id, project_id=novel_id, blueprint_id=plan.runtime_id,
            blueprint_version=plan.runtime_version, level=OutlineLevel.ARC, version=version,
            status=OutlineStatus.DRAFT,
            parent_package_id=(parent.package_id if parent else book_id), items=[row],
            source_package_versions=({parent.package_id: parent.version} if parent else {}),
            route_source=route_source, design_sections=design_sections))
        packages[f"arc_{blueprint.index}"] = package
    arc_index_by_chapter: dict[str, int] = {}
    for blueprint in plan.arcs:
        for chapter_id in blueprint.chapter_ids:
            arc_index_by_chapter[chapter_id] = blueprint.index
    for row, blueprint in zip(chapter_rows, plan.chapters):
        chapter_id = _package_id(f"ch{blueprint.index:03d}", novel_id, branch_id)
        parent = packages.get(f"arc_{arc_index_by_chapter.get(blueprint.id, 1)}")
        package = _save_package(repository, OutlinePackage(
            package_id=chapter_id, project_id=novel_id, blueprint_id=plan.runtime_id,
            blueprint_version=plan.runtime_version, level=OutlineLevel.CHAPTER, version=version,
            status=OutlineStatus.DRAFT,
            parent_package_id=(parent.package_id if parent else book_id), items=[row],
            source_package_versions=({parent.package_id: parent.version} if parent else {}),
            route_source=route_source, design_sections=design_sections))
        packages[f"chapter_{blueprint.index}"] = package
    return {"novel_id": novel_id, "branch_id": branch_id, "plan": plan.as_dict(),
            "quality": report.as_dict(),
            "package_ids": {key: value.package_id for key, value in packages.items()},
            "counts": report.counts}


def _digest_for_slot(project_root: Path, plan: ForgePlan) -> str:
    from .storage import StoryStateRepository

    states = StoryStateRepository(project_root)
    state = states.load(plan.runtime_id, plan.runtime_version, plan.branch_id)
    return state_digest(state)


def _save_package(repository: StoryOutlineRepository, package: OutlinePackage) -> OutlinePackage:
    latest = repository.latest(package.level, package.package_id)
    version = (latest.version + 1) if latest else package.version
    if latest and latest.status == OutlineStatus.CONFIRMED and latest.items == package.items \
            and latest.route_source == package.route_source:
        return latest
    return repository.save(package.model_copy(update={"version": version}))


def load_forge_chain(project_root: Path, novel_id: str, *,
                     branch_id: str = DEFAULT_BRANCH) -> dict[str, Any]:
    """读取这本小说当前的四级大纲链与质量报告（只读）。"""

    repository = StoryOutlineRepository(project_root)
    prefix = _chain_prefix(novel_id, branch_id)
    books = _latest_by_prefix(repository, OutlineLevel.BOOK, prefix)
    book = books[0] if books else None
    if book is None:
        return {"novel_id": novel_id, "branch_id": branch_id, "book": None, "volumes": [],
                "arcs": [], "chapters": [], "quality": None, "fresh": False}
    volumes = _latest_by_prefix(repository, OutlineLevel.VOLUME, prefix)
    arcs = _latest_by_prefix(repository, OutlineLevel.ARC, prefix)
    chapters = sorted(_latest_by_prefix(repository, OutlineLevel.CHAPTER, prefix),
                      key=lambda item: item.package_id)
    fresh = True
    quality: dict[str, Any] | None = None
    try:
        plan = build_forge_plan(project_root, novel_id, branch_id=branch_id)
        digest = _digest_for_slot(project_root, plan)
        fresh = digest == book.route_source.get("digest")
        quality = assess_forge_plan(plan).as_dict() if fresh else None
    except OutlineForgeError:
        fresh = False
    return {"novel_id": novel_id, "branch_id": branch_id, "book": book, "fresh": fresh,
            "volumes": volumes, "arcs": arcs, "chapters": chapters, "quality": quality}


def _chain_prefix(novel_id: str, branch_id: str) -> str:
    return f"ol_{_chain_stem(novel_id, branch_id)}_"


def _latest_by_prefix(repository: StoryOutlineRepository, level: OutlineLevel,
                      prefix: str) -> list[OutlinePackage]:
    """按前缀列出某一层的大纲包（每个包取最新版本），避免逐 id 猜测。"""

    root = repository.outlines_dir / level.value.lower()
    if not root.is_dir():
        return []
    rows: list[OutlinePackage] = []
    for folder in sorted(root.glob(f"{prefix}*")):
        versions = sorted(folder.glob("v*.json"))
        if not versions:
            continue
        version = int(versions[-1].stem[1:])
        try:
            rows.append(repository.load(folder.name, version))
        except StoryOutlineError:  # noqa: PERF203 - 单个损坏包不影响其它层
            continue
    return rows


def export_forge_markdown(project_root: Path, novel_id: str, *,
                          branch_id: str = DEFAULT_BRANCH) -> dict[str, Any]:
    """把四级大纲导出成一份可编辑的 Markdown（复用既有导出能力）。"""

    chain = load_forge_chain(project_root, novel_id, branch_id=branch_id)
    if chain["book"] is None:
        raise OutlineForgeError("OUTLINE_NOT_FOUND", "这本小说还没有锻造过大纲")
    lines = [f"# {chain['book'].design_sections.get('novel', novel_id)} 剧情与大纲", ""]
    lines.append(f"- 路线：{branch_id}")
    lines.append(f"- 结构：{chain['book'].design_sections.get('structure', '')}")
    lines.append(f"- 来源是否仍一致：{'是' if chain['fresh'] else '否（请重新锻造）'}")
    lines.append("")
    for package in [chain["book"], *chain["volumes"], *chain["arcs"], *chain["chapters"]]:
        for item in package.items:
            lines.extend([f"## {item.title}", "", item.summary, ""])
            if item.goals:
                lines.append(f"- 目标：{'；'.join(item.goals)}")
            if item.conflicts:
                lines.append(f"- 核心冲突：{'；'.join(item.conflicts)}")
            if item.major_turns:
                lines.append(f"- 转折：{'；'.join(item.major_turns)}")
            if item.information_changes:
                lines.append(f"- 信息释放：{'；'.join(item.information_changes)}")
            if item.costs:
                lines.append(f"- 代价 / 关系变化：{'；'.join(item.costs)}")
            if item.ending_hook:
                lines.append(f"- 结尾钩子：{item.ending_hook}")
            if item.must_keep:
                # 前缀只加一次：must_keep 里的条目可能自己已经带「来源：」，
                # 直接拼接会得到「来源：来源：…」（NF-017）。
                sources = "；".join(_strip_source_prefix(row) for row in item.must_keep)
                lines.append(f"- 来源：{sources}")
            if item.must_avoid:
                lines.append(f"- 不得违反：{'；'.join(item.must_avoid)}")
            lines.append("")
    return {"filename": f"剧情与大纲_{novel_id}_{branch_id}.md", "content": "\n".join(lines)}


def _strip_source_prefix(text: Any) -> str:
    """去掉条目自带的「来源：」前缀，保证展示层只加一次。"""

    out = str(text or "").strip()
    while out.startswith("来源："):
        out = out[len("来源："):].strip()
    return out


def verify_plan_sources(plan: ForgePlan, state: StoryState) -> dict[str, Any]:
    """把生成的章纲与路线来源对一遍（复用既有 verify_outline_sources）。"""

    route = build_route(state)
    items = [{"item_id": item.id, "must_keep": item.must_keep,
              "source_ids": item.source_ids} for item in plan.chapters
             if item.kind == "happened"]
    result = verify_outline_sources(items, route)
    return result.as_dict()
