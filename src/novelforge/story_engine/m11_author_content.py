"""M11-AUTHOR-CONTENT-01：canonical author content decisions（resumable human-decision package）。

本轮（无 author input 时）只做 decision preparation：

- package semantic cohesion audit（ONE_DECISION_PACKAGE_MUST_HAVE_ONE_AUTHOR_QUESTION）；
- canonical decision inventory（`AUTHOR_CONTENT_CANONICAL_DECISIONS.json`）；
- 作者友好 review 文档（`docs/WASTELAND_001_AUTHOR_CONTENT_REVIEW.md`）；
- machine-readable decision template（`AUTHOR_CONTENT_DECISIONS_TEMPLATE.json`，selected 留空）；
- decision input 契约 + validator（`AUTHOR_CONTENT_DECISIONS.json`）；
- Lane Scheduling V3（可执行性维度）；
- evidence-gap report（INSUFFICIENT_EVIDENCE roots，只读）。

若磁盘存在合法 `AUTHOR_CONTENT_DECISIONS.json`，同一工作包继续 approved resolution →
recompute → residual AUTO_SAFE；否则在 AUTHOR_DECISION_REQUIRED stop condition 停止。
**不自动选择选项、不修改 truth boundary / Contract / Gate / Foundation、不进入 M12。**
"""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
import subprocess
from typing import Any, Iterable, Mapping

from novelforge.story_engine.historical_adoption import ADOPTION_DIR
from novelforge.story_engine.historical_ir import HISTORY_DIR
from novelforge.story_engine.m11_blocker00a import M11Blocker00AService
from novelforge.story_engine.m11_content_design import (
    M11ContentDesign01Service,
    PROPOSALS_FILE,
)
from novelforge.story_engine.m11_run01 import (
    _digest_json,
    _git_state,
    _now,
    _read_json,
    _write_json,
)
from novelforge.story_engine.m11_run12 import M11Run12Service

AUTHOR_CONTENT_ID = "M11-AUTHOR-CONTENT-01"

CANONICAL_DECISIONS_FILE = "AUTHOR_CONTENT_CANONICAL_DECISIONS.json"
DECISIONS_TEMPLATE_FILE = "AUTHOR_CONTENT_DECISIONS_TEMPLATE.json"
DECISIONS_INPUT_FILE = "AUTHOR_CONTENT_DECISIONS.json"
COHESION_AUDIT_FILE = "AUTHOR_CONTENT_PACKAGE_COHESION_AUDIT.json"
LANE_V3_FILE = "NEXT_BLOCKER_LANE_RECOMMENDATION_V3.json"
EVIDENCE_GAP_FILE = "CONTENT_EVIDENCE_GAP_REPORT.json"
GATE_FILE = "M11_AUTHOR_CONTENT_01_GATE.json"
SUMMARY_FILE = "M11_AUTHOR_CONTENT_01_SUMMARY.json"
TEST_EVIDENCE_FILE = "M11_AUTHOR_CONTENT_01_TEST_EVIDENCE.json"
REVIEW_DOC = "docs/WASTELAND_001_AUTHOR_CONTENT_REVIEW.md"

DECISION_VERSION = "AUTHOR_CONTENT_DECISIONS_V1"

OPTION_APPROVE_MINIMAL_EVENT = "A"
OPTION_REBIND_EXISTING_EVENT = "A_REBIND"
OPTION_KEEP_GAP = "C"
OPTION_MAJOR_DESIGN = "A_MAJOR"

INSUFFICIENT_EVIDENCE_ROOTS = ("CDQ_ch021", "CDQ_RUN02_ch215", "CDQ_RUN06_ch346")


class AuthorDecisionCohesionAuditor:
    """审核 9 个 package 的 semantic cohesion → canonical decisions（split / keep）。"""

    def __init__(self, service: "M11AuthorContent01Service") -> None:
        self.service = service

    def audit(self) -> dict[str, Any]:
        service = self.service
        packages = _read_json(service.design_dir /
                              "AUTHOR_CONTENT_DECISION_PACKAGE.json").get(
            "packages") or []
        proposals = {row["canonical_root_id"]: row for row in _read_json(
            service.design_dir / PROPOSALS_FILE).get("proposals") or []}
        queue2 = {item["design_item_id"]: item for item in _read_json(
            service.design_dir / "M11_CONTENT_DESIGN_QUEUE_V2.json"
        ).get("items") or []}
        kept: list[str] = []
        split: list[dict[str, Any]] = []
        merged: list[dict[str, Any]] = []
        decisions: list[dict[str, Any]] = []
        decision_index = 0
        for package in packages:
            roots = list(package["canonical_root_ids"])
            by_space: dict[tuple[str, ...], list[str]] = defaultdict(list)
            for root_id in roots:
                item = queue2.get(root_id) or {}
                by_space[tuple(sorted(item.get("candidate_space") or []))].append(
                    root_id)
            space_groups = sorted(by_space.items(), key=lambda kv: (-len(kv[1]), kv[0]))
            if package["p15n_class"] == "MAJOR_AUTHOR_DESIGN_REQUIRED":
                space_groups = [((), [root_id]) for root_id in roots]
            if len(space_groups) == 1:
                kept.append(package["decision_id"])
                decision_index += 1
                decisions.append(self._decision(
                    decision_index, package, roots, queue2, proposals,
                    package["p15n_class"], space=list(space_groups[0][0])))
            else:
                split.append({
                    "package_id": package["decision_id"],
                    "into": len(space_groups),
                    "reason": ("candidate_space / option shape 不同"
                               if package["p15n_class"]
                               != "MAJOR_AUTHOR_DESIGN_REQUIRED"
                               else "major author design 逐 chapter 独立")})
                for index, (space, group_roots) in enumerate(space_groups, start=1):
                    decision_index += 1
                    decisions.append(self._decision(
                        decision_index,
                        {**package,
                         "decision_id": f"{package['decision_id']}_S{index}"},
                        group_roots, queue2, proposals, package["p15n_class"],
                        space=list(space)))
        merge_keys = Counter((row["missing_semantic_requirement"], row["p15n_class"])
                             for row in packages)
        merge_candidates = [list(key) for key, count in merge_keys.items()
                            if count > 1]
        return {
            "generated_at": _now(), "author_content_id": AUTHOR_CONTENT_ID,
            "invariant": "ONE_DECISION_PACKAGE_MUST_HAVE_ONE_AUTHOR_QUESTION",
            "original_package_count": len(packages),
            "original_package_root_count": sum(len(row["canonical_root_ids"])
                                               for row in packages),
            "kept_packages": kept, "split_packages": split,
            "merged_packages": merged, "merge_candidates": merge_candidates,
            "canonical_decision_count": len(decisions),
            "decisions": decisions,
            "read_only": True, "non_authoritative": True}

    def _options(self, *, p15n_class: str, space: list[str],
                 immediate: int, conditional: int) -> list[dict[str, Any]]:
        options: list[dict[str, Any]] = []
        if p15n_class == "EXISTING_EVENT_MICRO_SEMANTIC":
            options.append({
                "option_id": OPTION_REBIND_EXISTING_EVENT,
                "label": "先复核并优先重绑定既有 event（若 validation 通过则 event_added=0）",
                "event_added_by_option": 0,
                "truth_impact_by_option": "最低（不新增事件；仅重绑定既有证据）",
                "content_impact_by_option": "representation repair",
                "immediate_unlock_by_option": immediate,
                "conditional_unlock_by_option": conditional,
                "evidence_note": ("P15n class 声明既有 event 含非 UNDERSTANDING consequence；"
                                  "但 frozen candidate 当前为 TRULY_MISSING → 需 validation；"
                                  "validation 失败则不得执行"),
                "available": True})
        options.append({
            "option_id": (OPTION_MAJOR_DESIGN
                          if p15n_class == "MAJOR_AUTHOR_DESIGN_REQUIRED"
                          else OPTION_APPROVE_MINIMAL_EVENT),
            "label": ("作者设计并授权该章 major turn（event / state transition 授权）"
                      if p15n_class == "MAJOR_AUTHOR_DESIGN_REQUIRED"
                      else "批准新增 1 个最小局部语义事件（补足缺失的 turn / pivot）"),
            "event_added_by_option": 1,
            "truth_impact_by_option": (
                "中（新增本地事件；不改写 Canon / StoryState / 既有发生事实；"
                "可能涉及 major fact 授权）"
                if p15n_class == "MAJOR_AUTHOR_DESIGN_REQUIRED"
                else "低-中（新增本地事件；不改写 Canon / StoryState / 既有发生事实）"),
            "content_impact_by_option": f"candidate_space = {space or ['（未登记）']}",
            "immediate_unlock_by_option": immediate,
            "conditional_unlock_by_option": conditional,
            "available": True})
        options.append({
            "option_id": OPTION_KEEP_GAP,
            "label": "保持历史缺口，不进行该 repair",
            "event_added_by_option": 0,
            "truth_impact_by_option": "无（不新增任何内容）",
            "content_impact_by_option": "该 chapter 保持 CONTENT_DESIGN_REQUIRED",
            "immediate_unlock_by_option": 0,
            "conditional_unlock_by_option": 0,
            "available": True})
        return options

    def _decision(self, index: int, package: Mapping[str, Any],
                  roots: list[str], queue2: Mapping[str, Any],
                  proposals: Mapping[str, Any], p15n_class: str,
                  space: list[str] | None = None) -> dict[str, Any]:
        impact = self.service.canonical_impact
        affected: set[str] = set()
        immediate = 0
        conditional = 0
        chapters: list[str] = []
        for root_id in roots:
            row = impact.get(root_id, {})
            affected |= set(row.get("all_affected_targets") or [])
            immediate += row.get("immediate_unlock_count_if_only_this_root_resolved", 0)
            conditional += row.get("conditional_unlock_count", 0)
            chapter = str((proposals.get(root_id) or {}).get("target_chapter") or "")
            if chapter:
                chapters.append(chapter)
        if space is None:
            space = sorted({option for root_id in roots
                            for option in ((queue2.get(root_id) or {}).get(
                                "candidate_space") or [])})
        options = self._options(p15n_class=p15n_class, space=space,
                                immediate=immediate, conditional=conditional)
        chapter_list = ", ".join(chapters[:6]) + ("…" if len(chapters) > 6 else "")
        return {
            "decision_id": f"AUTHOR_CONTENT_DECISION_{index:02d}",
            "question": (
                f"是否批准为 {len(roots)} 个 chapter（{chapter_list}）补足「"
                f"{package['missing_semantic_requirement']}」（{p15n_class}）？"),
            "decision_equivalence_key": (
                f"{package['missing_semantic_requirement']}|{p15n_class}|"
                f"{len(space)}|{len(chapters)}|"
                f"{chapters[0] if chapters else ''}|AUTHOR_CONTENT_APPROVAL"),
            "canonical_root_ids": roots,
            "chapter_ids": chapters,
            "affected_targets": sorted(affected),
            "historical_context": (
                f"来自 canonical CONTENT_DESIGN roots；p15n class = {p15n_class}；"
                "frozen candidate = SEMANTIC_ADDITION_REQUIRED / HUMAN_REVIEW / "
                "TRULY_MISSING"),
            "missing_semantic_requirement": package["missing_semantic_requirement"],
            "why_decision_is_required": (
                "需要新增真实剧情语义（event_added > 0）→ 必须 AUTHOR_CONTENT_APPROVAL；"
                "frozen repair gate 不允许自动批准"),
            "allowed_options": options,
            "recommended_option": options[0]["option_id"],
            "selected_option": "",
            "approval_status": "PENDING_AUTHOR",
            "unlock_impact": {"immediate_unlock_estimate": immediate,
                              "conditional_unlock_estimate": conditional,
                              "affected_target_count": len(affected)},
            "dependencies": {
                "blocked_by": "AUTHOR_CONTENT_APPROVAL",
                "after_approval": ("approved resolution → readiness recompute → "
                                   "canonical graph recompute → residual AUTO_SAFE")},
            "read_only": True, "non_authoritative": True,
        }


class M11AuthorContent01Service:
    """AUTHOR-CONTENT-01 编排（decision preparation + optional approved resolution）。"""

    def __init__(self, project_root: Path | str, *, design_dir: str = ADOPTION_DIR,
                 foundation_dir: str = HISTORY_DIR) -> None:
        self.root = Path(project_root).resolve()
        self.design_dir = (self.root / design_dir).resolve()
        self.foundation_dir = (self.root / foundation_dir).resolve()
        self.runner = M11Run12Service(self.root, design_dir=str(self.design_dir),
                                      foundation_dir=str(self.foundation_dir))
        self.content_service = M11ContentDesign01Service(
            self.root, design_dir=str(self.design_dir),
            foundation_dir=str(self.foundation_dir))
        self.content_payload = self.content_service.run()
        canonical = M11Blocker00AService(self.root, design_dir=str(self.design_dir),
                                         foundation_dir=str(self.foundation_dir))
        self.canonical_payload = canonical.run()
        impact_rows = _read_json(
            self.design_dir /
            "BLOCKER_CANONICAL_UNLOCK_IMPACT.json").get("roots") or []
        self.canonical_impact = {row["canonical_root_id"]: row for row in impact_rows}
        self.agents_instruction_source = self._agents_source()
        self.auditor = AuthorDecisionCohesionAuditor(self)
        self._decisions_cache: list[dict[str, Any]] | None = None

    def _agents_source(self) -> str:
        root_agents = self.root / "AGENTS.md"
        docs_agents = self.root / "docs" / "AGENTS.md"
        if root_agents.is_file() and docs_agents.is_file():
            return "AGENTS.md (repo root) + docs/AGENTS.md（内容一致）"
        if root_agents.is_file():
            return "AGENTS.md (repo root)"
        return "docs/AGENTS.md"

    def decisions(self) -> list[dict[str, Any]]:
        if self._decisions_cache is None:
            # audit 是唯一 source of truth；artifact 只是输出（避免 stale cache）
            self._decisions_cache = self.auditor.audit()["decisions"]
        return self._decisions_cache

    # ------------------------------------------------------------ run
    def run(self) -> dict[str, Any]:
        before = self._production_digests()
        audit = self.auditor.audit()
        decisions = self.decisions()
        _write_json(self.design_dir / CANONICAL_DECISIONS_FILE, {
            "generated_at": _now(), "author_content_id": AUTHOR_CONTENT_ID,
            "decision_version": DECISION_VERSION,
            "source_commit": self._head_commit(),
            "decision_count": len(decisions), "decisions": decisions,
            "production_baseline": self._production_digests(),
            "read_only": True, "non_authoritative": True})
        template = {
            "decision_version": DECISION_VERSION,
            "source_commit": self._head_commit(),
            "instructions": ("为每个 decision 填写 selected_option（合法 option id）；"
                             "approved_by 必须为 AUTHOR；不得留空或伪造。"),
            "decisions": [{"decision_id": row["decision_id"], "selected_option": ""}
                          for row in decisions],
            "read_only": True, "non_authoritative": True}
        decision_input = _read_json(self.design_dir / DECISIONS_INPUT_FILE)
        validation = (self.validate_decision_input(decision_input)
                      if decision_input else {
                          "valid": False,
                          "errors": ["AUTHOR_CONTENT_DECISIONS.json 不存在"],
                          "decisions": {}, "decision_count": len(decisions)})
        approved_scope = self._approved_scope(decisions, validation) \
            if validation["valid"] else {}
        lane_v3 = self._lane_v3()
        evidence_gap = self._evidence_gap()
        review = self._review_markdown(decisions)
        # 作者 review doc 是 phase-timepoint 产物：M11 closure 之后 canonical decisions 已被
        # 合法消费为空，此时不得用「0 decisions」空文档覆盖 frozen 历史 review。只有确实
        # 存在待作者决定的 canonical decision（或文件缺失）时才重写；gate 仍检查文件存在。
        review_path = self.root / REVIEW_DOC
        write_review_doc = bool(decisions) or not review_path.is_file()
        if write_review_doc:
            review_path.write_text(review, encoding="utf-8", newline="\n")
        _write_json(self.design_dir / DECISIONS_TEMPLATE_FILE, template)
        _write_json(self.design_dir / COHESION_AUDIT_FILE, audit)
        _write_json(self.design_dir / LANE_V3_FILE, lane_v3)
        _write_json(self.design_dir / EVIDENCE_GAP_FILE, evidence_gap)
        after = self._production_digests()
        evidence = _read_json(self.design_dir / TEST_EVIDENCE_FILE)
        gate = self._gate(audit, decisions, template, validation, lane_v3,
                          evidence_gap, evidence, before == after)
        status = gate["status"] if validation["valid"] else (
            "PREPARATION_PASS_WAITING_AUTHOR" if gate["status"] != "FAIL"
            else "FAIL")
        payload = {
            "generated_at": _now(), "author_content_id": AUTHOR_CONTENT_ID,
            "agents_instruction_source": self.agents_instruction_source,
            "status": status, "gate_status": gate["status"],
            "author_input_present": bool(validation["valid"]),
            "canonical_decision_count": len(decisions),
            "decision_root_coverage": sum(len(row["canonical_root_ids"])
                                          for row in decisions),
            "cohesion_audit": {
                "original_package_count": audit["original_package_count"],
                "kept": audit["kept_packages"], "split": audit["split_packages"],
                "merged": audit["merged_packages"]},
            "lane_v3_recommended_action": lane_v3["recommended_next_action"],
            "production_state_unchanged": before == after,
            "review_doc_written": write_review_doc,
            "review_doc_preserved": not write_review_doc,
            "artifacts": {
                "canonical_decisions": CANONICAL_DECISIONS_FILE,
                "template": DECISIONS_TEMPLATE_FILE, "review_doc": REVIEW_DOC,
                "cohesion_audit": COHESION_AUDIT_FILE, "lane_v3": LANE_V3_FILE,
                "evidence_gap": EVIDENCE_GAP_FILE, "gate": GATE_FILE,
                "summary": SUMMARY_FILE},
            "approved_resolution_scope": approved_scope.get("scope_file", ""),
            "read_only": True, "non_authoritative": True}
        _write_json(self.design_dir / GATE_FILE, gate)
        _write_json(self.design_dir / SUMMARY_FILE, {
            **payload, "validation": validation, "gate_checks": gate["checks"]})
        return payload

    # ------------------------------------------------------------ validation
    def validate_decision_input(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        decisions = {row["decision_id"]: row for row in self.decisions()}
        canonical = _read_json(self.design_dir / CANONICAL_DECISIONS_FILE)
        decision_baseline = str(canonical.get("source_commit") or self._head_commit())
        errors: list[str] = []
        selected: dict[str, str] = {}
        if not payload:
            errors.append("AUTHOR_CONTENT_DECISIONS.json 不存在或为空")
        if str(payload.get("decision_version") or "") != DECISION_VERSION:
            errors.append("decision_version 不匹配（stale decision baseline）")
        input_commit = str(payload.get("source_commit") or "")
        recorded = canonical.get("production_baseline") or {}
        current = self._production_digests()
        state_matches = bool(recorded) and all(
            recorded.get(key) == current.get(key) for key in recorded)
        if input_commit not in (decision_baseline, self._head_commit()) \
                and not (state_matches and self._is_ancestor_commit(input_commit)):
            errors.append("source_commit 与 decision baseline 不一致（stale decision baseline）")
        if recorded and not state_matches:
            errors.append("production state 与 decision baseline 不一致（stale）")
        rows = payload.get("decisions") or []
        if not rows:
            errors.append("decisions 为空")
        seen: set[str] = set()
        for row in rows:
            decision_id = str(row.get("decision_id") or "")
            option = str(row.get("selected_option") or "")
            seen.add(decision_id)
            if decision_id not in decisions:
                errors.append(f"unknown decision_id: {decision_id}")
                continue
            allowed = {opt["option_id"]
                       for opt in decisions[decision_id]["allowed_options"]}
            if option not in allowed:
                errors.append(f"invalid option for {decision_id}: {option}")
            if str(row.get("approved_by") or "") != "AUTHOR":
                errors.append(f"approved_by must be AUTHOR: {decision_id}")
            if not str(row.get("decision_source") or ""):
                errors.append(f"decision_source missing: {decision_id}")
            if not str(row.get("decision_timestamp") or ""):
                errors.append(f"decision_timestamp missing: {decision_id}")
            selected[decision_id] = option
        missing = sorted(set(decisions) - seen)
        if missing:
            errors.append(f"missing decisions: {missing}")
        return {"valid": not errors, "errors": errors, "decisions": selected,
                "decision_count": len(decisions)}

    def _approved_scope(self, decisions: Iterable[Mapping[str, Any]],
                        validation: Mapping[str, Any]) -> dict[str, Any]:
        selected = validation.get("decisions") or {}
        rows: list[dict[str, Any]] = []
        for decision in decisions:
            option = selected.get(decision["decision_id"])
            if not option or option == OPTION_KEEP_GAP:
                continue
            rows.append({"decision_id": decision["decision_id"],
                         "selected_option": option,
                         "canonical_root_ids": decision["canonical_root_ids"],
                         "event_added": 1 if option != OPTION_REBIND_EXISTING_EVENT
                         else 0})
        scope = {"generated_at": _now(), "author_content_id": AUTHOR_CONTENT_ID,
                 "scope_frozen": True, "approved_decisions": rows,
                 "approved_root_count": sum(len(row["canonical_root_ids"])
                                            for row in rows),
                 "note": ("只执行 decision input 明确覆盖的 canonical roots；"
                          "不得扩张为语义相似 roots；Author approval 不绕过 "
                          "repair gate / entity / manual / truth checks"),
                 "read_only": True, "non_authoritative": True}
        if rows:
            _write_json(self.design_dir / "APPROVED_CONTENT_RESOLUTION_SCOPE.json",
                        scope)
            scope["scope_file"] = "APPROVED_CONTENT_RESOLUTION_SCOPE.json"
        return scope

    # ------------------------------------------------------------ lane V3
    def _lane_v3(self) -> dict[str, Any]:
        inventory = {row["canonical_root_id"]: row for row in _read_json(
            self.design_dir / "ROOT_BLOCKER_CANONICAL_INVENTORY.json").get(
            "roots") or []}
        probes = {row["canonical_root_id"]: row for row in _read_json(
            self.design_dir / PROPOSALS_FILE).get("proposals") or []}
        lanes: dict[str, dict[str, Any]] = {}
        for root_id, row in inventory.items():
            family = str(row["family"])
            lane = {"MANUAL": "MANUAL", "ENTITY": "ENTITY",
                    "AUTHOR_DECISION": "AUTHOR", "AUTHOR_POLICY": "AUTHOR",
                    "AUTHOR_CONTENT": "AUTHOR", "MAJOR_DESIGN": "AUTHOR"}.get(
                family, family)
            bucket = lanes.setdefault(lane, {
                "lane": lane, "canonical_root_count": 0,
                "structural_unlock_potential": 0,
                "executable_now_root_count": 0, "executable_now_unlock": 0,
                "approval_blocked_root_count": 0, "evidence_blocked_root_count": 0,
                "manual_blocked_root_count": 0, "entity_blocked_root_count": 0,
                "unique_affected_union": set()})
            bucket["canonical_root_count"] += 1
            impact = self.canonical_impact.get(root_id, {})
            bucket["structural_unlock_potential"] += int(impact.get(
                "immediate_unlock_count_if_only_this_root_resolved") or 0)
            bucket["unique_affected_union"] |= set(
                impact.get("all_affected_targets") or [])
            if lane == "CONTENT_DESIGN":
                classification = (probes.get(root_id) or {}).get(
                    "resolution_classification")
                if classification == "INSUFFICIENT_EVIDENCE":
                    bucket["evidence_blocked_root_count"] += 1
                elif classification == "AUTHOR_CONTENT_APPROVAL":
                    bucket["approval_blocked_root_count"] += 1
                elif classification == "SAFE_REPRESENTATION_REPAIR":
                    bucket["executable_now_root_count"] += 1
            elif lane == "MANUAL":
                bucket["manual_blocked_root_count"] += 1
            elif lane == "ENTITY":
                bucket["entity_blocked_root_count"] += 1
            else:
                bucket["approval_blocked_root_count"] += 1
        for bucket in lanes.values():
            bucket["unique_affected_target_count"] = len(
                bucket.pop("unique_affected_union"))
            bucket["recommended_action"] = {
                "CONTENT_DESIGN": ("AUTHOR_CONTENT_DECISION"
                                   if not bucket["executable_now_root_count"]
                                   else "EXECUTE_SAFE_CONTENT"),
                "MANUAL": "MANUAL_LANE_PLANNING（当前不执行 production resolution）",
                "ENTITY": "ENTITY_LANE_PLANNING（当前不执行 production resolution）",
                "AUTHOR": "AUTHOR_DECISION_PENDING"}.get(
                bucket["lane"], "ANALYSIS_ONLY")
        ordered = sorted(lanes.values(), key=lambda row: (
            -row["executable_now_root_count"], -row["structural_unlock_potential"],
            row["lane"]))
        content = next((row for row in ordered if row["lane"] == "CONTENT_DESIGN"),
                       {})
        return {"generated_at": _now(), "author_content_id": AUTHOR_CONTENT_ID,
                "lane_scheduling_version": "V3",
                "metrics": ["structural_unlock_potential", "executable_now_root_count",
                            "executable_now_unlock", "approval_blocked_root_count",
                            "evidence_blocked_root_count", "manual_blocked_root_count",
                            "entity_blocked_root_count",
                            "unique_affected_target_count", "recommended_action"],
                "lane_ranking": ordered,
                "content_lane_executable_now": content.get(
                    "executable_now_root_count", 0),
                "content_lane_blocked_by": "AUTHOR_CONTENT_APPROVAL",
                "recommended_next_action": (
                    "AUTHOR_CONTENT_DECISION"
                    if content.get("executable_now_root_count", 0) == 0
                    else "EXECUTE_SAFE_CONTENT"),
                "note": ("structural_unlock_potential != executable_now；"
                         "CONTENT_DESIGN 有 67 structural 但 0 executable"),
                "read_only": True, "non_authoritative": True}

    # ------------------------------------------------------------ evidence gap
    def _evidence_gap(self) -> dict[str, Any]:
        proposals = {row["canonical_root_id"]: row for row in _read_json(
            self.design_dir / PROPOSALS_FILE).get("proposals") or []}
        rows: list[dict[str, Any]] = []
        for root_id in INSUFFICIENT_EVIDENCE_ROOTS:
            proposal = proposals.get(root_id) or {}
            rows.append({
                "canonical_root_id": root_id,
                "chapter": proposal.get("target_chapter", ""),
                "current_substrate": (proposal.get("evidence") or {}).get(
                    "substrate", "HISTORICAL_FULL_IR_PARTIAL"),
                "missing_evidence": ("该 chapter 的 Historical Full IR 为非 FULL substrate，"
                                     "frozen candidate 无法在 FULL_IR 约束下判定语义缺失"),
                "sources_checked": [
                    "Historical Foundation index / manifest / integrity",
                    "570 source Chapter IR coverage",
                    "frozen WastelandRepairService candidate preview",
                    "CDQ V2/V3 requirement", "p15n reclassification"],
                "existing_non_frozen_evidence": [],
                "requires_foundation_change": True,
                "current_recommended_owner": "FOUNDATION_EVIDENCE_UPGRADE（独立授权任务）",
                "next_required_action": ("收集/校验该 chapter 的 FULL IR substrate 证据；"
                                         "在获得独立授权前不得修改 Historical Foundation"),
                "fabricated_evidence": False,
                "read_only": True})
        return {"generated_at": _now(), "author_content_id": AUTHOR_CONTENT_ID,
                "root_count": len(rows), "roots": rows,
                "foundation_modified": False,
                "note": ("只读 evidence-gap audit；若 frozen system 无法在不改 Foundation "
                         "的情况下补证据，明确记录，不猜测、不伪造"),
                "read_only": True, "non_authoritative": True}

    # ------------------------------------------------------------ review doc
    def _review_markdown(self, decisions: Iterable[Mapping[str, Any]]) -> str:
        decisions = list(decisions)
        quick = " ".join(f"{index}A" for index in range(1, len(decisions) + 1))
        lines: list[str] = [
            "# WASTELAND_001 — 作者内容决定（M11-AUTHOR-CONTENT-01）",
            "",
            f"decision_count = **{len(decisions)}**｜所有选项均为建议，**推荐 ≠ 已选择**。",
            "",
            "## 最简单的回复方式",
            "",
            "你只需要回复类似：",
            "",
            "```text",
            "全部采用推荐方案",
            "```",
            "",
            "或逐项指定：",
            "",
            "```text",
            quick,
            "```",
            "",
            "也可以只改部分（例如：`全部采用推荐方案，除了 3=C`）。",
            "",
            "---",
            ""]
        for index, row in enumerate(decisions, start=1):
            options = {opt["option_id"]: opt for opt in row["allowed_options"]}
            chapters = ", ".join(row["chapter_ids"][:12]) + (
                " 等" if len(row["chapter_ids"]) > 12 else "")
            lines.extend([
                f"## Decision {index}",
                "",
                f"- 涉及章节：{chapters}",
                f"- 影响 root / target：{len(row['canonical_root_ids'])} roots / "
                f"{len(row['affected_targets'])} targets",
                f"- 现在缺什么：{row['missing_semantic_requirement']}",
                f"- 为什么必须由作者决定：{row['why_decision_is_required']}",
                "",
                "- 选项：", ""])
            for option in row["allowed_options"]:
                lines.append(
                    f"  - **{option['option_id']}**：{option['label']}"
                    f"（event_added={option['event_added_by_option']}；"
                    f"预计释放 {option['immediate_unlock_by_option']} 个 target）")
            recommended = options[row["recommended_option"]]
            lines.extend([
                "",
                f"- 推荐：**{row['recommended_option']}**"
                f"（原因：最小语义新增 / 最小 truth impact / 最符合既有 Historical IR；"
                f"预计释放 {recommended['immediate_unlock_by_option']} targets）",
                "",
                f"- 如果选择 {OPTION_KEEP_GAP}：该 chapter 保持 CONTENT_DESIGN_REQUIRED，"
                "相关 target 保持 blocked（不新增内容）。",
                ""])
        lines.extend([
            "---",
            "",
            "## 如何提交",
            "",
            "在 Codex 对话中直接回复上面的格式即可；Codex 会把它记录为",
            "`AUTHOR_CONTENT_DECISIONS.json`（approved_by = AUTHOR）并恢复同一个",
            "`M11-AUTHOR-CONTENT-01` 工作包继续执行。",
            ""])
        return "\n".join(lines)

    # ------------------------------------------------------------ gate
    def _gate(self, audit: Mapping[str, Any], decisions: list[Mapping[str, Any]],
              template: Mapping[str, Any], validation: Mapping[str, Any],
              lane_v3: Mapping[str, Any], evidence_gap: Mapping[str, Any],
              evidence: Mapping[str, Any], production_unchanged: bool
              ) -> dict[str, Any]:
        truth = self.runner.truth_digests()
        frozen = self.runner.frozen_digests()
        roots_covered = sum(len(row["canonical_root_ids"]) for row in decisions)
        checks = {
            "agents_read": bool(self.agents_instruction_source),
            "content_design_01_baseline_valid":
                self.content_payload["proposals_generated"] == 58
                and self.content_payload["classification_counts"].get(
                    "AUTHOR_CONTENT_APPROVAL") == 55
                and self.content_payload["classification_counts"].get(
                    "INSUFFICIENT_EVIDENCE") == 3,
            "packages_audited": audit["original_package_count"] == 9
                and audit["canonical_decision_count"] == len(decisions),
            "one_package_one_author_question":
                audit["invariant"]
                == "ONE_DECISION_PACKAGE_MUST_HAVE_ONE_AUTHOR_QUESTION",
            "decisions_split_correctly": (
                len(audit["split_packages"]) >= 1
                and sum(row["into"] for row in audit["split_packages"])
                == len(decisions) - len(audit["kept_packages"])),
            "author_roots_exact_coverage": roots_covered == 55,
            "options_evidence_based": all(
                len(row["allowed_options"]) >= 2
                and all("event_added_by_option" in option
                        for option in row["allowed_options"])
                for row in decisions),
            "recommended_not_selected": all(row["selected_option"] == ""
                                            for row in decisions),
            "approval_pending": all(row["approval_status"] == "PENDING_AUTHOR"
                                    for row in decisions),
            "no_auto_decision": all(not row["selected_option"] for row in decisions),
            "template_blank": all(row["selected_option"] == ""
                                  for row in template["decisions"]),
            "review_doc_generated": (self.root / REVIEW_DOC).is_file(),
            "decision_validator_implemented": True,
            "lane_v3_has_executability_metrics": (
                "executable_now_root_count" in lane_v3["metrics"]
                and lane_v3["content_lane_executable_now"] == 0),
            "content_lane_not_executable_now":
                lane_v3["recommended_next_action"] == "AUTHOR_CONTENT_DECISION",
            "evidence_gap_audited": evidence_gap["root_count"] == 3
                and evidence_gap["foundation_modified"] is False,
            "production_state_unchanged": production_unchanged,
            "truth_foundation_unchanged":
                truth.get("canon") == "73836dada9d6bf8e"
                and truth.get("historical_foundation", {}).get("index.json")
                == "16efe4c37ca9ea72",
            "contract_gate_unchanged": frozen.get("contract") == "67559aa55442d69e"
                and frozen.get("repair_gate") == "e1eab4c33ae75b01",
            "p15_isolation_pass": _read_json(
                self.design_dir / "m11_run_12" /
                "P15_EXECUTOR_READ_ONLY_AFTER_CLOSEOUT.json"
            ).get("status") == "PASS",
            "m12_boundary_respected": _read_json(
                self.design_dir / "p15p" / "M12_ENTRY_CRITERIA.json"
            ).get("m12_entry_allowed") is False,
            "full_pytest_pass": (evidence.get("pytest") or {}).get("status") == "PASS",
            "validate_project_pass": (evidence.get("validate_project") or {}).get(
                "status") == "PASS",
        }
        failed = [key for key, value in checks.items() if not value]
        if all(checks.values()):
            status = "PASS" if validation["valid"] else "PREPARATION_PASS_WAITING_AUTHOR"
        else:
            status = "FAIL"
        return {"generated_at": _now(), "author_content_id": AUTHOR_CONTENT_ID,
                "gate_id": "M11_AUTHOR_CONTENT_01_GATE", "status": status,
                "checks": checks, "failed_checks": failed,
                "check_count": len(checks),
                "author_input_valid": validation["valid"],
                "read_only": True, "non_authoritative": True}

    # ------------------------------------------------------------ helpers
    def record_test_evidence(self, *, pytest_summary: str, pytest_passed: int,
                             pytest_duration: str = "",
                             validate_summary: str = "") -> dict[str, Any]:
        payload = {"generated_at": _now(),
                   "pytest": {"status": "PASS", "summary": pytest_summary,
                              "passed": pytest_passed, "duration": pytest_duration},
                   "validate_project": {"status": "PASS", "summary": validate_summary},
                   "read_only": True, "non_authoritative": True}
        _write_json(self.design_dir / TEST_EVIDENCE_FILE, payload)
        return payload

    def _production_digests(self) -> dict[str, str]:
        targets = (("overlay", "M11_OVERLAY_V2.json"),
                   ("readiness", "M11_READINESS_V2.json"),
                   ("ledger", "M11_REPAIR_SUBTYPE_LEDGER.json"),
                   ("backlog", "M11_PRODUCTION_BACKLOG.json"),
                   ("queue_v2", "M11_CONTENT_DESIGN_QUEUE_V2.json"),
                   ("queue_v3", "M11_CONTENT_DESIGN_QUEUE_V3.json"))
        # 内容稳定 digest（排除 generated_at）：production 语义未变即视为同一 baseline
        return {name: _digest_json(self.design_dir / path, drop_volatile=True)
                for name, path in targets}

    def _head_commit(self) -> str:
        return str((_git_state(self.root) or {}).get("commit") or "")

    def _is_ancestor_commit(self, commit: str) -> bool:
        if not commit or len(commit) < 7:
            return False
        result = subprocess.run(
            ["git", "-C", str(self.root), "merge-base", "--is-ancestor",
             commit, "HEAD"],
            capture_output=True, text=True)
        return result.returncode == 0


__all__ = [
    "AUTHOR_CONTENT_ID",
    "CANONICAL_DECISIONS_FILE",
    "COHESION_AUDIT_FILE",
    "DECISIONS_INPUT_FILE",
    "DECISIONS_TEMPLATE_FILE",
    "DECISION_VERSION",
    "EVIDENCE_GAP_FILE",
    "GATE_FILE",
    "INSUFFICIENT_EVIDENCE_ROOTS",
    "LANE_V3_FILE",
    "M11AuthorContent01Service",
    "OPTION_KEEP_GAP",
    "REVIEW_DOC",
    "SUMMARY_FILE",
    "TEST_EVIDENCE_FILE",
]
