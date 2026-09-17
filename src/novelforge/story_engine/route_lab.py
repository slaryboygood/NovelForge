"""W2：路线实验室（分支对比 / 合并 / 正式路线冻结）。

这一层只做三件事，全部复用现有事实体系：

1. **列出分支**：分支就是从同一份 StoryState 深拷贝出来的独立事实（`StoryStateRepository.fork`）。
2. **结构化对比**：逐项比较两个分支的事实差异（资源 / 知识 / 关系 / 支线 / 伏笔 / 身份 / 能力 / 地点 / 旗帜），
   并为“可以搬走的成果”生成一条可执行的 EffectSpec 草案；冲突项只报告，不自动改写。
3. **合并与冻结**：
   - 合并 = 在目标分支上**重放被作者选中的效果**（`apply_effects`），历史记录只会追加，不改写；
   - 冻结 = 把当前事实复制成不可再推进的正式路线快照，并把“正式路线”写进 NovelProfile。

设计约束：

- 不新增第二套状态或事件系统；合并只走既有 EffectSpec / apply_effects。
- 不改写已发生历史：合并产生的每条变化都带 `merge:<branch>` 来源写进 effect_log。
- 题材无关：只按通用字段比较，不认识任何题材名词。
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import Field

from novelforge.models import StrictModel

from .creator import DEFAULT_BRANCH, CreatorContextError, resolve_creator_context
from .effects import EffectSpec, apply_effects
from .linkage import plot_tracks
from .profile import NovelProfileRepository
from .state import StoryState
from .storage import StoryStateRepository, StoryStateStorageError

ROUTE_LAB_KEY = "route_lab"
OFFICIAL_BRANCH_LABEL = "official_branch"
FROZEN_REVISION_LABEL = "frozen_revision"
FROZEN_BRANCH_PREFIX = "branch_"
REVISION_OPS = ("choice", "runtime_action")


class BranchLabError(ValueError):
    def __init__(self, code: str, message: str, *, novel_id: str = "") -> None:
        self.code = code
        self.message = message
        self.novel_id = novel_id
        super().__init__(message)

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message, "novel_id": self.novel_id}


class BranchRow(StrictModel):
    """一条分支的摘要（事实来自 StoryState，不是前端缓存）。"""

    branch_id: str
    revision: int = 0
    tick: int = 0
    location: str = ""
    characters: int = 0
    knowledge: int = 0
    plots_active: int = 0
    foreshadows_open: int = 0
    official: bool = False
    frozen_revision: int = 0
    source_branch: str = ""


class DiffRow(StrictModel):
    """两个分支之间的一条结构化差异。"""

    kind: str
    item_id: str
    label: str = ""
    base: Any = None
    target: Any = None
    mergeable: bool = False
    conflict: bool = False
    note: str = ""
    effect: dict[str, Any] | None = None


class BranchComparison(StrictModel):
    novel_id: str = ""
    base_branch: str = DEFAULT_BRANCH
    target_branch: str = ""
    base_revision: int = 0
    target_revision: int = 0
    rows: list[DiffRow] = Field(default_factory=list)
    summary: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class MergeResult(StrictModel):
    novel_id: str = ""
    target_branch: str = ""
    merged: list[dict[str, Any]] = Field(default_factory=list)
    skipped: list[dict[str, Any]] = Field(default_factory=list)
    failures: list[dict[str, Any]] = Field(default_factory=list)
    revision: int = 0
    tick: int = 0
    history_preserved: bool = True


def _revision(state: StoryState) -> int:
    return len([item for item in state.effect_log if item.op in REVISION_OPS])


def _foreshadow_registry(state: StoryState) -> dict[str, dict[str, Any]]:
    registry = state.flags.get("foreshadows", {})
    return dict(registry) if isinstance(registry, Mapping) else {}


def _relationship_dimensions(state: StoryState) -> dict[tuple[str, str, str], float]:
    rows: dict[tuple[str, str, str], float] = {}
    for item in state.relationships:
        for dimension, value in item.dimensions.items():
            rows[(item.source_id, item.target_id, dimension)] = float(value)
    return rows


def _relationship_labels(state: StoryState) -> dict[tuple[str, str, str], str]:
    labels: dict[tuple[str, str, str], str] = {}
    for item in state.relationships:
        source = state.characters.get(item.source_id)
        target = state.characters.get(item.target_id)
        label = f"{source.name if source else item.source_id} → {target.name if target else item.target_id}"
        for dimension in item.dimensions:
            labels[(item.source_id, item.target_id, dimension)] = label
    return labels


def compare_states(base: StoryState, target: StoryState) -> BranchComparison:
    """比较两份事实：只报告差异，不写任何文件。"""

    rows: list[DiffRow] = []
    if base.location.current != target.location.current:
        rows.append(DiffRow(kind="location", item_id="current", label="当前地点",
                            base=base.location.current, target=target.location.current,
                            mergeable=True, note="合并 = 把当前地点改到目标分支的位置",
                            effect={"op": "change_location", "value": target.location.current}))
    for location_id in sorted(set(target.location.visited) - set(base.location.visited)):
        rows.append(DiffRow(kind="location", item_id=f"visited:{location_id}",
                            label="去过的新地点", base=False, target=True, mergeable=False,
                            note="地点访问是经过，不单独合并"))
    if base.timeline.tick != target.timeline.tick:
        rows.append(DiffRow(kind="time", item_id="tick", label="世界时间",
                            base=base.timeline.tick, target=target.timeline.tick,
                            mergeable=True,
                            note="合并 = 让时间前进到较晚的一支（时间不可倒退）",
                            effect={"op": "advance_time",
                                    "value": max(0, target.timeline.tick - base.timeline.tick)}))
    for resource_id in sorted(set(base.resources) | set(target.resources)):
        base_amount = float(base.resources[resource_id].amount) if resource_id in base.resources else 0.0
        target_amount = float(target.resources[resource_id].amount) if resource_id in target.resources else 0.0
        if base_amount == target_amount:
            continue
        delta = target_amount - base_amount
        rows.append(DiffRow(kind="resource", item_id=resource_id, label=resource_id,
                            base=base_amount, target=target_amount, mergeable=delta > 0,
                            conflict=delta < 0,
                            note="合并 = 只搬运收益；损失不自动合并" if delta > 0
                            else "目标分支比基准更少，属于损失，不自动合并",
                            effect=({"op": "add_resource", "target": resource_id, "value": delta}
                                    if delta > 0 else None)))
    base_knowledge = {item.id: set(item.holders) for item in base.knowledge}
    target_knowledge = {item.id: set(item.holders) for item in target.knowledge}
    for knowledge_id in sorted(set(target_knowledge) | set(base_knowledge)):
        gained = sorted(target_knowledge.get(knowledge_id, set()) - base_knowledge.get(knowledge_id, set()))
        if gained:
            rows.append(DiffRow(kind="knowledge", item_id=knowledge_id, label=knowledge_id,
                                base={"holders": sorted(base_knowledge.get(knowledge_id, set()))},
                                target={"holders": sorted(target_knowledge.get(knowledge_id, set()))},
                                mergeable=True, note="合并 = 让这些角色也拿到这条信息",
                                effect={"op": "add_knowledge", "target": knowledge_id,
                                        "entity": gained[0]}))
        lost = sorted(base_knowledge.get(knowledge_id, set()) - target_knowledge.get(knowledge_id, set()))
        if lost:
            rows.append(DiffRow(kind="knowledge", item_id=knowledge_id, label=knowledge_id,
                                base={"holders": sorted(base_knowledge.get(knowledge_id, set()))},
                                target={"holders": sorted(target_knowledge.get(knowledge_id, set()))},
                                mergeable=False, conflict=True,
                                note="目标分支里有人不知道这条信息，不自动合并"))
    for ability_id in sorted(set(target.abilities) - set(base.abilities)):
        rows.append(DiffRow(kind="ability", item_id=ability_id, label=ability_id,
                            base=False, target=True, mergeable=True,
                            note="合并 = 把这份能力带到正式路线",
                            effect={"op": "grant_ability", "target": ability_id,
                                    "data": {"kind": target.abilities[ability_id].kind}}))
    for ability_id in sorted(set(base.abilities) - set(target.abilities)):
        rows.append(DiffRow(kind="ability", item_id=ability_id, label=ability_id,
                            base=True, target=False, mergeable=False, conflict=True,
                            note="目标分支已失去这份能力，不自动合并"))
    for character_id in sorted(set(target.identities) | set(base.identities)):
        gained = sorted(set(target.identities.get(character_id, []))
                        - set(base.identities.get(character_id, [])))
        for identity in gained:
            rows.append(DiffRow(kind="identity", item_id=f"{character_id}:{identity}",
                                label=f"{character_id} 身份 {identity}", base=False, target=True,
                                mergeable=True, note="合并 = 让这个身份在正式路线成立",
                                effect={"op": "add_identity", "entity": character_id,
                                        "value": identity}))
    base_rel = _relationship_dimensions(base)
    target_rel = _relationship_dimensions(target)
    labels = _relationship_labels(target)
    for key in sorted(set(base_rel) | set(target_rel)):
        base_value, target_value = base_rel.get(key, 0.0), target_rel.get(key, 0.0)
        if base_value == target_value:
            continue
        source, target_id, dimension = key
        delta = target_value - base_value
        rows.append(DiffRow(
            kind="relationship", item_id=f"{source}:{target_id}:{dimension}",
            label=f"{labels.get(key, f'{source} → {target_id}')} · {dimension}",
            base=base_value, target=target_value, mergeable=delta > 0, conflict=delta < 0,
            note="合并 = 只搬运关系增益；下降属于代价，不自动合并" if delta > 0
            else "目标分支的关系更差，不自动合并",
            effect=({"op": "change_relationship", "entity": source, "target": target_id,
                     "key": dimension, "value": delta} if delta > 0 else None)))
    base_plots = {item.id: item.status for item in plot_tracks(base)}
    target_plots = {item.id: item.status for item in plot_tracks(target)}
    for plot_id in sorted(set(target_plots) | set(base_plots)):
        base_status, target_status = base_plots.get(plot_id, ""), target_plots.get(plot_id, "")
        if base_status == target_status:
            continue
        mergeable = base_status in ("", "inactive") or (
            base_status == "paused" and target_status == "active")
        rows.append(DiffRow(kind="plot", item_id=plot_id, label=plot_id,
                            base=base_status, target=target_status, mergeable=mergeable,
                            conflict=not mergeable,
                            note="合并 = 让正式路线也接受这条支线的状态" if mergeable
                            else "正式路线上的支线已经走到别处，不自动合并",
                            effect=({"op": "update_plot", "target": plot_id,
                                     "data": {"status": target_status}} if mergeable else None)))
    base_flags = {key: value for key, value in base.flags.items() if key != "foreshadows"}
    target_flags = {key: value for key, value in target.flags.items() if key != "foreshadows"}
    for flag in sorted(set(target_flags) | set(base_flags)):
        base_value, target_value = base_flags.get(flag), target_flags.get(flag)
        if base_value == target_value:
            continue
        rows.append(DiffRow(kind="flag", item_id=flag, label=flag, base=base_value,
                            target=target_value, mergeable=True,
                            note="合并 = 把目标分支的旗帜状态带过来",
                            effect={"op": "set_flag", "key": flag, "value": target_value}))
    base_fs = _foreshadow_registry(base)
    target_fs = _foreshadow_registry(target)
    order = ["planned", "planted", "reinforced", "revealed", "resolved", "abandoned"]
    for foreshadow_id in sorted(set(target_fs) | set(base_fs)):
        base_status = str((base_fs.get(foreshadow_id) or {}).get("status", ""))
        target_status = str((target_fs.get(foreshadow_id) or {}).get("status", ""))
        if base_status == target_status:
            continue
        mergeable = (base_status in ("", "planned")
                     or order.index(target_status) > order.index(base_status)
                     if target_status in order and base_status in order else False)
        rows.append(DiffRow(kind="foreshadow", item_id=foreshadow_id, label=foreshadow_id,
                            base=base_status, target=target_status, mergeable=mergeable,
                            conflict=not mergeable,
                            note="合并 = 伏笔推进到目标分支的状态" if mergeable
                            else "伏笔状态回退或不可比，不自动合并",
                            effect=({"op": "update_foreshadow", "target": foreshadow_id,
                                     "data": {"status": target_status}} if mergeable else None)))
    summary = [f"{row.kind}:{row.item_id}（{row.base} → {row.target}）" for row in rows]
    conflicts = [row.item_id for row in rows if row.conflict]
    return BranchComparison(rows=rows, summary=summary, conflicts=conflicts)


def _route_lab_meta(project_root: Path, novel_id: str) -> dict[str, Any]:
    profile = NovelProfileRepository(project_root).ensure(novel_id)
    payload = profile.world_profile.get(ROUTE_LAB_KEY)
    return dict(payload) if isinstance(payload, Mapping) else {}


def _save_route_lab_meta(project_root: Path, novel_id: str, payload: Mapping[str, Any]) -> None:
    repository = NovelProfileRepository(project_root)
    profile = repository.ensure(novel_id)
    world_profile = dict(profile.world_profile)
    world_profile[ROUTE_LAB_KEY] = dict(payload)
    repository.save(profile.model_copy(update={"world_profile": world_profile}))


def runtime_slot(context) -> tuple[str, int]:
    """事实槽：有蓝图用蓝图槽，否则用小说级运行槽（与 runtime API 完全一致）。"""

    return context.runtime_id, context.runtime_version


def list_branches(project_root: Path, novel_id: str) -> dict[str, Any]:
    """列出这本小说的所有分支（含正式路线标记）。"""

    try:
        context = resolve_creator_context(project_root, novel_id)
    except CreatorContextError as exc:
        raise BranchLabError(exc.code, exc.message, novel_id=novel_id) from exc
    if context.pack is None:
        # 还没有内容包 == 这本书还没有开始推演。对“列出分支”这种只读列表接口来说，
        # 这是一个合法的空结果，不是错误：前端据此渲染空态，而不是把预期空状态
        # 打成 404（浏览器会把 404 记为 Console Error）。
        # 会真正改动事实的接口（fork / compare / merge / freeze）仍然照旧抛错。
        return {"novel_id": novel_id, "runtime_id": context.runtime_id,
                "runtime_version": context.runtime_version, "official_branch": "",
                "frozen_revision": 0, "started": context.persisted, "branches": []}
    states = StoryStateRepository(project_root)
    slot_id, version = runtime_slot(context)
    meta = _route_lab_meta(project_root, novel_id)
    official = str(meta.get(OFFICIAL_BRANCH_LABEL, "") or "")
    frozen_revision = int(meta.get(FROZEN_REVISION_LABEL, 0) or 0)
    branch_ids = states.branches(slot_id, version)
    if not branch_ids and states.exists(slot_id, version, DEFAULT_BRANCH):
        branch_ids = [DEFAULT_BRANCH]
    rows: list[BranchRow] = []
    for branch_id in branch_ids:
        try:
            state = states.load(slot_id, version, branch_id)
        except StoryStateStorageError:
            continue
        rows.append(BranchRow(
            branch_id=branch_id, revision=_revision(state), tick=state.timeline.tick,
            location=state.location.current, characters=len(state.characters),
            knowledge=len(state.knowledge),
            plots_active=len([item for item in plot_tracks(state) if item.status == "active"]),
            foreshadows_open=len([item for item in _foreshadow_registry(state).values()
                                  if str(item.get("status", "")) not in ("resolved", "abandoned")]),
            official=branch_id == official, frozen_revision=frozen_revision if branch_id == official
            else 0, source_branch=str(meta.get(f"fork_of:{branch_id}", "") or "")))
    return {"novel_id": novel_id, "runtime_id": slot_id, "runtime_version": version,
            "official_branch": official, "frozen_revision": frozen_revision,
            "started": context.persisted, "branches": [row.model_dump(mode="json")
                                                       for row in rows]}


def fork_branch(project_root: Path, novel_id: str, *, source_branch: str = DEFAULT_BRANCH,
                label: str = "") -> dict[str, Any]:
    """从某条分支复制出新的试演分支；只读源分支，不改历史。"""

    context = resolve_creator_context(project_root, novel_id)
    if context.pack is None:
        raise BranchLabError("CONTENT_PACK_REQUIRED", "当前小说没有可用的内容包", novel_id=novel_id)
    states = StoryStateRepository(project_root)
    slot_id, version = runtime_slot(context)
    if not states.exists(slot_id, version, source_branch):
        raise BranchLabError("BRANCH_NOT_FOUND", f"找不到分支 {source_branch}", novel_id=novel_id)
    target_branch = _new_branch_id(label)
    if states.exists(slot_id, version, target_branch):
        raise BranchLabError("BRANCH_EXISTS", "目标分支已存在", novel_id=novel_id)
    forked = states.fork(slot_id, version, source_branch=source_branch,
                         target_branch=target_branch)
    meta = _route_lab_meta(project_root, novel_id)
    meta[f"fork_of:{target_branch}"] = source_branch
    if label:
        meta[f"label:{target_branch}"] = label[:60]
    _save_route_lab_meta(project_root, novel_id, meta)
    return {"branch_id": target_branch, "source_branch": source_branch,
            "revision": _revision(forked), "tick": forked.timeline.tick}


def _new_branch_id(label: str = "") -> str:
    import hashlib
    import uuid

    seed = f"{label}:{uuid.uuid4().hex}"
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:32]
    return f"{FROZEN_BRANCH_PREFIX}{digest}"


def compare_branches(project_root: Path, novel_id: str, *, base_branch: str = DEFAULT_BRANCH,
                     target_branch: str = "") -> BranchComparison:
    context = resolve_creator_context(project_root, novel_id)
    if context.pack is None:
        raise BranchLabError("CONTENT_PACK_REQUIRED", "当前小说没有可用的内容包", novel_id=novel_id)
    states = StoryStateRepository(project_root)
    slot_id, version = runtime_slot(context)
    try:
        base_state = states.load(slot_id, version, base_branch)
    except StoryStateStorageError as exc:
        raise BranchLabError("BRANCH_NOT_FOUND", f"找不到分支 {base_branch}",
                             novel_id=novel_id) from exc
    target = target_branch or base_branch
    try:
        target_state = states.load(slot_id, version, target)
    except StoryStateStorageError as exc:
        raise BranchLabError("BRANCH_NOT_FOUND", f"找不到分支 {target}",
                             novel_id=novel_id) from exc
    comparison = compare_states(base_state, target_state)
    comparison.novel_id = novel_id
    comparison.base_branch = base_branch
    comparison.target_branch = target
    comparison.base_revision = _revision(base_state)
    comparison.target_revision = _revision(target_state)
    return comparison


def merge_branches(project_root: Path, novel_id: str, *, target_branch: str,
                   source_branches: list[str], base_branch: str = DEFAULT_BRANCH,
                   item_keys: list[str] | None = None) -> MergeResult:
    """把别的分支里被选中的成果合并进目标分支：只重放效果，不改写历史。"""

    if not source_branches:
        raise BranchLabError("MERGE_SOURCE_REQUIRED", "至少要指定一条来源分支",
                             novel_id=novel_id)
    if target_branch in source_branches:
        raise BranchLabError("MERGE_SAME_BRANCH", "目标分支不能同时作为来源分支",
                             novel_id=novel_id)
    context = resolve_creator_context(project_root, novel_id)
    if context.pack is None:
        raise BranchLabError("CONTENT_PACK_REQUIRED", "当前小说没有可用的内容包", novel_id=novel_id)
    states = StoryStateRepository(project_root)
    slot_id, version = runtime_slot(context)
    try:
        target_state = states.load(slot_id, version, target_branch)
    except StoryStateStorageError as exc:
        raise BranchLabError("BRANCH_NOT_FOUND", f"找不到分支 {target_branch}",
                             novel_id=novel_id) from exc
    history_before = list(target_state.effect_log)
    merged: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    wanted = set(item_keys) if item_keys else None
    for source_id in source_branches:
        try:
            source_state = states.load(slot_id, version, source_id)
        except StoryStateStorageError as exc:
            raise BranchLabError("BRANCH_NOT_FOUND", f"找不到分支 {source_id}",
                                 novel_id=novel_id) from exc
        comparison = compare_states(target_state, source_state)
        for row in comparison.rows:
            key = f"{row.kind}:{row.item_id}"
            if wanted is not None and key not in wanted and row.item_id not in wanted:
                continue
            if not row.mergeable or row.effect is None:
                skipped.append({"branch": source_id, "kind": row.kind, "item": row.item_id,
                                "reason": "CONFLICT" if row.conflict else "NOT_MERGEABLE",
                                "note": row.note})
                continue
            spec = EffectSpec.model_validate({**row.effect, "source": f"merge:{source_id}"})
            outcome = apply_effects(target_state, [spec], actor="protagonist",
                                    source=f"merge:{source_id}")
            if not outcome.ok:
                failures.append({"branch": source_id, "kind": row.kind, "item": row.item_id,
                                 "code": outcome.code, "message": outcome.message})
                continue
            target_state = outcome.state
            merged.append({"branch": source_id, "kind": row.kind, "item": row.item_id,
                           "label": row.label, "base": row.base, "target": row.target,
                           "effect": row.effect})
    states.save(target_state, slot_id, version, target_branch)
    prefix_preserved = list(target_state.effect_log[:len(history_before)]) == history_before
    return MergeResult(novel_id=novel_id, target_branch=target_branch, merged=merged,
                       skipped=skipped, failures=failures, revision=_revision(target_state),
                       tick=target_state.timeline.tick, history_preserved=prefix_preserved)


def freeze_branch(project_root: Path, novel_id: str, *, branch_id: str = DEFAULT_BRANCH,
                  label: str = "") -> dict[str, Any]:
    """把某条分支标记为正式路线，并留一份只读快照；其它实验分支继续独立。"""

    context = resolve_creator_context(project_root, novel_id)
    if context.pack is None:
        raise BranchLabError("CONTENT_PACK_REQUIRED", "当前小说没有可用的内容包", novel_id=novel_id)
    states = StoryStateRepository(project_root)
    slot_id, version = runtime_slot(context)
    try:
        state = states.load(slot_id, version, branch_id)
    except StoryStateStorageError as exc:
        raise BranchLabError("BRANCH_NOT_FOUND", f"找不到分支 {branch_id}",
                             novel_id=novel_id) from exc
    snapshot_branch = _new_branch_id(f"frozen:{branch_id}")
    frozen = state.model_copy(deep=True)
    frozen.flags["frozen_from"] = branch_id
    frozen.flags["frozen_revision"] = _revision(state)
    states.save(frozen, slot_id, version, snapshot_branch)
    meta = _route_lab_meta(project_root, novel_id)
    meta[OFFICIAL_BRANCH_LABEL] = branch_id
    meta[FROZEN_REVISION_LABEL] = _revision(state)
    meta["frozen_snapshot_branch"] = snapshot_branch
    meta["frozen_label"] = label[:60]
    _save_route_lab_meta(project_root, novel_id, meta)
    return {"novel_id": novel_id, "official_branch": branch_id, "frozen_branch": snapshot_branch,
            "frozen_revision": _revision(state), "tick": state.timeline.tick,
            "label": label, "history_entries": len(state.effect_log)}


def merge_preview(project_root: Path, novel_id: str, *, target_branch: str,
                  source_branches: list[str]) -> dict[str, Any]:
    """只读预览：合并会带来什么、哪些项会被跳过。"""

    previews: list[dict[str, Any]] = []
    for source_id in source_branches:
        comparison = compare_branches(project_root, novel_id, base_branch=target_branch,
                                      target_branch=source_id)
        previews.append({
            "source_branch": source_id,
            "mergeable": [{"kind": row.kind, "item": row.item_id, "label": row.label,
                           "base": row.base, "target": row.target, "note": row.note}
                          for row in comparison.rows if row.mergeable],
            "conflicts": [{"kind": row.kind, "item": row.item_id, "label": row.label,
                           "base": row.base, "target": row.target, "note": row.note}
                          for row in comparison.rows if row.conflict],
            "other": [{"kind": row.kind, "item": row.item_id, "label": row.label,
                       "base": row.base, "target": row.target, "note": row.note}
                      for row in comparison.rows if not row.mergeable and not row.conflict],
        })
    return {"novel_id": novel_id, "target_branch": target_branch, "sources": previews,
            "note": "合并只搬运可执行的效果；冲突项必须由作者显式处理"}


def _label_for(meta: Mapping[str, Any], branch_id: str) -> str:
    return str(meta.get(f"label:{branch_id}", "") or "")


def branch_label(project_root: Path, novel_id: str, branch_id: str) -> str:
    return _label_for(_route_lab_meta(project_root, novel_id), branch_id)
