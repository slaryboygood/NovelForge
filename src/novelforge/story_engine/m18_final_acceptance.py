"""M18 Product Final Acceptance：产品能力矩阵 + 最终验收 + 文档收口 + freeze manifest。

scope 来源（repo）：MILESTONES M18「Product Final Acceptance：产品级验收 + 文档收口」+
MASTER_PLAN M18 行 + FINAL_GOAL_PLAN 的最终目标（通用剧情生成器 + 大纲生成器 +
规划/导出/Writer 下游能力 + 跨题材复用）。

本 milestone 不新增产品功能：只做可核验汇总、结构收敛与文档收口。
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
from novelforge.story_engine.milestone_acceptance import head_commit, publish_phase_snapshot
from novelforge.story_engine.m17_cross_genre_e2e import (
    E2E_CHAIN as M17_CHAIN,
    M17_DIR,
    REQUIRED_GENRES as M17_GENRES,
)

M18_DIR = "m18"
BASELINE_FILE = "M18_EXECUTION_BASELINE.json"
CAPABILITY_FILE = "M18_PRODUCT_CAPABILITY_MATRIX.json"
ARCHITECTURE_FILE = "M18_ARCHITECTURE_AUDIT.json"
DOCS_FILE = "M18_DOCUMENTATION_AUDIT.json"
TEST_EVIDENCE_FILE = "M18_TEST_EVIDENCE.json"
ACCEPTANCE_FILE = "M18_FINAL_ACCEPTANCE.json"
FREEZE_FILE = "NOVELFORGE_PRODUCT_V2_FREEZE.json"
RELEASE_FILE = "NOVELFORGE_PRODUCT_V2_RELEASE.json"
RELEASE_TAG = "novelforge-product-v2.0"
RELEASE_DATE = "2026-09-15"

# 产品能力矩阵（M18 §4）：每项都要在磁盘上可核验（files / tests / entry）。
CAPABILITIES: tuple[dict[str, Any], ...] = (
    {"capability_id": "idea_input", "name": "创意输入（一句创意 → 方向候选）",
     "source_milestone": "M13", "truth_boundary": "planned",
     "files": ["ui/src/CreativeBriefPanel.tsx", "src/novelforge/story_builder/ui_flow.py"],
     "tests": ["tests/test_m13_game_ui_p0.py"], "entry": "POST /creative/suggest · UI 引导流"},
    {"capability_id": "settings_generation", "name": "设定生成（世界 / 角色 / 势力 / 关系 / 成长 / 主线 / 伏笔）",
     "source_milestone": "M13", "truth_boundary": "planned",
     "files": ["ui/src/SettingSeedPanel.tsx", "src/novelforge/story_engine/settings_gen.py"],
     "tests": ["tests/test_story_builder_settings_seed.py"],
     "entry": "POST /settings/seed · UI 设定步骤"},
    {"capability_id": "settings_check", "name": "设定自检与可运行性修复",
     "source_milestone": "M13/M15", "truth_boundary": "planned",
     "files": ["src/novelforge/story_engine/settings_check.py",
               "src/novelforge/story_builder/inspector.py"],
     "tests": ["tests/test_story_builder_settings_check.py",
               "tests/test_m15_canon_inspector.py"],
     "entry": "POST /settings/check(repair) · UI 修复中心"},
    {"capability_id": "runtime_story_state", "name": "运行态 StoryState（唯一事实来源）",
     "source_milestone": "M6/M10/M13", "truth_boundary": "occurred",
     "files": ["src/novelforge/story_engine/state.py",
               "src/novelforge/story_engine/creator.py"],
     "tests": ["tests/test_story_engine_state.py", "tests/test_story_builder_runtime_api.py"],
     "entry": "POST /runtime/start · /runtime/advance"},
    {"capability_id": "dynamic_world", "name": "动态世界（地点 / 资源 / 世界事件）",
     "source_milestone": "M14", "truth_boundary": "occurred",
     "files": ["src/novelforge/story_engine/world_view.py",
               "ui/src/VisualOverviewPanels.tsx"],
     "tests": ["tests/test_m14_game_ui_p1.py"], "entry": "GET /creator/world · UI 区域卡片"},
    {"capability_id": "dynamic_characters", "name": "动态角色（目标 / 记忆 / 关系 / 弧线）",
     "source_milestone": "M14", "truth_boundary": "occurred",
     "files": ["src/novelforge/story_engine/character_view.py",
               "ui/src/VisualOverviewPanels.tsx"],
     "tests": ["tests/test_m14_game_ui_p1.py"], "entry": "GET /creator/characters · UI 关系网"},
    {"capability_id": "candidate_actions", "name": "候选行动（由状态生成，不可自证）",
     "source_milestone": "M6/M10", "truth_boundary": "occurred",
     "files": ["src/novelforge/story_engine/actions.py",
               "src/novelforge/story_engine/plot_view.py"],
     "tests": ["tests/test_m17_cross_genre_e2e.py"], "entry": "GET /runtime/state · POST /runtime/advance"},
    {"capability_id": "events_plots_foreshadows", "name": "事件 / 支线 / 伏笔生命周期",
     "source_milestone": "M6/M10", "truth_boundary": "occurred",
     "files": ["src/novelforge/story_engine/events.py",
               "src/novelforge/story_engine/foreshadow.py",
               "src/novelforge/story_engine/plot_view.py"],
     "tests": ["tests/test_story_engine_events.py", "tests/test_story_engine_foreshadow.py"],
     "entry": "GET /creator/plot · /creator/memory"},
    {"capability_id": "progression", "name": "通用成长（七类 progression / 代价）",
     "source_milestone": "M5/M10", "truth_boundary": "occurred",
     "files": ["src/novelforge/story_engine/progression.py",
               "src/novelforge/story_engine/progression_view.py"],
     "tests": ["tests/test_story_engine_progression.py"], "entry": "GET /creator/progression"},
    {"capability_id": "route_lab", "name": "路线试演 / 对比 / 合并 / 冻结",
     "source_milestone": "M13/M14", "truth_boundary": "occurred（分支事实）",
     "files": ["src/novelforge/story_engine/route_lab.py", "ui/src/RouteLabPanel.tsx"],
     "tests": ["tests/test_m14_game_ui_p1.py"], "entry": "POST /runtime/branches/* · UI 路线实验室"},
    {"capability_id": "outline_four_levels", "name": "四级大纲（BOOK → VOLUME → ARC → CHAPTER）",
     "source_milestone": "M9/M14", "truth_boundary": "planned",
     "files": ["src/novelforge/story_engine/outline_forge.py",
               "ui/src/VisualOutputPanels.tsx"],
     "tests": ["tests/test_m14_game_ui_p1.py"], "entry": "POST /outline/forge · GET /outline/chain"},
    {"capability_id": "outline_version_edit_export", "name": "大纲版本 / 修改 / 回退 / 导出",
     "source_milestone": "M9/M16A", "truth_boundary": "planned",
     "files": ["src/novelforge/story_engine/outline_revision.py",
               "src/novelforge/story_builder/export_package.py"],
     "tests": ["tests/test_m16a_planning_export.py"],
     "entry": "GET /outline/versions · POST /outline/revise|restore · GET /export/package"},
    {"capability_id": "ui_main_flow", "name": "UI 主流程（引导流 + 分组页签 + 阶段提示）",
     "source_milestone": "M13", "truth_boundary": "ui_derived",
     "files": ["ui/src/StoryBuilderPage.tsx", "ui/src/GuidedFlowPanel.tsx",
               "ui/src/guidedFlow.ts"],
     "tests": ["tests/browser_m13_game_ui_p0.cjs"], "entry": "UI #/story-builder?tab=guided"},
    {"capability_id": "ui_visualization", "name": "2D 可视化（总览 / 区域 / 关系 / 对比 / 大纲树 / 参考位）",
     "source_milestone": "M14", "truth_boundary": "occurred/planned/ui_derived",
     "files": ["ui/src/VisualOverviewPanels.tsx", "ui/src/VisualOutputPanels.tsx"],
     "tests": ["tests/browser_m14_game_ui_p1.cjs"], "entry": "UI tabs: 设定总览 / 区域卡片 / 关系网 / 路线对比 / 大纲结构树 / 风格参考位"},
    {"capability_id": "canon_inspector", "name": "Canon 检查器（跨层只读检查 + provenance）",
     "source_milestone": "M15", "truth_boundary": "read-only",
     "files": ["src/novelforge/story_builder/inspector.py",
               "ui/src/InspectorPanels.tsx",
               "ui/src/components/ProvenanceList.tsx"],
     "tests": ["tests/test_m15_canon_inspector.py",
               "tests/browser_m15_canon_inspector.cjs"],
     "entry": "GET /inspector/overview|search|record · UI Canon 检查器"},
    {"capability_id": "repair_center", "name": "修复中心（诊断 → 预览 → 审批 → 执行既有 API → 历史）",
     "source_milestone": "M15", "truth_boundary": "planned",
     "files": ["src/novelforge/story_builder/inspector.py",
               "ui/src/InspectorPanels.tsx"],
     "tests": ["tests/test_m15_canon_inspector.py",
               "tests/browser_m15_canon_inspector.cjs"],
     "entry": "GET /repair/diagnosis|history · UI 修复中心"},
    {"capability_id": "planning_export", "name": "Planning Export（Story Bible / 卡片 / Timeline / Spine / 大纲）",
     "source_milestone": "M16A", "truth_boundary": "planned",
     "files": ["src/novelforge/story_builder/export_package.py"],
     "tests": ["tests/test_m16a_planning_export.py"],
     "entry": "GET /export/package(json|markdown|docx) · GET /export/writer-bundle"},
    {"capability_id": "writer_integration", "name": "Writer Integration（分层 context + draft + Draft Fact Sync）",
     "source_milestone": "M16B", "truth_boundary": "preview",
     "files": ["src/novelforge/story_builder/writer_integration.py"],
     "tests": ["tests/test_m16b_writer_integration.py", "tests/test_story_engine_writer.py"],
     "entry": "GET /writer/context · POST /writer/drafts · /sync-facts"},
    {"capability_id": "cross_genre_e2e", "name": "跨题材复用（同一实现，只换数据）",
     "source_milestone": "M17", "truth_boundary": "n/a（验证设施）",
     "files": ["src/novelforge/story_builder/cross_genre_e2e.py"],
     "tests": ["tests/test_m17_cross_genre_e2e.py", "tests/test_story_engine_cross_genre.py"],
     "entry": "CrossGenreE2ERunner（3 题材 13 步产品链）"},
)

FINAL_ACCEPTANCE_CRITERIA: tuple[dict[str, str], ...] = (
    {"criterion": "capability_matrix_pass",
     "definition": "19 项产品能力全部有实现文件 + 测试 + 入口 + truth boundary，且在磁盘可核验"},
    {"criterion": "final_cross_genre_e2e_pass",
     "definition": "复用 CrossGenreE2ERunner：3 题材 13 步全链 PASS（不新增第四套 E2E）"},
    {"criterion": "negative_acceptance_pass",
     "definition": "非法 action / 导出篡改 / writer 新事实 / planning-vs-occurred / repair 预览边界全部被拦截"},
    {"criterion": "crash_resume_stability_pass",
     "definition": "crash/resume regression + compiler suite PASS；历史间歇问题标注为非阻塞"},
    {"criterion": "architecture_audit_pass",
     "definition": "无第二套状态模型 / 无题材分支 / acceptance 基础设施已收敛 / 无死浏览器脚本"},
    {"criterion": "documentation_audit_pass",
     "definition": "README / ARCHITECTURE / DATA_MODEL / roadmap / changelog 与实现一致，SSOT 唯一"},
    {"criterion": "frozen_truth_guard_pass",
     "definition": "Canon / StoryState / legacy / 570 source IR / Foundation / Contract / Gate + M11–M17 输入不变"},
    {"criterion": "full_verification_pass",
     "definition": "pytest / validate_project / UI build / canonical browser flows / export replay / writer integration 全绿"},
    {"criterion": "release_manifest_written",
     "definition": "NOVELFORGE_PRODUCT_V2_FREEZE.json 记录最终 digest、能力与已知债务分类"},
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


class M18FinalAcceptanceService:
    def __init__(self, project_root: Path | str, *, design_dir: str = ADOPTION_DIR,
                 foundation_dir: str = HISTORY_DIR) -> None:
        self.root = Path(project_root).resolve()
        self.design_dir = (self.root / design_dir).resolve()
        self.foundation_dir = (self.root / foundation_dir).resolve()
        self.out_dir = self.design_dir / M18_DIR
        self.runner = M11Run12Service(self.root, design_dir=str(self.design_dir),
                                      foundation_dir=str(self.foundation_dir))

    # ------------------------------------------------------------ capability matrix
    def capability_matrix(self) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        for spec in CAPABILITIES:
            files = [path for path in spec["files"] if (self.root / path).is_file()]
            tests = [path for path in spec["tests"] if (self.root / path).is_file()]
            rows.append({**spec, "files_present": files, "tests_present": tests,
                         "status": "PASS" if len(files) == len(spec["files"])
                         and len(tests) == len(spec["tests"]) else "FAIL"})
        failed = [row["capability_id"] for row in rows if row["status"] != "PASS"]
        payload = {"generated_at": _now(), "matrix_id": "M18_PRODUCT_CAPABILITY_MATRIX",
                   "capability_count": len(rows),
                   "status": "PASS" if not failed else "FAIL",
                   "failed_capabilities": failed,
                   "truth_layer_legend": {
                       "occurred": "Canon / StoryState（已发生事实）",
                       "planned": "规划 / 设定 / 大纲（未提交为事实）",
                       "historical_repair": "M11/M12 frozen repair lineage",
                       "preview": "writer 草稿 / 提议（不写事实）",
                       "ui_derived": "UI 派生（不成为 truth）",
                       "read-only": "只读检查（Inspector）"},
                   "capabilities": rows,
                   "read_only": True, "non_authoritative": True}
        _write_json(self.out_dir / CAPABILITY_FILE, payload)
        return payload

    # ------------------------------------------------------------ baseline / preflight
    def execution_baseline(self) -> dict[str, Any]:
        m17_dir = self.design_dir / M17_DIR
        readiness = _read_json(m17_dir / "M17_M18_READINESS.json")
        acceptance = _read_json(m17_dir / "M17_ACCEPTANCE.json")
        payload = {
            "generated_at": _now(), "baseline_id": "M18_EXECUTION_BASELINE",
            "milestone": "M18", "milestone_title": "Product Final Acceptance + Doc Closeout",
            "goal": ("产品级最终验收 + 文档/roadmap/状态收口（repo: MILESTONES M18；"
                     "FINAL_GOAL_PLAN 最终目标 = 通用剧情生成器 + 大纲生成器 + "
                     "规划/导出/Writer 下游能力 + 跨题材复用）"),
            "entry_criteria": {"requires": "M17 acceptance PASS / m18_entry_allowed",
                               "artifact": "M17_M18_READINESS.json",
                               "m17_acceptance_status": acceptance.get("status"),
                               "m18_entry_allowed": readiness.get("m18_entry_allowed")},
            "required_verification": [
                "Final Product Capability Matrix（19 项能力可核验）",
                "Final Cross-genre E2E（复用 CrossGenreE2ERunner，3 题材）",
                "Final negative acceptance（非法 action / 导出篡改 / writer 新事实 / planning≠occurred / repair 预览边界）",
                "Crash/resume stability（compiler suite + 3 轮 regression）",
                "Final architecture audit（第二套状态模型 / 题材分支 / acceptance 基础设施 / 死代码）",
                "Documentation audit（README / ARCHITECTURE / DATA_MODEL / roadmap / changelog SSOT）",
                "Final frozen guard（truth digests + M11–M17 输入）",
                "full pytest + validate_project + UI build + canonical browser flows"],
            "required_artifacts": [BASELINE_FILE, CAPABILITY_FILE, ARCHITECTURE_FILE,
                                   DOCS_FILE, TEST_EVIDENCE_FILE, ACCEPTANCE_FILE,
                                   FREEZE_FILE,
                                   "docs/NOVELFORGE_PRODUCT_V2_FINAL_ACCEPTANCE_REPORT.md"],
            "required_docs": {
                "product_overview": "README.md",
                "architecture_ssot": "docs/ARCHITECTURE.md",
                "data_model_ssot": "docs/DATA_MODEL.md",
                "roadmap_status": ["docs/NOVELFORGE_PRODUCT_V2_MASTER_PLAN.md",
                                   "docs/NOVELFORGE_PRODUCT_V2_MILESTONES.md",
                                   "docs/NOVELFORGE_PRODUCT_V2_PROGRESS_AUDIT.md"],
                "changelog": "docs/CHANGELOG.md",
                "user_guide": "docs/STORY_BUILDER_USER_GUIDE.md",
                "new_novel_guide": "docs/NEW_NOVEL_GUIDE.md",
                "production_guide": "docs/NOVELFORGE_REAL_NOVEL_PRODUCTION_GUIDE.md",
                "archive": "docs/ARCHIVE_W_ERA_STATUS.md",
            },
            "acceptance_criteria": [dict(row) for row in FINAL_ACCEPTANCE_CRITERIA],
            "next_state_semantics": ("无后续 milestone（repo M0–M18 全部完成）→ "
                                     "PRODUCT_V2_COMPLETE；不创建 M19"),
            "frozen_truth_digests": {"source": dict(FROZEN_SOURCE_DIGESTS),
                                     "foundation": dict(FROZEN_FOUNDATION_DIGESTS),
                                     "contract": "67559aa55442d69e",
                                     "repair_gate": "e1eab4c33ae75b01"},
            "m11_to_m17_fingerprint": semantic_fingerprint(self.design_dir),
            "read_only": True, "non_authoritative": True}
        _write_json(self.out_dir / BASELINE_FILE, payload)
        return payload

    def run_preflight(self, *, snapshot_refresh_reason: str = "") -> dict[str, Any]:
        baseline = self.execution_baseline()
        matrix = self.capability_matrix()
        payload = {"generated_at": _now(), "phase": "M18_PREFLIGHT",
                   "m17_entry_allowed": baseline["entry_criteria"]["m18_entry_allowed"],
                   "capability_count": matrix["capability_count"],
                   "capability_matrix_status": matrix["status"],
                   "status": "PASS" if baseline["entry_criteria"]["m18_entry_allowed"]
                   and matrix["status"] == "PASS" else "FAIL",
                   "read_only": True, "non_authoritative": True}
        _write_json(self.out_dir / "M18_PREFLIGHT_SUMMARY.json", payload)
        publish_phase_snapshot(self.root, "M18_PREFLIGHT", {
            "phase_id": "M18_PREFLIGHT",
            "m17_acceptance_status": baseline["entry_criteria"]["m17_acceptance_status"],
            "capability_count": matrix["capability_count"],
            "capability_matrix_status": matrix["status"],
            "acceptance_criteria": [row["criterion"]
                                    for row in baseline["acceptance_criteria"]],
        }, evidence_sources=[BASELINE_FILE, CAPABILITY_FILE],
            refresh_reason=snapshot_refresh_reason)
        return payload

    # ------------------------------------------------------------ audits
    def architecture_audit(self) -> dict[str, Any]:
        engine = self.root / "src" / "novelforge" / "story_engine"
        story_builder = self.root / "src" / "novelforge" / "story_builder"
        engine_text = "".join(path.read_text(encoding="utf-8")
                              for path in sorted(engine.glob("*.py")))
        shared_helper = engine / "milestone_acceptance.py"
        delegating = [path.name for path in engine.glob("m1[2-8]_*.py")
                      if "publish_phase_snapshot" in path.read_text(encoding="utf-8")]
        legacy_browser = [path.name for path in (self.root / "tests").glob("browser_*.cjs")]
        checks = {
            "no_second_state_model": (self.root / "src" / "novelforge" /
                                      "story_engine" / "state.py").is_file()
            and not (engine / "state_v2.py").exists(),
            "no_genre_branches_in_engine": not any(
                f"{verb} {name} ==" in engine_text for verb, name in
                (("if", "genre"), ("if", "pack_id"), ("if", "novel_id"),
                 ("elif", "template_id"))),
            "acceptance_helper_shared": shared_helper.is_file()
            and "milestone_acceptance" in (engine / "m17_cross_genre_e2e.py").read_text(
                encoding="utf-8"),
            "acceptance_duplication_converged": len(delegating) >= 5,
            "single_export_projection": (story_builder / "export_package.py").is_file(),
            "single_writer_context_builder": (
                story_builder / "writer_integration.py").is_file(),
            "single_ui_projection": (story_builder / "ui_flow.py").is_file(),
            "no_dead_v1_browser_scripts": all(
                "guided_flow" not in name for name in legacy_browser),
            "canonical_browser_flows_present": all(
                (self.root / "tests" / name).is_file() for name in
                ("browser_m13_game_ui_p0.cjs", "browser_m14_game_ui_p1.cjs",
                 "browser_m15_canon_inspector.cjs")),
        }
        payload = {"generated_at": _now(), "audit_id": "M18_ARCHITECTURE_AUDIT",
                   "status": "PASS" if all(checks.values()) else "FAIL",
                   "checks": checks, "browser_scripts": legacy_browser,
                   "snapshot_delegating_services": delegating,
                   "duplication_removed": [
                       "milestone acceptance 的 phase snapshot 发布收敛到 "
                       "story_engine/milestone_acceptance.py（M13–M17 委托）",
                       "M12–M17 的 freeze guard / baseline / acceptance 骨架保持同一形态"],
                   "dead_code_removed": [
                       "M15 已删除 4 个引用退役入口的 V1 浏览器脚本；本轮复核无残留"],
                   "architecture_debt": [
                       {"debt_id": "COMPILER_CRASH_RESUME_INTERMITTENT",
                        "classification": "HISTORICAL",
                        "detail": ("test_arc_batch_promotes_each_arc_and_survives_crash "
                                   "曾在 full suite 偶发失败，无法稳定复现；已加 3 轮循环 regression")},
                       {"debt_id": "M16_EXPORT_WRITER_NO_UI",
                        "classification": "OPTIONAL",
                        "detail": "M16A/M16B 目前为 application/API 入口；repo 未要求 UI"},
                       {"debt_id": "LIVE_ANALYSIS_PHASE_SCOPED_DIR",
                        "classification": "OPTIONAL",
                        "detail": "live analysis artifact 的 phase-scoped 目录化（可选优化）"},
                       {"debt_id": "REPAIR_CENTER_MORE_TYPES",
                        "classification": "OPTIONAL",
                        "detail": "Repair Center 目前只执行 settings/check 类修复；扩展更多 repair type 超出 M15 定义"}],
                   "read_only": True, "non_authoritative": True}
        _write_json(self.out_dir / ARCHITECTURE_FILE, payload)
        return payload

    def documentation_audit(self) -> dict[str, Any]:
        docs_dir = self.root / "docs"
        required = {
            "README.md": "product overview",
            "docs/ARCHITECTURE.md": "architecture SSOT",
            "docs/DATA_MODEL.md": "data model SSOT",
            "docs/NOVELFORGE_PRODUCT_V2_MASTER_PLAN.md": "roadmap SSOT",
            "docs/NOVELFORGE_PRODUCT_V2_MILESTONES.md": "milestones",
            "docs/NOVELFORGE_PRODUCT_V2_PROGRESS_AUDIT.md": "progress audit",
            "docs/CHANGELOG.md": "changelog",
            "docs/STORY_BUILDER_USER_GUIDE.md": "user guide",
            "docs/NEW_NOVEL_GUIDE.md": "new novel guide",
            "docs/NOVELFORGE_REAL_NOVEL_PRODUCTION_GUIDE.md": "production guide",
        }
        readme = (self.root / "README.md").read_text(encoding="utf-8")
        architecture = (self.root / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
        data_model = (self.root / "docs" / "DATA_MODEL.md").read_text(encoding="utf-8")
        coverage = {
            "readme_explains_what_and_status": "PRODUCT_V2" in readme
            and ("M18" in readme or "产品状态" in readme),
            "readme_has_run_instructions": "start_novelforge_ui" in readme
            and "pytest" in readme and "npm" in readme,
            "readme_has_flow_and_export": "引导流" in readme and "export" in readme.lower(),
            "readme_has_writer_role": "Writer" in readme,
            "readme_has_truth_layers": all(token in readme for token in
                                           ("Canon", "StoryState", "planning")),
            "readme_lists_frozen_dirs": "frozen" in readme.lower()
            or "冻结" in readme,
            "architecture_covers_m15_m17": all(
                token in architecture for token in
                ("Inspector", "Repair", "Planning Export", "Writer", "Cross-genre")),
            "architecture_layers_named": all(
                token in architecture for token in
                ("Domain", "Application", "API", "UI")),
            "data_model_covers_key_objects": all(
                token in data_model for token in
                ("NovelProfile", "ContentPack", "StoryState", "Planning",
                 "ChapterSemanticIR", "Historical IR", "WriterContext",
                 "ExportProjection")),
            "data_model_marks_authority": ("authoritative" in data_model.lower()
                                           and "derived" in data_model.lower()
                                           and "frozen" in data_model.lower()),
        }
        inventory = [
            {"doc": path.relative_to(self.root).as_posix(),
             "classification": ("CURRENT" if path.relative_to(self.root).as_posix()
                                in required else "HISTORICAL"),
             "kind": required.get(path.relative_to(self.root).as_posix(), "phase report / archive")}
            for path in sorted(list(docs_dir.glob("*.md")) + [self.root / "README.md"])]
        payload = {"generated_at": _now(), "audit_id": "M18_DOCUMENTATION_AUDIT",
                   "status": "PASS" if all(coverage.values()) else "FAIL",
                   "coverage_checks": coverage,
                   "ssot": required, "doc_count": len(inventory),
                   "inventory": inventory,
                   "obsolete_candidates": [],
                   "duplicate_removed": [
                       "roadmap/status 只保留 MASTER_PLAN + MILESTONES + PROGRESS_AUDIT 三处 SSOT",
                       "W 时代状态文档归档为 docs/ARCHIVE_W_ERA_STATUS.md"],
                   "read_only": True, "non_authoritative": True}
        _write_json(self.out_dir / DOCS_FILE, payload)
        return payload

    # ------------------------------------------------------------ evidence + acceptance
    def record_test_evidence(self, *, pytest: Mapping[str, Any],
                             validate_project: Mapping[str, Any],
                             ui_build: Mapping[str, Any], browser: Mapping[str, Any],
                             e2e: Mapping[str, Any], crash_resume: Mapping[str, Any]
                             ) -> dict[str, Any]:
        payload = {"generated_at": _now(), "evidence_id": "M18_TEST_EVIDENCE",
                   "pytest": dict(pytest), "validate_project": dict(validate_project),
                   "ui_build": dict(ui_build), "browser": dict(browser),
                   "e2e": dict(e2e), "crash_resume": dict(crash_resume),
                   "read_only": True, "non_authoritative": True}
        _write_json(self.out_dir / TEST_EVIDENCE_FILE, payload)
        return payload

    def final_acceptance(self, *, evidence: Mapping[str, Any] | None = None,
                         e2e_results: Mapping[str, Any] | None = None,
                         snapshot_refresh_reason: str = "") -> dict[str, Any]:
        baseline = _read_json(self.out_dir / BASELINE_FILE)
        matrix = self.capability_matrix()
        architecture = self.architecture_audit()
        doc_audit = self.documentation_audit()
        evidence = evidence or _read_json(self.out_dir / TEST_EVIDENCE_FILE)
        e2e = dict(e2e_results or evidence.get("e2e") or {})
        truth = self.runner.truth_digests()
        frozen = self.runner.frozen_digests()
        before = semantic_fingerprint(self.design_dir)
        m17 = _read_json(self.design_dir / M17_DIR / "M17_ACCEPTANCE.json")
        tests_ok = (str(evidence.get("pytest", {}).get("status")) == "PASS"
                    and str(evidence.get("validate_project", {}).get("status")) == "PASS")
        browser_ok = str(evidence.get("browser", {}).get("status")) == "PASS"
        build_ok = str(evidence.get("ui_build", {}).get("status")) == "PASS"
        resume_ok = str(evidence.get("crash_resume", {}).get("status")) == "PASS"
        rows = [
            {"criterion": "capability_matrix_pass",
             "satisfied": matrix["status"] == "PASS",
             "evidence": CAPABILITY_FILE},
            {"criterion": "final_cross_genre_e2e_pass",
             "satisfied": bool(e2e.get("status") == "PASS"
                               and e2e.get("case_count", 0) >= 3),
             "evidence": "CrossGenreE2ERunner（3 题材 13 步）"},
            {"criterion": "negative_acceptance_pass",
             "satisfied": all(row["negative_checks"] and all(row["negative_checks"].values())
                              for row in (e2e.get("results") or [])) if e2e.get("results")
             else False,
             "evidence": "M17 E2E negative checks（参数化）"},
            {"criterion": "crash_resume_stability_pass",
             "satisfied": bool(resume_ok),
             "evidence": "test_crash_resume_stability_regression + compiler suite"},
            {"criterion": "architecture_audit_pass",
             "satisfied": architecture["status"] == "PASS",
             "evidence": ARCHITECTURE_FILE},
            {"criterion": "documentation_audit_pass",
             "satisfied": doc_audit["status"] == "PASS",
             "evidence": DOCS_FILE},
            {"criterion": "frozen_truth_guard_pass",
             "satisfied": bool(
                 before == baseline.get("m11_to_m17_fingerprint")
                 and truth.get("canon") == FROZEN_SOURCE_DIGESTS["canon"]
                 and truth.get("story_state") == FROZEN_SOURCE_DIGESTS["story_state"]
                 and truth.get("legacy") == FROZEN_SOURCE_DIGESTS["legacy"]
                 and truth.get("chapter_ir") == FROZEN_SOURCE_DIGESTS["chapter_ir"]
                 and truth.get("historical_foundation") == FROZEN_FOUNDATION_DIGESTS
                 and frozen.get("contract") == "67559aa55442d69e"
                 and frozen.get("repair_gate") == "e1eab4c33ae75b01"
                 and m17.get("status") == "PASS"),
             "evidence": "truth digests + M11–M17 acceptance inputs"},
            {"criterion": "full_verification_pass",
             "satisfied": bool(tests_ok and build_ok and browser_ok),
             "evidence": TEST_EVIDENCE_FILE},
            {"criterion": "release_manifest_written",
             "satisfied": (self.out_dir / FREEZE_FILE).is_file(),
             "evidence": FREEZE_FILE},
        ]
        satisfied = sum(1 for row in rows if row["satisfied"])
        payload = {"generated_at": _now(), "acceptance_id": "M18_FINAL_ACCEPTANCE",
                   "milestone": "M18",
                   "milestone_title": "Product Final Acceptance + Doc Closeout",
                   "status": "PASS" if satisfied == len(rows) else "FAIL",
                   "criteria_count": len(rows), "satisfied_count": satisfied,
                   "unsatisfied_count": len(rows) - satisfied,
                   "blocking_count": len(rows) - satisfied, "criteria": rows,
                   "capability_matrix": {"count": matrix["capability_count"],
                                         "status": matrix["status"]},
                   "cross_genre_e2e": {"status": e2e.get("status"),
                                       "cases": [row.get("case_id")
                                                 for row in e2e.get("results") or []],
                                       "genres": list(M17_GENRES),
                                       "chain": list(M17_CHAIN)},
                   "evidence": {key: evidence.get(key) for key in
                                ("pytest", "validate_project", "ui_build", "browser",
                                 "e2e", "crash_resume")},
                   "documentation_audit": doc_audit,
                   "architecture_audit": architecture,
                   "m11_semantic_fingerprint": before,
                   "read_only": True, "non_authoritative": True}
        _write_json(self.out_dir / ACCEPTANCE_FILE, payload)
        freeze = {
            "generated_at": _now(), "freeze_id": "NOVELFORGE_PRODUCT_V2_FREEZE",
            "product": "NovelForge Product V2（通用剧情生成器 + 大纲生成器 + 规划/导出/Writer 下游）",
            "status": "FROZEN" if payload["status"] == "PASS" else "NOT_FROZEN",
            "milestones": [f"M{index}" for index in range(0, 19)],
            "milestone_status": {"M0-M9": "COMPLETE", "M10": "COMPLETE", "M11": "COMPLETE",
                                 "M12": "COMPLETE", "M13": "COMPLETE", "M14": "COMPLETE",
                                 "M15": "COMPLETE", "M16": "COMPLETE", "M17": "COMPLETE",
                                 "M18": payload["status"]},
            "truth_digests": truth,
            "frozen_digests": {"contract": frozen.get("contract"),
                               "repair_gate": frozen.get("repair_gate")},
            "m11_semantic_fingerprint": before,
            "capability_matrix_ref": CAPABILITY_FILE,
            "acceptance_ref": ACCEPTANCE_FILE,
            "known_debt": architecture["architecture_debt"],
            "next_state": ("PRODUCT_V2_COMPLETE（无后续 milestone；不创建 M19）"
                           if payload["status"] == "PASS" else "INCOMPLETE"),
            "read_only": True, "non_authoritative": True}
        _write_json(self.out_dir / FREEZE_FILE, freeze)
        publish_phase_snapshot(self.root, "M18_ACCEPTANCE", {
            "phase_id": "M18_ACCEPTANCE", "status": payload["status"],
            "criteria_count": payload["criteria_count"],
            "satisfied_count": payload["satisfied_count"],
            "capability_count": matrix["capability_count"],
            "cross_genre_status": e2e.get("status"),
            "documentation_status": doc_audit["status"],
            "architecture_status": architecture["status"],
            "product_v2_freeze": freeze["status"],
        }, evidence_sources=[ACCEPTANCE_FILE, CAPABILITY_FILE, DOCS_FILE,
                             ARCHITECTURE_FILE, FREEZE_FILE],
            refresh_reason=snapshot_refresh_reason)
        return {"acceptance": payload, "freeze": freeze, "matrix": matrix,
                "architecture": architecture, "documentation": doc_audit}

    def run(self, *, e2e_results: Mapping[str, Any] | None = None,
            snapshot_refresh_reason: str = "") -> dict[str, Any]:
        self.run_preflight(snapshot_refresh_reason=snapshot_refresh_reason)
        result = self.final_acceptance(e2e_results=e2e_results,
                                       snapshot_refresh_reason=snapshot_refresh_reason)
        return result

    # ------------------------------------------------------------ release manifest
    def release_manifest(self) -> dict[str, Any]:
        """Product V2 release manifest（deterministic：不含生成时间，重复生成字节一致）。"""

        acceptance = _read_json(self.out_dir / ACCEPTANCE_FILE)
        freeze = _read_json(self.out_dir / FREEZE_FILE)
        matrix = _read_json(self.out_dir / CAPABILITY_FILE)
        evidence = _read_json(self.out_dir / TEST_EVIDENCE_FILE)
        audit = _read_json(self.out_dir / ARCHITECTURE_FILE)
        truth = self.runner.truth_digests()
        frozen = self.runner.frozen_digests()
        debt = {row["debt_id"]: row["classification"]
                for row in audit.get("architecture_debt") or []}
        payload = {
            "product": "NovelForge Product V2",
            "status": "RELEASED" if acceptance.get("status") == "PASS"
            and freeze.get("status") == "FROZEN" else "NOT_RELEASED",
            "freeze": freeze.get("status"),
            "release_date": RELEASE_DATE,
            "release_tag": RELEASE_TAG,
            "m0_m18_complete": all(
                freeze.get("milestone_status", {}).get(key) in ("COMPLETE", "PASS")
                for key in ("M0-M9", "M10", "M11", "M12", "M13", "M14", "M15", "M16",
                            "M17", "M18")),
            "final_commit": head_commit(self.root),
            "final_acceptance": acceptance.get("status"),
            "final_acceptance_ref": {
                "artifact": ACCEPTANCE_FILE,
                "note": ("M18 验收 artifact 由 acceptance 提交产生；release manifest 与 handoff "
                         "文档为同一次封版提交，其中不含任何产品代码 / truth 变更。"),
            },
            "release_artifacts": {
                "manifest": f"{ADOPTION_DIR}/{M18_DIR}/{RELEASE_FILE}",
                "handoff": "docs/NOVELFORGE_PRODUCT_V2_RELEASE.md",
                "final_acceptance_report": (
                    "docs/NOVELFORGE_PRODUCT_V2_FINAL_ACCEPTANCE_REPORT.md"),
                "freeze": f"{ADOPTION_DIR}/{M18_DIR}/{FREEZE_FILE}",
            },
            "verification": {
                "pytest": (evidence.get("pytest") or {}).get("status"),
                "validate_project": (evidence.get("validate_project") or {}).get("status"),
                "ui_build": (evidence.get("ui_build") or {}).get("status"),
                "browser_acceptance": (evidence.get("browser") or {}).get("status"),
                "cross_genre_e2e": (evidence.get("e2e") or {}).get("status"),
                "crash_resume": (evidence.get("crash_resume") or {}).get("status"),
                "capability_matrix": matrix.get("status"),
                "capability_count": matrix.get("capability_count"),
            },
            "truth_digests": {
                "canon": truth.get("canon"),
                "story_state": truth.get("story_state"),
                "legacy": truth.get("legacy"),
                "source_ir": truth.get("chapter_ir"),
                "historical_foundation": truth.get("historical_foundation"),
            },
            "frozen_source_digests": dict(FROZEN_SOURCE_DIGESTS),
            "frozen_foundation_digests": dict(FROZEN_FOUNDATION_DIGESTS),
            "frozen_digests": {"contract": frozen.get("contract"),
                               "repair_gate": frozen.get("repair_gate")},
            "blocking_debt": 0,
            "non_blocking_debt": [{"debt_id": key, "classification": value}
                                  for key, value in sorted(debt.items())],
            "next_state": freeze.get("next_state"),
            "future_work": {
                "m19_created": False,
                "product_v3_executed": False,
                "rule": ("产品 V2 已 frozen：任何新产品需求必须作为独立 initiative / "
                         "Product V3 planning 立项，配独立 scope 与 acceptance。"),
            },
            "notes": [
                "M19 未创建；后续新产品需求必须作为独立 initiative / Product V3 planning 立项，"
                "配独立 scope 与 acceptance。",
                "本 manifest 为 deterministic：重复生成内容一致（仅依赖 frozen 输入、验收 evidence "
                "与当前 HEAD）；release 后如需重放，须在 release commit 上重新生成。",
            ],
            "read_only": True, "non_authoritative": True,
        }
        _write_json(self.out_dir / RELEASE_FILE, payload)
        return payload


__all__ = [
    "ACCEPTANCE_FILE", "ARCHITECTURE_FILE", "BASELINE_FILE", "CAPABILITIES",
    "CAPABILITY_FILE", "DOCS_FILE", "FINAL_ACCEPTANCE_CRITERIA", "FREEZE_FILE",
    "M18_DIR", "M18FinalAcceptanceService", "RELEASE_DATE", "RELEASE_FILE",
    "RELEASE_TAG", "TEST_EVIDENCE_FILE",
]
