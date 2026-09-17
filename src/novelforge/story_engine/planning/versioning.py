"""M2A：Story Planning IR versioning 基础能力。

支持 revision / parent_revision / branch / compare / promote / rollback，
并且**永远不删除历史**：promote 与 rollback 都是产生新 revision，而不是改写旧 revision。

supplied 保护：作者显式给出的条目（provenance=supplied）不会被 generated / inferred
的结果自动覆盖；M2B 的 Builder / Compiler 必须走 `merge_supplied` 才能合并。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from pydantic import Field

from novelforge.models import StrictModel

from .enums import RevisionSource, RevisionStatus
from .models import (
    PlannedModel,
    StoryPlanningIR,
    entry_id,
    iter_planning_entries,
    new_planning_id,
)


class PlanningVersionError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


def planning_digest(plan: StoryPlanningIR | dict[str, Any]) -> str:
    payload = plan.model_dump(mode="json") if isinstance(plan, StrictModel) else plan
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


class PlanningRevision(StrictModel):
    revision_id: str = Field(min_length=6, max_length=64)
    novel_id: str = Field(min_length=1, max_length=96)
    revision: int = Field(default=1, ge=1)
    parent_revision: str = Field(default="", max_length=64)
    branch: str = Field(default="main", max_length=64)
    status: RevisionStatus = "draft"
    source: RevisionSource = "author"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    note: str = Field(default="", max_length=300)
    digest: str = Field(default="", max_length=64)
    plan: StoryPlanningIR


class PlanningDiffRow(StrictModel):
    path: str = Field(min_length=1, max_length=240)
    change: str = Field(default="modified", max_length=16)
    domain: str = Field(default="meta", max_length=32)
    stable_id: str = Field(default="", max_length=64)
    base: Any = None
    target: Any = None
    supplied_field: bool = False


class PlanningDiff(StrictModel):
    novel_id: str = Field(default="", max_length=96)
    base_revision: str = Field(default="", max_length=64)
    target_revision: str = Field(default="", max_length=64)
    rows: list[PlanningDiffRow] = Field(default_factory=list)
    summary: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)

    def changed_paths(self) -> list[str]:
        return [row.path for row in self.rows]

    def domains(self) -> list[str]:
        return sorted({row.domain for row in self.rows})


class PlanningVersionStore:
    """纯内存的 revision / branch 图（持久化留给后续 milestone）。"""

    def __init__(self, *, novel_id: str) -> None:
        self.novel_id = novel_id
        self._revisions: dict[str, PlanningRevision] = {}
        self._branches: dict[str, str] = {}

    # ---------------------------------------------------------------- 读
    def get(self, revision_id: str) -> PlanningRevision:
        try:
            return self._revisions[revision_id]
        except KeyError as exc:
            raise PlanningVersionError("REVISION_NOT_FOUND",
                                       f"找不到 revision {revision_id}") from exc

    def revisions(self) -> list[PlanningRevision]:
        return [self._revisions[key] for key in sorted(self._revisions,
                                                       key=lambda item: self._revisions[item].revision)]

    def branches(self) -> dict[str, str]:
        return dict(self._branches)

    def head(self, branch: str = "main") -> PlanningRevision | None:
        revision_id = self._branches.get(branch)
        return self._revisions.get(revision_id) if revision_id else None

    def lineage(self, revision_id: str) -> list[PlanningRevision]:
        chain: list[PlanningRevision] = []
        current = self.get(revision_id)
        while current is not None:
            chain.append(current)
            if not current.parent_revision:
                break
            current = self._revisions.get(current.parent_revision)
        return list(reversed(chain))

    # ---------------------------------------------------------------- 写
    def add(self, plan: StoryPlanningIR, *, branch: str = "main",
            source: RevisionSource = "author", status: RevisionStatus = "draft",
            note: str = "", parent_revision: str = "") -> PlanningRevision:
        if plan.novel_id != self.novel_id:
            raise PlanningVersionError("NOVEL_ID_MISMATCH",
                                       f"plan.novel_id={plan.novel_id} != {self.novel_id}")
        parent = self._revisions.get(parent_revision) if parent_revision else self.head(branch)
        revision = PlanningRevision(
            revision_id=new_planning_id("revision"),
            novel_id=self.novel_id,
            revision=(parent.revision + 1) if parent else 1,
            parent_revision=parent.revision_id if parent else "",
            branch=branch, status=status, source=source, note=note,
            digest=planning_digest(plan), plan=plan)
        self._revisions[revision.revision_id] = revision
        self._branches[branch] = revision.revision_id
        return revision

    def commit(self, plan: StoryPlanningIR, *, branch: str = "main",
               source: RevisionSource = "author", note: str = "") -> PlanningRevision:
        return self.add(plan, branch=branch, source=source, status="proposed", note=note)

    def branch_pointer(self, revision_id: str, branch: str) -> str:
        self.get(revision_id)
        if branch in self._branches:
            raise PlanningVersionError("BRANCH_EXISTS", f"分支 {branch} 已存在")
        self._branches[branch] = revision_id
        return branch

    def promote(self, revision_id: str, *, target_branch: str = "main",
                note: str = "") -> PlanningRevision:
        """把某个 revision 提升为正式规划：产生新的 confirmed revision，旧历史保留。"""

        source_revision = self.get(revision_id)
        return self.add(source_revision.plan, branch=target_branch, source=source_revision.source,
                        status="confirmed",
                        note=note or f"promote {source_revision.revision_id}",
                        parent_revision=self._branches.get(target_branch, ""))

    def rollback(self, to_revision_id: str, *, branch: str = "main",
                 note: str = "") -> PlanningRevision:
        """回滚到某个历史 revision：复制该内容生成新 revision，并标记被替换者为 superseded。"""

        target = self.get(to_revision_id)
        current = self.head(branch)
        if current is not None:
            superseded = current.model_copy(update={"status": "superseded"})
            self._revisions[superseded.revision_id] = superseded
        return self.add(target.plan, branch=branch, source=target.source, status="rolled_back",
                        note=note or f"rollback to {target.revision_id}")

    # ---------------------------------------------------------------- 比较
    def compare(self, base_revision_id: str, target_revision_id: str) -> PlanningDiff:
        base = self.get(base_revision_id)
        target = self.get(target_revision_id)
        return build_diff(self.novel_id, base.plan, target.plan,
                          base_revision=base.revision_id,
                          target_revision=target.revision_id)


DIFF_DOMAINS: dict[str, str] = {
    "intent": "intent", "theme": "theme", "logline": "intent", "title": "intent",
    "world": "world", "characters": "character", "character_arcs": "character",
    "relationship_arcs": "relationship", "factions": "faction", "faction_arcs": "faction",
    "locations": "location", "location_graph": "location", "timeline": "timeline",
    "information_arcs": "information", "foreshadow_plans": "foreshadow",
    "progression_tracks": "progression", "plot_nodes": "plot", "spine": "plot",
    "volumes": "volume", "arcs": "arc", "pacing": "pacing",
}


def diff_domain(path: str) -> str:
    """把 JSON 路径映射到结构化 domain（不是 raw text diff）。"""

    root = path.split(".", 1)[0].split("[", 1)[0]
    return DIFF_DOMAINS.get(root, "meta")


def build_diff(novel_id: str, base_plan: StoryPlanningIR, target_plan: StoryPlanningIR, *,
               base_revision: str = "", target_revision: str = "") -> PlanningDiff:
    """结构化 diff：added / removed / modified + domain + stable_id。"""

    base_fields = _flatten(base_plan.model_dump(mode="json"))
    target_fields = _flatten(target_plan.model_dump(mode="json"))
    supplied = {path: identifier for path, identifier, provenance
                in _entry_index_paths(base_plan.model_dump(mode="json"))
                if provenance == "supplied"}
    supplied_paths = list(supplied)
    rows: list[PlanningDiffRow] = []
    for path in sorted(set(base_fields) | set(target_fields)):
        before, after = base_fields.get(path, _MISSING), target_fields.get(path, _MISSING)
        if before == after:
            continue
        change = ("added" if before is _MISSING
                  else "removed" if after is _MISSING else "modified")
        owner = next((prefix for prefix in supplied_paths if _inside(path, [prefix])), "")
        rows.append(PlanningDiffRow(
            path=path, change=change, domain=diff_domain(path),
            stable_id=supplied.get(owner, "") if owner else "",
            base=None if before is _MISSING else before,
            target=None if after is _MISSING else after,
            supplied_field=bool(owner)))
    summary = [f"{row.change}: {row.domain}: {row.path}" for row in rows[:20]]
    conflicts = [row.path for row in rows if row.supplied_field and row.change != "added"]
    return PlanningDiff(novel_id=novel_id, base_revision=base_revision,
                        target_revision=target_revision, rows=rows,
                        summary=summary, conflicts=conflicts)


def merge_supplied(base: StoryPlanningIR, patch: StoryPlanningIR,
                   ) -> tuple[StoryPlanningIR, list[str]]:
    """合并 planning 补丁：base 里 supplied 的条目不会被 patch 的 generated/inferred 覆盖。

    返回 (合并后的 plan, 被保护的 stable id 列表)。
    """

    if base.novel_id != patch.novel_id:
        raise PlanningVersionError("NOVEL_ID_MISMATCH",
                                   f"{base.novel_id} != {patch.novel_id}")
    patch_payload = patch.model_dump(mode="json")
    protected: list[str] = []
    for kind, patch_model in iter_planning_entries(patch):
        identifier = entry_id(kind, patch_model)
        if not identifier:
            continue
        base_model = _find_entry(base, kind, identifier)
        if base_model is None or identifier in protected:
            continue
        if base_model.provenance == "supplied" \
                and patch_model.provenance in ("generated", "inferred") \
                and base_model.model_dump(mode="json") != patch_model.model_dump(mode="json"):
            protected.append(identifier)
    if not protected:
        return patch, []
    replacements = {identifier: _find_entry(base, *_kind_of(base, identifier))
                    for identifier in protected}
    merged_payload = _replace_protected(patch_payload, {
        identifier: model.model_dump(mode="json")
        for identifier, model in replacements.items() if model is not None})
    return StoryPlanningIR.model_validate(merged_payload), protected


def _find_entry(plan: StoryPlanningIR, kind: str, identifier: str) -> PlannedModel | None:
    for entry_kind, model in iter_planning_entries(plan):
        if entry_kind == kind and entry_id(kind, model) == identifier:
            return model
    return None


def _kind_of(plan: StoryPlanningIR, identifier: str) -> tuple[str, str]:
    for kind, model in iter_planning_entries(plan):
        if entry_id(kind, model) == identifier:
            return kind, identifier
    return "", identifier


_IDENTIFIER_KEYS: tuple[str, ...] = (
    "intent_id", "theme_id", "world_id", "rule_id", "character_id", "arc_id", "faction_id",
    "location_id", "graph_id", "timeline_id", "entry_id", "truth_id", "move_id",
    "foreshadow_id", "track_id", "milestone_id", "node_id", "spine_id", "volume_id",
    "pacing_id",
)


def _identifier_of(item: dict[str, Any]) -> str:
    for key in _IDENTIFIER_KEYS:
        value = item.get(key)
        if value:
            return str(value)
    return ""


def _replace_protected(payload: Any, replacements: dict[str, dict[str, Any]]) -> Any:
    """递归替换 payload 里 stable id 命中 replacements 的条目（保持其它内容不变）。"""

    if isinstance(payload, dict):
        identifier = _identifier_of(payload)
        replacement = replacements.get(identifier) if identifier else None
        # 只有同一类条目（字段集合一致）才整条替换，避免命中引用型 dict（例如 DecisionStep）
        if replacement is not None and set(replacement) == set(payload):
            return replacement
        return {key: _replace_protected(value, replacements) for key, value in payload.items()}
    if isinstance(payload, list):
        return [_replace_protected(item, replacements) for item in payload]
    return payload


def _entry_index_paths(payload: Any, prefix: str = ""):
    """yield (index 路径, stable id, provenance)：用于把字段差异归到所属条目。"""

    if isinstance(payload, dict):
        identifier = _identifier_of(payload)
        if identifier:
            yield prefix, identifier, str(payload.get("provenance", ""))
        for key, value in payload.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            yield from _entry_index_paths(value, child)
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            yield from _entry_index_paths(value, f"{prefix}[{index}]")


def _inside(path: str, prefixes: list[str]) -> bool:
    return any(path == prefix or path.startswith(prefix + ".") or path.startswith(prefix + "[")
               for prefix in prefixes)


_MISSING = object()


def _flatten(payload: Any, prefix: str = "") -> dict[str, Any]:
    rows: dict[str, Any] = {}
    if isinstance(payload, dict):
        for key, value in payload.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            rows.update(_flatten(value, path))
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            rows.update(_flatten(value, f"{prefix}[{index}]"))
    else:
        rows[prefix] = payload
    return rows


__all__ = [
    "DIFF_DOMAINS",
    "PlanningDiff",
    "PlanningDiffRow",
    "PlanningRevision",
    "PlanningVersionError",
    "PlanningVersionStore",
    "build_diff",
    "diff_domain",
    "merge_supplied",
    "planning_digest",
]
