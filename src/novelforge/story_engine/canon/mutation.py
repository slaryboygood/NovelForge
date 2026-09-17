"""C11：Canon Fault Injection / Mutation Test —— 主动制造错误，验证防线真的会触发。

定位：本模块只服务测试与审计（fault injection / defense coverage），
生产路径（planner / context / graph / bootstrap）不导入它，也不含 mutation 逻辑。

核心断言不是「validator 会报错」，而是：

    injected fault → 预期防线触发 → 正式 StoryState / Canon / Outline 零污染。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from novelforge.story_engine import outline_forge

from .bootstrap import CanonBootstrap
from .chapters import ChapterLineage, ChapterLineageStore
from .context import CanonContextBuilder, contains_writer_metadata, sanitize_writer_text
from .gate import SchemaGateError, validate_chapter_plan
from .graph import CanonGraph, CanonGraphValidator
from .models import (
    CanonEvent,
    CanonFact,
    CanonForeshadow,
    CanonKnowledge,
    CanonRenderRef,
    CanonSourceMapping,
    CanonSourceRef,
)
from .planner import (
    ArcIntent,
    CanonAwareOutlinePlanner,
    CanonOutlineFlags,
    FileOutlineSink,
    PlanResult,
)
from .prose import (
    audit_prose_report,
    chapter_frame_findings,
    cross_field_findings,
    dog_role_object_findings,
    dog_role_presence_findings,
    dog_role_recompute,
    dog_role_alignment,
    dog_payload_evidence_findings,
    first_occurrence_findings,
    future_canon_leak_findings,
    state_transition_findings,
    irreversible_state_findings,
    narrative_lifecycle_findings,
    orphaned_reference_fragments,
    validate_sample_pack,
    within_chapter_state_findings,
)
from .repository import CanonRepository
from .semantic import EventSemanticSignature, LocalSemanticIndex
from .service import CanonService, CanonServiceError
from .sync import StoryStateCanonSync, source_stable_key
from .validator import SourceReferenceValidator

TARGET_LAYERS = ("schema", "context", "canon", "source_ref", "graph", "semantic", "planner",
                 "outline", "bootstrap", "repository", "writer")
DIGEST_KEYS = ("story_state", "canon", "outline", "source_mapping", "chapter_lineage")

# P0：必须从尽量真实的整链入口注入（planner / bootstrap / lineage / sync），不能只调 validator
P0_INTEGRATION_MUTATIONS = ("MUT-001", "MUT-006", "MUT-007", "MUT-012", "MUT-019",
                            "MUT-023", "MUT-028", "MUT-031", "MUT-034")


# --------------------------------------------------------------------------- 结构与工具


def _sha1(payload: Any) -> str:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _dir_digest(path: Path) -> str:
    rows: list[list[str]] = []
    for file in sorted(Path(path).rglob("*")):
        if file.is_file():
            rows.append([str(file.relative_to(path)),
                         file.read_text(encoding="utf-8", errors="replace")])
    return _sha1(rows)


@dataclass
class MutationObservation:
    """一次 fault injection 的实际结果（由 case 的 mutation 返回）。"""

    detected: bool = False
    detector: str = ""
    codes: list[str] = field(default_factory=list)
    severity: str = ""
    persisted: bool = False
    note: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class MutationResult:
    mutation_id: str
    category: str
    target_layer: str
    description: str
    status: str                      # passed / failed / blocked
    integration: bool = False
    expected_detector: str = ""
    detected: bool = False
    detector: str = ""
    codes: list[str] = field(default_factory=list)
    severity: str = ""
    persisted: bool = False
    digest_checks: dict[str, str] = field(default_factory=dict)
    violations: list[str] = field(default_factory=list)
    note: str = ""
    error: str = ""

    @property
    def passed(self) -> bool:
        return self.status == "passed"

    @property
    def polluted(self) -> bool:
        return any(item.endswith("_polluted") for item in self.violations)


@dataclass
class MutationCase:
    mutation_id: str
    category: str
    target_layer: str
    description: str
    expected_detector: str
    expected_codes: list[str]
    expected_severity: str
    setup: Callable[["MutationRuntime"], None]
    mutation: Callable[["MutationRuntime"], MutationObservation]
    should_persist: bool = False
    should_mutate_story_state: bool = False
    should_mutate_canon: bool = False
    should_mutate_outline: bool = False
    should_mutate_source_mapping: bool = False
    should_mutate_chapter_lineage: bool = False
    cleanup: Callable[["MutationRuntime"], None] | None = None
    integration: bool = False
    expected_code: str = ""          # 兼容任务书字段：主 expected code
    result: MutationResult | None = None

    def expected_digest_changes(self) -> dict[str, bool]:
        return {"story_state": self.should_mutate_story_state,
                "canon": self.should_mutate_canon,
                "outline": self.should_mutate_outline,
                "source_mapping": self.should_mutate_source_mapping,
                "chapter_lineage": self.should_mutate_chapter_lineage}


class MutationRuntime:
    """每个 mutation case 一个隔离工作区（独立 Canon DB / 独立 outline sink）。"""

    def __init__(self, root: Path, *, novel_id: str = "novel_mut") -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.novel_id = novel_id
        self.repository = CanonRepository(self.root / "canon.sqlite")
        self.official_dir = self.root / "official_outline"
        self.shadow_dir = self.root / "shadow_outline"
        self.official_dir.mkdir(parents=True, exist_ok=True)
        self.shadow_dir.mkdir(parents=True, exist_ok=True)
        self.official_sink = FileOutlineSink(self.official_dir)
        self.shadow_sink = FileOutlineSink(self.shadow_dir)
        self.story_state: dict[str, Any] = {}
        self.artifacts: dict[str, Any] = {}
        self.baseline: dict[str, str] = {}

    # ---- digest -----------------------------------------------------------
    def digests(self) -> dict[str, str]:
        repository = self.repository
        mappings = sorted(
            (str(row["source_type"]), str(row["source_stable_key"]), str(row["canon_type"]),
             str(row["canon_id"]))
            for row in repository._connection.execute(
                "SELECT * FROM canon_source_mappings WHERE novel_id = ?",
                (self.novel_id,)).fetchall())
        lineage = sorted(
            (str(row["chapter_uuid"]), str(row["novel_id"]), str(row["display_number"]),
             str(row["status"]), str(row["superseded_by"]), str(row["merged_into"]))
            for row in repository._connection.execute(
                "SELECT * FROM canon_chapter_lineage WHERE novel_id = ?",
                (self.novel_id,)).fetchall())
        manifests = repository._connection.execute(
            "SELECT COUNT(*) AS n FROM canon_context_manifests WHERE novel_id = ?",
            (self.novel_id,)).fetchone()["n"]
        return {
            "story_state": _sha1(self.story_state),
            "canon": _sha1(repository.export_json(self.novel_id)),
            "outline": _dir_digest(self.official_dir),
            "source_mapping": _sha1(mappings),
            "chapter_lineage": _sha1(lineage),
            "shadow_artifacts": _dir_digest(self.shadow_dir),
            "context_manifests": str(manifests),
        }

    def close(self) -> None:
        self.repository.close()


def _evaluate(case: MutationCase, runtime: MutationRuntime,
              observation: MutationObservation) -> MutationResult:
    after = runtime.digests()
    expected_changes = case.expected_digest_changes()
    checks: dict[str, str] = {}
    violations: list[str] = []
    for key in DIGEST_KEYS:
        changed = runtime.baseline.get(key) != after.get(key)
        checks[key] = "changed" if changed else "unchanged"
        if changed and not expected_changes.get(key, False):
            violations.append(f"{key}_polluted")
        if expected_changes.get(key, False) and not changed:
            violations.append(f"{key}_not_changed")
    if not observation.detected:
        violations.append("UNDETECTED")
    if case.expected_codes and not set(case.expected_codes) & set(observation.codes):
        violations.append("EXPECTED_CODE_MISMATCH")
    if case.expected_detector and case.expected_detector != observation.detector:
        violations.append("EXPECTED_DETECTOR_MISMATCH")
    if observation.persisted is not case.should_persist:
        violations.append("PERSISTENCE_MISMATCH")
    return MutationResult(
        mutation_id=case.mutation_id, category=case.category, target_layer=case.target_layer,
        description=case.description, status="passed" if not violations else "failed",
        integration=case.integration, expected_detector=case.expected_detector,
        detected=observation.detected,
        detector=observation.detector, codes=list(observation.codes),
        severity=observation.severity, persisted=observation.persisted,
        digest_checks=checks, violations=violations,
        note=observation.note + (f" | checks={observation.extra}" if observation.extra else ""))


def run_mutation_case(case: MutationCase, *, root: Path) -> MutationResult:
    runtime = MutationRuntime(Path(root))
    try:
        case.setup(runtime)
        runtime.baseline = runtime.digests()
        try:
            observation = case.mutation(runtime)
        except Exception as exc:  # noqa: BLE001 - 未预期异常 = blocked（不是 pass）
            return MutationResult(
                mutation_id=case.mutation_id, category=case.category,
                target_layer=case.target_layer, description=case.description,
                status="blocked", integration=case.integration,
                expected_detector=case.expected_detector,
                error=f"{type(exc).__name__}: {exc}"[:300])
        case.result = _evaluate(case, runtime, observation)
        return case.result
    finally:
        if case.cleanup is not None:
            case.cleanup(runtime)
        runtime.close()


@dataclass
class MutationSuiteReport:
    results: list[MutationResult] = field(default_factory=list)

    # ---- 汇总 -------------------------------------------------------------
    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for item in self.results if item.status == "passed")

    @property
    def failed(self) -> int:
        return sum(1 for item in self.results if item.status == "failed")

    @property
    def blocked(self) -> int:
        return sum(1 for item in self.results if item.status == "blocked")

    @property
    def mutation_kill_rate(self) -> float:
        return round(self.passed / self.total, 4) if self.total else 0.0

    @property
    def state_pollution_rate(self) -> float:
        return round(len(self.state_pollution_failures) / self.total, 4) if self.total else 0.0

    @property
    def by_layer(self) -> dict[str, dict[str, int]]:
        summary: dict[str, dict[str, int]] = {}
        for item in self.results:
            row = summary.setdefault(item.target_layer, {"total": 0, "passed": 0, "failed": 0})
            row["total"] += 1
            row["passed" if item.status == "passed" else "failed"] += 1
        return summary

    @property
    def by_detector(self) -> dict[str, int]:
        summary: dict[str, int] = {}
        for item in self.results:
            if item.status == "passed" and item.detector:
                summary[item.detector] = summary.get(item.detector, 0) + 1
        return summary

    @property
    def undetected_mutations(self) -> list[str]:
        return [item.mutation_id for item in self.results if not item.detected]

    @property
    def state_pollution_failures(self) -> list[str]:
        return [item.mutation_id for item in self.results if item.polluted]

    @property
    def expected_detector_mismatch(self) -> list[str]:
        return [item.mutation_id for item in self.results
                if "EXPECTED_DETECTOR_MISMATCH" in item.violations]

    @property
    def blocked_mutations(self) -> list[str]:
        return [item.mutation_id for item in self.results if item.status == "blocked"]

    def ok(self) -> bool:
        return self.total > 0 and self.passed == self.total

    # ---- 报告 -------------------------------------------------------------
    def to_markdown(self) -> str:
        lines = [
            "# Canon Defense Coverage Matrix（C11）",
            "",
            "来源：`run_mutation_suite()` 的真实执行结果（fault injection → 预期防线 → "
            "StoryState / Canon / Outline digest 校验）。",
            "测试：`tests/test_canon_mutation_unit.py`、`tests/test_canon_mutation_integration.py`；"
            "模块：`src/novelforge/story_engine/canon/mutation.py`。",
            "",
            "## 汇总",
            "",
            f"- mutation total：**{self.total}**（passed {self.passed} / failed {self.failed} / "
            f"blocked {self.blocked}）",
            f"- mutation_kill_rate：**{self.mutation_kill_rate:.2%}**",
            f"- state_pollution_rate：**{self.state_pollution_rate:.2%}**"
            f"（{len(self.state_pollution_failures)} 个污染失败）",
            f"- undetected mutations：{self.undetected_mutations or '无'}",
            f"- expected detector mismatch：{self.expected_detector_mismatch or '无'}",
            "",
            "## 分层覆盖（by_layer）",
            "",
            "| target layer | total | passed | failed |",
            "| --- | --- | --- | --- |",
        ]
        for layer in sorted(self.by_layer):
            row = self.by_layer[layer]
            lines.append(f"| {layer} | {row['total']} | {row['passed']} | {row['failed']} |")
        lines += ["", "## 防线命中统计（by_detector）", "", "| detector | passed cases |",
                  "| --- | --- |"]
        for detector in sorted(self.by_detector):
            lines.append(f"| {detector} | {self.by_detector[detector]} |")
        lines += [
            "",
            "## 逐条 mutation",
            "",
            "| Mutation ID | Injected fault | Target layer | Expected detector | Actual detector | "
            "Persist blocked? | StoryState clean? | Canon clean? | Outline clean? | PASS/FAIL |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for item in sorted(self.results, key=lambda row: row.mutation_id):
            persist = "blocked" if not item.persisted else "expected persist"
            lines.append(
                f"| {item.mutation_id} | {item.description} | {item.target_layer} | "
                f"{item.expected_detector or '—'} | {item.detector or '—'} | {persist} | "
                f"{'clean' if item.digest_checks.get('story_state') == 'unchanged' else 'changed'} | "
                f"{'clean' if item.digest_checks.get('canon') == 'unchanged' else 'changed'} | "
                f"{'clean' if item.digest_checks.get('outline') == 'unchanged' else 'changed'} | "
                f"{'PASS' if item.status == 'passed' else item.status.upper()} |")
        lines += ["", "## 逐条备注", ""]
        for item in sorted(self.results, key=lambda row: row.mutation_id):
            detail = f"- **{item.mutation_id}**（{item.codes or '—'}）：{item.note}"
            if item.error:
                detail += f"｜error={item.error}"
            if item.violations:
                detail += f"｜violations={item.violations}"
            lines.append(detail)
        lines.append("")
        return "\n".join(lines)


def run_mutation_suite(*, root: Path, cases: Sequence[MutationCase] | None = None,
                       only: Iterable[str] | None = None) -> MutationSuiteReport:
    selected = list(cases if cases is not None else build_mutation_cases())
    if only is not None:
        wanted = set(only)
        selected = [case for case in selected if case.mutation_id in wanted]
    report = MutationSuiteReport()
    base = Path(root)
    for case in selected:
        report.results.append(run_mutation_case(case, root=base / case.mutation_id))
    return report


# --------------------------------------------------------------------------- fixture builders


def _ref(source_uuid: str, fact_ids: Sequence[str], *,
         provenance: str = "happened") -> dict[str, Any]:
    return {"source_type": "chapter", "source_uuid": source_uuid, "chapter_uuid": source_uuid,
            "source_id": source_uuid, "claimed_fact_ids": list(fact_ids),
            "provenance": provenance}


def _beat(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"beat_id": "BEAT_1", "goal": "进入门禁并确认门后环境",
                            "event_ids": ["EVENT_GATE_OPEN"], "fact_ids": ["FACT_GATE_OPEN"],
                            "participant_ids": ["protagonist"], "location_ids": ["location_gate"]}
    base.update(overrides)
    return base


def _chapter(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "chapter_uuid": "uuid_ch_1", "display_number": 245, "title": "门后的第一层",
        "estimated_words": 3200, "temporal_position": 245, "location": "location_gate",
        "goal": "打开门禁并确认门后环境", "start_state": "队伍带齐装备站在门前",
        "concrete_events": ["主角把旧铭牌按进门前凹槽", "沉重门体在第七次尝试后打开",
                            "队伍沿干燥长廊继续深入"],
        "dog_role": "involved", "dog_action": "伙伴在门前贴地判断震动方向",
        "canon_fact_ids": ["FACT_GATE_OPEN"], "canon_event_ids": [],
        "canon_source_refs": [_ref("uuid_gate", ["FACT_GATE_OPEN"])],
        "participants": ["protagonist"], "locations": ["location_gate"],
        "prerequisites": [], "requires_abilities": [], "grants_abilities": [],
        "requires_identities": [], "grants_identities": [],
        "character_state_effects": [], "knowledge_changes": [], "relationship_changes": [],
        "resource_changes": {}, "ability_changes": [], "identity_changes": [],
        "foreshadow_actions": [], "hook": "长廊尽头传来第二种脚步",
    }
    base.update(overrides)
    return base


def _intent(runtime: MutationRuntime, *, position: int | None = 250,
            arc_id: str = "ARC_GATE") -> ArcIntent:
    return ArcIntent(arc_id=arc_id, novel_id=runtime.novel_id, goal="进入旧时代门禁",
                     volume_ref="V1", participant_ids=["protagonist"],
                     location_ids=["location_gate"], temporal_position=position)


def _planner(runtime: MutationRuntime, *,
             flags: CanonOutlineFlags | None = None) -> CanonAwareOutlinePlanner:
    return CanonAwareOutlinePlanner(runtime.repository, flags=flags or CanonOutlineFlags(),
                                    sink=runtime.official_sink, shadow_sink=runtime.shadow_sink)


def _seed_gate_fact(runtime: MutationRuntime, *, display_number: int = 10) -> str:
    """最小通用 Canon：FACT_GATE_OPEN（happened）+ chapter_uuid + lineage + 正式 outline 基线。"""

    repository = runtime.repository
    repository.save_fact(CanonFact(
        fact_id="FACT_GATE_OPEN", canonical_key="GATE_OPEN", novel_id=runtime.novel_id,
        status="happened", canonical_description="第一次打开旧时代门禁",
        source_type="story_state", provenance="story_state",
        source_refs=[CanonSourceRef(source_type="chapter", source_uuid="uuid_gate",
                                    chapter_uuid="uuid_gate", source_id="uuid_gate")],
        first_occurrence_ref=CanonRenderRef(chapter_uuid="uuid_gate",
                                           display_number=display_number)))
    ChapterLineageStore(repository).register(ChapterLineage(
        chapter_uuid="uuid_gate", novel_id=runtime.novel_id, display_number=display_number,
        title="门禁"))
    runtime.official_sink.write(PlanResult(arc_id="ARC_BASELINE", mode="canon", ok=True))
    runtime.artifacts["gate_fact"] = "FACT_GATE_OPEN"
    return "FACT_GATE_OPEN"


def _story_state(runtime: MutationRuntime) -> dict[str, Any]:
    return {
        "schema_version": 1, "novel_id": runtime.novel_id,
        "characters": {"protagonist": {"name": "主角"}, "partner": {"name": "伙伴"}},
        "factions": {"settlement": {"name": "聚落"}},
        "relationships": [{"source_id": "protagonist", "target_id": "partner",
                           "dimensions": {"trust": "80"}}],
        "knowledge": [{"id": "clue_water", "holders": ["protagonist"], "tick": 2,
                       "source": "action:probe", "source_event": ""}],
        "flags": {"foreshadows": {"fs_tag": {"status": "planted", "reason": "旧铭牌"}}},
        "effect_log": [{"op": "act_scavenge_ruins", "entity": "protagonist",
                        "target": "ruins", "value": 1, "source": "action:scavenge",
                        "data": {"tick": 1}}],
    }


def _codes(result: PlanResult) -> list[str]:
    return [finding.code for finding in result.findings]


def _graph_codes(graph: CanonGraph) -> list[str]:
    return [str(item["code"]) for item in CanonGraphValidator(graph).run()]


def _planner_reject(runtime: MutationRuntime, chapter: dict[str, Any], *,
                    position: int | None = 250, detector: str = "CanonAwareOutlinePlanner.plan",
                    note: str = "", expected: str = "") -> MutationObservation:
    result = _planner(runtime).plan(_intent(runtime, position=position), beats_raw=[_beat()],
                                    chapters_raw=[chapter])
    codes = _codes(result)
    return MutationObservation(detected=not result.ok and (not expected or expected in codes),
                               detector=detector, codes=codes, severity="reject",
                               persisted=bool(result.persisted_path),
                               note=note or "planner 拒绝，未写入正式 outline / Canon")


# --------------------------------------------------------------------------- MUT-001 … 020


def _case_001() -> MutationCase:
    def mutation(runtime: MutationRuntime) -> MutationObservation:
        return _planner_reject(
            runtime, _chapter(canon_source_refs=[_ref("uuid_ambush", ["FACT_GATE_OPEN"])]),
            detector="SourceReferenceValidator.validate_refs",
            expected="SOURCE_REF_SEMANTIC_MISMATCH",
            note="把「伏击章」当成「门禁首次开门」的来源，必须判语义不匹配")

    return MutationCase(
        mutation_id="MUT-001", category="source_integrity", target_layer="source_ref",
        description="错误 source：伏击章被声明支持「门禁首次开门」",
        expected_detector="SourceReferenceValidator.validate_refs",
        expected_codes=["SOURCE_REF_SEMANTIC_MISMATCH"], expected_severity="reject",
        setup=lambda runtime: _seed_gate_fact(runtime), mutation=mutation, integration=True)


def _case_002() -> MutationCase:
    def mutation(runtime: MutationRuntime) -> MutationObservation:
        return _planner_reject(
            runtime, _chapter(canon_fact_ids=["FACT_MISSING_ARCHIVE"],
                              canon_source_refs=[_ref("uuid_missing_archive",
                                                      ["FACT_MISSING_ARCHIVE"],
                                                      provenance="generated")]),
            detector="SourceReferenceValidator.validate_refs",
            expected="SOURCE_REF_MISSING",
            note="source_ref 指向不存在的 fact（UUID 与 fact 均不存在）")

    return MutationCase(
        mutation_id="MUT-002", category="source_integrity", target_layer="source_ref",
        description="缺失 source：引用不存在的 fact / UUID",
        expected_detector="SourceReferenceValidator.validate_refs",
        expected_codes=["SOURCE_REF_MISSING"], expected_severity="reject",
        setup=lambda runtime: _seed_gate_fact(runtime), mutation=mutation, integration=True)


def _case_003() -> MutationCase:
    def setup(runtime: MutationRuntime) -> None:
        _seed_gate_fact(runtime)
        runtime.repository.save_fact(CanonFact(
            fact_id="FACT_FUTURE_REVEAL", canonical_key="FUTURE_REVEAL",
            novel_id=runtime.novel_id, status="planned", canonical_description="潮汐装置的真相",
            source_refs=[CanonSourceRef(source_type="chapter", source_uuid="uuid_future",
                                        chapter_uuid="uuid_future", source_id="uuid_future")],
            first_occurrence_ref=CanonRenderRef(chapter_uuid="uuid_future", display_number=150)))

    def mutation(runtime: MutationRuntime) -> MutationObservation:
        return _planner_reject(
            runtime, _chapter(temporal_position=100, canon_fact_ids=["FACT_FUTURE_REVEAL"],
                              canon_source_refs=[_ref("uuid_future", ["FACT_FUTURE_REVEAL"],
                                                      provenance="planned")]),
            position=100, detector="SourceReferenceValidator.validate_refs",
            expected="SOURCE_REF_FUTURE_LEAK",
            note="cutoff=100 的章节引用 T=150 才出现的事实")

    return MutationCase(
        mutation_id="MUT-003", category="source_integrity", target_layer="source_ref",
        description="未来泄漏：当前章节引用未来事实",
        expected_detector="SourceReferenceValidator.validate_refs",
        expected_codes=["SOURCE_REF_FUTURE_LEAK"], expected_severity="reject",
        setup=setup, mutation=mutation, integration=True)


def _case_004() -> MutationCase:
    def setup(runtime: MutationRuntime) -> None:
        _seed_gate_fact(runtime)
        runtime.repository.save_fact(CanonFact(
            fact_id="FACT_PLANNED_ONLY", canonical_key="PLANNED_ONLY",
            novel_id=runtime.novel_id, status="planned", canonical_description="还没发生的约定",
            source_refs=[CanonSourceRef(source_type="chapter", source_uuid="uuid_planned",
                                        chapter_uuid="uuid_planned", source_id="uuid_planned")]))

    def mutation(runtime: MutationRuntime) -> MutationObservation:
        return _planner_reject(
            runtime, _chapter(canon_fact_ids=["FACT_PLANNED_ONLY"],
                              canon_source_refs=[_ref("uuid_planned", ["FACT_PLANNED_ONLY"],
                                                      provenance="happened")]),
            detector="SourceReferenceValidator.validate_refs",
            expected="SOURCE_REF_STATUS_MISMATCH",
            note="planned fact 被声明为已发生")

    return MutationCase(
        mutation_id="MUT-004", category="status_integrity", target_layer="source_ref",
        description="planned 当成 happened：状态不一致",
        expected_detector="SourceReferenceValidator.validate_refs",
        expected_codes=["SOURCE_REF_STATUS_MISMATCH"], expected_severity="reject",
        setup=setup, mutation=mutation, integration=True)


def _case_005() -> MutationCase:
    detector = "CanonAwareOutlinePlanner.plan + CanonService.update_fact"

    def mutation(runtime: MutationRuntime) -> MutationObservation:
        codes: list[str] = []
        detected = True
        early = _planner(runtime).plan(
            _intent(runtime, position=5), beats_raw=[_beat()],
            chapters_raw=[_chapter(display_number=5, temporal_position=5,
                                   canon_fact_ids=["FACT_GATE_OPEN"],
                                   canon_source_refs=[_ref("uuid_gate", ["FACT_GATE_OPEN"])])])
        codes.extend(_codes(early))
        if "HAPPENED_FACT_REWRITE" not in codes:
            detected = False
        try:
            CanonService(runtime.repository).update_fact(
                "FACT_GATE_OPEN", {"canonical_description": "被改写的描述"})
            detected = False
            codes.append("HAPPENED_FACT_IMMUTABLE_MISSED")
        except CanonServiceError as exc:
            codes.append(exc.code)
            detected = detected and exc.code == "HAPPENED_FACT_IMMUTABLE"
        fact = next(item for item in runtime.repository.facts(runtime.novel_id)
                    if item.fact_id == "FACT_GATE_OPEN")
        if fact.model_copy(update={"immutable": False}).immutable is not True:
            detected = False
            codes.append("IMMUTABLE_FLAG_LOST")
        return MutationObservation(
            detected=detected, detector=detector, codes=codes, severity="reject",
            persisted=False,
            note="happened fact 不可改写：planner 拒绝 + service 拒绝 + 不可变标记保留")

    return MutationCase(
        mutation_id="MUT-005", category="status_integrity", target_layer="canon",
        description="改写 happened fact：描述 / 状态 / 不可变标记",
        expected_detector=detector,
        expected_codes=["HAPPENED_FACT_REWRITE", "HAPPENED_FACT_IMMUTABLE"],
        expected_severity="reject", setup=lambda runtime: _seed_gate_fact(runtime),
        mutation=mutation, integration=True)


def _case_006() -> MutationCase:
    def setup(runtime: MutationRuntime) -> None:
        _seed_gate_fact(runtime)
        repository = runtime.repository
        repository.save_event(CanonEvent(
            event_id="EVENT_TOLL_PLANNED", canonical_key="TOLL_PLANNED", novel_id=runtime.novel_id,
            canonical_name="掠夺队收过路费", semantic_summary="第一次勒索", event_type="major",
            status="planned", location="salt_road", subjects=["raiders", "settlement"]))
        repository.save_event(CanonEvent(
            event_id="EVENT_TOLL_OCCURRED", canonical_key="TOLL_OCCURRED",
            novel_id=runtime.novel_id, canonical_name="掠夺队收过路费", semantic_summary="实际发生",
            event_type="major", status="occurred", location="salt_road",
            subjects=["raiders", "settlement"]))

    def mutation(runtime: MutationRuntime) -> MutationObservation:
        validator = SourceReferenceValidator(runtime.repository)
        conflicts = validator.promotion_conflicts(runtime.novel_id)
        codes = [finding.code for finding in conflicts]
        planned = next(event for event in runtime.repository.events(runtime.novel_id)
                       if event.event_id == "EVENT_TOLL_PLANNED")
        safe_match = CanonService(runtime.repository).match_promotion(
            planned, planned.model_copy(update={"event_id": "EVENT_TOLL_SAME_KEY"}))
        distinct = len(runtime.repository.events(runtime.novel_id)) == 2
        detected = codes == ["PROMOTION_CONFLICT"] and safe_match and distinct
        return MutationObservation(
            detected=detected, detector="SourceReferenceValidator.promotion_conflicts",
            codes=codes, severity="reject", persisted=False,
            note=f"不静默合并；同 canonical_key 可安全 promotion={safe_match}，事件数仍为 2")

    return MutationCase(
        mutation_id="MUT-006", category="identity_integrity", target_layer="canon",
        description="planned → occurred 重复：同一事件出现两个 canonical occurrence",
        expected_detector="SourceReferenceValidator.promotion_conflicts",
        expected_codes=["PROMOTION_CONFLICT"], expected_severity="reject",
        setup=setup, mutation=mutation, integration=True)


def _case_007() -> MutationCase:
    def setup(runtime: MutationRuntime) -> None:
        _seed_gate_fact(runtime)
        repository = runtime.repository
        repository.save_fact(CanonFact(
            fact_id="FACT_SECRET_LIST", canonical_key="SECRET_LIST", novel_id=runtime.novel_id,
            status="happened", canonical_description="档案室里还留着第二份名单",
            provenance="story_state"))
        repository.save_fact(CanonFact(
            fact_id="FACT_PUBLIC_STORE", canonical_key="PUBLIC_STORE", novel_id=runtime.novel_id,
            status="happened", canonical_description="据点第一次打开公共仓库"))
        repository.save_knowledge(CanonKnowledge(
            knowledge_id="KNW_UNKNOWN_SECRET", novel_id=runtime.novel_id,
            fact_id="FACT_SECRET_LIST", holder_id="protagonist", state="unknown"))
        repository.save_knowledge(CanonKnowledge(
            knowledge_id="KNW_NO_SOURCE", novel_id=runtime.novel_id,
            fact_id="FACT_PUBLIC_STORE", holder_id="protagonist", state="known",
            learned_from=""))

    def mutation(runtime: MutationRuntime) -> MutationObservation:
        builder = CanonContextBuilder(runtime.repository)
        character = builder.character_context(runtime.novel_id, "protagonist")
        writer = builder.writer_context(runtime.novel_id, character_scope="protagonist")
        secret = "档案室里还留着第二份名单"
        leaked = any(secret in entry.canonical_description for entry in character.entries) \
            or any(secret in line for line in writer.rendered)
        codes = _graph_codes(CanonGraph.from_repository(runtime.repository, runtime.novel_id))
        detected = (not leaked) and "KNOWLEDGE_LEAK" in codes
        return MutationObservation(
            detected=detected,
            detector="CanonContextBuilder.character_context + CanonGraphValidator.knowledge_leak",
            codes=codes, severity="reject", persisted=False,
            note=("角色未知的事实不进入其上下文；无来源的 known 知识报 KNOWLEDGE_LEAK"
                  if not leaked else "角色上下文泄漏了未知事实"))

    return MutationCase(
        mutation_id="MUT-007", category="knowledge_boundary", target_layer="context",
        description="知识泄漏：角色在 unknown 状态下拿到真相",
        expected_detector="CanonContextBuilder.character_context + "
                          "CanonGraphValidator.knowledge_leak",
        expected_codes=["KNOWLEDGE_LEAK"], expected_severity="reject",
        setup=setup, mutation=mutation, integration=True)


def _case_008() -> MutationCase:
    def setup(runtime: MutationRuntime) -> None:
        _seed_gate_fact(runtime)
        repository = runtime.repository
        repository.save_fact(CanonFact(
            fact_id="FACT_BELIEF_SIGNAL", canonical_key="BELIEF_SIGNAL",
            novel_id=runtime.novel_id, status="happened",
            canonical_description="塔里还有人在持续发报"))
        repository.save_fact(CanonFact(
            fact_id="FACT_TRUTH_SIGNAL", canonical_key="TRUTH_SIGNAL",
            novel_id=runtime.novel_id, status="happened",
            canonical_description="发报声只是旧设备的自动回放"))
        repository.save_knowledge(CanonKnowledge(
            knowledge_id="KNW_BELIEF", novel_id=runtime.novel_id, fact_id="FACT_BELIEF_SIGNAL",
            holder_id="protagonist", state="false_belief", learned_at=10, learned_from="rumor"))
        repository.save_knowledge(CanonKnowledge(
            knowledge_id="KNW_TRUTH", novel_id=runtime.novel_id, fact_id="FACT_TRUTH_SIGNAL",
            holder_id="protagonist", state="known", learned_at=100, learned_from="reveal"))

    def mutation(runtime: MutationRuntime) -> MutationObservation:
        builder = CanonContextBuilder(runtime.repository)
        early = builder.character_context(runtime.novel_id, "protagonist", temporal_cutoff=50)
        early_writer = builder.writer_context(runtime.novel_id, character_scope="protagonist",
                                              temporal_cutoff=50)
        late = builder.character_context(runtime.novel_id, "protagonist", temporal_cutoff=150)
        early_text = " ".join(entry.canonical_description for entry in early.entries)
        writer_text = " ".join(early_writer.rendered)
        late_text = " ".join(entry.canonical_description for entry in late.entries)
        detected = ("误信" in early_text and "持续发报" in early_text
                    and "自动回放" not in early_text and "自动回放" not in writer_text
                    and "自动回放" in late_text)
        return MutationObservation(
            detected=detected, detector="CanonContextBuilder.character_context",
            codes=["FALSE_BELIEF_PRESERVED"] if detected else ["FALSE_BELIEF_OVERWRITTEN"],
            severity="reject", persisted=False,
            note="T=50 只能表达误信；真相要到 T=100 之后才进入角色视角")

    return MutationCase(
        mutation_id="MUT-008", category="knowledge_boundary", target_layer="context",
        description="误信被真相覆盖：早期上下文直接给出事实",
        expected_detector="CanonContextBuilder.character_context",
        expected_codes=["FALSE_BELIEF_PRESERVED"], expected_severity="reject",
        setup=setup, mutation=mutation, integration=True)


def _case_009() -> MutationCase:
    def setup(runtime: MutationRuntime) -> None:
        _seed_gate_fact(runtime)
        runtime.repository.save_foreshadow(CanonForeshadow(
            foreshadow_id="FS_TIDE", novel_id=runtime.novel_id, subject="",
            intended_payoff="潮汐不是自然现象，而是某套装置仍在工作", status="planted",
            reveal_ref=CanonRenderRef(chapter_uuid="uuid_reveal", display_number=200)))

    def mutation(runtime: MutationRuntime) -> MutationObservation:
        bundle = CanonContextBuilder(runtime.repository).writer_context(
            runtime.novel_id, temporal_cutoff=80)
        joined = "\n".join(bundle.rendered)
        leaked = ("装置仍在工作" in joined) or ("不是自然现象" in joined)
        metadata = contains_writer_metadata(joined)
        detected = (not leaked) and (not metadata)
        return MutationObservation(
            detected=detected, detector="CanonContextBuilder.writer_context",
            codes=["FUTURE_REVEAL_BLOCKED"] if detected else ["FUTURE_REVEAL_LEAK"],
            severity="reject", persisted=False,
            note="planned payoff（T=200）在 T=80 的 writer context 不可渲染")

    return MutationCase(
        mutation_id="MUT-009", category="foreshadow_integrity", target_layer="writer",
        description="未来揭示泄漏：writer context 带出未到期的 payoff",
        expected_detector="CanonContextBuilder.writer_context",
        expected_codes=["FUTURE_REVEAL_BLOCKED"], expected_severity="reject",
        setup=setup, mutation=mutation, integration=True)


def _case_010() -> MutationCase:
    def mutation(runtime: MutationRuntime) -> MutationObservation:
        graph = CanonGraph.from_records(foreshadows=[
            {"foreshadow_id": "FS_INVERTED", "plant_order": 70, "reveal_order": 50,
             "status": "planned"}])
        codes = _graph_codes(graph)
        return MutationObservation(detected="REVEAL_BEFORE_PLANT" in codes,
                                   detector="CanonGraphValidator.reveal_before_plant",
                                   codes=codes, severity="reject", persisted=False,
                                   note="reveal T=50 早于 plant T=70")

    return MutationCase(
        mutation_id="MUT-010", category="temporal_integrity", target_layer="graph",
        description="伏笔倒置：reveal 在 plant 之前",
        expected_detector="CanonGraphValidator.reveal_before_plant",
        expected_codes=["REVEAL_BEFORE_PLANT"], expected_severity="reject",
        setup=lambda runtime: None, mutation=mutation)


def _case_011() -> MutationCase:
    def mutation(runtime: MutationRuntime) -> MutationObservation:
        graph = CanonGraph.from_records(foreshadows=[
            {"foreshadow_id": "FS_EARLY_PAYOFF", "plant_order": 10, "reveal_order": 60,
             "payoff_order": 40, "status": "planned"}])
        codes = _graph_codes(graph)
        return MutationObservation(detected="PAYOFF_BEFORE_REVEAL" in codes,
                                   detector="CanonGraphValidator.payoff_before_reveal",
                                   codes=codes, severity="reject", persisted=False,
                                   note="payoff T=40 早于 reveal T=60")

    return MutationCase(
        mutation_id="MUT-011", category="temporal_integrity", target_layer="graph",
        description="回收倒置：payoff 在 reveal 之前",
        expected_detector="CanonGraphValidator.payoff_before_reveal",
        expected_codes=["PAYOFF_BEFORE_REVEAL"], expected_severity="reject",
        setup=lambda runtime: None, mutation=mutation)


def _case_012() -> MutationCase:
    def setup(runtime: MutationRuntime) -> None:
        _seed_gate_fact(runtime)
        repository = runtime.repository
        repository.save_event(CanonEvent(
            event_id="EVENT_LEAVE", canonical_key="LEAVE", novel_id=runtime.novel_id,
            canonical_name="伙伴离队", status="occurred", event_type="major",
            temporal_position=10))
        repository.save_event(CanonEvent(
            event_id="EVENT_LEAVE_RESOLVED", canonical_key="LEAVE_RESOLVED",
            novel_id=runtime.novel_id, canonical_name="伙伴回归", status="resolved",
            event_type="major", narrative_role="consequence", canonical_event_id="EVENT_LEAVE",
            temporal_position=12))
        repository.save_event(CanonEvent(
            event_id="EVENT_STILL_AWAY", canonical_key="STILL_AWAY", novel_id=runtime.novel_id,
            canonical_name="伙伴仍未归来", status="planned", event_type="major",
            narrative_role="reinterpretation", canonical_event_id="EVENT_LEAVE",
            temporal_position=14))

    def mutation(runtime: MutationRuntime) -> MutationObservation:
        codes = _graph_codes(CanonGraph.from_repository(runtime.repository, runtime.novel_id))
        return MutationObservation(detected="RESOLVED_EVENT_REOPENED" in codes,
                                   detector="CanonGraphValidator.run", codes=codes,
                                   severity="reject", persisted=False,
                                   note="离开→回归（resolved）之后又出现「仍未归来」事件")

    return MutationCase(
        mutation_id="MUT-012", category="temporal_integrity", target_layer="graph",
        description="时间顺序倒置：resolved 事件被重新打开",
        expected_detector="CanonGraphValidator.run",
        expected_codes=["RESOLVED_EVENT_REOPENED"], expected_severity="reject",
        setup=setup, mutation=mutation, integration=True)


def _case_013() -> MutationCase:
    def mutation(runtime: MutationRuntime) -> MutationObservation:
        graph = CanonGraph.from_records(
            entities=[{"entity_id": "ENT_FALLEN", "dead_at": 80}],
            events=[{"event_id": "EVENT_AFTER_DEATH", "order": 100,
                     "participants": ["ENT_FALLEN"]}],
            dependencies=[{"from_id": "ENT_FALLEN", "to_id": "EVENT_AFTER_DEATH",
                           "relation": "PARTICIPATES_IN"}])
        codes = _graph_codes(graph)
        return MutationObservation(detected="DEAD_CHARACTER_ACTION" in codes,
                                   detector="CanonGraphValidator.dead_character_action",
                                   codes=codes, severity="reject", persisted=False,
                                   note="dead_at=80 的角色出现在 T=100 事件")

    return MutationCase(
        mutation_id="MUT-013", category="entity_integrity", target_layer="graph",
        description="已死亡角色继续行动",
        expected_detector="CanonGraphValidator.dead_character_action",
        expected_codes=["DEAD_CHARACTER_ACTION"], expected_severity="reject",
        setup=lambda runtime: None, mutation=mutation)


def _case_014() -> MutationCase:
    def mutation(runtime: MutationRuntime) -> MutationObservation:
        graph = CanonGraph.from_records(events=[
            {"event_id": "EVENT_ABILITY_UNLOCK", "order": 100},
            {"event_id": "EVENT_ABILITY_USE", "order": 70,
             "requires_abilities": ["EVENT_ABILITY_UNLOCK"]}])
        codes = _graph_codes(graph)
        return MutationObservation(detected="ABILITY_BEFORE_UNLOCK" in codes,
                                   detector="CanonGraphValidator.ability_before_unlock",
                                   codes=codes, severity="reject", persisted=False,
                                   note="能力解锁 T=100，却在 T=70 被使用")

    return MutationCase(
        mutation_id="MUT-014", category="progression_integrity", target_layer="graph",
        description="能力在解锁前被使用",
        expected_detector="CanonGraphValidator.ability_before_unlock",
        expected_codes=["ABILITY_BEFORE_UNLOCK"], expected_severity="reject",
        setup=lambda runtime: None, mutation=mutation)


def _case_015() -> MutationCase:
    def mutation(runtime: MutationRuntime) -> MutationObservation:
        graph = CanonGraph.from_records(events=[
            {"event_id": "EVENT_IDENTITY_ACQUIRED", "order": 120},
            {"event_id": "EVENT_IDENTITY_USE", "order": 90,
             "requires_identities": ["EVENT_IDENTITY_ACQUIRED"]}])
        codes = _graph_codes(graph)
        return MutationObservation(detected="IDENTITY_BEFORE_ACQUIRED" in codes,
                                   detector="CanonGraphValidator.identity_before_acquired",
                                   codes=codes, severity="reject", persisted=False,
                                   note="身份获得 T=120，却在 T=90 被使用")

    return MutationCase(
        mutation_id="MUT-015", category="progression_integrity", target_layer="graph",
        description="身份在获得前被使用",
        expected_detector="CanonGraphValidator.identity_before_acquired",
        expected_codes=["IDENTITY_BEFORE_ACQUIRED"], expected_severity="reject",
        setup=lambda runtime: None, mutation=mutation)


def _case_016() -> MutationCase:
    def mutation(runtime: MutationRuntime) -> MutationObservation:
        graph = CanonGraph.from_records(
            entities=[{"entity_id": "ENT_TRAVELER", "locations": ["location_a"]}],
            events=[{"event_id": "EVENT_FAR_AWAY", "order": 40, "location": "location_b",
                     "participants": ["ENT_TRAVELER"]}])
        codes = _graph_codes(graph)
        return MutationObservation(detected="LOCATION_IMPOSSIBILITY" in codes,
                                   detector="CanonGraphValidator.location_impossibility",
                                   codes=codes, severity="reject", persisted=False,
                                   note="角色只在 A 地，却无位移事件地出现在 B 地")

    return MutationCase(
        mutation_id="MUT-016", category="spatial_integrity", target_layer="graph",
        description="不可能位移：跨地点无 travel 事件",
        expected_detector="CanonGraphValidator.location_impossibility",
        expected_codes=["LOCATION_IMPOSSIBILITY"], expected_severity="reject",
        setup=lambda runtime: None, mutation=mutation)


def _case_017() -> MutationCase:
    def mutation(runtime: MutationRuntime) -> MutationObservation:
        graph = CanonGraph.from_records(
            events=[{"event_id": "EVENT_A", "order": 10}, {"event_id": "EVENT_B", "order": 20}],
            dependencies=[{"from_id": "EVENT_A", "to_id": "EVENT_B", "relation": "REQUIRES"},
                          {"from_id": "EVENT_B", "to_id": "EVENT_A", "relation": "REQUIRES"}])
        codes = _graph_codes(graph)
        return MutationObservation(detected="CAUSAL_CYCLE" in codes,
                                   detector="CanonGraphValidator.causal_cycle",
                                   codes=codes, severity="reject", persisted=False,
                                   note="A requires B 且 B requires A")

    return MutationCase(
        mutation_id="MUT-017", category="causal_integrity", target_layer="graph",
        description="因果环：A 依赖 B 且 B 依赖 A",
        expected_detector="CanonGraphValidator.causal_cycle",
        expected_codes=["CAUSAL_CYCLE"], expected_severity="reject",
        setup=lambda runtime: None, mutation=mutation)


def _case_018() -> MutationCase:
    def mutation(runtime: MutationRuntime) -> MutationObservation:
        graph = CanonGraph.from_records(events=[
            {"event_id": "EVENT_NEEDS_MISSING", "order": 20,
             "prerequisites": ["EVENT_NOT_IMPORTED"]}])
        codes = _graph_codes(graph)
        return MutationObservation(detected="PREREQUISITE_MISSING" in codes,
                                   detector="CanonGraphValidator.prerequisite_missing",
                                   codes=codes, severity="reject", persisted=False,
                                   note="前置 EVENT_NOT_IMPORTED 不存在")

    return MutationCase(
        mutation_id="MUT-018", category="causal_integrity", target_layer="graph",
        description="缺失前置：prerequisite 不在 Canon",
        expected_detector="CanonGraphValidator.prerequisite_missing",
        expected_codes=["PREREQUISITE_MISSING"], expected_severity="reject",
        setup=lambda runtime: None, mutation=mutation)


def _case_019() -> MutationCase:
    detector = "SchemaGate.validate_chapter_plan"

    def mutation(runtime: MutationRuntime) -> MutationObservation:
        result = _planner(runtime).plan(
            _intent(runtime), beats_raw=[_beat()],
            chapters_raw=[_chapter(concrete_events="主角利用能力挡住风暴")])
        codes = _codes(result)
        try:
            validate_chapter_plan(_chapter(concrete_events="主角利用能力挡住风暴"))
        except SchemaGateError as exc:
            codes.append(exc.code)
        else:
            codes.append("SCHEMA_COERCION_ALLOWED")
        detected = (not result.ok and "CHAPTER_SCHEMA_INVALID" in codes
                    and "CHAPTER_PLAN_SCHEMA_INVALID" in codes)
        return MutationObservation(
            detected=detected, detector=detector, codes=codes, severity="reject",
            persisted=bool(result.persisted_path),
            note="planner 层与 gate 层都拒绝 str；无任何自动 coercion / 逐字符展开")

    return MutationCase(
        mutation_id="MUT-019", category="schema_integrity", target_layer="schema",
        description="concrete_events 传 str：禁止逐字符展开",
        expected_detector=detector,
        expected_codes=["CHAPTER_SCHEMA_INVALID", "CHAPTER_PLAN_SCHEMA_INVALID"],
        expected_severity="reject", setup=lambda runtime: _seed_gate_fact(runtime),
        mutation=mutation, integration=True)


def _case_020() -> MutationCase:
    def mutation(runtime: MutationRuntime) -> MutationObservation:
        return _planner_reject(runtime,
                               _chapter(concrete_events=["打开封闭舱门并冲进走廊"] * 3),
                               detector="SchemaGate.validate_chapter_plan",
                               expected="CHAPTER_SCHEMA_INVALID",
                               note="同章 concrete_events 完全重复")

    return MutationCase(
        mutation_id="MUT-020", category="schema_integrity", target_layer="schema",
        description="同章事件重复：三条完全相同",
        expected_detector="SchemaGate.validate_chapter_plan",
        expected_codes=["CHAPTER_SCHEMA_INVALID"], expected_severity="reject",
        setup=lambda runtime: _seed_gate_fact(runtime), mutation=mutation)


# --------------------------------------------------------------------------- MUT-021 … 040


def _case_021() -> MutationCase:
    def mutation(runtime: MutationRuntime) -> MutationObservation:
        return _planner_reject(runtime, _chapter(concrete_events=["主", "角", "走"]),
                               detector="SchemaGate.validate_chapter_plan",
                               expected="CHAPTER_SCHEMA_INVALID",
                               note="事件是单字碎片（field fragment）")

    return MutationCase(
        mutation_id="MUT-021", category="schema_integrity", target_layer="schema",
        description="事件碎片：单字被当成具体事件",
        expected_detector="SchemaGate.validate_chapter_plan",
        expected_codes=["CHAPTER_SCHEMA_INVALID"], expected_severity="reject",
        setup=lambda runtime: _seed_gate_fact(runtime), mutation=mutation)


def _case_022() -> MutationCase:
    def mutation(runtime: MutationRuntime) -> MutationObservation:
        missing = _chapter()
        missing.pop("locations")
        result = _planner(runtime).plan(_intent(runtime), beats_raw=[_beat()],
                                        chapters_raw=[missing])
        codes = _codes(result)
        empty = _planner(runtime).plan(_intent(runtime), beats_raw=[_beat()],
                                       chapters_raw=[_chapter(locations=[])], mode="shadow")
        empty_codes = _codes(empty)
        codes.extend(empty_codes)
        detected = (not result.ok and "GRAPH_METADATA_MISSING" in codes
                    and empty.ok and "GRAPH_METADATA_MISSING" not in empty_codes)
        return MutationObservation(
            detected=detected, detector="CanonAwareOutlinePlanner.plan",
            codes=codes, severity="reject", persisted=False,
            note="key 缺失 → GRAPH_METADATA_MISSING；显式 [] 合法（missing ≠ empty）")

    return MutationCase(
        mutation_id="MUT-022", category="graph_metadata", target_layer="planner",
        description="缺失 graph metadata key：必须与显式空列表区分",
        expected_detector="CanonAwareOutlinePlanner.plan",
        expected_codes=["GRAPH_METADATA_MISSING"], expected_severity="reject",
        setup=lambda runtime: _seed_gate_fact(runtime), mutation=mutation)


def _case_023() -> MutationCase:
    detector = "CanonAwareOutlinePlanner.plan + sanitize_writer_text"

    def mutation(runtime: MutationRuntime) -> MutationObservation:
        return _planner_reject(
            runtime,
            _chapter(trigger="承接 ch142 的封锁结果",
                     information_release="EVENT_GATE 之后旧记录仍在",
                     next_chapter_causality="chapter_uuid 的变化决定后续"),
            detector=detector, expected="WRITER_VISIBLE_METADATA_LEAK",
            note="章节号 / canon ID / 内部字段名出现在 writer-visible 字段（trigger 等全覆盖）")

    return MutationCase(
        mutation_id="MUT-023", category="writer_surface", target_layer="writer",
        description="Writer metadata leak：ch142 / FACT_* / chapter_uuid 混入正文层",
        expected_detector=detector,
        expected_codes=["WRITER_VISIBLE_METADATA_LEAK"], expected_severity="reject",
        setup=lambda runtime: _seed_gate_fact(runtime), mutation=mutation, integration=True)


def _case_024() -> MutationCase:
    detector = "CanonAwareOutlinePlanner.plan + sanitize_writer_text"

    def mutation(runtime: MutationRuntime) -> MutationObservation:
        observation = _planner_reject(
            runtime,
            _chapter(escalation="本卷（第6卷）的冲突升级", cost="消耗一份 source_ref",
                     next_chapter_causality="Arc 4 的后果尚未回收"),
            detector=detector, expected="WRITER_VISIBLE_METADATA_LEAK",
            note="Arc / 卷号 / 内部字段名全部拒绝；普通数字不误伤")
        negative = ["第3天他们走了390公里，遇到三个人", "他在第2条路线里数到7块电池"]
        positives = ["ch142", "FACT_SECRET", "EVENT_GATE", "source_ref", "context_manifest_id",
                     "Arc 4", "第6卷"]
        clean = sanitize_writer_text("承接 source_ref 与 Arc 4 的结果")
        flags_ok = (not any(contains_writer_metadata(line) for line in negative)
                    and all(contains_writer_metadata(token) for token in positives)
                    and not contains_writer_metadata(clean))
        observation.extra["negative_control"] = flags_ok
        observation.detected = observation.detected and flags_ok
        return observation

    return MutationCase(
        mutation_id="MUT-024", category="writer_surface", target_layer="writer",
        description="规划元数据泄漏：Arc / 卷号 / 内部字段名",
        expected_detector=detector,
        expected_codes=["WRITER_VISIBLE_METADATA_LEAK"], expected_severity="reject",
        setup=lambda runtime: _seed_gate_fact(runtime), mutation=mutation)


def _case_025() -> MutationCase:
    def mutation(runtime: MutationRuntime) -> MutationObservation:
        index = LocalSemanticIndex()
        first = EventSemanticSignature(
            event_id="EVENT_ALLIANCE_CONDITIONS",
            subjects=["faction_black", "faction_salt", "faction_research"],
            action="递交结盟条件", objects=["settlement"], location="core_camp",
            event_type="political",
            semantic_summary="三家势力同日向自由据点递交结盟条件，要求据点选边")
        second = EventSemanticSignature(
            event_id="EVENT_ALLIANCE_REWORDED",
            subjects=["faction_black", "faction_salt", "faction_research"],
            action="递交结盟条件", objects=["settlement"], location="core_camp",
            event_type="political",
            semantic_summary="黑塔、盐队与研究院同日递交结盟条件，要求自由据点选边")
        index.index_event(first)
        candidates = index.candidates(second)
        codes = [candidate.relation for candidate in candidates]
        return MutationObservation(
            detected=any(candidate.relation == "duplicate" for candidate in candidates),
            detector="SemanticIndex.classify_relation", codes=codes or ["NO_CANDIDATE"],
            severity="candidate", persisted=False,
            note="换措辞的同一重大事件必须产生 duplicate candidate（只提示，不自动合并）")

    return MutationCase(
        mutation_id="MUT-025", category="semantic_duplicate", target_layer="semantic",
        description="重大事件换措辞重复：语义索引必须报 duplicate",
        expected_detector="SemanticIndex.classify_relation",
        expected_codes=["duplicate"], expected_severity="candidate",
        setup=lambda runtime: None, mutation=mutation)


def _case_026() -> MutationCase:
    def mutation(runtime: MutationRuntime) -> MutationObservation:
        index = LocalSemanticIndex()
        first = EventSemanticSignature(event_id="EVENT_PATROL_1", subjects=["watch"],
                                       action="日常巡逻", location="camp", event_type="patrol",
                                       can_repeat=True, semantic_summary="据点日常巡逻")
        second = EventSemanticSignature(event_id="EVENT_PATROL_2", subjects=["watch"],
                                        action="日常巡逻", location="camp", event_type="patrol",
                                        can_repeat=True, semantic_summary="据点日常巡逻")
        relation = index.classify_relation(first, second)
        return MutationObservation(detected=relation == "legitimate_recurrence",
                                   detector="SemanticIndex.classify_relation", codes=[relation],
                                   severity="accept", persisted=False,
                                   note="可重复事件不得被判为 duplicate canonical occurrence")

    return MutationCase(
        mutation_id="MUT-026", category="semantic_duplicate", target_layer="semantic",
        description="合法复现误报：日常巡逻连续两次",
        expected_detector="SemanticIndex.classify_relation",
        expected_codes=["legitimate_recurrence"], expected_severity="accept",
        setup=lambda runtime: None, mutation=mutation)


def _case_027() -> MutationCase:
    def mutation(runtime: MutationRuntime) -> MutationObservation:
        index = LocalSemanticIndex()
        attack = EventSemanticSignature(event_id="EVENT_RAID", subjects=["raiders"],
                                        action="第一次攻击", objects=["camp"], location="camp",
                                        event_type="major", semantic_summary="掠夺者首次袭击据点")
        blockade = EventSemanticSignature(event_id="EVENT_BLOCKADE", subjects=["raiders"],
                                          action="报复性封锁", objects=["camp"], location="camp",
                                          event_type="major", narrative_role="consequence",
                                          canonical_event_id="EVENT_RAID",
                                          semantic_summary="袭击之后掠夺者实施报复性封锁")
        relation = index.classify_relation(attack, blockade)
        return MutationObservation(detected=relation == "consequence",
                                   detector="SemanticIndex.classify_relation", codes=[relation],
                                   severity="accept", persisted=False,
                                   note="显式 consequence 关系优先于相似度")

    return MutationCase(
        mutation_id="MUT-027", category="semantic_duplicate", target_layer="semantic",
        description="后果误报：报复性封锁不是重复事件",
        expected_detector="SemanticIndex.classify_relation",
        expected_codes=["consequence"], expected_severity="accept",
        setup=lambda runtime: None, mutation=mutation)


def _case_028() -> MutationCase:
    def setup(runtime: MutationRuntime) -> None:
        repository = runtime.repository
        repository.save_fact(CanonFact(
            fact_id="FACT_ZERO_LAYER_GATE_FIRST_OPEN",
            canonical_key="ZERO_LAYER_GATE_FIRST_OPEN", novel_id=runtime.novel_id,
            status="happened", canonical_description="第一次打开旧时代门禁",
            source_refs=[CanonSourceRef(source_type="chapter", source_uuid="uuid_gate",
                                        chapter_uuid="uuid_gate", source_id="uuid_gate")],
            first_occurrence_ref=CanonRenderRef(chapter_uuid="uuid_gate", display_number=325)))
        repository.add_render_ref(novel_id=runtime.novel_id,
                                  canon_id="FACT_ZERO_LAYER_GATE_FIRST_OPEN",
                                  ref=CanonRenderRef(chapter_uuid="uuid_gate", display_number=325))
        repository.save_mapping(CanonSourceMapping(
            novel_id=runtime.novel_id, source_type="outline", source_stable_key="uuid_gate",
            canon_type="fact", canon_id="FACT_ZERO_LAYER_GATE_FIRST_OPEN"))
        repository.save_knowledge(CanonKnowledge(
            knowledge_id="KNW_GATE", novel_id=runtime.novel_id,
            fact_id="FACT_ZERO_LAYER_GATE_FIRST_OPEN", holder_id="protagonist",
            state="known", learned_at=300, learned_from="witness"))
        repository.save_foreshadow(CanonForeshadow(
            foreshadow_id="FS_GATE_TAG", novel_id=runtime.novel_id, status="planted",
            subject="铭牌与门禁的关系", planted_fact_id="FACT_ZERO_LAYER_GATE_FIRST_OPEN",
            plant_ref=CanonRenderRef(chapter_uuid="uuid_gate", display_number=325)))
        ChapterLineageStore(repository).register(ChapterLineage(
            chapter_uuid="uuid_gate", novel_id=runtime.novel_id, display_number=325,
            title="门禁"))

    def mutation(runtime: MutationRuntime) -> MutationObservation:
        repository = runtime.repository
        store = ChapterLineageStore(repository)
        before_facts = {item.fact_id: item.canonical_key
                        for item in repository.facts(runtime.novel_id)}
        before_events = {item.event_id for item in repository.events(runtime.novel_id)}
        before_knowledge = {item.knowledge_id for item in repository.knowledge(runtime.novel_id)}
        before_foreshadows = {item.foreshadow_id
                              for item in repository.foreshadows(runtime.novel_id)}
        mapping_before = repository.find_mapping(runtime.novel_id, "outline", "uuid_gate", "fact")
        store.renumber(runtime.novel_id, {"uuid_gate": 318})
        changed = repository.renumber_render_refs(novel_id=runtime.novel_id, mapping={325: 318})
        fact = next(item for item in repository.facts(runtime.novel_id)
                    if item.fact_id == "FACT_ZERO_LAYER_GATE_FIRST_OPEN")
        lineage = store.get("uuid_gate")
        mapping_after = repository.find_mapping(runtime.novel_id, "outline", "uuid_gate", "fact")
        table_refs = repository.render_refs(runtime.novel_id,
                                            canon_id="FACT_ZERO_LAYER_GATE_FIRST_OPEN")
        identity_ok = (
            {item.fact_id: item.canonical_key for item in repository.facts(runtime.novel_id)}
            == before_facts
            and {item.event_id for item in repository.events(runtime.novel_id)} == before_events
            and {item.knowledge_id for item in repository.knowledge(runtime.novel_id)}
            == before_knowledge
            and {item.foreshadow_id for item in repository.foreshadows(runtime.novel_id)}
            == before_foreshadows
            and mapping_before is not None and mapping_after is not None
            and mapping_before.canon_id == mapping_after.canon_id
            == "FACT_ZERO_LAYER_GATE_FIRST_OPEN"
            and lineage is not None and lineage.chapter_uuid == "uuid_gate"
            and lineage.display_number == 318)
        display_ok = (fact.first_occurrence_ref is not None
                      and fact.first_occurrence_ref.display_number == 318
                      and bool(table_refs) and table_refs[0]["display_number"] == 318
                      and changed >= 2)
        detected = identity_ok and display_ok
        return MutationObservation(
            detected=detected,
            detector="ChapterLineageStore.renumber + CanonRepository.renumber_render_refs",
            codes=["DISPLAY_RENUMBERED"] if detected else ["IDENTITY_DRIFT"],
            severity="expected_change", persisted=True,
            note="只允许 display_number 325→318；fact / event / knowledge / foreshadow / mapping / "
                 "chapter_uuid 全部不变（render_refs 表与 payload 同步）")

    return MutationCase(
        mutation_id="MUT-028", category="identity_integrity", target_layer="repository",
        description="章节重编号：display number 325 → 318",
        expected_detector="ChapterLineageStore.renumber + CanonRepository.renumber_render_refs",
        expected_codes=["DISPLAY_RENUMBERED"], expected_severity="expected_change",
        should_persist=True, should_mutate_canon=True, should_mutate_chapter_lineage=True,
        setup=setup, mutation=mutation, integration=True)


def _case_029() -> MutationCase:
    def setup(runtime: MutationRuntime) -> None:
        repository = runtime.repository
        repository.save_fact(CanonFact(
            fact_id="FACT_SPLIT_SOURCE", canonical_key="SPLIT_SOURCE", novel_id=runtime.novel_id,
            status="happened", canonical_description="长章里的两件事",
            source_refs=[CanonSourceRef(source_type="chapter", source_uuid="uuid_split",
                                        chapter_uuid="uuid_split", source_id="uuid_split")]))
        ChapterLineageStore(repository).register(ChapterLineage(
            chapter_uuid="uuid_split", novel_id=runtime.novel_id, display_number=40,
            title="长章"))

    def mutation(runtime: MutationRuntime) -> MutationObservation:
        repository = runtime.repository
        store = ChapterLineageStore(repository)
        first, second = store.split("uuid_split", novel_id=runtime.novel_id)
        old = store.get("uuid_split")
        report = SourceReferenceValidator(repository).validate_refs(
            runtime.novel_id,
            refs=[CanonSourceRef(source_type="chapter", source_uuid="uuid_split",
                                 chapter_uuid="uuid_split", source_id="uuid_split",
                                 claimed_fact_ids=["FACT_SPLIT_SOURCE"],
                                 provenance="happened")])
        detected = (old is not None and old.status == "superseded"
                    and old.superseded_by == [first, second]
                    and store.get(first) is not None and store.get(second) is not None
                    and report.ok() and len(repository.facts(runtime.novel_id)) == 1)
        return MutationObservation(
            detected=detected, detector="ChapterLineageStore.split + SourceReferenceValidator",
            codes=["SPLIT_TRACEABLE"] if detected else ["SPLIT_TRACE_LOST"],
            severity="expected_change", persisted=True,
            note="拆章后旧 uuid 标 superseded_by，Canon fact 与 source tracing 不丢失")

    return MutationCase(
        mutation_id="MUT-029", category="identity_integrity", target_layer="repository",
        description="拆章：uuid_split → 两个新 uuid",
        expected_detector="ChapterLineageStore.split + SourceReferenceValidator",
        expected_codes=["SPLIT_TRACEABLE"], expected_severity="expected_change",
        should_persist=True, should_mutate_chapter_lineage=True, setup=setup,
        mutation=mutation, integration=True)


def _case_030() -> MutationCase:
    def setup(runtime: MutationRuntime) -> None:
        repository = runtime.repository
        for suffix in ("a", "b"):
            repository.save_fact(CanonFact(
                fact_id=f"FACT_MERGE_{suffix.upper()}", canonical_key=f"MERGE_{suffix.upper()}",
                novel_id=runtime.novel_id, status="happened",
                canonical_description=f"合并前的第 {suffix} 件事",
                source_refs=[CanonSourceRef(source_type="chapter",
                                            source_uuid=f"uuid_merge_{suffix}",
                                            chapter_uuid=f"uuid_merge_{suffix}",
                                            source_id=f"uuid_merge_{suffix}")]))
        store = ChapterLineageStore(repository)
        store.register(ChapterLineage(chapter_uuid="uuid_merge_a", novel_id=runtime.novel_id,
                                      display_number=50, title="前半"))
        store.register(ChapterLineage(chapter_uuid="uuid_merge_b", novel_id=runtime.novel_id,
                                      display_number=51, title="后半"))

    def mutation(runtime: MutationRuntime) -> MutationObservation:
        repository = runtime.repository
        store = ChapterLineageStore(repository)
        merged = store.merge(["uuid_merge_a", "uuid_merge_b"], novel_id=runtime.novel_id,
                             title="合并章")
        first, second = store.get("uuid_merge_a"), store.get("uuid_merge_b")
        facts = repository.facts(runtime.novel_id)
        source_uuids = {ref.chapter_uuid for fact in facts for ref in fact.source_refs}
        detected = (first is not None and second is not None and first.status == "merged"
                    and second.status == "merged" and first.merged_into == merged
                    and second.merged_into == merged and store.get(merged) is not None
                    and {"uuid_merge_a", "uuid_merge_b"} <= source_uuids and len(facts) == 2)
        return MutationObservation(
            detected=detected, detector="ChapterLineageStore.merge",
            codes=["MERGE_TRACEABLE"] if detected else ["MERGE_DROPPED_SOURCE_REFS"],
            severity="expected_change", persisted=True,
            note="合章后旧 uuid 标 merged_into，原 source refs 不被静默丢弃")

    return MutationCase(
        mutation_id="MUT-030", category="identity_integrity", target_layer="repository",
        description="合章：uuid_merge_a/b → 合并 uuid",
        expected_detector="ChapterLineageStore.merge",
        expected_codes=["MERGE_TRACEABLE"], expected_severity="expected_change",
        should_persist=True, should_mutate_chapter_lineage=True, setup=setup,
        mutation=mutation, integration=True)


def _case_031() -> MutationCase:
    def mutation(runtime: MutationRuntime) -> MutationObservation:
        planner = _planner(runtime, flags=CanonOutlineFlags(canon_outline_shadow_mode=True))
        manifests_before = runtime.digests()["context_manifests"]
        lineage_before = runtime.repository._connection.execute(
            "SELECT COUNT(*) AS n FROM canon_chapter_lineage").fetchone()["n"]
        result = planner.shadow_plan(_intent(runtime), beats_raw=[_beat()],
                                     chapters_raw=[_chapter()])
        codes = _codes(result)
        shadow_files = sorted(path.name for path in runtime.shadow_dir.glob("*.json"))
        lineage_count = runtime.repository._connection.execute(
            "SELECT COUNT(*) AS n FROM canon_chapter_lineage").fetchone()["n"]
        manifests_after = runtime.digests()["context_manifests"]
        detected = (result.ok and result.mode == "shadow" and bool(shadow_files)
                    and lineage_count == lineage_before
                    and ChapterLineageStore(runtime.repository).get("uuid_ch_1") is None)
        return MutationObservation(
            detected=detected, detector="CanonAwareOutlinePlanner.shadow_plan",
            codes=codes or ["SHADOW_ISOLATED"], severity="isolated", persisted=False,
            note=f"shadow 产物只在隔离 sink（{','.join(shadow_files)}）；"
                 f"正式 lineage 不新增（{lineage_before}→{lineage_count}）；"
                 f"shadow 仍写 1 条 context manifest {manifests_before}→{manifests_after}"
                 "（规划工件，非 Canon truth）")

    return MutationCase(
        mutation_id="MUT-031", category="isolation", target_layer="outline",
        description="Shadow 污染：shadow planner 不得触碰正式 Canon / Outline / StoryState",
        expected_detector="CanonAwareOutlinePlanner.shadow_plan",
        expected_codes=["SHADOW_ISOLATED"], expected_severity="isolated",
        setup=lambda runtime: _seed_gate_fact(runtime), mutation=mutation, integration=True)


def _case_032() -> MutationCase:
    def mutation(runtime: MutationRuntime) -> MutationObservation:
        result = CanonBootstrap(runtime.repository).bootstrap(
            runtime.novel_id, state=_story_state(runtime),
            outline_metadata=[{"id": "clue_water", "summary": "旧大纲声称线索来自另一处"}])
        confirmed = [item for item in runtime.repository.facts(runtime.novel_id)
                     if item.provenance in ("story_state", "confirmed")]
        imported = [item for item in runtime.repository.facts(runtime.novel_id)
                    if item.provenance == "imported"]
        detected = (bool(confirmed) and bool(imported)
                    and all(item.status == "happened" for item in confirmed)
                    and all("旧大纲声称" not in item.canonical_description for item in confirmed)
                    and result.created.get("outline") == 1)
        return MutationObservation(
            detected=detected, detector="CanonBootstrap.bootstrap",
            codes=["CONFIRMED_PRIORITY_KEPT"] if detected else ["INFERRED_OVERWROTE_CONFIRMED"],
            severity="reject", persisted=False,
            note=f"confirmed facts={len(confirmed)}，低置信 imported facts={len(imported)}；"
                 "legacy outline 不覆盖 StoryState")

    return MutationCase(
        mutation_id="MUT-032", category="bootstrap_priority", target_layer="bootstrap",
        description="Bootstrap 优先级：legacy outline 不得覆盖 StoryState confirmed",
        expected_detector="CanonBootstrap.bootstrap",
        expected_codes=["CONFIRMED_PRIORITY_KEPT"], expected_severity="reject",
        should_mutate_canon=True, should_mutate_source_mapping=True,
        setup=lambda runtime: None, mutation=mutation, integration=True)


def _case_033() -> MutationCase:
    def mutation(runtime: MutationRuntime) -> MutationObservation:
        result = CanonBootstrap(runtime.repository).bootstrap(runtime.novel_id,
                                                             state=_story_state(runtime))
        report = result.report
        detected = (report.partial is True and "CANON_PARTIAL" in report.note
                    and result.created.get("story_state", 0) >= 1
                    and bool(report.missing_areas))
        return MutationObservation(
            detected=detected, detector="CanonBootstrap.coverage",
            codes=["CANON_PARTIAL"] if detected else ["PARTIAL_CANON_TREATED_AS_FAILURE"],
            severity="degrade", persisted=False,
            note=f"只有 StoryState（无 route / outline）时 Bootstrap 必须成功："
                 f"missing_areas={report.missing_areas}")

    return MutationCase(
        mutation_id="MUT-033", category="bootstrap_priority", target_layer="bootstrap",
        description="部分 Canon：只有 StoryState 也要能启动（CANON_PARTIAL）",
        expected_detector="CanonBootstrap.coverage",
        expected_codes=["CANON_PARTIAL"], expected_severity="degrade",
        should_mutate_canon=True, should_mutate_source_mapping=True,
        setup=lambda runtime: None, mutation=mutation)


def _case_034() -> MutationCase:
    def setup(runtime: MutationRuntime) -> None:
        repository = runtime.repository
        repository.save_fact(CanonFact(
            fact_id="FACT_GATE_OPEN", canonical_key="GATE_OPEN", novel_id=runtime.novel_id,
            status="happened", canonical_description="第一次打开旧时代门禁",
            first_occurrence_ref=CanonRenderRef(chapter_uuid="uuid_gate", display_number=10)))
        repository.save_knowledge(CanonKnowledge(
            knowledge_id="KNW_TOO_EARLY", novel_id=runtime.novel_id, fact_id="FACT_GATE_OPEN",
            holder_id="protagonist", state="known", learned_at=5, learned_from="witness"))
        repository.save_mapping(CanonSourceMapping(
            novel_id=runtime.novel_id, source_type="outline", source_stable_key="uuid_gate",
            canon_type="fact", canon_id="FACT_GATE_OPEN"))

    def mutation(runtime: MutationRuntime) -> MutationObservation:
        before = sorted(item.fact_id for item in runtime.repository.facts(runtime.novel_id))
        result = CanonBootstrap(runtime.repository).rebuild(runtime.novel_id)
        after = sorted(item.fact_id for item in runtime.repository.facts(runtime.novel_id))
        rejected = "REBUILD_REJECTED" in result.report.note
        detected = rejected and before == after
        return MutationObservation(
            detected=detected, detector="CanonBootstrap.rebuild",
            codes=["REBUILD_REJECTED"] if rejected else ["REBUILD_ACCEPTED_BAD_CANDIDATE"],
            severity="reject", persisted=False,
            note=f"候选库校验失败（KNOWLEDGE_BEFORE_FACT）→ 原 Canon 保留；"
                 f"note={result.report.note[:60]}")

    return MutationCase(
        mutation_id="MUT-034", category="atomicity", target_layer="bootstrap",
        description="Rebuild 失败回滚：validator 阶段拒绝候选库",
        expected_detector="CanonBootstrap.rebuild",
        expected_codes=["REBUILD_REJECTED"], expected_severity="reject",
        setup=setup, mutation=mutation, integration=True)


def _case_035() -> MutationCase:
    def mutation(runtime: MutationRuntime) -> MutationObservation:
        broken_state = {"schema_version": 1, "novel_id": runtime.novel_id,
                        "knowledge": [{"id": "clue", "holders": ["protagonist"],
                                       "tick": {"bad": 1}, "source": "broken"}]}
        result = CanonBootstrap(runtime.repository).rebuild(runtime.novel_id, state=broken_state)
        kept = "REBUILD_FAILED_KEPT_ORIGINAL" in result.report.note
        facts = runtime.repository.facts(runtime.novel_id)
        detected = kept and len(facts) == 1 and facts[0].fact_id == "FACT_GATE_OPEN"
        return MutationObservation(
            detected=detected, detector="CanonBootstrap.rebuild",
            codes=["REBUILD_FAILED_KEPT_ORIGINAL"] if kept else ["REBUILD_EXCEPTION_LOST_DATA"],
            severity="reject", persisted=False,
            note=f"导入中途抛异常 → transaction rollback，原 Canon 完整；"
                 f"note={result.report.note[:60]}")

    return MutationCase(
        mutation_id="MUT-035", category="atomicity", target_layer="bootstrap",
        description="Rebuild 异常回滚：导入中途 exception",
        expected_detector="CanonBootstrap.rebuild",
        expected_codes=["REBUILD_FAILED_KEPT_ORIGINAL"], expected_severity="reject",
        setup=lambda runtime: _seed_gate_fact(runtime), mutation=mutation, integration=True)


def _case_036() -> MutationCase:
    def setup(runtime: MutationRuntime) -> None:
        repository = runtime.repository
        rows = [
            CanonFact(fact_id="FACT_GATE_OPEN", canonical_key="GATE_OPEN",
                      novel_id=runtime.novel_id, status="happened",
                      canonical_description="第一次打开旧时代门禁",
                      first_occurrence_ref=CanonRenderRef(chapter_uuid="uuid_gate",
                                                          display_number=10)),
            CanonFact(fact_id="FACT_LATER_PLAN", canonical_key="LATER_PLAN",
                      novel_id=runtime.novel_id, status="planned",
                      canonical_description="之后才计划的事"),
            CanonFact(fact_id="FACT_WATER_RULE", canonical_key="WATER_RULE",
                      novel_id=runtime.novel_id, status="happened",
                      canonical_description="水必须靠交换获得",
                      first_occurrence_ref=CanonRenderRef(chapter_uuid="uuid_water",
                                                          display_number=30)),
        ]
        for row in rows:
            repository.save_fact(row)
        repository.save_event(CanonEvent(
            event_id="EVENT_GATE_OPEN", canonical_key="GATE_OPEN_EVENT",
            novel_id=runtime.novel_id, canonical_name="门禁打开", status="occurred",
            event_type="major", temporal_position=10))
        repository.save_event(CanonEvent(
            event_id="EVENT_RITUAL", canonical_key="RITUAL", novel_id=runtime.novel_id,
            canonical_name="据点第一次立规", status="planned", event_type="major",
            temporal_position=40, prerequisites=["EVENT_GATE_OPEN"]))
        runtime.artifacts["facts"] = [row.model_dump(mode="json") for row in rows]
        runtime.artifacts["events"] = [event.model_dump(mode="json")
                                       for event in repository.events(runtime.novel_id)]

    def mutation(runtime: MutationRuntime) -> MutationObservation:
        builder = CanonContextBuilder(runtime.repository)
        first = builder.planner_context(runtime.novel_id, arc_intent="立规", temporal_cutoff=250)
        second = builder.planner_context(runtime.novel_id, arc_intent="立规", temporal_cutoff=250)
        shuffled = CanonRepository(runtime.root / "shuffled.sqlite")
        try:
            for payload in reversed(runtime.artifacts["facts"]):
                shuffled.save_fact(CanonFact.model_validate(payload))
            for payload in reversed(runtime.artifacts["events"]):
                shuffled.save_event(CanonEvent.model_validate(payload))
            third = CanonContextBuilder(shuffled).planner_context(
                runtime.novel_id, arc_intent="立规", temporal_cutoff=250)
            digests = {first.manifest.context_digest, second.manifest.context_digest,
                       third.manifest.context_digest}
            ids_match = ([entry.canon_id for entry in first.entries]
                         == [entry.canon_id for entry in third.entries])
            detected = len(digests) == 1 and ids_match
        finally:
            shuffled.close()
        return MutationObservation(
            detected=detected, detector="CanonContextBuilder.planner_context",
            codes=["CONTEXT_DETERMINISTIC"] if detected else ["CONTEXT_NONDETERMINISTIC"],
            severity="reject", persisted=False,
            note="同一 Canon / purpose / cutoff / scope / budget，打乱 DB 返回顺序后 digest 仍一致")

    return MutationCase(
        mutation_id="MUT-036", category="determinism", target_layer="context",
        description="上下文确定性：打乱 DB 返回顺序后 digest 必须一致",
        expected_detector="CanonContextBuilder.planner_context",
        expected_codes=["CONTEXT_DETERMINISTIC"], expected_severity="reject",
        setup=setup, mutation=mutation)


def _case_037() -> MutationCase:
    def setup(runtime: MutationRuntime) -> None:
        repository = runtime.repository
        repository.save_fact(CanonFact(
            fact_id="FACT_GATE_OPEN", canonical_key="GATE_OPEN", novel_id=runtime.novel_id,
            status="happened", canonical_description="第一次打开旧时代门禁"))
        repository.save_fact(CanonFact(
            fact_id="FACT_LATER_PLAN", canonical_key="LATER_PLAN", novel_id=runtime.novel_id,
            status="planned", canonical_description="之后才计划的事"))
        repository.save_event(CanonEvent(
            event_id="EVENT_RITUAL", canonical_key="RITUAL", novel_id=runtime.novel_id,
            canonical_name="据点立规", status="planned", event_type="major",
            temporal_position=40, prerequisites=["EVENT_GATE_OPEN"]))
        repository.save_event(CanonEvent(
            event_id="EVENT_PLAIN", canonical_key="PLAIN", novel_id=runtime.novel_id,
            canonical_name="日常劳作", status="planned", event_type="daily_work"))
        repository.save_knowledge(CanonKnowledge(
            knowledge_id="KNW_WATER", novel_id=runtime.novel_id, fact_id="FACT_GATE_OPEN",
            holder_id="protagonist", state="known", learned_at=30, learned_from="witness"))
        repository.save_foreshadow(CanonForeshadow(
            foreshadow_id="FS_TIDE", novel_id=runtime.novel_id, subject="周期性的震动",
            status="planned"))

    def mutation(runtime: MutationRuntime) -> MutationObservation:
        builder = CanonContextBuilder(runtime.repository)
        bundle = builder.planner_context(runtime.novel_id, max_items=1, max_chars=1)
        kept = {entry.canon_id for entry in bundle.entries}
        character = builder.character_context(runtime.novel_id, "protagonist", max_items=1)
        character_kept = {entry.canon_id for entry in character.entries}
        trimmed = set(bundle.manifest.trimmed_ids)
        detected = ({"FACT_GATE_OPEN", "EVENT_RITUAL"} <= kept
                    and "KNW_WATER" in character_kept
                    and {"FACT_LATER_PLAN", "FS_TIDE"} <= trimmed)
        return MutationObservation(
            detected=detected, detector="CanonContextBuilder._apply_budget",
            codes=["HARD_CONSTRAINTS_KEPT"] if detected else ["HARD_CONSTRAINT_TRIMMED"],
            severity="reject", persisted=False,
            note=f"max_items=1 / max_chars=1 仍保留 P0/P1（{sorted(kept)}）；"
                 f"低优先级被裁剪 {sorted(trimmed)}")

    return MutationCase(
        mutation_id="MUT-037", category="budget_integrity", target_layer="context",
        description="预算裁剪：hard prerequisite / knowledge boundary 不可被裁掉",
        expected_detector="CanonContextBuilder._apply_budget",
        expected_codes=["HARD_CONSTRAINTS_KEPT"], expected_severity="reject",
        setup=setup, mutation=mutation)


def _case_038() -> MutationCase:
    def setup(runtime: MutationRuntime) -> None:
        _seed_gate_fact(runtime)
        repository = runtime.repository
        repository.save_event(CanonEvent(
            event_id="EVENT_TOLL_PLANNED", canonical_key="TOLL_PLANNED", novel_id=runtime.novel_id,
            canonical_name="掠夺队收过路费", semantic_summary="计划中的勒索", event_type="major",
            status="planned", location="salt_road", subjects=["raiders", "settlement"]))
        repository.save_event(CanonEvent(
            event_id="EVENT_TOLL_OCCURRED", canonical_key="TOLL_OCCURRED",
            novel_id=runtime.novel_id, canonical_name="掠夺队收过路费",
            semantic_summary="实际发生的勒索", event_type="major", status="occurred",
            location="north_gate", subjects=["raiders", "settlement"]))

    def mutation(runtime: MutationRuntime) -> MutationObservation:
        conflicts = SourceReferenceValidator(runtime.repository).promotion_conflicts(
            runtime.novel_id)
        codes = [finding.code for finding in conflicts]
        planned = next(event for event in runtime.repository.events(runtime.novel_id)
                       if event.event_id == "EVENT_TOLL_PLANNED")
        occurred = next(event for event in runtime.repository.events(runtime.novel_id)
                        if event.event_id == "EVENT_TOLL_OCCURRED")
        auto_merge = CanonService(runtime.repository).match_promotion(planned, occurred)
        detected = codes == ["PROMOTION_CONFLICT"] and auto_merge is False
        return MutationObservation(
            detected=detected, detector="SourceReferenceValidator.promotion_conflicts",
            codes=codes, severity="reject", persisted=False,
            note=f"参与者相同但地点不一致 → 必须报冲突且不自动 merge（auto_merge={auto_merge}）")

    return MutationCase(
        mutation_id="MUT-038", category="identity_integrity", target_layer="canon",
        description="Promotion 歧义：相似度高但参与者 / 地点不完全一致",
        expected_detector="SourceReferenceValidator.promotion_conflicts",
        expected_codes=["PROMOTION_CONFLICT"], expected_severity="reject",
        setup=setup, mutation=mutation, integration=True)


def _case_039() -> MutationCase:
    def setup(runtime: MutationRuntime) -> None:
        runtime.story_state = _story_state(runtime)

    def mutation(runtime: MutationRuntime) -> MutationObservation:
        first_record = runtime.story_state["effect_log"][0]
        key = source_stable_key(first_record)
        StoryStateCanonSync(runtime.repository).sync(runtime.novel_id, runtime.story_state)
        mapping = runtime.repository.find_mapping(runtime.novel_id, "story_state", key, "fact")
        if mapping is None:
            return MutationObservation(detected=False, detector="StoryStateCanonSync.sync",
                                       codes=["MAPPING_NOT_CREATED"], severity="reject",
                                       note="首次 sync 未建立 source mapping")
        first_id = mapping.canon_id
        db_path = runtime.repository.path
        runtime.repository.close()
        runtime.repository = CanonRepository(db_path)
        appended = dict(runtime.story_state)
        appended["effect_log"] = [
            first_record,
            {"op": "act_build_camp", "entity": "protagonist", "target": "camp", "value": 1,
             "source": "action:camp", "data": {"tick": 3}}]
        StoryStateCanonSync(runtime.repository).sync(runtime.novel_id, appended)
        second = runtime.repository.find_mapping(runtime.novel_id, "story_state", key, "fact")
        facts = {item.fact_id: item for item in runtime.repository.facts(runtime.novel_id)}
        detected = (second is not None and second.canon_id == first_id
                    and first_id in facts and len(facts) == 3
                    and facts[first_id].canonical_description.startswith("act_scavenge_ruins"))
        return MutationObservation(
            detected=detected,
            detector="StoryStateCanonSync.sync + CanonRepository.find_mapping",
            codes=["MAPPING_STABLE"] if detected else ["MAPPING_REBOUND"],
            severity="reject", persisted=True,
            note="关闭并重开 repository 后再次 sync：source X → 同一 FACT identity；"
                 "追加的新 effect 只新增自己的 fact（3 facts = 2 effect + 1 knowledge）")

    return MutationCase(
        mutation_id="MUT-039", category="identity_integrity", target_layer="canon",
        description="Source mapping 持久化：重开 DB 后 identity 不变",
        expected_detector="StoryStateCanonSync.sync + CanonRepository.find_mapping",
        expected_codes=["MAPPING_STABLE"], expected_severity="reject",
        should_persist=True, should_mutate_canon=True, should_mutate_source_mapping=True,
        setup=setup, mutation=mutation, integration=True)


def _case_040() -> MutationCase:
    def mutation(runtime: MutationRuntime) -> MutationObservation:
        flags = CanonOutlineFlags()
        planner = _planner(runtime, flags=flags)
        legacy_off = planner.should_use_canon_path() is False
        shadow = planner.shadow_plan(_intent(runtime), beats_raw=[_beat()],
                                     chapters_raw=[_chapter()])
        codes = _codes(shadow)
        shadow_files = list(runtime.shadow_dir.glob("*.json"))
        source = Path(outline_forge.__file__).read_text(encoding="utf-8", errors="replace")
        no_wiring = "canon" not in source.lower()
        detected = (legacy_off and codes == ["SHADOW_DISABLED"] and not shadow_files
                    and no_wiring)
        return MutationObservation(
            detected=detected, detector="CanonOutlineFlags / CanonAwareOutlinePlanner",
            codes=codes or ["SHADOW_DISABLED"], severity="legacy", persisted=False,
            note=f"flag 默认关闭：canon path={planner.should_use_canon_path()}；"
                 f"shadow 未执行（{len(shadow_files)} 个产物）；"
                 f"legacy outline_forge 未接线 canon={no_wiring}")

    return MutationCase(
        mutation_id="MUT-040", category="compatibility", target_layer="planner",
        description="Legacy flag off：新基础设施不得偷偷改变旧产品行为",
        expected_detector="CanonOutlineFlags / CanonAwareOutlinePlanner",
        expected_codes=["SHADOW_DISABLED"], expected_severity="legacy",
        setup=lambda runtime: _seed_gate_fact(runtime), mutation=mutation)


def build_mutation_cases() -> list[MutationCase]:
    """MUT-001 … MUT-051（C11 + C12 + C13 人工审核暴露的 blind spots）。"""

    builders = [_case_001, _case_002, _case_003, _case_004, _case_005, _case_006, _case_007,
                _case_008, _case_009, _case_010, _case_011, _case_012, _case_013, _case_014,
                _case_015, _case_016, _case_017, _case_018, _case_019, _case_020, _case_021,
                _case_022, _case_023, _case_024, _case_025, _case_026, _case_027, _case_028,
                _case_029, _case_030, _case_031, _case_032, _case_033, _case_034, _case_035,
                _case_036, _case_037, _case_038, _case_039, _case_040, _case_041, _case_042,
                _case_043, _case_044, _case_045, _case_046, _case_047, _case_048, _case_049,
                _case_050, _case_051]
    return [builder() for builder in builders]


# --------------------------------------------------------------------------- MUT-041 … 046（C12）


def _case_041() -> MutationCase:
    """删除 anchor 后留下的残句：metadata_leak=0 但 prose 已损坏。"""

    samples = ["承接 的投靠先例", "按 的先例", "中铭牌编号", "已在被确认",
               "把的首次开门", "而的塔回应", "与 确认的阿灰编号"]

    def mutation(runtime: MutationRuntime) -> MutationObservation:
        findings = [item for text in samples
                    for item in orphaned_reference_fragments(text, where="draft")]
        codes = sorted({item.code for item in findings})
        return MutationObservation(
            detected=len(findings) >= len(samples) and
            codes == ["ORPHANED_REFERENCE_FRAGMENT"],
            detector="prose.orphaned_reference_fragments", codes=codes or ["NO_FINDING"],
            severity="reject", persisted=False,
            note=f"{len(samples)} 处人工发现的残句全部命中（metadata_leak 检测不到这类损坏）")

    return MutationCase(
        mutation_id="MUT-041", category="writer_prose_integrity", target_layer="writer",
        description="孤立引用残片：删除 ch###/anchor 后留下「承接 的…」「已在被…」",
        expected_detector="prose.orphaned_reference_fragments",
        expected_codes=["ORPHANED_REFERENCE_FRAGMENT"], expected_severity="reject",
        setup=lambda runtime: None, mutation=mutation, integration=False)


def _case_042() -> MutationCase:
    """Canon audit prose spam：每条 event 都在解释历史，而不是推进当前动作。"""

    events = ["这是首次回应之后的连锁后果",
              "韩彻把编号记录重新解释为体系的延伸",
              "这一段属于旧广播之后确立的格式",
              "而不是首次事件，只是后续验证节点"]

    def mutation(runtime: MutationRuntime) -> MutationObservation:
        report = audit_prose_report(events)
        codes = sorted({item.code for item in report.findings})
        good = audit_prose_report(["他带人拆下门板", "阿灰先闻到水味", "队伍趁夜把货推进去"])
        clean = not good.findings and good.audit_events == 0
        return MutationObservation(
            detected="CANON_AUDIT_PROSE_SPAM" in codes and clean,
            detector="prose.audit_prose_report", codes=codes or ["NO_FINDING"],
            severity="reject", persisted=False,
            note=f"audit_events={report.audit_events} density={report.density}；"
                 f"动作章（3 条 action）不误报={clean}")

    return MutationCase(
        mutation_id="MUT-042", category="writer_prose_integrity", target_layer="writer",
        description="Canon 审计腔刷屏：连续 event 都在解释历史 anchor",
        expected_detector="prose.audit_prose_report",
        expected_codes=["CANON_AUDIT_PROSE_SPAM"], expected_severity="reject",
        setup=lambda runtime: None, mutation=mutation, integration=False)


def _case_043() -> MutationCase:
    """dog role 语义对齐：absent 却出场 / supportive 只有被保护 / payload 字段拼接。"""

    def mutation(runtime: MutationRuntime) -> MutationObservation:
        codes: list[str] = []
        absent = dog_role_alignment({"dog_role": "absent", "title": "夜哨", "goal": "绕营一周",
                                     "concrete_events": ["韩彻带阿灰绕营一周", "他数了下火位",
                                                         "风从北边压过来"]})
        codes += [item.code for item in absent]
        passive = dog_role_alignment({"dog_role": "supportive", "title": "谷底", "goal": "救狗",
                                      "dog_action": "阿灰被困在塌陷口，等人把它挖出来",
                                      "concrete_events": ["阿灰被困在塌陷口", "韩彻下谷开挖",
                                                          "余震压住通道"]})
        codes += [item.code for item in passive]
        copy = dog_role_alignment({"dog_role": "supportive", "title": "门后的第一层",
                                   "goal": "打开门禁确认门后环境",
                                   "dog_action": "门后的第一层打开门禁确认门后环境",
                                   "concrete_events": ["韩彻把旧铭牌按进凹槽",
                                                       "门体在第七次尝试后打开",
                                                       "队伍沿干燥长廊继续深入"]})
        codes += [item.code for item in copy]
        clean = dog_role_alignment({"dog_role": "involved", "title": "巡边", "goal": "确认退路",
                                    "dog_action": "阿灰贴地嗅出踩坏的草，把队伍拦在坡下",
                                    "concrete_events": ["阿灰贴地嗅出踩坏的草", "韩彻改走坡下",
                                                        "伏击点被绕开"]})
        detected = ({"DOG_ROLE_PRESENCE_MISMATCH", "DOG_ROLE_ACTION_ALIGNMENT",
                     "DOG_ROLE_PAYLOAD_SUMMARY_COPY"} <= set(codes)) and not clean
        return MutationObservation(
            detected=detected, detector="prose.dog_role_alignment",
            codes=sorted(set(codes)) or ["NO_FINDING"], severity="reject", persisted=False,
            note="absent 出场 / 被保护当 supportive / 字段拼接 payload 全部命中；"
                 "真实嗅探+拦截动作不误报")

    return MutationCase(
        mutation_id="MUT-043", category="dog_role_alignment", target_layer="writer",
        description="狗角色语义：role 必须由实际动作支撑，payload 不得是字段拼接",
        expected_detector="prose.dog_role_alignment",
        expected_codes=["DOG_ROLE_PRESENCE_MISMATCH", "DOG_ROLE_ACTION_ALIGNMENT",
                        "DOG_ROLE_PAYLOAD_SUMMARY_COPY"],
        expected_severity="reject", setup=lambda runtime: None, mutation=mutation,
        integration=False)


def _case_044() -> MutationCase:
    """resolved 之后重开：departure → return → 又「未归」。"""

    def mutation(runtime: MutationRuntime) -> MutationObservation:
        conflict = narrative_lifecycle_findings([
            {"id": "chA", "events": ["阿灰离开据点，三天后归队"]},
            {"id": "chB", "goal": "处理阿灰未归后的空缺", "events": ["守夜人手不够"]}])
        codes = [item.code for item in conflict]
        clean = narrative_lifecycle_findings([
            {"id": "ch1", "events": ["阿灰独自离队，三天没有回来"]},
            {"id": "ch2", "events": ["阿灰自己走回据点，带回猎团的消息"]},
            {"id": "ch3", "events": ["韩彻把门闩修好，不再整夜等门"]}])
        return MutationObservation(
            detected=codes and set(codes) == {"NARRATIVE_EVENT_LIFECYCLE_CONFLICT"}
            and not clean,
            detector="prose.narrative_lifecycle_findings", codes=codes or ["NO_FINDING"],
            severity="reject", persisted=False,
            note="departure → resolved return 之后又回到未归状态必须报冲突；"
                 "正常 departure → return → 余波不误报")

    return MutationCase(
        mutation_id="MUT-044", category="narrative_lifecycle", target_layer="graph",
        description="已解决的人物事件被重开：阿灰去而复返之后又「未归」",
        expected_detector="prose.narrative_lifecycle_findings",
        expected_codes=["NARRATIVE_EVENT_LIFECYCLE_CONFLICT"], expected_severity="reject",
        setup=lambda runtime: None, mutation=mutation, integration=False)


def _case_045() -> MutationCase:
    """跨字段语义矛盾：decision / world_state_change 属于另一条剧情。"""

    def mutation(runtime: MutationRuntime) -> MutationObservation:
        conflict = cross_field_findings({
            "goal": "调查塔基最早刻写，判断重刻年代",
            "concrete_events": ["韩彻清理塔基泥土", "发现基座叠着两层刻写", "把两层拓印并排比照"],
            "decision": "韩彻以一人一狗名义签署新规矩",
            "world_state_change": "废土第一条共同规矩成立"})
        codes = sorted({item.code for item in conflict})
        clean = cross_field_findings({
            "goal": "调查塔基最早刻写，判断重刻年代",
            "concrete_events": ["韩彻清理塔基泥土", "发现两层刻写", "拓印比照确认后世重刻"],
            "decision": "暂不破坏塔体，先查明重刻者与年代",
            "world_state_change": "确认塔基存在原刻与后世重刻两层记录"})
        return MutationObservation(
            detected=codes == ["CROSS_FIELD_SEMANTIC_MISMATCH"] and not clean,
            detector="prose.cross_field_findings", codes=codes or ["NO_FINDING"],
            severity="reject", persisted=False,
            note="同一章字段跨剧情 frame 必须报错；同 frame 字段不误报")

    return MutationCase(
        mutation_id="MUT-045", category="cross_field_semantics", target_layer="planner",
        description="跨字段语义矛盾：goal/event 是一章，decision/world_state 是另一章",
        expected_detector="prose.cross_field_findings",
        expected_codes=["CROSS_FIELD_SEMANTIC_MISMATCH"], expected_severity="reject",
        setup=lambda runtime: None, mutation=mutation, integration=False)


def _case_046() -> MutationCase:
    """Sample Pack 完整性：重复章 / 每卷不足 / 真随机不足 / 同章多类别。"""

    def mutation(runtime: MutationRuntime) -> MutationObservation:
        entries = [{"chapter": f"ch{index:03d}", "volume": 2, "category": "normal"}
                   for index in range(1, 6)]
        entries += [{"chapter": "ch002", "volume": 4, "category": "conflict"},
                    {"chapter": "ch002", "volume": 4, "category": "climax"}]
        findings = validate_sample_pack(entries, volumes=[2, 4], expected_per_volume=5,
                                        min_random=18)
        codes = sorted({item.code for item in findings})
        good = validate_sample_pack(
            [{"chapter": f"v{volume}c{index}", "volume": volume,
              "category": "normal" if index <= 4 else "climax"}
             for volume in (2, 4, 6, 7, 8, 9, 10) for index in range(1, 6)],
            volumes=[2, 4, 6, 7, 8, 9, 10], expected_per_volume=5, min_random=18)
        detected = ({"SAMPLE_ENTRY_COUNT", "SAMPLE_DUPLICATE_CHAPTER", "SAMPLE_PER_VOLUME_COUNT",
                     "SAMPLE_RANDOM_COUNT", "SAMPLE_CHAPTER_MULTI_CATEGORY"} <= set(codes)
                    and not good)
        return MutationObservation(
            detected=detected, detector="prose.validate_sample_pack",
            codes=codes, severity="reject", persisted=False,
            note="重复章 / 每卷数量 / 真随机数量 / 同章多类别全部命中；"
                 "合规样本（28 normal ≥ 18）零 finding 不误报")

    return MutationCase(
        mutation_id="MUT-046", category="sample_integrity", target_layer="outline",
        description="Sample Pack 完整性：35 条 / 35 唯一 / 每卷 5 / 真随机 ≥18",
        expected_detector="prose.validate_sample_pack",
        expected_codes=["SAMPLE_ENTRY_COUNT", "SAMPLE_DUPLICATE_CHAPTER",
                        "SAMPLE_PER_VOLUME_COUNT", "SAMPLE_RANDOM_COUNT",
                        "SAMPLE_CHAPTER_MULTI_CATEGORY"],
        expected_severity="reject", setup=lambda runtime: None, mutation=mutation,
        integration=False)


# --------------------------------------------------------------------------- MUT-047 … 051（C13）


def _stale_frame_sample() -> dict[str, Any]:
    return {
        "goal": "审讯活口，从货源单据里找出内应",
        "concrete_events": ["韩彻把活口关进旧仓，先给他水", "活口交代接头暗号",
                            "韩彻把货单与账册比对，锁定报备车次的副手"],
        "trigger": "伏击队在灰雾路段动手，箭擦过车辕",
        "protagonist_action": "韩彻用残响外放震退伏击",
        "opposition": "阿灰扑咬伏击者",
        "turn": "弃货保人",
        "end_state": "韩彻带人货回集",
    }


def _case_047() -> MutationCase:
    """targeted repair 只改 goal/events/end_state，decision/trigger/action/turn/payoff/cost/loss 仍是旧剧情。

    fixture 直接来自 Final Convergence 的真实结构（salt road 124/133/149、V5 215/260）。
    """

    real_structures = [
        {   # ch124：events 已改为审讯/内应，decision 仍宣布商路控制
            "goal": "审讯活口，从货源单据里找出内应",
            "concrete_events": ["韩彻把活口关进旧仓，先给他水", "活口交代接头暗号",
                                "比对货单锁定报备副手", "放下一次报备的饵"],
            "end_state": "内应锁定但未惊动",
            "decision": "公开协议陷阱，宣布商路归铁锈集控制",
            "trigger": "伏击队在灰雾路段动手，箭擦过车辕",
            "protagonist_action": "韩彻用残响外放震退伏击",
            "opposition": "阿灰扑咬伏击者",
            "turn": "弃货保人",
            "payoff": "商路归铁锈集",
            "cost": "两箱盐货留在弯道",
            "loss": "盐路安全假象被打破"},
        {   # ch133：改道谈判，但 decision 仍是弃货保人
            "goal": "在谈判破裂后把盐路的实际控制权拿到手里",
            "concrete_events": ["管事拒绝交出报备权", "商队改走北线被地裂卡住",
                                "回来接受按趟结算"],
            "end_state": "盐路按趟结算，报备权归铁锈集",
            "decision": "弃部分货保人",
            "turn": "弃货换全员撤出",
            "payoff": "人货两全"},
        {   # ch149：封锁/水道/内应落网，但 decision 仍是弃货撤离
            "goal": "顶住封锁并让内应自己暴露",
            "concrete_events": ["封锁方扣下两车货", "改走小水道按时送货",
                                "盯住报备副手", "内应在接头点落网"],
            "end_state": "封锁解除，内应落网",
            "decision": "弃一箱货换全员撤出",
            "loss": "两箱货被扣"},
        {   # ch215：谷口踏勘，但 decision 仍是救阿灰
            "goal": "在低频谷入口完成第一次生态踏勘",
            "concrete_events": ["记录谷口低频节律", "标出三处下撤点", "沿岩脊改道"],
            "end_state": "谷口路线与下撤点确定",
            "decision": "放弃材料先救阿灰",
            "turn": "外放救出阿灰"},
        {   # ch260：医疗/隔离，但 decision 仍是外放救人
            "goal": "处理塌陷救援之后的医疗、隔离与关系后果",
            "concrete_events": ["送阿灰进隔离棚", "分箱封存骨片与拓印",
                                "把再入谷的决定权交回阿灰"],
            "end_state": "伤情与证据各归其位",
            "decision": "冒险外放救阿灰"},
        {   # ch559：正式签署，但 action/decision/cost 仍属「公开数据 + 分残响」旧 frame
            "goal": "用一人一狗两个名字签下共守规矩",
            "concrete_events": ["各方代表聚在塔壁前", "两方为署名顺序争执",
                                "韩彻刻下自己与阿灰两个名字", "各方依次落笔，新秩序成立"],
            "end_state": "新秩序成立，韩彻独自出塔",
            "protagonist_action": "韩彻公开 observatory_data，把可外传的部分分给记录者",
            "decision": "不独占数据，分出部分残响力量",
            "cost": "韩彻独自留塔完成刻写"},
    ]

    def mutation(runtime: MutationRuntime) -> MutationObservation:
        stale = chapter_frame_findings(_stale_frame_sample())
        codes = sorted({item.code for item in stale})
        real_hits = {index: sorted({item.where for item in chapter_frame_findings(structure)})
                     for index, structure in enumerate(real_structures, start=1)}
        real_ok = all(real_hits.values()) and {"decision", "trigger", "protagonist_action"} <= set(
            real_hits[1])
        transition = state_transition_findings([
            {"id": "ch107", "display_number": 107,
             "world_state_change": "一条商路正式受铁锈集控制"},
            {"id": "ch133", "display_number": 133,
             "goal": "取得盐路的实际控制权，谈成按趟结算"}])
        payload_bad = dog_payload_evidence_findings({
            "dog_role": "supportive",
            "concrete_events": ["韩彻带阿灰试走通道", "尽头发现旧文明残堆"],
            "dog_action": "阿灰嗅出残堆入口"})
        payload_good = dog_payload_evidence_findings({
            "dog_role": "supportive",
            "concrete_events": ["阿灰嗅出残堆入口", "韩彻带人跟进"],
            "dog_action": "阿灰嗅出残堆入口"})
        clean = chapter_frame_findings({
            "goal": "审讯活口，从货源单据里找出内应",
            "concrete_events": ["韩彻把活口关进旧仓，先给他水", "活口交代接头暗号",
                                "韩彻把货单与账册比对，锁定报备车次的副手"],
            "trigger": "仓棚里多出一个被绑的活口",
            "protagonist_action": "韩彻先给他水，再问谁付的钱",
            "opposition": "活口不肯先开口",
            "turn": "货单上盖着商队内印",
            "payoff": "内应身份被锁定",
            "end_state": "内应被锁定但未惊动"})
        fields = {item.where for item in stale}
        detected = (codes == ["STALE_CHAPTER_FRAME"] and real_ok and not clean
                    and [item.code for item in transition] == ["STATE_TRANSITION_PREMATURE"]
                    and [item.code for item in payload_bad] == ["DOG_ROLE_PAYLOAD_UNSUPPORTED"]
                    and not payload_good
                    and {"trigger", "protagonist_action", "opposition"} <= fields)
        codes = codes + [f"REAL_FIXTURE_{index}:" + ",".join(sorted(hit))
                         for index, hit in real_hits.items()]
        return MutationObservation(
            detected=detected, detector="prose.chapter_frame_findings",
            codes=codes or ["NO_FINDING"], severity="reject", persisted=False,
            note=f"半改章必须报 stale frame；命中字段={sorted(fields)}；"
                 f"5 个真实结构全部命中={real_ok}；整章同 frame 不误报")

    return MutationCase(
        mutation_id="MUT-047", category="stale_chapter_frame", target_layer="planner",
        description="Stale Chapter Semantic Frame：只改 events，trigger/action/opposition 仍是旧剧情",
        expected_detector="prose.chapter_frame_findings",
        expected_codes=["STALE_CHAPTER_FRAME"], expected_severity="reject",
        setup=lambda runtime: None, mutation=mutation, integration=False)


def _case_048() -> MutationCase:
    """被标为 first occurrence 的章节不得说「首次之后 / 再次 / 上次」；未来 institution 也不得提前引用。"""

    def mutation(runtime: MutationRuntime) -> MutationObservation:
        bad = first_occurrence_findings({
            "first_occurrence_event_id": "EVENT_ZERO_LAYER_GATE_FIRST_OPEN",
            "goal": "门开，进入干燥混凝土长廊",
            "concrete_events": [
                "前六次尝试均失败，门体只升温",
                "韩彻判断这是第零层门禁首次打开后系统对重复接触的延迟响应，而非门从未被开启过",
                "第七次尝试门开"]})
        codes = sorted({item.code for item in bad})
        clean = first_occurrence_findings({
            "first_occurrence_event_id": "EVENT_ZERO_LAYER_GATE_FIRST_OPEN",
            "goal": "第七次尝试后门第一次打开",
            "concrete_events": ["前六次尝试均失败，门体只升温", "第七次把铭牌按进凹槽",
                                "门体第一次打开，队伍进入干燥长廊"]})
        future = future_canon_leak_findings([
            {"id": "ch358", "display_number": 358,
             "goal": "在遗迹争议中封存第三柜",
             "events": ["韩彻按共守规矩与最终投票所确立的公开规则封存第三柜"],
             "end_state": "第三柜被封存"},
            {"id": "ch559", "display_number": 559, "goal": "正式签署共守规矩",
             "events": ["各方依次落笔，新秩序成立"]}])
        future_codes = sorted({item.code for item in future})
        return MutationObservation(
            detected=(codes == ["FIRST_OCCURRENCE_SELF_CONTRADICTION"] and not clean
                      and future_codes == ["FUTURE_CANON_LEAK"]),
            detector="prose.first_occurrence_findings", codes=codes or ["NO_FINDING"],
            severity="reject", persisted=False,
            note="first occurrence 自相矛盾 + V7 引用 V10 institution（future canon leak）"
                 "都必须报错；正常首次章与合法位置不误报")

    return MutationCase(
        mutation_id="MUT-048", category="first_occurrence", target_layer="writer",
        description="First Occurrence Self Contradiction：首次发生章自称「首次之后 / 再次」",
        expected_detector="prose.first_occurrence_findings",
        expected_codes=["FIRST_OCCURRENCE_SELF_CONTRADICTION"], expected_severity="reject",
        setup=lambda runtime: None, mutation=mutation, integration=False)


def _case_049() -> MutationCase:
    """不可逆状态（永久封闭）被重复声明。"""

    def mutation(runtime: MutationRuntime) -> MutationObservation:
        bad = irreversible_state_findings([
            {"id": "ch350", "events": ["三方同时抵达第零层，防御系统失控"]},
            {"id": "ch379", "events": ["韩彻决定永久封闭第零层"]},
            {"id": "ch380", "events": ["第零层永久封死，入口坍塌"]}])
        codes = sorted({item.code for item in bad})
        clean = irreversible_state_findings([
            {"id": "ch350", "events": ["韩彻紧急锁闭第零层核心门禁"]},
            {"id": "ch379", "events": ["老鸦带人爆破主通道，把第零层永久封死"]},
            {"id": "ch380", "events": ["各方在停火桌上清点封层后果"]}])
        return MutationObservation(
            detected=codes == ["IRREVERSIBLE_STATE_REPEATED"] and not clean,
            detector="prose.irreversible_state_findings", codes=codes or ["NO_FINDING"],
            severity="reject", persisted=False,
            note="永久封闭重复声明必须报错；紧急锁闭 → 唯一永久封死 不误报")

    return MutationCase(
        mutation_id="MUT-049", category="irreversible_state", target_layer="graph",
        description="Repeated Irreversible Transition：第零层被多次声明永久封闭",
        expected_detector="prose.irreversible_state_findings",
        expected_codes=["IRREVERSIBLE_STATE_REPEATED"], expected_severity="reject",
        setup=lambda runtime: None, mutation=mutation, integration=False)


def _case_050() -> MutationCase:
    """同一章内同行 / 留守自相矛盾。"""

    def mutation(runtime: MutationRuntime) -> MutationObservation:
        bad = within_chapter_state_findings({
            "protagonist_action": "带阿灰出发去旧观测通道",
            "loss": "阿灰留在据点",
            "end_state": "队伍又带阿灰出发"})
        codes = sorted({item.code for item in bad})
        clean = within_chapter_state_findings({
            "protagonist_action": "带阿灰出发去旧观测通道",
            "loss": "通道里的风声盖住了脚步",
            "end_state": "阿灰先一步探到通道口"})
        return MutationObservation(
            detected=codes == ["WITHIN_CHAPTER_STATE_CONTRADICTION"] and not clean,
            detector="prose.within_chapter_state_findings", codes=codes or ["NO_FINDING"],
            severity="reject", persisted=False,
            note="同章「带阿灰出发」+「阿灰留在据点」必须报错；同行章不误报")

    return MutationCase(
        mutation_id="MUT-050", category="within_chapter_state", target_layer="writer",
        description="Within Chapter State Contradiction：同行与留守在同一章并存",
        expected_detector="prose.within_chapter_state_findings",
        expected_codes=["WITHIN_CHAPTER_STATE_CONTRADICTION"], expected_severity="reject",
        setup=lambda runtime: None, mutation=mutation, integration=False)


def _case_051() -> MutationCase:
    """阿灰只是对象（被保护/被交易/被讨论/受伤/不在场）时不能判 supportive。"""

    def mutation(runtime: MutationRuntime) -> MutationObservation:
        object_only = dog_role_object_findings({
            "dog_role": "supportive",
            "concrete_events": ["缝合会代表要求引用阿灰的编号", "韩彻拒绝交出编号",
                                "阿灰被留在营地"],
            "dog_action": "阿灰被留在营地"})
        codes = sorted({item.code for item in object_only})
        traded = dog_role_object_findings({
            "dog_role": "supportive",
            "concrete_events": ["信使开价，以补给换阿灰编号的使用权", "韩彻把报价单压在桌上",
                                "阿灰在门边等着"],
            "dog_action": "信使开价，以补给换阿灰编号的使用权"})
        real_action = dog_role_object_findings({
            "dog_role": "supportive",
            "concrete_events": ["阿灰贴地嗅出踩坏的草", "韩彻改走坡下", "伏击点被绕开"],
            "dog_action": "阿灰贴地嗅出踩坏的草"})
        # physical_presence 自洽（真实 ch436 / ch437 结构）
        present_left = dog_role_presence_findings("offscreen_effect", physical_presence=True)
        absent_supportive = dog_role_presence_findings("supportive", physical_presence=False)
        presence_codes = sorted({item.code for item in present_left + absent_supportive})
        recompute_present = dog_role_recompute(
            {"physical_presence": True, "goal": "招揽阿灰",
             "concrete_events": ["阿灰自己来回走了两趟，最后自己跟着那只同类走出旧路钉"],
             "dog_action": "阿灰自己跟随同类离开"})
        recompute_absent = dog_role_recompute(
            {"physical_presence": False, "goal": "处理阿灰离开后的第一夜",
             "concrete_events": ["据点会议上有人要求追回阿灰", "韩彻拒绝用锁链"],
             "dog_action": "阿灰不在据点"})
        # 真实人审结构：守门/担架在场不得 offscreen；把药给狗不算 independent；事件里的动作与角色一致
        presence_cases = [
            (dog_role_presence_findings("offscreen_effect", physical_presence=True), "ch361/439"),
            (dog_role_presence_findings("supportive", physical_presence=False), "ch499"),
        ]
        presence_ok = all([item.code for item in rows] == ["DOG_ROLE_PRESENCE_MISMATCH"]
                          for rows, _ in presence_cases)
        recompute_passive = dog_role_recompute({
            "physical_presence": True, "goal": "重伤下慢速撤离",
            "concrete_events": ["韩彻在撤离中伤势加重", "改走慢速路线", "阿灰在担架上被抬着"],
            "dog_action": "韩彻把仅剩的药品留给阿灰"})
        recompute_found = dog_role_recompute({
            "physical_presence": True, "goal": "撤离中发现猎团器械",
            "concrete_events": ["阿灰发现猎团的测绘钉", "韩彻把钉子起出来带回"],
            "dog_action": "阿灰发现猎团的测绘钉"})
        presence_ok = (presence_ok and recompute_passive in ("involved", "supportive")
                       and recompute_found == "supportive")
        detected = (codes == ["DOG_ROLE_OBJECT_NOT_SUPPORTIVE"] and traded
                    and not real_action
                    and presence_codes == ["DOG_ROLE_PRESENCE_MISMATCH"]
                    and recompute_present == "independent"
                    and recompute_absent == "offscreen_effect"
                    and presence_ok)
        return MutationObservation(
            detected=detected, detector="prose.dog_role_object_findings",
            codes=codes or ["NO_FINDING"], severity="reject", persisted=False,
            note="被保护 / 被交易 / 被讨论 / 受伤 / 不在场不能判 supportive；"
                 f"在场=independent({recompute_present})、不在场=offscreen_effect"
                 f"({recompute_absent})；在场/不在场契约与真实动作证据均校验；"
                 "真实嗅探帮忙动作不误报")

    return MutationCase(
        mutation_id="MUT-051", category="dog_role_object", target_layer="writer",
        description="Dog Role Object vs Action：对象化场景不得判 supportive",
        expected_detector="prose.dog_role_object_findings",
        expected_codes=["DOG_ROLE_OBJECT_NOT_SUPPORTIVE"], expected_severity="reject",
        setup=lambda runtime: None, mutation=mutation, integration=False)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="C11 Canon fault injection / mutation suite")
    parser.add_argument("--root", default="", help="临时工作目录（默认系统临时目录）")
    parser.add_argument("--output", default="", help="写出 Defense Coverage Matrix 的路径")
    parser.add_argument("--only", default="", help="逗号分隔的 mutation id（默认全部）")
    args = parser.parse_args(list(argv) if argv is not None else None)
    root = Path(args.root) if args.root else Path(tempfile.mkdtemp(prefix="canon_mutations_"))
    only = [item for item in args.only.split(",") if item] if args.only else None
    report = run_mutation_suite(root=root, only=only)
    text = report.to_markdown()
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text)
    print(f"total={report.total} passed={report.passed} failed={report.failed} "
          f"blocked={report.blocked} kill_rate={report.mutation_kill_rate:.2%} "
          f"pollution_rate={report.state_pollution_rate:.2%}")
    return 0 if report.ok() else 1


if __name__ == "__main__":  # pragma: no cover - CLI
    raise SystemExit(main())
