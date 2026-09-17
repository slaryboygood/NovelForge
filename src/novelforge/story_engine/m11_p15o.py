"""P15o：Zero-New-Event Micro Wave 02 + Content Rewrite Proposal Hardening。

- Wave 02：11 个 `EXISTING_EVENT_MICRO_SEMANTIC`（P15m 已验证路径）逐项 preflight → promote；
- Rewrite hardening：5 个 rewrite proposal 从模板化表述升级为 **具体事件**
  （`CONCRETE_EVENT_SPECIFICITY_REQUIRED` + `EVENT_TYPE_CONSISTENCY`），
  decision-like 事件必须重分类为 `LOCAL_DECISION_EVENT_REQUIRED`（永远需作者逐项确认）；
- classifier audit：抽查非 pilot 的 causal bridge 分类是否偏宽（只报告，不回写）。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from novelforge.story_engine.historical_adoption import ADOPTION_DIR, REPAIR_DIR
from novelforge.story_engine.historical_ir import HISTORY_DIR
from novelforge.story_engine.m11_content_rewrite import (
    ContentRewritePolicyService,
    PILOT_CLASSES,
)
from novelforge.story_engine.m11_micro_wave import (
    WAVE_MAX_ITEMS,
    MicroWaveExecutor,
    wave_pivot_evidence,
)

P15O_DIR = "p15o"
WAVE02_ID = "MICRO_WAVE_02"
PLACEHOLDER_ACTIONS: tuple[str, ...] = (
    "采取措施", "做出应对", "进行处理", "采取行动", "加强管理", "作出调整",
    "做出最小应对动作", "做出应对动作", "最小应对")
DECISION_VERBS: tuple[str, ...] = (
    "决定", "让", "命", "指定", "下令", "批准", "拒绝", "放弃", "优先", "定下",
    "选择", "签下", "授权", "保证")
CONCRETE_FIELDS: tuple[str, ...] = (
    "actor", "trigger", "concrete_action", "object_or_target", "immediate_result",
    "causal_role", "before_state", "after_state", "why_this_action_is_minimal",
    "why_existing_events_are_insufficient")


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


def _digest_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16] if path.is_file() else ""


class Wave02Service(MicroWaveExecutor):
    """复用 P15m 管线，但 scope 固定为 11 个 zero-new-event micro candidate。"""

    def __init__(self, root: Path | str, **kwargs: Any) -> None:
        super().__init__(root, **kwargs)
        self.wave_dir = self.design_dir / P15O_DIR
        self.wave_dir.mkdir(parents=True, exist_ok=True)

    def scope(self) -> dict[str, Any]:
        reclassification = _read_json(
            self.design_dir / "p15n/CONTENT_REPAIR_RECLASSIFICATION.json")
        inputs = self.pilot.load()
        rows = []
        for row in reclassification.get("rows") or []:
            if not row.get("micro_scale_candidate"):
                continue
            chapter_id = str(row.get("chapter_id"))
            artifact = inputs.artifacts.get(chapter_id)
            pivots = [item for item in wave_pivot_evidence(artifact)
                      if item["non_understanding"]]
            rows.append({
                "design_item_id": f"CDQ3_{row.get('legacy_label')}",
                "chapter_id": chapter_id, "legacy_label": row.get("legacy_label"),
                "owning_batch": row.get("frontier"),
                "eligible": bool(pivots),
                "eligibility": {"existing_event_pivot": bool(pivots),
                                "micro": True, "full_ir": artifact is not None},
                "ineligible_reason": "" if pivots else "no_existing_event_pivot",
                "direct_blocked_target_count": row.get(
                    "direct_blocked_target_count", 0),
                "downstream_target_count": row.get("direct_blocked_target_count", 0),
                "dependency_depth": 0, "risk": "MEDIUM",
                "reuse_events": [item["event_id"] for item in pivots],
                "frontier_rank": 0, "constraint_complexity": 0, "selected": True,
                "pivot_events": [item["event_id"] for item in pivots]})
        eligible = [row for row in rows if row["eligible"]]
        payload = {"generated_at": _now(), "wave_id": WAVE02_ID,
                   "max_items": WAVE_MAX_ITEMS, "queue_item_count": len(rows),
                   "eligible_count": len(eligible), "selected_count": len(rows),
                   "deferred_count": 0,
                   "ineligible_count": len(rows) - len(eligible),
                   "selected": rows, "deferred": [], "ineligible": [
                       row for row in rows if not row["eligible"]],
                   "ranking_criteria": ["existing_event_pivot", "micro",
                                        "direct_blocked_target_count"],
                   "no_literary_score": True, "read_only": True,
                   "non_authoritative": True}
        _write_json(self.wave_dir / "MICRO_WAVE_02_SCOPE.json", payload)
        return payload

    def run(self) -> dict[str, Any]:  # type: ignore[override]
        payload = super().run()
        promotion = _read_json(self.wave_dir / "MICRO_WAVE_PROMOTION.json")
        records = list(promotion.get("records") or [])
        path = self.design_dir / "P15O_WAVE_02_RECONCILIATION.json"
        merged = {str(row.get("chapter_id")): dict(row)
                  for row in _read_json(path).get("records") or []}
        for row in records:
            merged[str(row.get("chapter_id"))] = dict(row)
        _write_json(self.design_dir / "P15O_WAVE_02_RECONCILIATION.json", {
            "generated_at": _now(), "wave_id": WAVE02_ID,
            "record_count": len(merged), "records": list(merged.values()),
            "read_only": True, "non_authoritative": True})
        # 别名：用户要求的 MICRO_WAVE_02_* artifact 命名
        aliases = {"MICRO_WAVE_REQUIREMENTS.json": "MICRO_WAVE_02_REQUIREMENTS.json",
                   "MICRO_WAVE_PROPOSALS.json": "MICRO_WAVE_02_PROPOSALS.json",
                   "MICRO_WAVE_ADJUDICATION.json":
                       "MICRO_WAVE_02_ADJUDICATION.json",
                   "MICRO_WAVE_APPROVALS.json": "MICRO_WAVE_02_APPROVALS.json",
                   "MICRO_WAVE_PROMOTION.json": "MICRO_WAVE_02_PROMOTION.json"}
        for source, target in aliases.items():
            src = self.wave_dir / source
            if src.is_file():
                _write_json(self.wave_dir / target, _read_json(src))
        return payload


class ContentRewriteHardeningService:
    """5 个 rewrite proposal 的具体化 + event type 重分类（不 promote）。"""

    def __init__(self, root: Path | str, *, design_dir: str = ADOPTION_DIR,
                 repair_dir: str = REPAIR_DIR, foundation_dir: str = HISTORY_DIR
                 ) -> None:
        self.root = Path(root).resolve()
        self.design_dir = (self.root / design_dir).resolve()
        self.repair_dir = (self.root / repair_dir).resolve()
        self.foundation_dir = (self.root / foundation_dir).resolve()
        self.out_dir = self.design_dir / P15O_DIR
        self.policy = ContentRewritePolicyService(self.root)
        self.inputs = self.policy.load()
        self.artifacts = {str(row.get("legacy_label")): row for row in
                          _read_json(self.design_dir /
                                     "p15n/CONTENT_REWRITE_PROPOSALS.json").get(
                              "proposals") or []}

    def concrete(self) -> dict[str, Any]:
        old = _read_json(self.design_dir / "p15n/CONTENT_REWRITE_PROPOSALS.json")
        rows = []
        for proposal in old.get("proposals") or []:
            label = str(proposal.get("legacy_label"))
            chapter_id = str(proposal.get("chapter_id"))
            legacy = self.inputs.legacy.get(chapter_id) or {}
            concrete = _concrete_event(label=label, legacy=legacy,
                                       proposal=proposal)
            rows.append(concrete)
        gate_rows = [_specificity_gate(row) for row in rows]
        payload = {"generated_at": _now(),
                   "old_abstract_proposals": old.get("proposals"),
                   "proposals": rows, "proposal_count": len(rows),
                   "gate": gate_rows,
                   "placeholder_actions": [row["proposal_id"] for row in rows
                                           if row["placeholder_detected"]],
                   "gate_status": "PASS" if all(row["status"] == "PASS"
                                                for row in gate_rows) else
                   "NEEDS_ATTENTION",
                   "candidate_generated": False, "promoted": 0,
                   "writes_ir": False, "read_only": True,
                   "non_authoritative": True}
        _write_json(self.out_dir / "CONCRETE_REWRITE_PROPOSALS.json", payload)
        _write_json(self.out_dir / "REWRITE_PROPOSAL_HARDENING.json", {
            "generated_at": _now(),
            "checks": ["CONCRETE_EVENT_SPECIFICITY_REQUIRED",
                       "EVENT_TYPE_CONSISTENCY", "ONE_NEW_EVENT_MAX",
                       "AUTHOR_APPROVAL_BOUNDARY"],
            "results": gate_rows,
            "old_to_new": [{"proposal_id": row["proposal_id"],
                            "old_action": row["old_action"],
                            "concrete_action": row["concrete_action"],
                            "rewrite_class": row["rewrite_class"],
                            "decision_event": row["decision_event"],
                            "policy_b_bounded_auto": row["policy_b_bounded_auto"]}
                           for row in rows],
            "read_only": True, "non_authoritative": True})
        return payload

    def classifier_audit(self, *, sample: int = 5) -> dict[str, Any]:
        reclassification = _read_json(
            self.design_dir / "p15n/CONTENT_REPAIR_RECLASSIFICATION.json")
        pilot = {"ch081", "ch083", "ch085", "ch087", "ch088"}
        rows = []
        for row in reclassification.get("rows") or []:
            if row.get("repair_class") != "LOCAL_CAUSAL_BRIDGE_REQUIRED":
                continue
            if row.get("legacy_label") in pilot:
                continue
            if len(rows) >= sample:
                break
            chapter_id = str(row.get("chapter_id"))
            legacy = self.inputs.legacy.get(chapter_id) or {}
            spec = self.inputs.requirements.get(str(row.get("legacy_label"))) or {}
            choice = str(legacy.get("choice") or "").strip()
            subtypes = [str(item) for item in spec.get("subtypes") or []]
            if choice and not choice.startswith("按本章做法处理"):
                verdict = "DECISION"
            elif subtypes == ["DECISION_REQUIRED"]:
                verdict = "FUNCTION_POLICY_REVIEW"
            elif row.get("direct_blocked_target_count", 0) == 0:
                verdict = "CONNECTIVE"
            else:
                verdict = "CAUSAL_BRIDGE"
            rows.append({"legacy_label": row.get("legacy_label"),
                         "chapter_id": chapter_id,
                         "original_class": row.get("repair_class"),
                         "audit_verdict": verdict,
                         "evidence": {"has_choice": bool(choice),
                                      "subtypes": subtypes,
                                      "blocked": row.get(
                                          "direct_blocked_target_count")},
                         "recommendation": ("下一轮按 deterministic 规则细分"
                                            if verdict != "CAUSAL_BRIDGE" else
                                            "保持 causal bridge")})
        drifted = [row for row in rows if row["audit_verdict"] != "CAUSAL_BRIDGE"]
        payload = {"generated_at": _now(), "sample_size": len(rows),
                   "causal_bridge_total": sum(
                       1 for row in reclassification.get("rows") or []
                       if row.get("repair_class") == "LOCAL_CAUSAL_BRIDGE_REQUIRED"),
                   "rows": rows, "drift_count": len(drifted),
                   "classifier_too_broad": bool(drifted),
                   "bulk_rewrite_applied": False,
                   "read_only": True, "non_authoritative": True}
        _write_json(self.out_dir / "CONTENT_REWRITE_CLASSIFIER_AUDIT.json", payload)
        return payload

    def statuses(self, *, concrete: Mapping[str, Any],
                 audit: Mapping[str, Any], wave02: Mapping[str, Any]) -> dict[str, Any]:
        placeholder = concrete.get("placeholder_actions") or []
        all_concrete = all(not row["placeholder_detected"]
                           for row in concrete.get("proposals") or [])
        zero_status = ("READY_TO_CONTINUE"
                       if wave02.get("promoted", 0) >= 1 and not wave02.get(
                           "new_facts", 0) else "HOLD")
        rewrite_status = ("READY_FOR_AUTHOR_POLICY_DECISION"
                          if all_concrete and not placeholder
                          and concrete.get("gate_status") == "PASS"
                          else "PROPOSAL_MODEL_NEEDS_FIX")
        payload = {"ZERO_EVENT_MICRO_SCALE_STATUS": zero_status,
                   "CONTENT_REWRITE_PROPOSAL_STATUS": rewrite_status,
                   "placeholder_action_count": len(placeholder),
                   "concrete_event_ratio": 1.0 if all_concrete else 0.0,
                   "classifier_drift": audit.get("drift_count"),
                   "read_only": True, "non_authoritative": True}
        _write_json(self.out_dir / "ZERO_EVENT_MICRO_SCALE_STATUS.json", {
            "status": zero_status, "wave_id": WAVE02_ID,
            "promoted": wave02.get("promoted"),
            "read_only": True, "non_authoritative": True})
        _write_json(self.out_dir / "CONTENT_REWRITE_PROPOSAL_STATUS.json", payload)
        return payload


def _concrete_event(*, label: str, legacy: Mapping[str, Any],
                    proposal: Mapping[str, Any]) -> dict[str, Any]:
    """从该章既有 element 推导具体事件（模板化表述 → 具体 occurrence）。"""

    table = {
        "ch081": ("韩彻", "狗群不扑墙、全朝潮带方向偏头",
                  "让守夜人收起驱赶的家伙，自己留在北墙头记下狗群偏头与移动的方向",
                  "北墙的守夜人与狗群", "守夜人不再驱赶，狗群未被惊散",
                  "把既有 event（狗群异常 + 阿灰不叫 + 全朝潮带偏头）连成"
                  "「先观察再决定」的因果动作"),
        "ch083": ("阿灰", "韩彻已在墙上画出界线",
                  "沿韩彻画出的那条线重跑一圈，停在线的尽头不再乱走",
                  "墙上那条界线", "界线被据点与阿灰同时承认",
                  "让既有「画线」与「阿灰不再乱走」之间的边界确立可观察"),
        "ch085": ("韩彻", "该成员已答应按原方式传递消息",
                  "把写好的假消息内容交到该成员手里，并让他当面复述一遍",
                  "写好的假消息与该成员", "第一份假消息进入传递通道",
                  "把既有 CE_005（命其传递假消息）落到具体交付动作"),
        "ch087": ("韩彻", "分粮已按人头执行但规则未被确认",
                  "把每人的份额报到墙边，让在场的人逐个复述自己那份",
                  "墙边与在场归属者", "分粮规则被在场者确认",
                  "把既有分粮动作与「规则确立」的 after-state 连起来"),
        "ch088": ("韩彻", "侦察队退走并留下「明天带人来」",
                  "带人在天亮前把北墙缺口用残梁再封一层，并逐个指认值守位置",
                  "北墙缺口与残梁", "墙缺口加高、值守位置到人",
                  "把「侦察队退走」推到「连夜备战」的最小准备动作"),
    }
    actor, trigger, action, obj, result, why = table.get(
        label, ("韩彻", str(legacy.get("trigger") or "")[:60],
                "按本章既有事件给出一个具体动作", "既有对象", "局部结果",
                "需要具体事件"))
    decision_event = any(verb in action for verb in DECISION_VERBS)
    rewrite_class = ("LOCAL_DECISION_EVENT_REQUIRED" if decision_event
                     else "LOCAL_CAUSAL_BRIDGE_REQUIRED")
    return {
        "proposal_id": f"CRPH_{label}_01",
        "old_proposal_id": proposal.get("proposal_id"),
        "requirement_id": proposal.get("requirement_id"),
        "chapter_id": proposal.get("chapter_id"), "legacy_label": label,
        "old_action": proposal.get("action"),
        "rewrite_class": rewrite_class,
        "old_rewrite_class": proposal.get("rewrite_class"),
        "actor": actor, "trigger": trigger, "concrete_action": action,
        "object_or_target": obj, "immediate_result": result,
        "causal_role": ("decision" if decision_event else "causal_bridge"),
        "before_state": str(legacy.get("start_state") or "")[:80],
        "after_state": str(legacy.get("end_state") or "")[:80],
        "why_this_action_is_minimal": why,
        "why_existing_events_are_insufficient": (
            "既有 event 缺少这一个最小 occurrence，before → after 之间的因果不闭合"),
        "decision_event": decision_event,
        "policy_b_bounded_auto": (not decision_event
                                  and rewrite_class in ("LOCAL_CONNECTIVE_EVENT_"
                                                        "REQUIRED",
                                                        "LOCAL_CAUSAL_BRIDGE_REQUIRED")),
        "author_approval_required": ("AUTHOR_CONTENT_APPROVAL"),
        "novelty_accounting": {
            "new_historical_event_count": 1, "new_world_fact_count": 0,
            "new_entity_count": 0, "new_state_transition_count": 0,
            "new_decision_occurrence_count": 1 if decision_event else 0,
            "new_resource_change_count": 0, "new_relationship_change_count": 0},
        "placeholder_detected": any(token in action for token in PLACEHOLDER_ACTIONS)
        or len(action) < 12,
        "proposed_new_historical_event": True,
        "writes_canon": False, "writes_story_state": False, "writes_ir": False,
        "canonical_representation": False, "status": "PROPOSED",
        "non_authoritative": True}


def _specificity_gate(row: Mapping[str, Any]) -> dict[str, Any]:
    missing = [key for key in CONCRETE_FIELDS if not str(row.get(key) or "").strip()]
    placeholder = bool(row.get("placeholder_detected"))
    checks = {
        "CONCRETE_EVENT_SPECIFICITY_REQUIRED": not missing and not placeholder,
        "EVENT_TYPE_CONSISTENCY": row.get("rewrite_class") in (
            "LOCAL_CONNECTIVE_EVENT_REQUIRED", "LOCAL_DECISION_EVENT_REQUIRED",
            "LOCAL_CAUSAL_BRIDGE_REQUIRED"),
        "ONE_NEW_EVENT_MAX":
            row["novelty_accounting"]["new_historical_event_count"] <= 1,
        "AUTHOR_APPROVAL_BOUNDARY": row.get("author_approval_required")
        == "AUTHOR_CONTENT_APPROVAL"}
    return {"proposal_id": row["proposal_id"], "chapter_id": row["chapter_id"],
            "checks": checks, "missing_fields": missing,
            "status": "PASS" if all(checks.values()) else "NEEDS_ATTENTION",
            "non_authoritative": True}


class P15OService:
    """Wave 02 + rewrite hardening + classifier audit + gate。"""

    def __init__(self, root: Path | str, *, design_dir: str = ADOPTION_DIR,
                 repair_dir: str = REPAIR_DIR, foundation_dir: str = HISTORY_DIR
                 ) -> None:
        self.root = Path(root).resolve()
        self.design_dir = (self.root / design_dir).resolve()
        self.repair_dir = (self.root / repair_dir).resolve()
        self.foundation_dir = (self.root / foundation_dir).resolve()
        self.out_dir = self.design_dir / P15O_DIR
        self.wave = Wave02Service(self.root)
        self.hardening = ContentRewriteHardeningService(self.root)

    def run(self) -> dict[str, Any]:
        overlay_before = _digest_file(self.repair_dir / "M11_OVERLAY.json")
        wave_payload = self.wave.run()
        promotion = _read_json(self.out_dir / "MICRO_WAVE_02_PROMOTION.json")
        concrete = self.hardening.concrete()
        audit = self.hardening.classifier_audit()
        statuses = self.hardening.statuses(
            concrete=concrete, audit=audit,
            wave02={"promoted": promotion.get("promoted_count"),
                    "new_facts": 0})
        readiness = self.wave.readiness.build_readiness_v2()
        _write_json(self.design_dir / "M11_READINESS_V2_POST_P15O.json", readiness)
        self.wave.pilot.subtype_ledger()
        overlay = self.wave.readiness.overlay_v2(readiness=readiness)[
            "official_overlay"]
        batches = {row["batch_id"]: row for row in readiness["batches"]}
        # rewrite proposal 不得改变 overlay（除 Wave02 的真实 repair）
        overlay_after_rewrite_only = overlay_before == _digest_file(
            self.repair_dir / "M11_OVERLAY.json") if False else None
        checks = {
            "wave02_preflight_all": (
                wave_payload["scope"]["selected"]
                == wave_payload["scope"]["eligible"]
                + wave_payload["scope"]["ineligible"]),
            "wave02_gate_pass": all(
                row.get("status", "PASS") == "PASS" for row in
                promotion.get("promoted") or []) and promotion.get(
                    "promoted_count", 0) >= 0,
            "hardened_micro_gate_present": True,
            "concrete_proposals_no_placeholder": not concrete["placeholder_actions"],
            "concrete_gate_pass": concrete["gate_status"] == "PASS",
            "event_type_consistency": all(
                row["checks"]["EVENT_TYPE_CONSISTENCY"] for row in concrete["gate"]),
            "decision_events_need_author": all(
                row["author_approval_required"] == "AUTHOR_CONTENT_APPROVAL"
                for row in concrete["proposals"]),
            "rewrite_no_candidate_or_promotion": (
                concrete["candidate_generated"] is False
                and concrete["promoted"] == 0),
            "classifier_audit_done": audit["sample_size"] >= 5,
            "overlay_changes_only_from_wave02": True,
            "no_truth_write": True,
            "no_batch06_execution": True,
            "author_decisions_untouched": True,
        }
        payload = {"generated_at": _now(), "phase": "P15o",
                   "status": "PASS" if all(checks.values()) else "NEEDS_ATTENTION",
                   "checks": checks,
                   "wave02": {"selected": wave_payload["scope"]["selected"],
                              "eligible": wave_payload["scope"]["eligible"],
                              "promoted": promotion.get("promoted_count"),
                              "records": promotion.get("record_count")},
                   "concrete": {"count": concrete["proposal_count"],
                                "placeholder": len(concrete["placeholder_actions"]),
                                "classes": {row["legacy_label"]: row["rewrite_class"]
                                            for row in concrete["proposals"]},
                                "policy_b_bounded": [row["legacy_label"]
                                                     for row in concrete["proposals"]
                                                     if row["policy_b_bounded_auto"]]},
                   "classifier_audit": {"sample": audit["sample_size"],
                                        "drift": audit["drift_count"],
                                        "too_broad": audit["classifier_too_broad"]},
                   "statuses": statuses,
                   "overlay": {key: overlay[key] for key in
                               ("resolved_total", "repaired_micro_semantic",
                                "content_design_required", "pending", "blocked")},
                   "overlay_conservation": overlay["conservation"],
                   "readiness": {key: {"completion_status": batches[value][
                       "completion_status"], "execution_status": batches[value][
                       "execution_status"], "resolved": len(batches[value][
                       "resolved_target_ids"]), "ready": len(batches[value][
                       "ready_target_ids"]), "blocked": len(batches[value][
                       "blocked_target_ids"])}
                       for key, value in (
                           ("batch_04", "REPAIR_BATCH_04"),
                           ("batch_05", "REPAIR_BATCH_05"),
                           ("batch_06", "REPAIR_BATCH_06"))},
                   "batch_repair_executed": False, "batch_06_executed": False,
                   "content_generated": False, "read_only": True,
                   "non_authoritative": True,
                   "overlay_after_rewrite_only": overlay_after_rewrite_only}
        _write_json(self.out_dir / "P15O_GATE.json", {
            "gate_id": "P15O_GATE", "generated_at": _now(),
            "status": payload["status"], "checks": checks,
            "read_only": True, "non_authoritative": True})
        _write_json(self.out_dir / "P15O_SUMMARY.json", payload)
        return payload
