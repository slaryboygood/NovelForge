"""M9：Chapter IR artifact 持久化（staging → promote → official refs）。

- staging：candidate 先写 `chapter_ir/staging/<candidate_id>.json`（proposal，非正式）；
- official：revision 创建成功后写 `chapter_ir/<planning_revision_id>/<arc_id>.json`，
  绑定 planning_revision_id / arc_id / source_digest / chapter_ir_digest / candidate_id；
- 不产生"没有版本关联的第二 truth"：official 文档必须能被 Planning revision 的
  `arc.chapter_refs` + `arc.chapter_ir_digest` 验证；对不上就是 orphan，可修复或丢弃。
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import Field

from novelforge.models import StrictModel
from novelforge.story_engine.chapter_ir.models import ChapterSemanticIR

from .chapter_compiler import ChapterCompilationCandidate
from .findings import PlanningFinding, add_finding
from .versioning import planning_digest

CHAPTER_IR_SCHEMA_VERSION = 1


class ArcChapterIRDocument(StrictModel):
    """一个 Arc 的正式 Chapter IR 文档（绑定 planning revision）。"""

    schema_version: int = CHAPTER_IR_SCHEMA_VERSION
    planning_revision_id: str = Field(default="", max_length=64)
    arc_id: str = Field(default="", max_length=64)
    source_revision_id: str = Field(default="", max_length=64)
    source_digest: str = Field(default="", max_length=64)
    candidate_id: str = Field(default="", max_length=64)
    compiler_version: str = Field(default="", max_length=32)
    chapter_ir_digest: str = Field(default="", max_length=64)
    chapter_ids: list[str] = Field(default_factory=list)
    chapters: list[ChapterSemanticIR] = Field(default_factory=list)
    committed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    non_authoritative: bool = False


class ArcChapterIndex(StrictModel):
    schema_version: int = CHAPTER_IR_SCHEMA_VERSION
    planning_revision_id: str = Field(default="", max_length=64)
    arcs: dict[str, dict[str, Any]] = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ChapterIRIntegrityReport(StrictModel):
    revision_id: str = Field(default="", max_length=64)
    ok: bool = True
    missing_arc_ids: list[str] = Field(default_factory=list)
    digest_mismatch_arc_ids: list[str] = Field(default_factory=list)
    orphan_staging_candidate_ids: list[str] = Field(default_factory=list)
    repaired_arc_ids: list[str] = Field(default_factory=list)
    findings: list[PlanningFinding] = Field(default_factory=list)


def chapter_ir_digest(chapters: list[ChapterSemanticIR]) -> str:
    payload = [item.model_dump(mode="json") for item in
               sorted(chapters, key=lambda row: row.chapter_uuid)]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True)
                          .encode("utf-8")).hexdigest()[:16]


class ChapterIRStore:
    """chapter IR artifact 仓储（原子写；staging 与 official 分离）。"""

    def __init__(self, project_root: Path, novel_id: str,
                 *, root: Path | str = "novel/authoring/story_engine/planning") -> None:
        base = (Path(root).resolve() if Path(root).is_absolute()
                else (project_root / Path(root)).resolve())
        self.root = base / novel_id / "chapter_ir"
        self.staging_root = self.root / "staging"

    # ---------------------------------------------------------------- paths
    def staging_path(self, candidate_id: str) -> Path:
        return self.staging_root / f"{candidate_id}.json"

    def revision_root(self, planning_revision_id: str) -> Path:
        return self.root / planning_revision_id

    def arc_path(self, planning_revision_id: str, arc_id: str) -> Path:
        return self.revision_root(planning_revision_id) / f"{arc_id}.json"

    def index_path(self, planning_revision_id: str) -> Path:
        return self.revision_root(planning_revision_id) / "index.json"

    # ---------------------------------------------------------------- staging
    def stage_candidate(self, candidate: ChapterCompilationCandidate) -> str:
        digest = chapter_ir_digest(candidate.chapter_irs)
        payload = candidate.model_dump(mode="json")
        payload["staged_chapter_ir_digest"] = digest
        self._atomic_write(self.staging_path(candidate.candidate_id), payload)
        return digest

    def load_staged(self, candidate_id: str) -> dict[str, Any] | None:
        path = self.staging_path(candidate_id)
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return None

    def staged_candidate_ids(self) -> list[str]:
        if not self.staging_root.is_dir():
            return []
        return sorted(item.stem for item in self.staging_root.glob("*.json"))

    def staged_candidate(self, candidate_id: str) -> ChapterCompilationCandidate | None:
        payload = self.load_staged(candidate_id)
        if payload is None:
            return None
        payload = {key: value for key, value in payload.items()
                   if key != "staged_chapter_ir_digest"}
        try:
            return ChapterCompilationCandidate.model_validate(payload)
        except Exception:  # noqa: BLE001
            return None

    # ---------------------------------------------------------------- official
    def commit_candidate(self, candidate: ChapterCompilationCandidate, *,
                         planning_revision_id: str,
                         chapter_ir_digest_value: str = "") -> ArcChapterIRDocument:
        digest = chapter_ir_digest_value or chapter_ir_digest(candidate.chapter_irs)
        document = ArcChapterIRDocument(
            planning_revision_id=planning_revision_id, arc_id=candidate.arc_id,
            source_revision_id=candidate.source_revision_id,
            source_digest=candidate.source_digest, candidate_id=candidate.candidate_id,
            compiler_version=candidate.compiler_version,
            chapter_ir_digest=digest,
            chapter_ids=[item.chapter_uuid for item in candidate.chapter_irs],
            chapters=list(candidate.chapter_irs))
        self._atomic_write(self.arc_path(planning_revision_id, candidate.arc_id),
                           document.model_dump(mode="json"))
        index = self.load_index(planning_revision_id)
        index.arcs[candidate.arc_id] = {
            "chapter_ids": list(document.chapter_ids), "chapter_ir_digest": digest,
            "chapter_count": len(document.chapter_ids),
            "candidate_id": candidate.candidate_id}
        self._atomic_write(self.index_path(planning_revision_id),
                           index.model_dump(mode="json"))
        global_index = self.load_global_index()
        global_index[candidate.arc_id] = {
            "planning_revision_id": planning_revision_id,
            "chapter_ir_digest": digest, "chapter_count": len(document.chapter_ids),
            "candidate_id": candidate.candidate_id}
        self._atomic_write(self.global_index_path(), global_index)
        return document

    def global_index_path(self) -> Path:
        return self.root / "index.json"

    def load_global_index(self) -> dict[str, dict[str, Any]]:
        path = self.global_index_path()
        if not path.is_file():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}

    def load_arc_in_lineage(self, repository: Any, revision_id: str,
                            arc_id: str) -> ArcChapterIRDocument | None:
        """official artifact 可能写在更早的 revision 上（chapter_refs 沿 lineage 继承）。"""

        entry = self.load_global_index().get(arc_id) or {}
        if entry.get("planning_revision_id"):
            document = self.load_arc(str(entry["planning_revision_id"]), arc_id)
            if document is not None:
                return document
        seen: set[str] = set()
        current = revision_id
        while current and current not in seen:
            seen.add(current)
            document = self.load_arc(current, arc_id)
            if document is not None:
                return document
            try:
                current = repository.load(current).parent_revision_id
            except Exception:  # noqa: BLE001
                break
        return None

    def load_index(self, planning_revision_id: str) -> ArcChapterIndex:
        path = self.index_path(planning_revision_id)
        if not path.is_file():
            return ArcChapterIndex(planning_revision_id=planning_revision_id)
        try:
            return ArcChapterIndex.model_validate(json.loads(path.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001
            return ArcChapterIndex(planning_revision_id=planning_revision_id)

    def load_arc(self, planning_revision_id: str,
                 arc_id: str) -> ArcChapterIRDocument | None:
        path = self.arc_path(planning_revision_id, arc_id)
        if not path.is_file():
            return None
        try:
            return ArcChapterIRDocument.model_validate(
                json.loads(path.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001
            return None

    def list_arcs(self, planning_revision_id: str) -> list[str]:
        return sorted(self.load_index(planning_revision_id).arcs)

    # ---------------------------------------------------------------- integrity
    def verify(self, repository: Any, revision_id: str) -> ChapterIRIntegrityReport:
        """revision 的 chapter_refs / digest 与 artifact 是否一致（orphan 检测）。"""

        record = repository.load(revision_id)
        report = ChapterIRIntegrityReport(revision_id=revision_id)
        committed_candidates: set[str] = set()
        for arc in record.plan.arcs:
            if arc.detail_level != "chapter_ready":
                continue
            document = self.load_arc_in_lineage(repository, revision_id, arc.arc_id)
            if document is None:
                report.missing_arc_ids.append(arc.arc_id)
                add_finding(report.findings, "CHAPTER_IR_ARTIFACT_MISSING", "ERROR",
                            "chapter", arc.arc_id, "chapter_ready Arc 没有 official chapter IR",
                            related=(arc.arc_id,))
                continue
            committed_candidates.add(document.candidate_id)
            digest = chapter_ir_digest(document.chapters)
            if arc.chapter_ir_digest and arc.chapter_ir_digest != digest:
                report.digest_mismatch_arc_ids.append(arc.arc_id)
                add_finding(report.findings, "CHAPTER_IR_DIGEST_MISMATCH", "ERROR", "chapter",
                            arc.arc_id, "revision 记录的 chapter_ir_digest 与 artifact 不一致",
                            related=(arc.arc_id,))
            if arc.chapter_refs and set(arc.chapter_refs) != set(document.chapter_ids):
                add_finding(report.findings, "CHAPTER_IR_REF_MISMATCH", "ERROR", "chapter",
                            arc.arc_id, "revision chapter_refs 与 artifact chapter_ids 不一致",
                            related=(arc.arc_id,))
        if record.plan.arcs and not committed_candidates:
            report.orphan_staging_candidate_ids = [
                item for item in self.staged_candidate_ids()
                if item and self.load_staged(item) is not None]
        report.ok = not report.findings
        return report

    def repair(self, repository: Any, revision_id: str) -> ChapterIRIntegrityReport:
        """从 staging 补写缺失的 official artifact（崩溃恢复；不新建 revision）。"""

        record = repository.load(revision_id)
        staged_by_arc: dict[str, dict[str, Any]] = {}
        for candidate_id in self.staged_candidate_ids():
            payload = self.load_staged(candidate_id) or {}
            arc_id = str(payload.get("arc_id") or "")
            if arc_id and payload.get("source_revision_id"):
                staged_by_arc.setdefault(arc_id, payload)
        repaired: list[str] = []
        for arc in record.plan.arcs:
            if arc.detail_level != "chapter_ready":
                continue
            if self.load_arc(revision_id, arc.arc_id) is not None:
                continue
            payload = staged_by_arc.get(arc.arc_id)
            if payload is None:
                continue
            candidate = self.staged_candidate(str(payload.get("candidate_id") or ""))
            if candidate is None:
                continue
            self.commit_candidate(candidate, planning_revision_id=revision_id,
                                  chapter_ir_digest_value=arc.chapter_ir_digest)
            repaired.append(arc.arc_id)
        report = self.verify(repository, revision_id)
        report.repaired_arc_ids = repaired
        return report

    def arc_summaries(self, planning_revision_id: str) -> list[dict[str, Any]]:
        index = self.load_index(planning_revision_id)
        return [{"arc_id": arc_id, **row} for arc_id, row in sorted(index.arcs.items())]

    # ---------------------------------------------------------------- atomic
    @staticmethod
    def _atomic_write(path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        body = json.dumps(payload, ensure_ascii=False, indent=1) + "\n"
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(body)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def chapter_digest(chapters: list[ChapterSemanticIR]) -> str:
    return planning_digest([item.model_dump(mode="json") for item in chapters])


__all__ = [
    "CHAPTER_IR_SCHEMA_VERSION",
    "ArcChapterIRDocument",
    "ArcChapterIndex",
    "ChapterIRIntegrityReport",
    "ChapterIRStore",
    "chapter_digest",
    "chapter_ir_digest",
]
