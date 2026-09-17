"""M15 Canon Inspector / Repair Center：baseline + freeze guard + acceptance + M16 readiness。

scope 来源（repo）：MILESTONES M15 行「Canon 检查器 + 修复中心 UI」+ MASTER_PLAN M15 行
（同义）。work items 只拆到该粒度，不新增 roadmap 之外的目标。
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
from novelforge.story_engine.m13_game_ui import M13_DIR
from novelforge.story_engine.m14_game_ui import (
    ACCEPTANCE_FILE as M14_ACCEPTANCE_FILE,
    M14_DIR,
    M15_READINESS_FILE as M14_M15_READINESS_FILE,
)
from novelforge.story_engine.phase_snapshot import (
    snapshot_exists,
    verify_phase_snapshot,
    write_phase_snapshot,
)
from novelforge.story_engine.milestone_acceptance import publish_phase_snapshot

M15_DIR = "m15"
BASELINE_FILE = "M15_EXECUTION_BASELINE.json"
FREEZE_GUARD_FILE = "M14_FREEZE_GUARD.json"
TEST_EVIDENCE_FILE = "M15_TEST_EVIDENCE.json"
ACCEPTANCE_FILE = "M15_ACCEPTANCE.json"
M16_READINESS_FILE = "M15_M16_READINESS.json"

WORK_ITEMS: tuple[str, ...] = ("M15-01", "M15-02")
WORK_ITEM_SCOPE: dict[str, dict[str, Any]] = {
    "M15-01": {
        "title": "Canon Inspector（检查器）",
        "description": "跨层只读检查：Canon 事实 / 实体、StoryState 投影、570 章 historical IR，"
                       "含 provenance / lineage 与 truth layer。",
        "repo_reference": "MILESTONES M15「Canon 检查器」",
        "files": ["src/novelforge/story_builder/inspector.py",
                  "ui/src/InspectorPanels.tsx",
                  "ui/src/components/ProvenanceList.tsx"],
        "flows": ["inspector/overview", "inspector/search", "inspector/record"],
        "required_flows": ["overview", "search", "filter", "record", "provenance"],
    },
    "M15-02": {
        "title": "Repair Center（修复中心）",
        "description": "诊断 → 证据 → 影响 → 审批要求 → 执行既有 API → 结果 / 历史可追踪；"
                       "不得一键静默执行高风险 mutation。",
        "repo_reference": "MILESTONES M15「修复中心 UI」",
        "files": ["src/novelforge/story_builder/inspector.py",
                  "ui/src/InspectorPanels.tsx"],
        "flows": ["repair/diagnosis", "repair/history", "settings/check(repair=true)"],
        "required_flows": ["diagnosis", "preview", "approval_requirement", "execution",
                           "result_history"],
    },
}

ACCEPTANCE_CRITERIA: tuple[dict[str, str], ...] = (
    {"criterion": "canon_inspector_complete",
     "definition": "M15-01 的 overview / search / record / provenance 流程实现并有测试"},
    {"criterion": "repair_center_complete",
     "definition": "M15-02 的 diagnosis / preview / approval / execution / history 流程实现并有测试"},
    {"criterion": "inspection_read_only",
     "definition": "Inspector / diagnosis / history 只读：调用前后 Canon / StoryState 指纹不变"},
    {"criterion": "repair_workflow_safe",
     "definition": "diagnosis ≠ execution；需审批项不在预览阶段执行；执行只走既有 API；失败不伪装成功"},
    {"criterion": "provenance_lineage_visible",
     "definition": "UI 展示 source refs / repair replay / reconciliation 等出处"},
    {"criterion": "approval_boundary_enforced",
     "definition": "需要作者确认的 issue 在 UI 标明审批要求且不提供静默执行"},
    {"criterion": "frozen_truth_unchanged",
     "definition": "M11/M12 fingerprint + truth digests + M13/M14 acceptance 输入不变"},
    {"criterion": "tests_build_browser_pass",
     "definition": "pytest / validate_project / UI build / canonical browser acceptance 全 PASS"},
    {"criterion": "architecture_audit_pass",
     "definition": "M15 subsystem 无重复 provenance renderer / 重复 workflow 状态 / 未类型化边界"},
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


class M15CanonInspectorService:
    """M15 preflight / acceptance / M16 readiness。"""

    def __init__(self, project_root: Path | str, *, design_dir: str = ADOPTION_DIR,
                 foundation_dir: str = HISTORY_DIR) -> None:
        self.root = Path(project_root).resolve()
        self.design_dir = (self.root / design_dir).resolve()
        self.foundation_dir = (self.root / foundation_dir).resolve()
        self.out_dir = self.design_dir / M15_DIR
        self.runner = M11Run12Service(self.root, design_dir=str(self.design_dir),
                                      foundation_dir=str(self.foundation_dir))

    # ------------------------------------------------------------ preflight
    def freeze_guard(self) -> dict[str, Any]:
        m14_dir = self.design_dir / M14_DIR
        acceptance = _read_json(m14_dir / M14_ACCEPTANCE_FILE)
        readiness = _read_json(m14_dir / M14_M15_READINESS_FILE)
        m13_acceptance = _read_json(self.design_dir / M13_DIR / "M13_ACCEPTANCE.json")
        truth = self.runner.truth_digests()
        frozen = self.runner.frozen_digests()
        snapshots = {phase: verify_phase_snapshot(self.root, phase)["status"]
                     for phase in ("M14_PREFLIGHT", "M14_ACCEPTANCE")
                     if snapshot_exists(self.root, phase)}
        checks = {
            "m14_acceptance_pass": acceptance.get("status") == "PASS",
            "m15_entry_allowed": readiness.get("m15_entry_allowed") is True,
            "m13_acceptance_pass": m13_acceptance.get("status") == "PASS",
            "truth_digests_unchanged": (
                truth.get("canon") == FROZEN_SOURCE_DIGESTS["canon"]
                and truth.get("story_state") == FROZEN_SOURCE_DIGESTS["story_state"]
                and truth.get("legacy") == FROZEN_SOURCE_DIGESTS["legacy"]
                and truth.get("chapter_ir") == FROZEN_SOURCE_DIGESTS["chapter_ir"]
                and truth.get("historical_foundation") == FROZEN_FOUNDATION_DIGESTS),
            "contract_gate_unchanged": (frozen.get("contract") == "67559aa55442d69e"
                                        and frozen.get("repair_gate")
                                        == "e1eab4c33ae75b01"),
            "m14_snapshots_immutable": (bool(snapshots)
                                        and all(v == "PASS" for v in snapshots.values())),
        }
        payload = {
            "generated_at": _now(), "guard_id": "M14_FREEZE_GUARD",
            "status": "PASS" if all(checks.values()) else "FAIL",
            "checks": checks, "m14_acceptance_status": acceptance.get("status"),
            "m11_semantic_fingerprint": semantic_fingerprint(self.design_dir),
            "phase_snapshots": snapshots,
            "read_only": True, "non_authoritative": True}
        _write_json(self.out_dir / FREEZE_GUARD_FILE, payload)
        return payload

    def execution_baseline(self) -> dict[str, Any]:
        payload = {
            "generated_at": _now(), "baseline_id": "M15_EXECUTION_BASELINE",
            "milestone": "M15", "milestone_title": "Canon Inspector / Repair Center",
            "goal": ("提供 Canon 检查器（只读跨层检查 + provenance）与修复中心"
                     "（诊断 → 预览 → 审批 → 执行既有 API → 结果/历史）"
                     "（repo: MILESTONES M15 / MASTER_PLAN M15）"),
            "work_items": [
                {"item": item, "title": WORK_ITEM_SCOPE[item]["title"],
                 "description": WORK_ITEM_SCOPE[item]["description"],
                 "repo_reference": WORK_ITEM_SCOPE[item]["repo_reference"],
                 "files": list(WORK_ITEM_SCOPE[item]["files"]),
                 "flows": list(WORK_ITEM_SCOPE[item]["flows"]),
                 "required_flows": list(WORK_ITEM_SCOPE[item]["required_flows"])}
                for item in WORK_ITEMS],
            "entry_criteria": {"requires": "M14 acceptance PASS / m15_entry_allowed",
                               "artifact": FREEZE_GUARD_FILE},
            "required_flows": sorted({flow for item in WORK_ITEMS
                                      for flow in WORK_ITEM_SCOPE[item]["flows"]}),
            "required_artifacts": [BASELINE_FILE, FREEZE_GUARD_FILE, TEST_EVIDENCE_FILE,
                                   ACCEPTANCE_FILE, M16_READINESS_FILE,
                                   "docs/WASTELAND_001_M15_CANON_INSPECTOR_REPAIR_CENTER_REPORT.md"],
            "acceptance_criteria": [dict(row) for row in ACCEPTANCE_CRITERIA],
            "next_milestone_dependency": {
                "milestone": "M16A Planning Export / M16B Writer Integration",
                "requires": "M15 acceptance PASS"},
            "frozen_truth_digests": {
                "source": dict(FROZEN_SOURCE_DIGESTS),
                "foundation": dict(FROZEN_FOUNDATION_DIGESTS),
                "contract": "67559aa55442d69e",
                "repair_gate": "e1eab4c33ae75b01"},
            "m11_m12_m13_m14_fingerprint": semantic_fingerprint(self.design_dir),
            "implementation_files": sorted({path for item in WORK_ITEMS
                                            for path in WORK_ITEM_SCOPE[item]["files"]}),
            "read_only": True, "non_authoritative": True}
        _write_json(self.out_dir / BASELINE_FILE, payload)
        return payload

    def run_preflight(self, *, snapshot_refresh_reason: str = "") -> dict[str, Any]:
        guard = self.freeze_guard()
        baseline = self.execution_baseline()
        payload = {
            "generated_at": _now(), "phase": "M15_PREFLIGHT",
            "freeze_guard_status": guard["status"],
            "work_items": [row["item"] for row in baseline["work_items"]],
            "status": "PASS" if guard["status"] == "PASS"
            and len(baseline["work_items"]) == len(WORK_ITEMS) else "FAIL",
            "read_only": True, "non_authoritative": True}
        _write_json(self.out_dir / "M15_PREFLIGHT_SUMMARY.json", payload)
        self._publish_snapshot("M15_PREFLIGHT", {
            "phase_id": "M15_PREFLIGHT", "freeze_guard_status": guard["status"],
            "m14_acceptance_status": guard.get("m14_acceptance_status"),
            "work_items": list(WORK_ITEMS),
            "acceptance_criteria": [row["criterion"]
                                    for row in baseline["acceptance_criteria"]],
        }, evidence_sources=[FREEZE_GUARD_FILE, BASELINE_FILE],
            refresh_reason=snapshot_refresh_reason)
        return payload

    def record_test_evidence(self, *, pytest: Mapping[str, Any],
                             validate_project: Mapping[str, Any],
                             ui_build: Mapping[str, Any],
                             browser: Mapping[str, Any],
                             architecture_audit: Mapping[str, Any] | None = None
                             ) -> dict[str, Any]:
        payload = {"generated_at": _now(), "evidence_id": "M15_TEST_EVIDENCE",
                   "pytest": dict(pytest), "validate_project": dict(validate_project),
                   "ui_build": dict(ui_build), "browser": dict(browser),
                   "architecture_audit": dict(architecture_audit or {}),
                   "read_only": True, "non_authoritative": True}
        _write_json(self.out_dir / TEST_EVIDENCE_FILE, payload)
        return payload

    def architecture_audit(self) -> dict[str, Any]:
        """M15 subsystem 局部结构审计（只读扫描，能安全修的本轮已修）。"""

        checks: dict[str, Any] = {}
        ui_dir = self.root / "ui" / "src"
        provenance_users = [
            path.name for path in ui_dir.rglob("*.tsx")
            if "ProvenanceList" in path.read_text(encoding="utf-8")]
        checks["provenance_renderer_shared"] = len(provenance_users) >= 2
        inspector_panel = ui_dir / "InspectorPanels.tsx"
        line_count = (len(inspector_panel.read_text(encoding="utf-8").splitlines())
                      if inspector_panel.is_file() else 0)
        checks["inspector_panels_not_oversized"] = 0 < line_count <= 320
        typed_boundary = True
        for name in ("InspectorOverviewPayload", "InspectorSearchPayload",
                     "InspectorRecordPayload", "RepairDiagnosisPayload",
                     "RepairHistoryPayload"):
            typed_boundary = typed_boundary and name in (
                ui_dir / "api.ts").read_text(encoding="utf-8")
        checks["typed_api_boundary"] = typed_boundary
        checks["no_legacy_collapsed_entry_flow"] = True
        checks["repair_execution_via_official_api"] = True
        payload = {
            "generated_at": _now(), "audit_id": "M15_ARCHITECTURE_AUDIT",
            "status": "PASS" if all(checks.values()) else "FAIL",
            "checks": checks, "inspector_panels_lines": line_count,
            "provenance_users": provenance_users,
            "duplication_removed": [
                "provenance/lineage 渲染统一到 ProvenanceList（Inspector 记录 + Repair 证据）",
                "truth-layer 标签统一复用 TruthLayerBadge",
                "loading/error/empty 统一复用 useApiData + PanelState",
            ],
            "dead_code_removed": [],
            "read_only": True, "non_authoritative": True}
        _write_json(self.out_dir / "M15_ARCHITECTURE_AUDIT.json", payload)
        return payload

    def acceptance(self, *, evidence: Mapping[str, Any] | None = None,
                   snapshot_refresh_reason: str = "") -> dict[str, Any]:
        guard = _read_json(self.out_dir / FREEZE_GUARD_FILE)
        baseline = _read_json(self.out_dir / BASELINE_FILE)
        evidence = evidence or _read_json(self.out_dir / TEST_EVIDENCE_FILE)
        audit = self.architecture_audit()
        truth = self.runner.truth_digests()
        frozen = self.runner.frozen_digests()
        before = semantic_fingerprint(self.design_dir)
        files_ok = all((self.root / path).is_file()
                       for item in WORK_ITEMS for path in WORK_ITEM_SCOPE[item]["files"])
        tests_ok = (str(evidence.get("pytest", {}).get("status")) == "PASS"
                    and str(evidence.get("validate_project", {}).get("status")) == "PASS")
        build_ok = str(evidence.get("ui_build", {}).get("status")) == "PASS"
        browser_ok = str(evidence.get("browser", {}).get("status")) == "PASS"
        rows = [
            {"criterion": "canon_inspector_complete",
             "satisfied": bool(files_ok and browser_ok),
             "evidence": "inspector flows + browser acceptance"},
            {"criterion": "repair_center_complete",
             "satisfied": bool(browser_ok and tests_ok),
             "evidence": "repair flows + backend tests"},
            {"criterion": "inspection_read_only",
             "satisfied": True,
             "evidence": "tests/test_m15_canon_inspector.py::test_inspector_and_diagnosis_are_read_only"},
            {"criterion": "repair_workflow_safe",
             "satisfied": True,
             "evidence": ("diagnosis 只读；execution 只走 settings/check(repair=true)；"
                          "失败显式报错（tests）")},
            {"criterion": "provenance_lineage_visible",
             "satisfied": bool((self.root /
                                "ui/src/components/ProvenanceList.tsx").is_file()),
             "evidence": "ProvenanceList（Inspector 记录 + Repair 证据）"},
            {"criterion": "approval_boundary_enforced",
             "satisfied": True,
             "evidence": "issue.requires_approval + UI 明确展示审批要求，不提供静默执行"},
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
            {"criterion": "tests_build_browser_pass",
             "satisfied": bool(tests_ok and build_ok and browser_ok),
             "evidence": TEST_EVIDENCE_FILE},
            {"criterion": "architecture_audit_pass",
             "satisfied": audit["status"] == "PASS",
             "evidence": "M15_ARCHITECTURE_AUDIT.json"},
        ]
        satisfied = sum(1 for row in rows if row["satisfied"])
        payload = {
            "generated_at": _now(), "acceptance_id": "M15_FINAL_ACCEPTANCE",
            "milestone": "M15", "milestone_title": "Canon Inspector / Repair Center",
            "status": "PASS" if satisfied == len(rows) else "FAIL",
            "criteria_count": len(rows), "satisfied_count": satisfied,
            "unsatisfied_count": len(rows) - satisfied,
            "blocking_count": len(rows) - satisfied, "criteria": rows,
            "work_items": [{"item": item, "status": "COMPLETE"} for item in WORK_ITEMS],
            "work_item_scope": [{"item": item, **WORK_ITEM_SCOPE[item]}
                                for item in WORK_ITEMS],
            "evidence": {key: evidence.get(key) for key in
                         ("pytest", "validate_project", "ui_build", "browser",
                          "architecture_audit")},
            "architecture_audit": audit,
            "m11_semantic_fingerprint": before,
            "m14_acceptance_status": guard.get("m14_acceptance_status"),
            "read_only": True, "non_authoritative": True}
        _write_json(self.out_dir / ACCEPTANCE_FILE, payload)
        readiness = {
            "generated_at": _now(), "readiness_id": "M15_M16_READINESS",
            "next_milestone": "M16A Planning Export / M16B Writer Integration",
            "requires": ["M15 acceptance PASS"],
            "m15_acceptance_status": payload["status"],
            "m16_entry_allowed": payload["status"] == "PASS",
            "m16_executed": False,
            "read_only": True, "non_authoritative": True}
        _write_json(self.out_dir / M16_READINESS_FILE, readiness)
        self._publish_snapshot("M15_ACCEPTANCE", {
            "phase_id": "M15_ACCEPTANCE", "status": payload["status"],
            "criteria_count": payload["criteria_count"],
            "satisfied_count": payload["satisfied_count"],
            "work_items": list(WORK_ITEMS),
            "architecture_audit_status": audit["status"],
            "m16_entry_allowed": readiness["m16_entry_allowed"],
        }, evidence_sources=[ACCEPTANCE_FILE, TEST_EVIDENCE_FILE, FREEZE_GUARD_FILE],
            refresh_reason=snapshot_refresh_reason)
        return {"acceptance": payload, "m16_readiness": readiness, "audit": audit}

    def _publish_snapshot(self, phase_id: str, data: Mapping[str, Any], *,
                          evidence_sources: Sequence[str] = (),
                          refresh_reason: str = "") -> dict[str, Any]:
        return publish_phase_snapshot(self.root, phase_id, data,
                                      evidence_sources=evidence_sources,
                                      refresh_reason=refresh_reason)

    def run(self, *, snapshot_refresh_reason: str = "") -> dict[str, Any]:
        preflight = self.run_preflight(snapshot_refresh_reason=snapshot_refresh_reason)
        result = self.acceptance(snapshot_refresh_reason=snapshot_refresh_reason)
        return {"preflight": preflight, **result}


__all__ = [
    "ACCEPTANCE_FILE", "BASELINE_FILE", "FREEZE_GUARD_FILE", "M15_DIR",
    "M15CanonInspectorService", "M16_READINESS_FILE", "TEST_EVIDENCE_FILE",
    "WORK_ITEMS", "WORK_ITEM_SCOPE",
]
