"""M2B：PlanningRepository —— Story Planning IR 的正式持久化与 revision 服务。

边界（硬规则）：

- 只保存 **Planning truth**；repository 里没有任何写 Canon / StoryState / Chapter IR 的路径；
- 旧 revision 文件一旦写入就不再改动（immutable）；branch head / superseded 这类可变元数据
  只写在 `index.json`；
- 修改必须产生新 revision，不允许静默覆盖；generated / inferred 覆盖 supplied 时
  返回 `PlanningConflict`（`PlanningConflictError` 携带该对象），不自动选择；
- Planning branch 与 Route Lab candidate 分离：`create_branch` 只接受
  `source_kind="planning_revision"`；route candidate 走 `source_planning_revision_id` 预留字段。

目录布局与 StoryStateRepository / NovelProfileRepository 同风格：

    novel/authoring/story_engine/planning/<novel_id>/index.json
    novel/authoring/story_engine/planning/<novel_id>/revisions/<REVISION_ID>.json
"""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import Field, ValidationError

from novelforge.models import StrictModel

from .enums import (
    PLANNING_BRANCH_SOURCE_KINDS,
    BranchSourceKind,
    RevisionSource,
    RevisionStatus,
)
from .models import StoryPlanningIR, entry_id, iter_planning_entries, new_planning_id
from .schemas import validate_planning_ir
from .versioning import PlanningDiff, build_diff, merge_supplied, planning_digest

DEFAULT_PLANNING_PATH = Path("novel/authoring/story_engine/planning")
PLANNING_REVISION_SCHEMA_VERSION = 1
NOVEL_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{2,95}$")
BRANCH_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
INDEX_FILE = "index.json"


class PlanningRepositoryError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


class PlanningConflictItem(StrictModel):
    stable_id: str = Field(min_length=1, max_length=64)
    domain: str = Field(default="", max_length=32)
    message: str = Field(default="", max_length=200)
    base_provenance: str = Field(default="", max_length=32)
    incoming_provenance: str = Field(default="", max_length=32)


class PlanningConflict(StrictModel):
    """supplied / confirmed 内容被 generated / inferred 覆盖时的结构化冲突（不自动选择）。"""

    code: str = Field(default="PLANNING_SUPPLIED_OVERWRITE", max_length=64)
    novel_id: str = Field(default="", max_length=96)
    base_revision_id: str = Field(default="", max_length=64)
    items: list[PlanningConflictItem] = Field(default_factory=list)
    message: str = Field(default="", max_length=300)

    def ok(self) -> bool:
        return not self.items


class PlanningConflictError(PlanningRepositoryError):
    def __init__(self, conflict: PlanningConflict) -> None:
        super().__init__(conflict.code,
                         conflict.message or "supplied 内容不能被 generated / inferred 覆盖")
        self.conflict = conflict


class PlanningRevisionMeta(StrictModel):
    planning_id: str = Field(min_length=5, max_length=64)
    revision_id: str = Field(min_length=6, max_length=64)
    novel_id: str = Field(min_length=1, max_length=96)
    revision: int = Field(default=1, ge=1)
    parent_revision_id: str = Field(default="", max_length=64)
    source_revision: str = Field(default="", max_length=64)
    branch_id: str = Field(default="main", max_length=32)
    status: RevisionStatus = "draft"
    source: RevisionSource = "author"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    content_digest: str = Field(default="", max_length=64)
    note: str = Field(default="", max_length=300)


class PlanningRevisionRecord(PlanningRevisionMeta):
    plan: StoryPlanningIR


class StoredPlanningRevision(StrictModel):
    schema_version: int = PLANNING_REVISION_SCHEMA_VERSION
    revision: PlanningRevisionRecord


class PlanningIndex(StrictModel):
    schema_version: int = PLANNING_REVISION_SCHEMA_VERSION
    planning_id: str = Field(default="", max_length=64)
    novel_id: str = Field(default="", max_length=96)
    branches: dict[str, str] = Field(default_factory=dict)
    revisions: list[str] = Field(default_factory=list)
    superseded_revisions: list[str] = Field(default_factory=list)
    updated_at: datetime | None = None


class PlanningRepository:
    """一个 novel 一个目录；revision 文件不可变，index 只记录可变元数据。"""

    def __init__(self, project_root: Path, novel_id: str, *,
                 root: Path | str = DEFAULT_PLANNING_PATH) -> None:
        if not NOVEL_ID_PATTERN.match(novel_id or ""):
            raise PlanningRepositoryError("PLANNING_NOVEL_ID_INVALID", "小说编号格式不正确")
        self.project_root = project_root.resolve()
        relative = Path(root)
        base = (relative.resolve() if relative.is_absolute()
                else (self.project_root / relative).resolve())
        try:
            base.relative_to(self.project_root)
        except ValueError as exc:
            raise PlanningRepositoryError("PLANNING_PATH_OUTSIDE_PROJECT",
                                          "Planning 目录超出当前项目范围") from exc
        self.novel_id = novel_id
        self.root = base / novel_id
        self.revisions_dir = self.root / "revisions"
        self.index_path = self.root / INDEX_FILE

    # ---------------------------------------------------------------- 路径
    def revision_path(self, revision_id: str) -> Path:
        if not revision_id.startswith("PREV_"):
            raise PlanningRepositoryError("PLANNING_REVISION_ID_INVALID",
                                          f"revision id 形态非法：{revision_id}")
        return self.revisions_dir / f"{revision_id}.json"

    def exists(self, revision_id: str) -> bool:
        return self.revision_path(revision_id).is_file()

    # ---------------------------------------------------------------- index
    def _load_index(self) -> PlanningIndex:
        if not self.index_path.is_file():
            return PlanningIndex(novel_id=self.novel_id)
        try:
            return PlanningIndex.model_validate(
                json.loads(self.index_path.read_text(encoding="utf-8-sig")))
        except (OSError, UnicodeError, json.JSONDecodeError, ValidationError) as exc:
            raise PlanningRepositoryError("PLANNING_INDEX_READ_FAILED",
                                          "无法读取 planning index") from exc

    def _save_index(self, index: PlanningIndex) -> None:
        index = index.model_copy(update={"updated_at": datetime.now(timezone.utc)})
        self._atomic_write(self.index_path, index.model_dump(mode="json"))

    # ---------------------------------------------------------------- 写
    def create(self, plan: StoryPlanningIR, *, branch_id: str = "main",
               source: RevisionSource = "author", status: RevisionStatus = "draft",
               note: str = "", parent_revision_id: str | None = None,
               source_revision: str = "", revision_id: str = "") -> PlanningRevisionRecord:
        """新建一个 revision：补 planning_id、串 parent、写内容摘要，旧 revision 不动。"""

        if not BRANCH_PATTERN.match(branch_id):
            raise PlanningRepositoryError("PLANNING_BRANCH_ID_INVALID",
                                          f"branch id 形态非法：{branch_id}")
        index = self._load_index()
        # 一个 novel 一份 Planning：未显式给出 planning_id 时沿用本 novel 已有的 id
        planning_id = plan.planning_id or index.planning_id or new_planning_id("plan")
        if index.planning_id and index.planning_id != planning_id:
            raise PlanningRepositoryError(
                "PLANNING_ID_MISMATCH",
                f"该 novel 的 planning_id 是 {index.planning_id}，收到 {planning_id}")
        payload = plan.model_dump(mode="json")
        payload["planning_id"] = planning_id
        plan = validate_planning_ir(payload)
        parent_id = parent_revision_id if parent_revision_id is not None \
            else index.branches.get(branch_id, "")
        parent = self.load(parent_id) if parent_id else None
        record = PlanningRevisionRecord(
            planning_id=planning_id, revision_id=revision_id or new_planning_id("revision"),
            novel_id=self.novel_id, revision=(parent.revision + 1) if parent else 1,
            parent_revision_id=parent.revision_id if parent else "",
            source_revision=source_revision or (parent.revision_id if parent else ""),
            branch_id=branch_id,
            status=status, source=source, content_digest=planning_digest(plan), note=note,
            plan=plan)
        target = self.revision_path(record.revision_id)
        if target.exists():
            raise PlanningRepositoryError("PLANNING_REVISION_IMMUTABLE",
                                          f"revision 已存在，不能覆盖：{record.revision_id}")
        self._atomic_write(target, StoredPlanningRevision(revision=record).model_dump(mode="json"))
        index.planning_id = index.planning_id or planning_id
        index.novel_id = self.novel_id
        if record.revision_id not in index.revisions:
            index.revisions.append(record.revision_id)
        index.branches[branch_id] = record.revision_id
        self._save_index(index)
        return record

    save = create

    def revise(self, base_revision_id: str, patch_plan: StoryPlanningIR, *,
               branch_id: str = "", status: RevisionStatus = "proposed", note: str = "",
               source: RevisionSource = "author", on_conflict: str = "reject",
               ) -> PlanningRevisionRecord:
        """基于某个 revision 生成新 revision；supplied 冲突默认拒绝（不自动选择）。"""

        base = self.load(base_revision_id)
        patch = patch_plan
        if not patch.planning_id:
            payload = patch.model_dump(mode="json")
            payload["planning_id"] = base.planning_id
            patch = validate_planning_ir(payload)
        conflict = self.conflicts_for(base, patch)
        if conflict.items and on_conflict != "preserve":
            raise PlanningConflictError(conflict)
        plan = patch if not conflict.items else merge_supplied(base.plan, patch)[0]
        return self.create(plan, branch_id=branch_id or base.branch_id, source=source,
                           status=status, note=note, parent_revision_id=base.revision_id)

    def conflicts_for(self, base: PlanningRevisionRecord,
                      patch_plan: StoryPlanningIR) -> PlanningConflict:
        """只报告冲突，不写任何文件。"""

        _, protected = merge_supplied(base.plan, patch_plan)
        items = []
        for identifier in protected:
            base_entry = _entry_by_id(base.plan, identifier)
            patch_entry = _entry_by_id(patch_plan, identifier)
            items.append(PlanningConflictItem(
                stable_id=identifier,
                domain=_domain_of_entry(base_entry[0] if base_entry else ""),
                message="generated / inferred 不能覆盖 supplied 内容",
                base_provenance=getattr(base_entry[1], "provenance", "") if base_entry else "",
                incoming_provenance=getattr(patch_entry[1], "provenance", "") if patch_entry else ""))
        return PlanningConflict(
            novel_id=self.novel_id, base_revision_id=base.revision_id, items=items,
            message="; ".join(item.stable_id for item in items)[:300])

    # ---------------------------------------------------------------- 读
    def load(self, revision_id: str) -> PlanningRevisionRecord:
        path = self.revision_path(revision_id)
        if not path.is_file():
            raise PlanningRepositoryError("PLANNING_REVISION_NOT_FOUND",
                                          f"找不到 revision {revision_id}")
        try:
            stored = StoredPlanningRevision.model_validate(
                json.loads(path.read_text(encoding="utf-8-sig")))
        except (OSError, UnicodeError, json.JSONDecodeError, ValidationError) as exc:
            raise PlanningRepositoryError("PLANNING_REVISION_READ_FAILED",
                                          f"无法读取 revision {revision_id}") from exc
        record = stored.revision
        index = self._load_index()
        if revision_id in index.superseded_revisions and record.status != "superseded":
            record = record.model_copy(update={"status": "superseded"})
        return record

    def verify_digest(self, revision_id: str) -> str:
        record = self.load(revision_id)
        digest = planning_digest(record.plan)
        if digest != record.content_digest:
            raise PlanningRepositoryError(
                "PLANNING_CONTENT_DIGEST_MISMATCH",
                f"revision {revision_id} 内容摘要不一致：{record.content_digest} != {digest}")
        return digest

    def list_revisions(self, *, branch_id: str = "") -> list[PlanningRevisionMeta]:
        index = self._load_index()
        if branch_id:
            head_id = index.branches.get(branch_id, "")
            if not head_id:
                return []
            return self.lineage(head_id)
        rows: list[PlanningRevisionMeta] = []
        for revision_id in index.revisions:
            record = self.load(revision_id)
            rows.append(PlanningRevisionMeta.model_validate(
                record.model_dump(exclude={"plan"})))
        rows.sort(key=lambda row: (row.revision, row.created_at))
        return rows

    def list_branches(self) -> dict[str, str]:
        return dict(self._load_index().branches)

    def resolve_branch_head(self, branch_id: str = "main") -> PlanningRevisionRecord | None:
        revision_id = self._load_index().branches.get(branch_id, "")
        return self.load(revision_id) if revision_id else None

    def lineage(self, revision_id: str) -> list[PlanningRevisionMeta]:
        rows: list[PlanningRevisionMeta] = []
        current = self.load(revision_id)
        while True:
            rows.append(PlanningRevisionMeta.model_validate(current.model_dump(exclude={"plan"})))
            if not current.parent_revision_id:
                break
            current = self.load(current.parent_revision_id)
        return list(reversed(rows))

    def compare(self, base_revision_id: str, target_revision_id: str) -> PlanningDiff:
        base = self.load(base_revision_id)
        target = self.load(target_revision_id)
        return build_diff(self.novel_id, base.plan, target.plan,
                          base_revision=base.revision_id,
                          target_revision=target.revision_id)

    # ---------------------------------------------------------------- branch
    def create_branch(self, branch_id: str, *, from_revision_id: str = "",
                      source_kind: BranchSourceKind = "planning_revision",
                      source_planning_revision_id: str = "") -> str:
        """只允许从 Planning revision 拉分支；Route candidate 不是 Planning branch。"""

        if source_kind not in PLANNING_BRANCH_SOURCE_KINDS:
            raise PlanningRepositoryError(
                "ROUTE_CANDIDATE_IS_NOT_PLANNING_BRANCH",
                "Route Lab candidate 是 simulation candidate，不能注册成 Planning branch；"
                "请先 promote 成新的 Planning revision（source_planning_revision_id 仅供 M7 引用）")
        if not BRANCH_PATTERN.match(branch_id):
            raise PlanningRepositoryError("PLANNING_BRANCH_ID_INVALID",
                                          f"branch id 形态非法：{branch_id}")
        index = self._load_index()
        if branch_id in index.branches:
            raise PlanningRepositoryError("PLANNING_BRANCH_EXISTS", f"分支已存在：{branch_id}")
        base_id = from_revision_id or source_planning_revision_id or \
            index.branches.get("main", "")
        if not base_id:
            raise PlanningRepositoryError("PLANNING_BRANCH_SOURCE_REQUIRED",
                                          "还没有任何 revision 可以拉分支")
        self.load(base_id)
        index.branches[branch_id] = base_id
        self._save_index(index)
        return branch_id

    def promote_revision(self, revision_id: str, *, target_branch: str = "main",
                         note: str = "", new_revision_id: str = ""
                         ) -> PlanningRevisionRecord:
        """提升为正式规划：产生新的 confirmed revision，来源 revision 原样保留。"""

        source_revision = self.load(revision_id)
        if not BRANCH_PATTERN.match(target_branch):
            raise PlanningRepositoryError("PLANNING_BRANCH_ID_INVALID",
                                          f"branch id 形态非法：{target_branch}")
        index = self._load_index()
        parent_id = index.branches.get(target_branch, "")
        record = self.create(source_revision.plan, branch_id=target_branch,
                             source=source_revision.source, status="confirmed",
                             note=note or f"promote {source_revision.revision_id}",
                             parent_revision_id=parent_id,
                             source_revision=source_revision.revision_id,
                             revision_id=new_revision_id)
        return record

    def rollback_head(self, to_revision_id: str, *, branch_id: str = "main",
                      note: str = "", new_revision_id: str = ""
                      ) -> PlanningRevisionRecord:
        """回滚：复制历史内容生成新 revision，并把被替换的 head 记进 superseded（历史不删除）。"""

        target = self.load(to_revision_id)
        index = self._load_index()
        current_id = index.branches.get(branch_id, "")
        record = self.create(target.plan, branch_id=branch_id, source=target.source,
                             status="rolled_back",
                             note=note or f"rollback to {target.revision_id}",
                             parent_revision_id=current_id,
                             source_revision=target.revision_id,
                             revision_id=new_revision_id)
        if current_id:
            index = self._load_index()
            if current_id not in index.superseded_revisions:
                index.superseded_revisions.append(current_id)
                self._save_index(index)
        return record

    @staticmethod
    def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        body = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(body)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def _entry_by_id(plan: StoryPlanningIR, identifier: str):
    for kind, model in iter_planning_entries(plan):
        if entry_id(kind, model) == identifier:
            return kind, model
    return None


def _domain_of_entry(kind: str) -> str:
    return {"rule": "world", "character": "character", "char_arc": "character",
            "relationship_arc": "relationship", "faction": "faction",
            "faction_arc": "faction", "location": "location", "truth": "information",
            "information_arc": "information", "information_move": "information",
            "foreshadow": "foreshadow", "foreshadow_move": "foreshadow",
            "track": "progression", "milestone": "progression", "node": "plot",
            "volume": "volume", "arc": "arc", "timeline_entry": "timeline"}.get(kind, "meta")


__all__ = [
    "BRANCH_PATTERN",
    "DEFAULT_PLANNING_PATH",
    "PlanningConflict",
    "PlanningConflictError",
    "PlanningConflictItem",
    "PlanningIndex",
    "PlanningRepository",
    "PlanningRepositoryError",
    "PlanningRevisionMeta",
    "PlanningRevisionRecord",
    "StoredPlanningRevision",
]
