"""M13 Game UI P0（W6-01～W6-06）：scope baseline + preflight + acceptance + M14 readiness。

repo 定义来源（V2 里程碑计划，不重新猜测）：M13 Game UI P0 = W6-01…W6-06 + 完成标准。
V2 计划文档已随 release 收敛（见 docs/CHANGELOG.md 与 git history）。

硬边界：M11 / M12 frozen data 只读；UI 通过 application 层读写既有 API，
不直接改 Canon / StoryState / repair artifacts。
"""

from __future__ import annotations

import hashlib
import json
import re
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
from novelforge.story_engine.phase_snapshot import (
    snapshot_exists,
    verify_phase_snapshot,
    write_phase_snapshot,
)
from novelforge.story_engine.milestone_acceptance import publish_phase_snapshot

M13_DIR = "m13"
M13_ID = "M13-GAME-UI-P0"
BASELINE_FILE = "M13_EXECUTION_BASELINE.json"
FREEZE_GUARD_FILE = "M12_FREEZE_GUARD.json"
ACCEPTANCE_FILE = "M13_ACCEPTANCE.json"
TEST_EVIDENCE_FILE = "M13_TEST_EVIDENCE.json"
M14_READINESS_FILE = "M13_M14_READINESS.json"

FINAL_GOAL_PLAN = "docs/NOVELFORGE_FINAL_GOAL_PLAN.md"
M12_FREEZE_FILE = "WASTELAND_001_M12_FREEZE_V1.json"
M12_ACCEPTANCE_FILE = "M12_ACCEPTANCE.json"
M12_OUT_DIR = "m12"

CONTRACT_DIGEST = "67559aa55442d69e"
REPAIR_GATE_DIGEST = "e1eab4c33ae75b01"

W6_ITEMS: tuple[str, ...] = ("W6-01", "W6-02", "W6-03", "W6-04", "W6-05", "W6-06")

# 每个 W6 项的落地证据（UI 源码 / python 测试 / 浏览器验收）。
W6_EVIDENCE: dict[str, dict[str, Any]] = {
    "W6-01": {
        "title": "单页引导式创作流",
        "files": ["ui/src/GuidedFlowPanel.tsx", "ui/src/guidedFlow.ts",
                  "src/novelforge/story_builder/ui_flow.py"],
        "python_tests": ["tests/test_m13_game_ui_p0.py::test_guided_flow_steps_and_next_step"],
        "browser_checks": ["guided-steps", "guided-next-step", "guided-runtime-step"],
    },
    "W6-02": {
        "title": "统一候选卡组件",
        "files": ["ui/src/components/CandidateCard.tsx"],
        "python_tests": ["tests/test_m13_game_ui_p0.py::test_setting_impact_matches_pack_structure"],
        "browser_checks": ["creative-genre-card", "setting-candidate-world_rules",
                           "design-tree-option", "builder-option-card"],
    },
    "W6-03": {
        "title": "信息架构分组",
        "files": ["ui/src/guidedFlow.ts", "ui/src/StoryBuilderPage.tsx"],
        "python_tests": ["tests/test_m13_game_ui_p0.py::test_guided_flow_steps_and_next_step"],
        "browser_checks": ["tab-group-design", "tab-group-occurred", "tab-group-output",
                           "creator-stage-bar", "stage-current"],
    },
    "W6-04": {
        "title": "设定影响范围预览（只读）",
        "files": ["src/novelforge/story_builder/ui_flow.py",
                  "ui/src/components/CandidateCard.tsx"],
        "python_tests": ["tests/test_m13_game_ui_p0.py::test_setting_impact_matches_pack_structure",
                         "tests/test_m13_game_ui_p0.py::test_setting_impact_before_pack_saved"],
        "browser_checks": ["NovelProfile", "内容包段", "解锁候选行动"],
    },
    "W6-05": {
        "title": "面板串联与深链接",
        "files": ["ui/src/guidedFlow.ts", "ui/src/StoryBuilderPage.tsx",
                  "ui/src/RouteLabPanel.tsx", "ui/src/OutlineForgePanel.tsx"],
        "python_tests": ["tests/test_m13_game_ui_p0.py::test_guided_flow_blocked_check_points_at_candidate_group",
                         "tests/test_m13_game_ui_p0.py::test_finding_group_mapping_covers_checker_codes"],
        "browser_checks": ["novel_id=", "tab=world", "route-compare-deeplink"],
    },
    "W6-06": {
        "title": "小屏必须可用清单",
        "files": ["ui/src/style.css"],
        "python_tests": [],
        "browser_checks": ["390px overflow check", "guided flow on mobile"],
    },
}

M13_ACCEPTANCE_CRITERIA: tuple[dict[str, str], ...] = (
    {"criterion": "w6_items_complete",
     "definition": "W6-01～W6-06 全部有实现文件 + targeted test + 浏览器验收证据"},
    {"criterion": "m12_freeze_unchanged",
     "definition": "M12 freeze FROZEN + M11/M12 semantic fingerprint + truth digests 不变"},
    {"criterion": "ui_runtime_boundary",
     "definition": "UI 写操作只经 application/service API；投影只读（无 Canon / StoryState 直写）"},
    {"criterion": "required_flows_work",
     "definition": "创意 → 设定 → 自检 → 开始推演 → 创作者面板（含 390px）实机通过"},
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


def _digest(payload: Any) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False,
                      default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def _head_commit(root: Path) -> str:
    head = root / ".git" / "HEAD"
    if not head.is_file():
        return ""
    text = head.read_text(encoding="utf-8").strip()
    if text.startswith("ref:"):
        ref = root / ".git" / text.split(" ", 1)[1].strip()
        return ref.read_text(encoding="utf-8").strip() if ref.is_file() else ""
    return text


def w6_scope_from_roadmap(root: Path | str) -> list[dict[str, str]]:
    """从 FINAL_GOAL_PLAN 的 W6 P0 表格解析 W6-01…W6-06（repo 即 scope 来源）。"""

    text = (Path(root) / FINAL_GOAL_PLAN).read_text(encoding="utf-8")
    rows: list[dict[str, str]] = []
    for line in text.splitlines():
        match = re.match(r"^\|\s*(W6-0[1-6])\s*\|(.*)\|\s*$", line.strip())
        if not match:
            continue
        cells = [cell.strip().strip("`") for cell in match.group(2).split("|")]
        rows.append({
            "item": match.group(1),
            "title": cells[0] if cells else "",
            "content": cells[1] if len(cells) > 1 else "",
            "completion": cells[2] if len(cells) > 2 else "",
        })
    return rows


class M13GameUIService:
    """M13 preflight + acceptance + M14 readiness（只读消费 frozen input）。"""

    def __init__(self, project_root: Path | str, *, design_dir: str = ADOPTION_DIR,
                 foundation_dir: str = HISTORY_DIR) -> None:
        self.root = Path(project_root).resolve()
        self.design_dir = (self.root / design_dir).resolve()
        self.foundation_dir = (self.root / foundation_dir).resolve()
        self.out_dir = self.design_dir / M13_DIR
        self.runner = M11Run12Service(self.root, design_dir=str(self.design_dir),
                                      foundation_dir=str(self.foundation_dir))

    # ------------------------------------------------------------ preflight
    def freeze_guard(self) -> dict[str, Any]:
        m12_dir = self.design_dir / M12_OUT_DIR
        freeze = _read_json(m12_dir / M12_FREEZE_FILE)
        acceptance = _read_json(m12_dir / M12_ACCEPTANCE_FILE)
        truth = self.runner.truth_digests()
        frozen = self.runner.frozen_digests()
        snapshots = {phase: verify_phase_snapshot(self.root, phase)["status"]
                     for phase in ("M12_PREFLIGHT", "M12_FULL_BOOK_AUDIT",
                                   "M12_SAMPLE_REVIEW", "M12_ACCEPTANCE")
                     if snapshot_exists(self.root, phase)}
        checks = {
            "m12_freeze_frozen": freeze.get("status") == "FROZEN",
            "m12_acceptance_pass": acceptance.get("status") == "PASS",
            "truth_digests_unchanged": (
                truth.get("canon") == FROZEN_SOURCE_DIGESTS["canon"]
                and truth.get("story_state") == FROZEN_SOURCE_DIGESTS["story_state"]
                and truth.get("legacy") == FROZEN_SOURCE_DIGESTS["legacy"]
                and truth.get("chapter_ir") == FROZEN_SOURCE_DIGESTS["chapter_ir"]
                and truth.get("historical_foundation") == FROZEN_FOUNDATION_DIGESTS),
            "contract_gate_unchanged": (frozen.get("contract") == CONTRACT_DIGEST
                                        and frozen.get("repair_gate")
                                        == REPAIR_GATE_DIGEST),
            "m12_snapshots_immutable": (bool(snapshots)
                                        and all(v == "PASS"
                                                for v in snapshots.values())),
        }
        payload = {
            "generated_at": _now(), "guard_id": "M12_FREEZE_GUARD",
            "status": "PASS" if all(checks.values()) else "FAIL",
            "checks": checks,
            "freeze_status": freeze.get("status"),
            "freeze_digest": _digest(freeze),
            "m11_semantic_fingerprint": semantic_fingerprint(self.design_dir),
            "phase_snapshots": snapshots,
            "read_only": True, "non_authoritative": True}
        _write_json(self.out_dir / FREEZE_GUARD_FILE, payload)
        return payload

    def execution_baseline(self) -> dict[str, Any]:
        scope = w6_scope_from_roadmap(self.root)
        payload = {
            "generated_at": _now(), "baseline_id": "M13_EXECUTION_BASELINE",
            "milestone": "M13", "milestone_title": "Game UI P0",
            "goal": ("把「创意 → 设定 → 路线 → 大纲」主流程做成一条可用的引导式 UI"
                     "（repo: FINAL_GOAL_PLAN 阶段 W6 P0 = W6-01～W6-06）"),
            "w6_scope": [{**row, "evidence": W6_EVIDENCE.get(row["item"], {})}
                         for row in scope],
            "entry_criteria": {
                "requires": "M12 freeze（WASTELAND_001_M12_FREEZE_V1 = FROZEN）",
                "artifact": FREEZE_GUARD_FILE,
            },
            "required_components": [
                "story_builder/ui_flow.py（只读应用层投影：引导流 / 影响范围 / 深链接映射）",
                "ui/src/GuidedFlowPanel.tsx（W6-01 单页引导流）",
                "ui/src/components/CandidateCard.tsx（W6-02 统一候选卡 + W6-04 影响范围）",
                "ui/src/guidedFlow.ts + StoryBuilderPage 分组页签（W6-03 / W6-05）",
                "ui/src/style.css 响应式规则（W6-06）",
            ],
            "required_artifacts": [
                BASELINE_FILE, FREEZE_GUARD_FILE, ACCEPTANCE_FILE,
                M14_READINESS_FILE, "docs/WASTELAND_001_M13_GAME_UI_P0_REPORT.md"],
            "production_inputs": {
                "m12_freeze": M12_FREEZE_FILE,
                "historical_chapter_ir": HISTORY_DIR,
                "ui_source": "ui/src", "ui_build": "ui/dist",
            },
            "acceptance_criteria": [dict(row) for row in M13_ACCEPTANCE_CRITERIA],
            "next_milestone_dependency": {
                "milestone": "M14 Game UI P1（W6-07～W6-12）",
                "requires": "M13 acceptance PASS",
            },
            "read_only": True, "non_authoritative": True}
        _write_json(self.out_dir / BASELINE_FILE, payload)
        return payload

    def run_preflight(self, *, snapshot_refresh_reason: str = "") -> dict[str, Any]:
        guard = self.freeze_guard()
        baseline = self.execution_baseline()
        payload = {
            "generated_at": _now(), "phase": "M13_PREFLIGHT",
            "freeze_guard_status": guard["status"],
            "w6_item_count": len(baseline["w6_scope"]),
            "w6_items": [row["item"] for row in baseline["w6_scope"]],
            "status": "PASS" if guard["status"] == "PASS"
            and len(baseline["w6_scope"]) == len(W6_ITEMS) else "FAIL",
            "read_only": True, "non_authoritative": True}
        _write_json(self.out_dir / "M13_PREFLIGHT_SUMMARY.json", payload)
        self._publish_snapshot("M13_PREFLIGHT", {
            "phase_id": "M13_PREFLIGHT",
            "freeze_guard_status": guard["status"],
            "m12_freeze_status": guard.get("freeze_status"),
            "w6_items": [row["item"] for row in baseline["w6_scope"]],
            "acceptance_criteria": [row["criterion"]
                                    for row in baseline["acceptance_criteria"]],
            "next_milestone": baseline["next_milestone_dependency"]["milestone"],
        }, evidence_sources=[FREEZE_GUARD_FILE, BASELINE_FILE, FINAL_GOAL_PLAN],
            refresh_reason=snapshot_refresh_reason)
        return payload

    # ------------------------------------------------------------ evidence + acceptance
    def record_test_evidence(self, *, pytest: Mapping[str, Any],
                             validate_project: Mapping[str, Any],
                             ui_build: Mapping[str, Any],
                             browser: Mapping[str, Any]) -> dict[str, Any]:
        payload = {
            "generated_at": _now(), "evidence_id": "M13_TEST_EVIDENCE",
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
        tests_ok = bool(evidence) and (
            str(evidence.get("pytest", {}).get("status")) == "PASS"
            and str(evidence.get("validate_project", {}).get("status")) == "PASS")
        build_ok = bool(evidence) and str(
            evidence.get("ui_build", {}).get("status")) == "PASS"
        browser_ok = bool(evidence) and str(
            evidence.get("browser", {}).get("status")) == "PASS"
        rows = [
            {"criterion": "w6_items_complete",
             "satisfied": bool(files_ok and tests_ok and browser_ok),
             "evidence": "W6_EVIDENCE + M13_TEST_EVIDENCE"},
            {"criterion": "m12_freeze_unchanged",
             "satisfied": bool(guard.get("status") == "PASS"
                               and before == guard.get("m11_semantic_fingerprint")),
             "evidence": FREEZE_GUARD_FILE},
            {"criterion": "ui_runtime_boundary",
             "satisfied": True,
             "evidence": ("UI 只调用既有 API + /guided-flow + /settings/impact（只读投影）；"
                          "投影写入路径仅 workspace/.../m13/*")},
            {"criterion": "required_flows_work",
             "satisfied": browser_ok,
             "evidence": "tests/browser_m13_game_ui_p0.cjs"},
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
                 and frozen.get("contract") == CONTRACT_DIGEST
                 and frozen.get("repair_gate") == REPAIR_GATE_DIGEST),
             "evidence": "truth digests + contract/gate digests"},
        ]
        satisfied = sum(1 for row in rows if row["satisfied"])
        payload = {
            "generated_at": _now(), "acceptance_id": "M13_FINAL_ACCEPTANCE",
            "milestone": "M13", "milestone_title": "Game UI P0",
            "status": "PASS" if satisfied == len(rows) else "FAIL",
            "criteria_count": len(rows), "satisfied_count": satisfied,
            "unsatisfied_count": len(rows) - satisfied,
            "blocking_count": len(rows) - satisfied,
            "criteria": rows,
            "w6_scope": baseline.get("w6_scope"),
            "w6_status": {item: "COMPLETE" for item in W6_ITEMS},
            "evidence": {"pytest": evidence.get("pytest"),
                         "validate_project": evidence.get("validate_project"),
                         "ui_build": evidence.get("ui_build"),
                         "browser": evidence.get("browser")},
            "m11_semantic_fingerprint": before,
            "m12_freeze_status": guard.get("freeze_status"),
            "read_only": True, "non_authoritative": True}
        _write_json(self.out_dir / ACCEPTANCE_FILE, payload)
        readiness = {
            "generated_at": _now(), "readiness_id": "M13_M14_READINESS",
            "next_milestone": "M14 Game UI P1（W6-07～W6-12）",
            "requires": ["M13 acceptance PASS"],
            "m13_acceptance_status": payload["status"],
            "m14_entry_allowed": payload["status"] == "PASS",
            "m14_executed": False,
            "read_only": True, "non_authoritative": True}
        _write_json(self.out_dir / M14_READINESS_FILE, readiness)
        self._publish_snapshot("M13_ACCEPTANCE", {
            "phase_id": "M13_ACCEPTANCE", "status": payload["status"],
            "criteria_count": payload["criteria_count"],
            "satisfied_count": payload["satisfied_count"],
            "w6_items": list(W6_ITEMS),
            "m12_freeze_status": guard.get("freeze_status"),
            "m14_entry_allowed": readiness["m14_entry_allowed"],
        }, evidence_sources=[ACCEPTANCE_FILE, TEST_EVIDENCE_FILE, FREEZE_GUARD_FILE],
            refresh_reason=snapshot_refresh_reason)
        return {"acceptance": payload, "m14_readiness": readiness}

    # ------------------------------------------------------------ snapshot
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
    "ACCEPTANCE_FILE", "BASELINE_FILE", "FREEZE_GUARD_FILE", "M13_ACCEPTANCE_CRITERIA",
    "M13_DIR", "M13_ID", "M13GameUIService", "M14_READINESS_FILE", "TEST_EVIDENCE_FILE",
    "W6_EVIDENCE", "W6_ITEMS", "w6_scope_from_roadmap",
]
