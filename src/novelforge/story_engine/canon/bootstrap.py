"""C10：CanonBootstrap（旧项目无 Canon DB 也能启动）+ 原子 rebuild + CoverageReport。"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from novelforge.models import StrictModel

from .graph import CanonGraph, CanonGraphValidator
from .models import CanonSourceMapping
from .repository import CanonRepository
from .service import CanonService
from .sync import StoryStateCanonSync

BootstrapSource = Literal["story_state", "content_pack", "profile", "route", "foreshadow",
                          "outline", "inferred"]
CONFIDENCE: dict[str, float] = {"story_state": 1.0, "content_pack": 0.9, "profile": 0.8,
                                "route": 0.7, "foreshadow": 0.7, "outline": 0.6, "inferred": 0.3}
PROVENANCE: dict[str, str] = {"story_state": "confirmed", "content_pack": "imported",
                              "profile": "imported", "route": "imported", "foreshadow": "imported",
                              "outline": "imported", "inferred": "inferred"}


class CanonCoverageReport(StrictModel):
    novel_id: str = ""
    fact_coverage: float = Field(default=0.0, ge=0, le=1)
    event_coverage: float = Field(default=0.0, ge=0, le=1)
    knowledge_coverage: float = Field(default=0.0, ge=0, le=1)
    foreshadow_coverage: float = Field(default=0.0, ge=0, le=1)
    source_ref_coverage: float = Field(default=0.0, ge=0, le=1)
    missing_areas: list[str] = Field(default_factory=list)
    low_confidence_items: list[str] = Field(default_factory=list)
    imported: dict[str, int] = Field(default_factory=dict)
    partial: bool = False
    note: str = "CANON_PARTIAL：Canon 不完整 ≠ 故事里没发生"


class BootstrapResult(StrictModel):
    report: CanonCoverageReport
    created: dict[str, int] = Field(default_factory=dict)


class CanonBootstrap:
    """来源优先级：StoryState > ContentPack > Profile > Route > Foreshadow > Outline > 自然语言推断。"""

    def __init__(self, repository: CanonRepository) -> None:
        self.repository = repository
        self.sync = StoryStateCanonSync(repository)
        self.service = CanonService(repository)

    def bootstrap(self, novel_id: str, *, state: dict[str, Any] | None = None,
                  content_pack: dict[str, Any] | None = None,
                  profile: dict[str, Any] | None = None,
                  route: dict[str, Any] | None = None,
                  foreshadows: list[dict[str, Any]] | None = None,
                  outline_metadata: list[dict[str, Any]] | None = None) -> BootstrapResult:
        created = {"story_state": 0, "content_pack": 0, "profile": 0, "route": 0,
                   "foreshadow": 0, "outline": 0}
        if state:
            result = self.sync.sync(novel_id, state)
            created["story_state"] = result["facts"] + result["knowledge"] + result["foreshadows"]
        if content_pack:
            created["content_pack"] = self._import_pack(novel_id, content_pack)
        if profile:
            created["profile"] = self._import_profile(novel_id, profile)
        for label, rows, key in (("route", route, "route"), ("foreshadow", foreshadows, "foreshadow"),
                                 ("outline", outline_metadata, "outline")):
            if not rows:
                continue
            items = rows if isinstance(rows, list) else rows.get("items") or []
            for index, row in enumerate(items):
                stable_key = f"{key}:{row.get('id') or row.get('event_id') or index}"
                fact = self.service.new_fact(
                    novel_id=novel_id, category=key,
                    description=str(row.get("summary") or row.get("title") or row.get("goal") or ""))
                fact = fact.model_copy(update={"provenance": PROVENANCE[key], "source_type": "imported"})
                self.service.import_fact(fact, source_type="imported", source_stable_key=stable_key)
                created[key] += 1
        report = self.coverage(novel_id, imported=created)
        return BootstrapResult(report=report, created=created)

    # ---- 导入辅助 ---------------------------------------------------------
    def _import_pack(self, novel_id: str, pack: dict[str, Any]) -> int:
        count = 0
        for row in (pack.get("foreshadows") or []):
            stable = f"content_pack:foreshadow:{row.get('id', '')}"
            fact = self.service.new_fact(novel_id=novel_id, category="foreshadow",
                                         description=str(row.get("title", "")))
            fact = fact.model_copy(update={"provenance": "imported", "source_type": "imported"})
            self.service.import_fact(fact, source_type="imported", source_stable_key=stable)
            count += 1
        return count

    def _import_profile(self, novel_id: str, profile: dict[str, Any]) -> int:
        count = 0
        for stage in ((profile.get("future_plan") or {}).get("stages") or []):
            stable = f"profile:stage:{stage.get('id', '')}"
            fact = self.service.new_fact(novel_id=novel_id, category="stage",
                                         description=str(stage.get("title", "")))
            fact = fact.model_copy(update={"provenance": "imported", "source_type": "imported",
                                           "status": "planned"})
            self.service.import_fact(fact, source_type="imported", source_stable_key=stable)
            count += 1
        return count

    # ---- coverage ---------------------------------------------------------
    def coverage(self, novel_id: str, *, imported: dict[str, int] | None = None,
                 expected: dict[str, int] | None = None) -> CanonCoverageReport:
        expected = expected or {}
        facts = self.repository.facts(novel_id)
        events = self.repository.events(novel_id)
        knowledge = self.repository.knowledge(novel_id)
        foreshadows = self.repository.foreshadows(novel_id)
        mappings = self.repository._connection.execute(
            "SELECT COUNT(*) AS n FROM canon_source_mappings WHERE novel_id = ?",
            (novel_id,)).fetchone()["n"]
        with_source = sum(1 for f in facts if f.source_refs or f.first_occurrence_ref)

        def ratio(actual: int, want: int) -> float:
            if want <= 0:
                return 1.0 if actual else 0.0
            return round(min(1.0, actual / want), 3)

        low_confidence = [f.fact_id for f in facts if f.provenance in ("inferred", "generated")]
        missing = []
        if not events:
            missing.append("events")
        if not foreshadows:
            missing.append("foreshadows")
        if not with_source:
            missing.append("source_refs")
        fact_cov = ratio(len(facts), expected.get("facts", len(facts)))
        event_cov = ratio(len(events), expected.get("events", len(events)))
        knowledge_cov = ratio(len(knowledge), expected.get("knowledge", len(knowledge)))
        foreshadow_cov = ratio(len(foreshadows), expected.get("foreshadows", len(foreshadows)))
        source_cov = round(with_source / len(facts), 3) if facts else 0.0
        partial = min(fact_cov, event_cov, knowledge_cov, foreshadow_cov, source_cov) < 1.0
        return CanonCoverageReport(
            novel_id=novel_id, fact_coverage=fact_cov, event_coverage=event_cov,
            knowledge_coverage=knowledge_cov, foreshadow_coverage=foreshadow_cov,
            source_ref_coverage=source_cov, missing_areas=missing,
            low_confidence_items=low_confidence, imported=imported or {}, partial=partial)

    # ---- 原子 rebuild -----------------------------------------------------
    def rebuild(self, novel_id: str, *, state: dict[str, Any] | None = None,
                content_pack: dict[str, Any] | None = None,
                profile: dict[str, Any] | None = None) -> BootstrapResult:
        """snapshot → candidate → validate → swap；任何失败保留原 DB。"""

        snapshot = self.repository.export_json(novel_id)
        candidate_dir = Path(tempfile.mkdtemp(prefix="canon_rebuild_"))
        candidate_path = candidate_dir / "candidate.sqlite"
        candidate = CanonRepository(candidate_path)
        try:
            candidate.import_json(snapshot)
            bootstrap = CanonBootstrap(candidate)
            result = bootstrap.bootstrap(novel_id, state=state, content_pack=content_pack,
                                         profile=profile)
            findings = self._validate_candidate(candidate, novel_id)
            if findings:
                return BootstrapResult(
                    report=result.report.model_copy(
                        update={"note": f"REBUILD_REJECTED：{'; '.join(findings[:3])}"}),
                    created=result.created)
            # commit：把候选数据合并回原 DB（不 DROP、不删除）
            payload = candidate.export_json(novel_id)
            self.repository.import_json(payload)
            for row in candidate._connection.execute(
                    "SELECT * FROM canon_source_mappings WHERE novel_id = ?", (novel_id,)).fetchall():
                self.repository.save_mapping(CanonSourceMapping(
                    novel_id=row["novel_id"], source_type=row["source_type"],
                    source_stable_key=row["source_stable_key"], canon_type=row["canon_type"],
                    canon_id=row["canon_id"], created_at=row["created_at"]))
            return BootstrapResult(report=result.report, created=result.created)
        except Exception as exc:  # noqa: BLE001 - 失败保留原 DB
            return BootstrapResult(
                report=CanonCoverageReport(novel_id=novel_id,
                                           note=f"REBUILD_FAILED_KEPT_ORIGINAL：{exc}"[:200]),
                created={})
        finally:
            candidate.close()
            shutil.rmtree(candidate_dir, ignore_errors=True)

    @staticmethod
    def _validate_candidate(repository: CanonRepository, novel_id: str) -> list[str]:
        findings: list[str] = []
        # C11 加固：通过唯一转换入口构建全量图（含 facts / prerequisites / dependencies），
        # 否则 KNOWLEDGE_BEFORE_FACT / CAUSAL_CYCLE 在 rebuild 校验里永远不可达。
        graph = CanonGraph.from_repository(repository, novel_id)
        for item in CanonGraphValidator(graph).run():
            if item["code"] in ("CAUSAL_CYCLE", "KNOWLEDGE_BEFORE_FACT"):
                findings.append(item["code"])
        return findings
