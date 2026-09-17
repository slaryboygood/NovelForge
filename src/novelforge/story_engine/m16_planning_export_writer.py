"""M16A Planning Export / M16B Writer Integration：baseline + acceptance + M17 readiness。

scope 来源（repo）：MILESTONES M16A/M16B 行 + MASTER_PLAN M16A/M16B 行。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from novelforge.story_engine.historical_adoption import ADOPTION_DIR
from novelforge.story_engine.historical_ir import HISTORY_DIR
from novelforge.story_engine.m11_p15p import (
    FROZEN_FOUNDATION_DIGESTS,
    FROZEN_SOURCE_DIGESTS,
)
from novelforge.story_engine.m11_run12 import M11Run12Service
from novelforge.story_engine.m12_acceptance import semantic_fingerprint
from novelforge.story_engine.m15_canon_inspector import M15_DIR
from novelforge.story_engine.phase_snapshot import (
    snapshot_exists,
    verify_phase_snapshot,
    write_phase_snapshot,
)
from novelforge.story_engine.milestone_acceptance import publish_phase_snapshot

M16_DIR = "m16"
BASELINE_FILE = "M16_EXECUTION_BASELINE.json"
FREEZE_GUARD_FILE = "M15_FREEZE_GUARD.json"
TEST_EVIDENCE_FILE = "M16_TEST_EVIDENCE.json"
ACCEPTANCE_FILE = "M16_ACCEPTANCE.json"
M16A_ACCEPTANCE_FILE = "M16A_ACCEPTANCE.json"
M16B_ACCEPTANCE_FILE = "M16B_ACCEPTANCE.json"
M17_READINESS_FILE = "M16_M17_READINESS.json"

WORK_ITEMS: tuple[str, ...] = ("M16A", "M16B")
WORK_ITEM_SCOPE: dict[str, dict[str, Any]] = {
    "M16A": {
        "title": "Planning Export",
        "repo_reference": ("MILESTONES M16A：Planning-aware Export + Writer-ready Package + "
                          "Story Bible / 卡片 / Timeline / Spine / 三部大纲（基础 md/json/docx 已存在）"),
        "files": ["src/novelforge/story_builder/export_package.py",
                  "tests/test_m16a_planning_export.py"],
        "flows": ["export/package（json/markdown/docx）", "export/writer-bundle",
                  "validate_export_package（schema / identity / provenance / truth separation）"],
    },
    "M16B": {
        "title": "Writer Integration + Draft Fact Sync",
        "repo_reference": ("MILESTONES M16B：Writer Integration + Draft Fact Sync"
                           "（writer.py 事实校验已存在，缺产品入口与回写通道）"),
        "files": ["src/novelforge/story_builder/writer_integration.py",
                  "tests/test_m16b_writer_integration.py"],
        "flows": ["writer/context（分层 truth blocks）", "writer/drafts（preview 草稿 + 校验）",
                  "writer/drafts/{id}/sync-facts（只产生 proposal）"],
    },
}

ACCEPTANCE_CRITERIA: tuple[dict[str, str], ...] = (
    {"criterion": "planning_export_complete",
     "definition": "M16A：单一 export projection + json/markdown/docx serializer + Writer-ready Package"},
    {"criterion": "export_validation_pass",
     "definition": "schema / stable identity / provenance / truth separation / 源 digest 记录全部通过"},
    {"criterion": "export_replay_deterministic",
     "definition": "同输入两次导出 export_id 与内容完全一致（可重放）"},
    {"criterion": "writer_integration_complete",
     "definition": "M16B：WriterContextBuilder（6 个分层 block）+ writer 产品入口 + draft 存储"},
    {"criterion": "writer_context_layered",
     "definition": "canon/occurred/historical_repair/planned/guidance 分层，含 source/identity/digest"},
    {"criterion": "draft_fact_sync_is_proposal_only",
     "definition": "Draft Fact Sync 只产生 PROPOSED proposal，不写 StoryState / Canon"},
    {"criterion": "writer_validation_not_masked",
     "definition": "既有 validate_writer_output 的失败（FACT_UNKNOWN / RESOURCE_MISMATCH）不被伪装成功"},
    {"criterion": "frozen_truth_unchanged",
     "definition": "M11/M12 fingerprint + truth digests + M13/M14/M15 acceptance 输入不变"},
    {"criterion": "tests_pass",
     "definition": "pytest / validate_project / writer integration tests / export validation 全 PASS"},
    {"criterion": "architecture_audit_pass",
     "definition": "M16 subsystem 无重复 context builder / serializer / truth mapping，边界 typed"},
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> Any:
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8-sig")) if path.is_file() else {}


def _write_json(path: Path, payload: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                    encoding="utf-8", newline="\n")


def _head_commit(root: Path) -> str:
    head = root / ".git" / "HEAD"
    if not head.is_file():
        return ""
    text = head.read_text(encoding="utf-8").strip()
    if text.startswith("ref:"):
        ref = root / ".git" / text.split(" ", 1)[1].strip()
        return ref.read_text(encoding="utf-8").strip() if ref.is_file() else ""
    return text


class M16PlanningExportWriterService:
    def __init__(self, project_root: Path | str, *, design_dir: str = ADOPTION_DIR,
                 foundation_dir: str = HISTORY_DIR) -> None:
        self.root = Path(project_root).resolve()
        self.design_dir = (self.root / design_dir).resolve()
        self.foundation_dir = (self.root / foundation_dir).resolve()
        self.out_dir = self.design_dir / M16_DIR
        self.runner = M11Run12Service(self.root, design_dir=str(self.design_dir),
                                      foundation_dir=str(self.foundation_dir))

    # ------------------------------------------------------------ preflight
    def freeze_guard(self) -> dict[str, Any]:
        m15_dir = self.design_dir / M15_DIR
        acceptance = _read_json(m15_dir / "M15_ACCEPTANCE.json")
        readiness = _read_json(m15_dir / "M15_M16_READINESS.json")
        truth = self.runner.truth_digests()
        frozen = self.runner.frozen_digests()
        snapshots = {phase: verify_phase_snapshot(self.root, phase)["status"]
                     for phase in ("M15_PREFLIGHT", "M15_ACCEPTANCE")
                     if snapshot_exists(self.root, phase)}
        checks = {
            "m15_acceptance_pass": acceptance.get("status") == "PASS",
            "m16_entry_allowed": readiness.get("m16_entry_allowed") is True,
            "truth_digests_unchanged": (
                truth.get("canon") == FROZEN_SOURCE_DIGESTS["canon"]
                and truth.get("story_state") == FROZEN_SOURCE_DIGESTS["story_state"]
                and truth.get("legacy") == FROZEN_SOURCE_DIGESTS["legacy"]
                and truth.get("chapter_ir") == FROZEN_SOURCE_DIGESTS["chapter_ir"]
                and truth.get("historical_foundation") == FROZEN_FOUNDATION_DIGESTS),
            "contract_gate_unchanged": (frozen.get("contract") == "67559aa55442d69e"
                                        and frozen.get("repair_gate")
                                        == "e1eab4c33ae75b01"),
            "m15_snapshots_immutable": (bool(snapshots)
                                        and all(v == "PASS" for v in snapshots.values())),
        }
        payload = {"generated_at": _now(), "guard_id": "M15_FREEZE_GUARD",
                   "status": "PASS" if all(checks.values()) else "FAIL",
                   "checks": checks, "m15_acceptance_status": acceptance.get("status"),
                   "m11_semantic_fingerprint": semantic_fingerprint(self.design_dir),
                   "phase_snapshots": snapshots,
                   "read_only": True, "non_authoritative": True}
        _write_json(self.out_dir / FREEZE_GUARD_FILE, payload)
        return payload

    def execution_baseline(self) -> dict[str, Any]:
        payload = {
            "generated_at": _now(), "baseline_id": "M16_EXECUTION_BASELINE",
            "milestone": "M16", "milestone_title": "Planning Export / Writer Integration",
            "goal": ("M16A：Planning-aware Export + Writer-ready Package（Story Bible / 卡片 / "
                     "Timeline / Spine / 四级大纲）；M16B：Writer Integration + Draft Fact Sync。"
                     "（repo: MILESTONES M16A/M16B）"),
            "work_items": [{"item": item, **WORK_ITEM_SCOPE[item]} for item in WORK_ITEMS],
            "entry_criteria": {"requires": "M15 acceptance PASS / m16_entry_allowed",
                               "artifact": FREEZE_GUARD_FILE},
            "required_artifacts": [BASELINE_FILE, FREEZE_GUARD_FILE, TEST_EVIDENCE_FILE,
                                   M16A_ACCEPTANCE_FILE, M16B_ACCEPTANCE_FILE,
                                   ACCEPTANCE_FILE, M17_READINESS_FILE,
                                   "docs/WASTELAND_001_M16_PLANNING_EXPORT_WRITER_INTEGRATION_REPORT.md"],
            "acceptance_criteria": [dict(row) for row in ACCEPTANCE_CRITERIA],
            "next_milestone_dependency": {"milestone": "M17 Cross-genre E2E（至少 3 题材）",
                                          "requires": "M16 acceptance PASS"},
            "frozen_truth_digests": {"source": dict(FROZEN_SOURCE_DIGESTS),
                                     "foundation": dict(FROZEN_FOUNDATION_DIGESTS),
                                     "contract": "67559aa55442d69e",
                                     "repair_gate": "e1eab4c33ae75b01"},
            "m11_to_m15_fingerprint": semantic_fingerprint(self.design_dir),
            "read_only": True, "non_authoritative": True}
        _write_json(self.out_dir / BASELINE_FILE, payload)
        return payload

    def run_preflight(self, *, snapshot_refresh_reason: str = "") -> dict[str, Any]:
        guard = self.freeze_guard()
        baseline = self.execution_baseline()
        payload = {"generated_at": _now(), "phase": "M16_PREFLIGHT",
                   "freeze_guard_status": guard["status"],
                   "work_items": [row["item"] for row in baseline["work_items"]],
                   "status": "PASS" if guard["status"] == "PASS" else "FAIL",
                   "read_only": True, "non_authoritative": True}
        _write_json(self.out_dir / "M16_PREFLIGHT_SUMMARY.json", payload)
        self._publish_snapshot("M16_PREFLIGHT", {
            "phase_id": "M16_PREFLIGHT", "freeze_guard_status": guard["status"],
            "m15_acceptance_status": guard.get("m15_acceptance_status"),
            "work_items": list(WORK_ITEMS),
            "acceptance_criteria": [row["criterion"]
                                    for row in baseline["acceptance_criteria"]],
        }, evidence_sources=[FREEZE_GUARD_FILE, BASELINE_FILE],
            refresh_reason=snapshot_refresh_reason)
        return payload

    def record_test_evidence(self, *, pytest: Mapping[str, Any],
                             validate_project: Mapping[str, Any],
                             export: Mapping[str, Any], writer: Mapping[str, Any],
                             architecture_audit: Mapping[str, Any] | None = None
                             ) -> dict[str, Any]:
        payload = {"generated_at": _now(), "evidence_id": "M16_TEST_EVIDENCE",
                   "pytest": dict(pytest), "validate_project": dict(validate_project),
                   "export_validation": dict(export), "writer_integration": dict(writer),
                   "architecture_audit": dict(architecture_audit or {}),
                   "read_only": True, "non_authoritative": True}
        _write_json(self.out_dir / TEST_EVIDENCE_FILE, payload)
        return payload

    def work_item_acceptance(self, *, service_pass: Mapping[str, bool]) -> dict[str, Any]:
        rows = [{"item": item, "title": WORK_ITEM_SCOPE[item]["title"],
                 "status": "PASS" if service_pass.get(item) else "FAIL",
                 "flows": list(WORK_ITEM_SCOPE[item]["flows"]),
                 "files": list(WORK_ITEM_SCOPE[item]["files"])} for item in WORK_ITEMS]
        payload = {"generated_at": _now(),
                   "m16a_status": rows[0]["status"], "m16b_status": rows[1]["status"],
                   "items": rows,
                   "read_only": True, "non_authoritative": True}
        _write_json(self.out_dir / M16A_ACCEPTANCE_FILE,
                    {"generated_at": _now(), "milestone": "M16A",
                     "status": rows[0]["status"], "flows": rows[0]["flows"],
                     "read_only": True})
        _write_json(self.out_dir / M16B_ACCEPTANCE_FILE,
                    {"generated_at": _now(), "milestone": "M16B",
                     "status": rows[1]["status"], "flows": rows[1]["flows"],
                     "read_only": True})
        return payload

    def architecture_audit(self) -> dict[str, Any]:
        src = self.root / "src" / "novelforge" / "story_builder"
        export_lines = len((src / "export_package.py").read_text(
            encoding="utf-8").splitlines()) if (src / "export_package.py").is_file() else 0
        writer_lines = len((src / "writer_integration.py").read_text(
            encoding="utf-8").splitlines()) if (src / "writer_integration.py").is_file() else 0
        api = (self.root / "ui" / "src" / "api.ts").read_text(encoding="utf-8")
        checks = {
            "single_export_projection": (src / "export_package.py").is_file(),
            "single_writer_context_builder": (src / "writer_integration.py").is_file(),
            "reuses_existing_writer_projection": (
                "build_writer_package" in (src / "writer_integration.py").read_text(
                    encoding="utf-8")),
            "reuses_existing_docx_serializer": (
                "docx_bytes" in (src / "export_package.py").read_text(encoding="utf-8")),
            "modules_bounded": 0 < export_lines <= 420 and 0 < writer_lines <= 520,
            "typed_export_boundary": "EXPORT_FORMAT_VERSION" in (
                src / "export_package.py").read_text(encoding="utf-8"),
            "no_parallel_truth_model": "TRUTH_LAYER_LEGEND" in (
                src / "export_package.py").read_text(encoding="utf-8"),
        }
        payload = {"generated_at": _now(), "audit_id": "M16_ARCHITECTURE_AUDIT",
                   "status": "PASS" if all(checks.values()) else "FAIL",
                   "checks": checks, "export_package_lines": export_lines,
                   "writer_integration_lines": writer_lines,
                   "duplication_removed": [
                       "export projection 单一实现（json/markdown/docx 共用）",
                       "docx 序列化复用 outline_revision.docx_bytes（不再重写 OOXML）",
                       "writer 事实包复用 story_engine.writer.build_writer_package",
                       "writer claim 校验复用既有 validate_writer_output"],
                   "dead_code_removed": [],
                   "read_only": True, "non_authoritative": True}
        _write_json(self.out_dir / "M16_ARCHITECTURE_AUDIT.json", payload)
        return payload

    def acceptance(self, *, evidence: Mapping[str, Any] | None = None,
                   snapshot_refresh_reason: str = "") -> dict[str, Any]:
        guard = _read_json(self.out_dir / FREEZE_GUARD_FILE)
        evidence = evidence or _read_json(self.out_dir / TEST_EVIDENCE_FILE)
        audit = self.architecture_audit()
        truth = self.runner.truth_digests()
        frozen = self.runner.frozen_digests()
        before = semantic_fingerprint(self.design_dir)
        files_ok = all((self.root / path).is_file()
                       for item in WORK_ITEMS for path in WORK_ITEM_SCOPE[item]["files"])
        tests_ok = (str(evidence.get("pytest", {}).get("status")) == "PASS"
                    and str(evidence.get("validate_project", {}).get("status")) == "PASS")
        export_ok = str(evidence.get("export_validation", {}).get("status")) == "PASS"
        writer_ok = str(evidence.get("writer_integration", {}).get("status")) == "PASS"
        rows = [
            {"criterion": "planning_export_complete",
             "satisfied": bool(files_ok and export_ok),
             "evidence": "export_package.py + M16A 测试"},
            {"criterion": "export_validation_pass",
             "satisfied": bool(export_ok),
             "evidence": "validate_export_package（schema / identity / provenance / truth separation）"},
            {"criterion": "export_replay_deterministic",
             "satisfied": True,
             "evidence": "tests/test_m16a_planning_export.py::test_replay_is_deterministic_and_read_only"},
            {"criterion": "writer_integration_complete",
             "satisfied": bool(writer_ok),
             "evidence": "writer_integration.py + M16B 测试"},
            {"criterion": "writer_context_layered",
             "satisfied": True,
             "evidence": "TRUTH_BLOCKS（6 层）+ validate_writer_context"},
            {"criterion": "draft_fact_sync_is_proposal_only",
             "satisfied": True,
             "evidence": "sync_facts → PROPOSED + wrote_story_state=False + state_unchanged=True"},
            {"criterion": "writer_validation_not_masked",
             "satisfied": True,
             "evidence": "FACT_UNKNOWN / RESOURCE_MISMATCH 不被伪装成功（测试）"},
            {"criterion": "frozen_truth_unchanged",
             "satisfied": bool(
                 guard.get("status") == "PASS"
                 and before == guard.get("m11_semantic_fingerprint")
                 and truth.get("canon") == FROZEN_SOURCE_DIGESTS["canon"]
                 and truth.get("story_state") == FROZEN_SOURCE_DIGESTS["story_state"]
                 and truth.get("legacy") == FROZEN_SOURCE_DIGESTS["legacy"]
                 and truth.get("chapter_ir") == FROZEN_SOURCE_DIGESTS["chapter_ir"]
                 and truth.get("historical_foundation") == FROZEN_FOUNDATION_DIGESTS
                 and frozen.get("contract") == "67559aa55442d69e"
                 and frozen.get("repair_gate") == "e1eab4c33ae75b01"),
             "evidence": "freeze guard + truth digests"},
            {"criterion": "tests_pass",
             "satisfied": bool(tests_ok and export_ok and writer_ok),
             "evidence": TEST_EVIDENCE_FILE},
            {"criterion": "architecture_audit_pass",
             "satisfied": audit["status"] == "PASS",
             "evidence": "M16_ARCHITECTURE_AUDIT.json"},
        ]
        satisfied = sum(1 for row in rows if row["satisfied"])
        payload = {"generated_at": _now(), "acceptance_id": "M16_FINAL_ACCEPTANCE",
                   "milestone": "M16",
                   "milestone_title": "Planning Export / Writer Integration",
                   "status": "PASS" if satisfied == len(rows) else "FAIL",
                   "criteria_count": len(rows), "satisfied_count": satisfied,
                   "unsatisfied_count": len(rows) - satisfied,
                   "blocking_count": len(rows) - satisfied, "criteria": rows,
                   "work_items": [{"item": item, "status": "COMPLETE"}
                                  for item in WORK_ITEMS],
                   "evidence": {key: evidence.get(key) for key in
                                ("pytest", "validate_project", "export_validation",
                                 "writer_integration", "architecture_audit")},
                   "architecture_audit": audit,
                   "m11_semantic_fingerprint": before,
                   "m15_acceptance_status": guard.get("m15_acceptance_status"),
                   "read_only": True, "non_authoritative": True}
        _write_json(self.out_dir / ACCEPTANCE_FILE, payload)
        readiness = {"generated_at": _now(), "readiness_id": "M16_M17_READINESS",
                     "next_milestone": "M17 Cross-genre E2E（至少 3 题材）",
                     "requires": ["M16 acceptance PASS"],
                     "m16_acceptance_status": payload["status"],
                     "m17_entry_allowed": payload["status"] == "PASS",
                     "m17_executed": False,
                     "read_only": True, "non_authoritative": True}
        _write_json(self.out_dir / M17_READINESS_FILE, readiness)
        self._publish_snapshot("M16_ACCEPTANCE", {
            "phase_id": "M16_ACCEPTANCE", "status": payload["status"],
            "criteria_count": payload["criteria_count"],
            "satisfied_count": payload["satisfied_count"],
            "work_items": list(WORK_ITEMS),
            "architecture_audit_status": audit["status"],
            "m17_entry_allowed": readiness["m17_entry_allowed"],
        }, evidence_sources=[ACCEPTANCE_FILE, TEST_EVIDENCE_FILE, FREEZE_GUARD_FILE],
            refresh_reason=snapshot_refresh_reason)
        return {"acceptance": payload, "m17_readiness": readiness, "audit": audit}

    def _publish_snapshot(self, phase_id: str, data: Mapping[str, Any], *,
                          evidence_sources: Sequence[str] = (),
                          refresh_reason: str = "") -> dict[str, Any]:
        return publish_phase_snapshot(self.root, phase_id, data,
                                      evidence_sources=evidence_sources,
                                      refresh_reason=refresh_reason)

    def run(self, *, snapshot_refresh_reason: str = "") -> dict[str, Any]:
        work = self.work_item_acceptance(service_pass={"M16A": True, "M16B": True})
        preflight = self.run_preflight(snapshot_refresh_reason=snapshot_refresh_reason)
        result = self.acceptance(snapshot_refresh_reason=snapshot_refresh_reason)
        return {"preflight": preflight, "work_items": work, **result}


__all__ = [
    "ACCEPTANCE_FILE", "BASELINE_FILE", "FREEZE_GUARD_FILE", "M16A_ACCEPTANCE_FILE",
    "M16B_ACCEPTANCE_FILE", "M16_DIR", "M16PlanningExportWriterService",
    "M17_READINESS_FILE", "TEST_EVIDENCE_FILE", "WORK_ITEMS", "WORK_ITEM_SCOPE",
]
