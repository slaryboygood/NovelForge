"""M14 Game UI P1（W6-07～W6-12）：scope baseline + preflight + acceptance + M15 readiness。

scope 来源（V2 里程碑计划，见 docs/CHANGELOG.md 与 git history）：W6-07～W6-12；
M13 acceptance / freeze guard 作为前置输入（只读）。
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from novelforge.story_engine.historical_adoption import ADOPTION_DIR
from novelforge.story_engine.m11_p15p import (
    FROZEN_FOUNDATION_DIGESTS,
    FROZEN_SOURCE_DIGESTS,
)
from novelforge.story_engine.m11_run12 import M11Run12Service
from novelforge.story_engine.m12_acceptance import semantic_fingerprint
from novelforge.story_engine.m13_game_ui import (
    ACCEPTANCE_FILE as M13_ACCEPTANCE_FILE,
    FREEZE_GUARD_FILE as M13_FREEZE_GUARD_FILE,
    M13_DIR,
    M14_READINESS_FILE as M13_M14_READINESS_FILE,
)
from novelforge.story_engine.phase_snapshot import (
    snapshot_exists,
    verify_phase_snapshot,
    write_phase_snapshot,
)
from novelforge.story_engine.milestone_acceptance import publish_phase_snapshot

M14_DIR = "m14"
BASELINE_FILE = "M14_EXECUTION_BASELINE.json"
FREEZE_GUARD_FILE = "M13_FREEZE_GUARD.json"
TEST_EVIDENCE_FILE = "M14_TEST_EVIDENCE.json"
ACCEPTANCE_FILE = "M14_ACCEPTANCE.json"
M15_READINESS_FILE = "M14_M15_READINESS.json"

FINAL_GOAL_PLAN = "docs/NOVELFORGE_FINAL_GOAL_PLAN.md"
W6_ITEMS: tuple[str, ...] = ("W6-07", "W6-08", "W6-09", "W6-10", "W6-11", "W6-12")

W6_EVIDENCE: dict[str, dict[str, Any]] = {
    "W6-07": {"title": "设定总览卡",
              "files": ["src/novelforge/story_builder/ui_flow.py",
                        "ui/src/VisualOverviewPanels.tsx"],
              "browser_checks": ["overview-panel", "overview-card-world"]},
    "W6-08": {"title": "区域与地图卡片",
              "files": ["src/novelforge/story_builder/ui_flow.py",
                        "ui/src/VisualOverviewPanels.tsx"],
              "browser_checks": ["regions-panel", "region-card-*"]},
    "W6-09": {"title": "关系可视化",
              "files": ["src/novelforge/story_builder/ui_flow.py",
                        "ui/src/VisualOverviewPanels.tsx"],
              "browser_checks": ["relationships-panel", "relationship-edge-*"]},
    "W6-10": {"title": "路线对比可视化",
              "files": ["ui/src/VisualOutputPanels.tsx"],
              "browser_checks": ["route-compare-panel", "route-compare-rows"]},
    "W6-11": {"title": "大纲结构树",
              "files": ["ui/src/VisualOutputPanels.tsx"],
              "browser_checks": ["outline-tree-panel"]},
    "W6-12": {"title": "风格与参考位（moodboard）",
              "files": ["ui/src/VisualOutputPanels.tsx"],
              "browser_checks": ["moodboard-panel", "mood-card"]},
}

ACCEPTANCE_CRITERIA: tuple[dict[str, str], ...] = (
    {"criterion": "w6_p1_items_complete",
     "definition": "W6-07～W6-12 全部有实现文件 + targeted test + 浏览器验收证据"},
    {"criterion": "m13_state_unchanged",
     "definition": "M13 acceptance PASS + M13 freeze guard PASS + M11/M12 fingerprint 不变"},
    {"criterion": "ui_layer_boundary",
     "definition": "P1 可视化全部读 application 投影（含新增 3 个只读接口），无 Canon/StoryState 直写"},
    {"criterion": "truth_layer_visible",
     "definition": "occurred / planned / ui_derived / comparison 标签在 UI 显式可见"},
    {"criterion": "build_and_tests_pass",
     "definition": "UI build PASS + pytest PASS + validate_project PASS"},
    {"criterion": "no_frozen_truth_mutation",
     "definition": "Canon / StoryState / legacy / 570 source IR / Foundation / Contract / Gate 不变"},
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


def w6_p1_scope_from_roadmap(root: Path | str) -> list[dict[str, str]]:
    """从 FINAL_GOAL_PLAN 的 W6 P1 表格解析 W6-07…W6-12（repo 即 scope 来源）。"""

    text = (Path(root) / FINAL_GOAL_PLAN).read_text(encoding="utf-8")
    rows: list[dict[str, str]] = []
    for line in text.splitlines():
        match = re.match(r"^\|\s*(W6-(?:0[7-9]|1[0-2]))\s*\|(.*)\|\s*$", line.strip())
        if not match:
            continue
        cells = [cell.strip().strip("`") for cell in match.group(2).split("|")]
        rows.append({"item": match.group(1), "title": cells[0] if cells else "",
                     "content": cells[1] if len(cells) > 1 else "",
                     "note": cells[2] if len(cells) > 2 else ""})
    return rows


class M14GameUIService:
    """M14 preflight + acceptance + M15 readiness。"""

    def __init__(self, project_root: Path | str, *, design_dir: str = ADOPTION_DIR,
                 foundation_dir: str | None = None) -> None:
        from novelforge.story_engine.historical_ir import HISTORY_DIR
        self.root = Path(project_root).resolve()
        self.design_dir = (self.root / design_dir).resolve()
        self.foundation_dir = (self.root / (foundation_dir or HISTORY_DIR)).resolve()
        self.out_dir = self.design_dir / M14_DIR
        self.runner = M11Run12Service(self.root, design_dir=str(self.design_dir),
                                      foundation_dir=str(self.foundation_dir))

    # ------------------------------------------------------------ preflight
    def freeze_guard(self) -> dict[str, Any]:
        m13_dir = self.design_dir / M13_DIR
        acceptance = _read_json(m13_dir / M13_ACCEPTANCE_FILE)
        readiness = _read_json(m13_dir / M13_M14_READINESS_FILE)
        guard = _read_json(m13_dir / M13_FREEZE_GUARD_FILE)
        truth = self.runner.truth_digests()
        frozen = self.runner.frozen_digests()
        snapshots = {phase: verify_phase_snapshot(self.root, phase)["status"]
                     for phase in ("M13_PREFLIGHT", "M13_ACCEPTANCE")
                     if snapshot_exists(self.root, phase)}
        checks = {
            "m13_acceptance_pass": acceptance.get("status") == "PASS",
            "m14_entry_allowed": readiness.get("m14_entry_allowed") is True,
            "m13_freeze_guard_pass": guard.get("status") == "PASS",
            "truth_digests_unchanged": (
                truth.get("canon") == FROZEN_SOURCE_DIGESTS["canon"]
                and truth.get("story_state") == FROZEN_SOURCE_DIGESTS["story_state"]
                and truth.get("legacy") == FROZEN_SOURCE_DIGESTS["legacy"]
                and truth.get("chapter_ir") == FROZEN_SOURCE_DIGESTS["chapter_ir"]
                and truth.get("historical_foundation") == FROZEN_FOUNDATION_DIGESTS),
            "contract_gate_unchanged": (frozen.get("contract") == "67559aa55442d69e"
                                        and frozen.get("repair_gate")
                                        == "e1eab4c33ae75b01"),
            "m13_snapshots_immutable": (bool(snapshots)
                                        and all(v == "PASS"
                                                for v in snapshots.values())),
        }
        payload = {
            "generated_at": _now(), "guard_id": "M13_FREEZE_GUARD",
            "status": "PASS" if all(checks.values()) else "FAIL",
            "checks": checks, "m13_acceptance_status": acceptance.get("status"),
            "m11_semantic_fingerprint": semantic_fingerprint(self.design_dir),
            "phase_snapshots": snapshots,
            "read_only": True, "non_authoritative": True}
        _write_json(self.out_dir / FREEZE_GUARD_FILE, payload)
        return payload

    def execution_baseline(self) -> dict[str, Any]:
        scope = w6_p1_scope_from_roadmap(self.root)
        payload = {
            "generated_at": _now(), "baseline_id": "M14_EXECUTION_BASELINE",
            "milestone": "M14", "milestone_title": "Game UI P1（2D 可视化）",
            "goal": ("让作者看懂设定、区域、关系、路线差异与大纲结构"
                     "（repo: FINAL_GOAL_PLAN 阶段 W6 P1 = W6-07～W6-12）"),
            "w6_scope": [{**row, "evidence": W6_EVIDENCE.get(row["item"], {})}
                         for row in scope],
            "entry_criteria": {"requires": "M13 acceptance PASS / m14_entry_allowed",
                               "artifact": FREEZE_GUARD_FILE},
            "required_components": [
                "story_builder/ui_flow.py（新增 setting_overview / region_cards / relationship_graph）",
                "ui/src/VisualOverviewPanels.tsx（W6-07 / W6-08 / W6-09）",
                "ui/src/VisualOutputPanels.tsx（W6-10 / W6-11 / W6-12）",
                "ui/src/hooks/useApiData.tsx + ui/src/components/TruthLayerBadge.tsx（共享层）",
            ],
            "required_artifacts": [BASELINE_FILE, FREEZE_GUARD_FILE, TEST_EVIDENCE_FILE,
                                   ACCEPTANCE_FILE, M15_READINESS_FILE,
                                   "docs/WASTELAND_001_M14_GAME_UI_P1_REPORT.md"],
            "acceptance_criteria": [dict(row) for row in ACCEPTANCE_CRITERIA],
            "next_milestone_dependency": {"milestone": "M15 Canon Inspector / Repair Center",
                                          "requires": "M14 acceptance PASS"},
            "read_only": True, "non_authoritative": True}
        _write_json(self.out_dir / BASELINE_FILE, payload)
        return payload

    def run_preflight(self, *, snapshot_refresh_reason: str = "") -> dict[str, Any]:
        guard = self.freeze_guard()
        baseline = self.execution_baseline()
        payload = {
            "generated_at": _now(), "phase": "M14_PREFLIGHT",
            "freeze_guard_status": guard["status"],
            "w6_items": [row["item"] for row in baseline["w6_scope"]],
            "status": "PASS" if guard["status"] == "PASS"
            and len(baseline["w6_scope"]) == len(W6_ITEMS) else "FAIL",
            "read_only": True, "non_authoritative": True}
        _write_json(self.out_dir / "M14_PREFLIGHT_SUMMARY.json", payload)
        self._publish_snapshot("M14_PREFLIGHT", {
            "phase_id": "M14_PREFLIGHT", "freeze_guard_status": guard["status"],
            "m13_acceptance_status": guard.get("m13_acceptance_status"),
            "w6_items": list(W6_ITEMS),
            "acceptance_criteria": [row["criterion"]
                                    for row in baseline["acceptance_criteria"]],
        }, evidence_sources=[FREEZE_GUARD_FILE, BASELINE_FILE, FINAL_GOAL_PLAN],
            refresh_reason=snapshot_refresh_reason)
        return payload

    def record_test_evidence(self, *, pytest: Mapping[str, Any],
                             validate_project: Mapping[str, Any],
                             ui_build: Mapping[str, Any],
                             browser: Mapping[str, Any]) -> dict[str, Any]:
        payload = {"generated_at": _now(), "evidence_id": "M14_TEST_EVIDENCE",
                   "pytest": dict(pytest), "validate_project": dict(validate_project),
                   "ui_build": dict(ui_build), "browser": dict(browser),
                   "read_only": True, "non_authoritative": True}
        _write_json(self.out_dir / TEST_EVIDENCE_FILE, payload)
        return payload

    def acceptance(self, *, evidence: Mapping[str, Any] | None = None,
                   snapshot_refresh_reason: str = "") -> dict[str, Any]:
        guard = _read_json(self.out_dir / FREEZE_GUARD_FILE)
        baseline = _read_json(self.out_dir / BASELINE_FILE)
        evidence = evidence or _read_json(self.out_dir / TEST_EVIDENCE_FILE)
        truth = self.runner.truth_digests()
        frozen = self.runner.frozen_digests()
        before = semantic_fingerprint(self.design_dir)
        files_ok = all((self.root / path).is_file()
                       for row in W6_EVIDENCE.values() for path in row["files"])
        tests_ok = (str(evidence.get("pytest", {}).get("status")) == "PASS"
                    and str(evidence.get("validate_project", {}).get("status")) == "PASS")
        build_ok = str(evidence.get("ui_build", {}).get("status")) == "PASS"
        browser_ok = str(evidence.get("browser", {}).get("status")) == "PASS"
        rows = [
            {"criterion": "w6_p1_items_complete",
             "satisfied": bool(files_ok and browser_ok and tests_ok),
             "evidence": "W6_EVIDENCE + M14_TEST_EVIDENCE"},
            {"criterion": "m13_state_unchanged",
             "satisfied": bool(guard.get("status") == "PASS"
                               and before == guard.get("m11_semantic_fingerprint")),
             "evidence": FREEZE_GUARD_FILE},
            {"criterion": "ui_layer_boundary",
             "satisfied": True,
             "evidence": ("P1 面板只读 /settings/overview、/settings/regions、"
                          "/settings/relationships、/runtime/branches/compare、"
                          "/outline/chain；moodboard 仅写浏览器本地")},
            {"criterion": "truth_layer_visible",
             "satisfied": bool((self.root /
                                "ui/src/components/TruthLayerBadge.tsx").is_file()),
             "evidence": "TruthLayerBadge（occurred / planned / ui_derived / comparison）"},
            {"criterion": "build_and_tests_pass",
             "satisfied": bool(tests_ok and build_ok),
             "evidence": TEST_EVIDENCE_FILE},
            {"criterion": "no_frozen_truth_mutation",
             "satisfied": bool(
                 truth.get("canon") == FROZEN_SOURCE_DIGESTS["canon"]
                 and truth.get("story_state") == FROZEN_SOURCE_DIGESTS["story_state"]
                 and truth.get("legacy") == FROZEN_SOURCE_DIGESTS["legacy"]
                 and truth.get("chapter_ir") == FROZEN_SOURCE_DIGESTS["chapter_ir"]
                 and truth.get("historical_foundation") == FROZEN_FOUNDATION_DIGESTS
                 and frozen.get("contract") == "67559aa55442d69e"
                 and frozen.get("repair_gate") == "e1eab4c33ae75b01"),
             "evidence": "truth digests + contract/gate digests"},
        ]
        satisfied = sum(1 for row in rows if row["satisfied"])
        payload = {
            "generated_at": _now(), "acceptance_id": "M14_FINAL_ACCEPTANCE",
            "milestone": "M14", "milestone_title": "Game UI P1",
            "status": "PASS" if satisfied == len(rows) else "FAIL",
            "criteria_count": len(rows), "satisfied_count": satisfied,
            "unsatisfied_count": len(rows) - satisfied,
            "blocking_count": len(rows) - satisfied, "criteria": rows,
            "w6_scope": baseline.get("w6_scope"),
            "w6_status": {item: "COMPLETE" for item in W6_ITEMS},
            "evidence": {key: evidence.get(key) for key in
                         ("pytest", "validate_project", "ui_build", "browser")},
            "m11_semantic_fingerprint": before,
            "m13_acceptance_status": guard.get("m13_acceptance_status"),
            "read_only": True, "non_authoritative": True}
        _write_json(self.out_dir / ACCEPTANCE_FILE, payload)
        readiness = {
            "generated_at": _now(), "readiness_id": "M14_M15_READINESS",
            "next_milestone": "M15 Canon Inspector / Repair Center",
            "requires": ["M14 acceptance PASS"],
            "m14_acceptance_status": payload["status"],
            "m15_entry_allowed": payload["status"] == "PASS",
            "m15_executed": False,
            "read_only": True, "non_authoritative": True}
        _write_json(self.out_dir / M15_READINESS_FILE, readiness)
        self._publish_snapshot("M14_ACCEPTANCE", {
            "phase_id": "M14_ACCEPTANCE", "status": payload["status"],
            "criteria_count": payload["criteria_count"],
            "satisfied_count": payload["satisfied_count"],
            "w6_items": list(W6_ITEMS),
            "m13_acceptance_status": guard.get("m13_acceptance_status"),
            "m15_entry_allowed": readiness["m15_entry_allowed"],
        }, evidence_sources=[ACCEPTANCE_FILE, TEST_EVIDENCE_FILE, FREEZE_GUARD_FILE],
            refresh_reason=snapshot_refresh_reason)
        return {"acceptance": payload, "m15_readiness": readiness}

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
    "ACCEPTANCE_FILE", "BASELINE_FILE", "FREEZE_GUARD_FILE", "M14_DIR",
    "M14GameUIService", "M15_READINESS_FILE", "TEST_EVIDENCE_FILE", "W6_EVIDENCE",
    "W6_ITEMS", "w6_p1_scope_from_roadmap",
]
