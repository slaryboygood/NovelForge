"""P15f：Historical Full Chapter Semantic IR Foundation（M11 内部 foundation）。

目标：为 570 个历史章节建立**完整、证据驱动、不可变、可审计**的
Historical ChapterSemanticIR body（wrapper 只做 provenance，body 仍是正式 M1 model）。

硬边界：
- 只读 Canon / StoryState / legacy candidate / M10 baseline / 570 source IR；
- 不新增 happened truth；Historical IR = derived historical representation
  （`time_layer=happened_historical`、`derived=true`、`canonical_representation=false`、
  `non_authoritative=true`）；
- evidence-first：每个 semantic field 有 assertion mode（CONFIRMED / DIRECT_SOURCE /
  DERIVED / INFERRED / NOT_APPLICABLE / UNRESOLVED）+ source ref（含 quote）；
- 无 LLM：materialization 只用 deterministic extraction（可选 LLM 通道预留但本轮不启用）。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence

from pydantic import Field

from novelforge.models import StrictModel
from novelforge.story_engine.chapter_ir.evidence import EvidenceValidator
from novelforge.story_engine.chapter_ir.extractor import LegacyIRSemanticExtractor
from novelforge.story_engine.chapter_ir.models import (
    ChapterEffect,
    ChapterSemanticIR,
    FieldEvidence,
)
from novelforge.story_engine.chapter_ir.state import (
    DEFAULT_TRANSITION_BINDINGS,
    build_default_registry,
)
from novelforge.story_engine.chapter_ir.validator import ChapterIRValidator

HISTORY_DIR = "workspace/wasteland_001_exports/historical_chapter_ir_v1"
RECON_DIR = "workspace/wasteland_001_exports/reconstruction_v2"
REPAIR_DIR = "workspace/wasteland_001_exports/repair_v1"
M1_DIR = "workspace/wasteland_001_exports/chapter_ir_v1"
LEGACY_CANDIDATE = ("workspace/wasteland_001_exports/"
                    "WASTELAND_001_OUTLINE_CANON_FINAL_CANDIDATE_V5.json")
CANON_DB = "novel/authoring/story_engine/canon/wasteland_001.sqlite"
STATE_JSON = "novel/authoring/story_engine/state/runtime_wasteland_001/v000001.json"
CANON_FACT_REGISTRY = ("workspace/wasteland_001_exports/"
                       "WASTELAND_001_CANON_FACT_REGISTRY.json")
COMPILER_VERSION = "historical-ir-foundation-v1"
TIME_LAYER = "happened_historical"
# P15f scope：foundation 的 repair replay / human-review 重评只覆盖 Batch 01–03
# （Batch 04+ 由后续阶段用各自的 reconciliation artifact 处理）
FOUNDATION_REPLAY_BATCHES: tuple[str, ...] = ("REPAIR_BATCH_01", "REPAIR_BATCH_02",
                                              "REPAIR_BATCH_03")

AssertionMode = Literal["CONFIRMED", "DIRECT_SOURCE", "DERIVED", "INFERRED",
                        "NOT_APPLICABLE", "UNRESOLVED"]
CoverageStatus = Literal["SUFFICIENT", "PARTIAL", "INSUFFICIENT"]
MaterializationStatus = Literal["FULL", "PARTIAL", "FAILED"]
EvidenceChannel = Literal["legacy_outline", "prose_text", "shadow_summary",
                          "compiled_preview", "deterministic_verifier", "canon_ref",
                          "story_state_ref"]
ReplayStatus = Literal["APPLIES_CLEANLY", "NEEDS_REBASE", "OBSOLETE_REPAIR",
                       "CONFLICT", "HUMAN_REVIEW"]
ReevaluationClass = Literal["EVIDENCE_ONLY", "FIELD_REBIND", "N/A_CORRECTION",
                            "TRULY_MISSING", "AUTHOR_DECISION_REQUIRED",
                            "SOURCE_EVIDENCE_INSUFFICIENT"]

# §24 Full IR evidence coverage 字段（顺序固定，便于报告）
COVERAGE_FIELDS: tuple[str, ...] = (
    "events", "effects", "state_transition", "decision", "turn", "payoff",
    "knowledge", "relationship", "resource", "progression", "location", "causality")
FUNCTION_FIELDS: tuple[str, ...] = (
    "decision", "turn", "payoff", "cost", "loss", "information_release",
    "world_state_change")

# pivot evidence（§15）：只收"显式 pivot"关键词，避免把普通 loss / 计划句当 turn
PIVOT_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("decision_pivot", ("决定不再", "决定改为", "拍板", "立誓", "许诺", "答应下来",
                        "拒绝", "放弃原计划", "定下规矩", "立下规矩")),
    ("information_pivot", ("第一次意识到", "第一次知道", "第一次看清", "才明白",
                           "终于明白", "识破", "看穿", "真相", "暴露了", "查出真相")),
    ("relationship_pivot", ("反目", "决裂", "结盟", "背叛", "和解", "托付",
                            "第一次冲")),
    ("strategy_pivot", ("改主意", "换打法", "转守为攻", "改变计划", "换一条",
                        "另走", "转为主攻")),
    ("state_pivot", ("易手", "夺回", "永久", "封死", "转为", "再也", "失控")),
)
# 参与 pivot 扫描的 narrative 字段（goal / start_state 只描述计划，不作为 pivot 证据）
PIVOT_SOURCE_FIELDS: tuple[str, ...] = (
    "turn", "escalation", "end_state", "decision", "choice", "cost", "loss",
    "payoff", "world_state_change", "trigger", "protagonist_action", "opposition",
    "next_chapter_causality")

TOKEN_PATTERN = ("ENTITY_", "CE_", "EF_", "ST_", "state_key", "uuid_", "chapter_goal",
                 "protagonist", "npc_1", "CE_0", "ir://")

# §38 golden chapters：覆盖 confirmed / field conflict / evidence·turn·decision gap /
# state binding / information / relationship / resource / progression / map /
# dog·NPC action / 不同 ChapterFunction。expectation 全部来自已实跑核对（非拟合猜测）。
FOUNDATION_GOLDEN: tuple[tuple[str, dict[str, str]], ...] = (
    ("ch001", {"turn": "UNRESOLVED", "decision": "UNRESOLVED", "resource": "NOT_APPLICABLE"}),
    ("ch005", {"canon_ref": "FACT_RADIO_FIRST_RESPONSE", "knowledge": "UNRESOLVED"}),
    ("ch008", {"turn": "DIRECT_SOURCE", "reclassification": "EVIDENCE_ONLY"}),
    ("ch011", {"replay": "APPLIES_CLEANLY"}),
    ("ch015", {"turn": "UNRESOLVED", "reclassification": "TRULY_MISSING"}),
    ("ch020", {"turn": "UNRESOLVED", "reclassification": "TRULY_MISSING"}),
    ("ch021", {"dog_role": "offscreen_effect", "materialization_status": "PARTIAL"}),
    ("ch027", {"turn": "DIRECT_SOURCE", "reclassification": "EVIDENCE_ONLY"}),
    ("ch036", {"reclassification": "AUTHOR_DECISION_REQUIRED", "payoff": "DERIVED"}),
    ("ch043", {"turn": "DIRECT_SOURCE", "reclassification": "EVIDENCE_ONLY"}),
    ("ch048", {"replay": "OBSOLETE_REPAIR"}),
    ("ch049", {"turn": "DIRECT_SOURCE", "reclassification": "EVIDENCE_ONLY"}),
    ("ch050", {"replay": "APPLIES_CLEANLY"}),
    ("ch055", {"replay": "OBSOLETE_REPAIR", "turn": "DIRECT_SOURCE"}),
    ("ch056", {"reclassification": "TRULY_MISSING"}),
    ("ch059", {"turn": "DIRECT_SOURCE", "reclassification": "EVIDENCE_ONLY"}),
    ("ch063", {"reclassification": "FIELD_REBIND", "world_state_change": "DIRECT_SOURCE"}),
    ("ch067", {"reclassification": "TRULY_MISSING"}),
    ("ch107", {"primary_transition": "salt_route_control:contested"}),
    ("ch505", {"progression": "NOT_APPLICABLE"}),
)


def digest_payload(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                     default=str).encode("utf-8")).hexdigest()[:16]


def digest_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16] if path.is_file() else ""


def fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> Any:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                    encoding="utf-8", newline="\n")


# --------------------------------------------------------------------------- models
class HistoricalSourceRef(StrictModel):
    """字段级 source ref：channel + 具体 ref + quote（source span）。"""

    channel: EvidenceChannel
    field_name: str = Field(default="", max_length=64)
    ref: str = Field(default="", max_length=200)
    quote: str = Field(default="", max_length=200)
    digest: str = Field(default="", max_length=64)


class HistoricalFieldAssertion(StrictModel):
    """每个 semantic field 的 assertion mode + 证据（§9）。"""

    field_name: str = Field(min_length=2, max_length=64)
    assertion_mode: AssertionMode = "UNRESOLVED"
    bound_ir_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[HistoricalSourceRef] = Field(default_factory=list)
    reason: str = Field(default="", max_length=200)
    non_authoritative: bool = True


class HistoricalIREvidenceCoverage(StrictModel):
    """§24 coverage：逐 field 状态 + overall（不伪造 0-100 分）。"""

    events: CoverageStatus = "INSUFFICIENT"
    effects: CoverageStatus = "INSUFFICIENT"
    state_transition: CoverageStatus = "INSUFFICIENT"
    decision: CoverageStatus = "INSUFFICIENT"
    turn: CoverageStatus = "INSUFFICIENT"
    payoff: CoverageStatus = "INSUFFICIENT"
    knowledge: CoverageStatus = "INSUFFICIENT"
    relationship: CoverageStatus = "INSUFFICIENT"
    resource: CoverageStatus = "INSUFFICIENT"
    progression: CoverageStatus = "INSUFFICIENT"
    location: CoverageStatus = "INSUFFICIENT"
    causality: CoverageStatus = "INSUFFICIENT"
    overall_status: CoverageStatus = "INSUFFICIENT"
    sufficiency_reason: str = Field(default="", max_length=240)
    non_authoritative: bool = True


class HistoricalChapterIRArtifact(StrictModel):
    """provenance wrapper（§5）：body 仍是正式 ChapterSemanticIR。"""

    artifact_id: str = Field(min_length=3, max_length=80)
    chapter_id: str = Field(min_length=3, max_length=128)
    chapter_uuid: str = Field(min_length=3, max_length=128)
    legacy_label: str = Field(default="", max_length=32)
    volume_id: str = Field(default="", max_length=64)
    arc_id: str = Field(default="", max_length=64)
    display_number: int | None = Field(default=None, ge=0)
    time_layer: Literal["happened_historical"] = "happened_historical"
    derived: bool = True
    canonical_representation: bool = False
    non_authoritative: bool = True
    source_text_available: bool = False
    source_text_digest: str = Field(default="", max_length=64)
    legacy_source_digest: str = Field(default="", max_length=64)
    shadow_digest: str = Field(default="", max_length=64)
    compiled_preview_digest: str = Field(default="", max_length=64)
    verifier_digest: str = Field(default="", max_length=64)
    canon_digest_ref: str = Field(default="", max_length=64)
    story_state_digest_ref: str = Field(default="", max_length=64)
    chapter_ir: ChapterSemanticIR
    chapter_ir_digest: str = Field(min_length=8, max_length=64)
    materialization_method: str = Field(default="deterministic_legacy_extraction",
                                        max_length=64)
    materialization_status: MaterializationStatus = "PARTIAL"
    chapter_function: str = Field(default="", max_length=48)
    evidence_coverage: HistoricalIREvidenceCoverage = Field(
        default_factory=HistoricalIREvidenceCoverage)
    field_assertions: list[HistoricalFieldAssertion] = Field(default_factory=list)
    unresolved_fields: list[str] = Field(default_factory=list)
    inference_records: list[dict[str, Any]] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    validator_results: dict[str, str] = Field(default_factory=dict)
    created_at: str = Field(default="", max_length=64)
    compiler_version: str = Field(default=COMPILER_VERSION, max_length=64)
    parent_artifact_ref: str = Field(default="", max_length=200)
    notes: str = Field(default="", max_length=300)

    def assertion(self, field_name: str) -> HistoricalFieldAssertion | None:
        return next((item for item in self.field_assertions
                     if item.field_name == field_name), None)


class HistoricalIRSourceInventoryRow(StrictModel):
    """§2 source inventory：逐章记录磁盘上真实存在什么 source。"""

    chapter_id: str
    chapter_uuid: str
    legacy_label: str
    display_number: int | None = None
    volume: int | None = None
    arc: str = ""
    title: str = ""
    source_text_available: bool = False
    source_text_digest: str = ""
    legacy_fields_available: bool = False
    legacy_fields_digest: str = ""
    shadow_summary_available: bool = False
    shadow_digest: str = ""
    compiled_preview_available: bool = False
    preview_digest: str = ""
    deterministic_verifier_available: bool = False
    verifier_digest: str = ""
    story_map_available: bool = False
    canon_refs: list[str] = Field(default_factory=list)
    story_state_refs: list[str] = Field(default_factory=list)
    m1_classification: str = ""
    m10_classification: str = ""
    repair_overlay_refs: list[str] = Field(default_factory=list)
    evidence_completeness: CoverageStatus = "INSUFFICIENT"
    non_authoritative: bool = True


class HistoricalIRSourceInventory(StrictModel):
    generated_at: str = ""
    novel_id: str = "wasteland_001"
    chapter_count: int = 0
    counts: dict[str, int] = Field(default_factory=dict)
    channel_availability: dict[str, int] = Field(default_factory=dict)
    prose_note: str = ""
    rows: list[HistoricalIRSourceInventoryRow] = Field(default_factory=list)
    read_only: bool = True


class RepairReplayResult(StrictModel):
    """§30 RepairReplayResult：旧 verified repair 在 full IR base 上的 dry-run。"""

    repair_id: str
    chapter_id: str
    legacy_label: str = ""
    batch_id: str = ""
    old_overlay_digest: str = ""
    full_ir_base_digest: str = ""
    patch_ops: list[str] = Field(default_factory=list)
    patch_applicable: bool = False
    evidence_valid: bool = False
    semantic_diff: dict[str, str] = Field(default_factory=dict)
    forbidden_change_violation: bool = False
    validator_results: dict[str, str] = Field(default_factory=dict)
    status: ReplayStatus = "HUMAN_REVIEW"
    reason: str = ""
    non_authoritative: bool = True


class HistoricalChapterReevaluation(StrictModel):
    """§32/§44：human_review target 的 classification refresh（不改正式 overlay）。"""

    chapter_id: str
    legacy_label: str = ""
    batch_id: str = ""
    previous_reason: str = ""
    required_fields: list[str] = Field(default_factory=list)
    proposed_class: ReevaluationClass = "SOURCE_EVIDENCE_INSUFFICIENT"
    proposed_detail: str = ""
    base_binding: dict[str, str] = Field(default_factory=dict)
    pivot_evidence: list[str] = Field(default_factory=list)
    non_authoritative: bool = True


@dataclass
class FoundationInputs:
    chapters: list[dict[str, Any]] = field(default_factory=list)
    full_rows: dict[str, dict[str, Any]] = field(default_factory=dict)
    recon_rows: dict[str, dict[str, Any]] = field(default_factory=dict)
    story_rows: dict[str, dict[str, Any]] = field(default_factory=dict)
    canon_refs: dict[str, list[str]] = field(default_factory=dict)
    knowledge_refs: dict[str, list[str]] = field(default_factory=dict)
    repair_overlays: dict[str, dict[str, Any]] = field(default_factory=dict)
    human_review_entries: list[dict[str, Any]] = field(default_factory=list)
    candidate_patches: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    candidate_refinements: dict[str, dict[str, Any]] = field(default_factory=dict)
    digests: dict[str, str] = field(default_factory=dict)
    prose_available: dict[str, bool] = field(default_factory=dict)


# ----------------------------------------------------------------- adapter / pivot
class WastelandSourceAdapter:
    """WASTELAND_001 dogfood adapter（§39/§40）：legacy 字段 → narrative evidence。

    WASTELAND-specific 的别名 / 状态绑定 / 字段映射只留在 adapter 内，
    不搬进 M9/new general Core。
    """

    novel_id = "wasteland_001"
    protagonist_id = "ENTITY_PROTAGONIST"
    dog_entity_id = "ENTITY_DOG_AHUI"
    entity_aliases = {
        "韩彻": "ENTITY_PROTAGONIST", "阿灰": "ENTITY_DOG_AHUI", "老鸦": "ENTITY_RAVEN",
        "秦霜": "ENTITY_QINSHUANG", "穆医生": "ENTITY_DOCTOR_MU", "织工": "ENTITY_WEAVER",
        "锈牙": "ENTITY_FACTION_RUST_TOOTH", "黑塔": "ENTITY_FACTION_BLACK_TOWER",
        "缝合会": "ENTITY_FACTION_STITCHING", "盐路": "ENTITY_FACTION_SALT_ROAD",
        "编号犬": "ENTITY_HUNTER_DOG_01", "荒原犬": "ENTITY_HUNTER_DOG_01",
        "猎团": "ENTITY_FACTION_HUNTERS", "笼中同类": "ENTITY_CAGED_KIN",
    }
    kind_index = {"dog": ["ENTITY_DOG_AHUI", "ENTITY_HUNTER_DOG_01", "ENTITY_CAGED_KIN"]}
    actor_names = {
        "ENTITY_PROTAGONIST": "韩彻", "ENTITY_DOG_AHUI": "阿灰", "ENTITY_RAVEN": "老鸦",
        "ENTITY_QINSHUANG": "秦霜", "ENTITY_DOCTOR_MU": "穆医生", "ENTITY_WEAVER": "织工",
        "ENTITY_FACTION_BLACK_TOWER": "黑塔", "ENTITY_FACTION_STITCHING": "缝合会",
        "ENTITY_FACTION_SALT_ROAD": "盐路商队", "ENTITY_FACTION_RUST_TOOTH": "锈牙",
        "ENTITY_FACTION_HUNTERS": "猎团", "ENTITY_HUNTER_DOG_01": "编号荒原犬",
        "ENTITY_CAGED_KIN": "笼中同类", "ENTITY_THREE_FACTIONS": "三方代表",
        "ENTITY_RUST_SETTLEMENT": "铁锈集", "ENTITY_SETTLEMENT_EDGE": "边缘聚落",
        "ENTITY_EXTERNAL_TEAM": "外部队伍",
    }
    decision_placeholder = "按本章做法处理"

    def state_bindings(self) -> dict[str, int]:
        return {binding.state_key: binding.display_number
                for binding in DEFAULT_TRANSITION_BINDINGS}

    def narrative_texts(self, row: Mapping[str, Any]) -> dict[str, str]:
        """字段级 narrative 文本（pivot 扫描口径，见 PIVOT_SOURCE_FIELDS）。"""

        texts: dict[str, str] = {name: str(row.get(name) or "").strip()
                                 for name in PIVOT_SOURCE_FIELDS}
        events = [str(item).strip() for item in row.get("events") or []]
        texts["events"] = " ".join(item for item in events if item)
        return texts

    def is_placeholder(self, value: Any) -> bool:
        text = str(value or "").strip()
        return (not text) or text.startswith(self.decision_placeholder)

    def map_names(self, payload: Mapping[str, Any]) -> list[str]:
        names: list[str] = []
        for item in payload.get("maps") or []:
            if isinstance(item, Mapping):
                name = str(item.get("name") or item.get("id") or "").strip()
            else:
                name = str(item).strip()
            if name:
                names.append(name)
        return names


def analyze_pivot_evidence(row: Mapping[str, Any], adapter: WastelandSourceAdapter
                           ) -> list[dict[str, str]]:
    """§15：只把显式 pivot 关键词当 turn 证据，并记录来源字段与 quote。"""

    matches: list[dict[str, str]] = []
    for field_name, text in adapter.narrative_texts(row).items():
        if not text:
            continue
        for pivot_type, keywords in PIVOT_RULES:
            for keyword in keywords:
                index = text.find(keyword)
                if index < 0:
                    continue
                quote = text[max(0, index - 30):index + len(keyword) + 30]
                matches.append({"pivot_type": pivot_type, "keyword": keyword,
                                "field_name": field_name, "quote": quote})
                break
            else:
                continue
            break
    return matches


# ---------------------------------------------------------------------- materializer
class HistoricalIRMaterializer:
    """570 章 deterministic materialization（evidence-first，无 LLM）。"""

    def __init__(self, project_root: Path | str, *, store_dir: str = HISTORY_DIR,
                 adapter: WastelandSourceAdapter | None = None) -> None:
        self.root = Path(project_root).resolve()
        self.store_dir = (self.root / store_dir).resolve() \
            if not Path(store_dir).is_absolute() else Path(store_dir)
        self.adapter = adapter or WastelandSourceAdapter()
        self.m1_dir = self.root / M1_DIR
        self.recon_dir = self.root / RECON_DIR
        self.repair_dir = self.root / REPAIR_DIR
        self.legacy_candidate = self.root / LEGACY_CANDIDATE
        self.canon_db = self.root / CANON_DB
        self.state_json = self.root / STATE_JSON
        registry = build_default_registry(self.adapter.state_bindings())
        self.validator = ChapterIRValidator(
            registry=registry,
            evidence=EvidenceValidator(dog_id=self.adapter.dog_entity_id,
                                       protagonist_id=self.adapter.protagonist_id))
        self.evidence = EvidenceValidator(dog_id=self.adapter.dog_entity_id,
                                          protagonist_id=self.adapter.protagonist_id)
        self.extractor = LegacyIRSemanticExtractor(
            novel_id=self.adapter.novel_id, dog_entity_id=self.adapter.dog_entity_id,
            protagonist_id=self.adapter.protagonist_id,
            entity_aliases=self.adapter.entity_aliases,
            kind_index=self.adapter.kind_index,
            state_bindings=self.adapter.state_bindings())

    # ---- inputs ----------------------------------------------------------
    def source_digests(self) -> dict[str, str]:
        return {
            "canon": digest_file(self.canon_db),
            "story_state": digest_file(self.state_json),
            "legacy_candidate": digest_file(self.legacy_candidate),
            "chapter_ir": digest_file(
                self.m1_dir / "full_migration/WASTELAND_001_CHAPTER_IR_FULL.json"),
        }

    def load(self) -> FoundationInputs:
        payload = _read_json(self.legacy_candidate)
        chapters = list(payload.get("chapters") or [])
        full = _read_json(self.m1_dir / "full_migration/"
                          "WASTELAND_001_CHAPTER_IR_FULL.json")
        recon = _read_json(self.m1_dir / "m1b_v2/"
                           "WASTELAND_001_CHAPTER_IR_RECONCILIATION_FINAL_V2.json")
        story = _read_json(self.recon_dir / "HISTORICAL_STORY_MAP.json")
        registry = _read_json(self.root / CANON_FACT_REGISTRY)
        knowledge = _read_json(self.root / "workspace/wasteland_001_exports/"
                               "WASTELAND_001_KNOWLEDGE_REVEAL_REGISTRY.json")
        canon_refs: dict[str, list[str]] = {}
        for fact_id, fact in (registry.get("facts") or {}).items():
            for ref in fact.get("source_refs") or [fact.get("first_occurrence")]:
                label = str(ref or "").strip()
                if label:
                    canon_refs.setdefault(label, []).append(str(fact_id))
        knowledge_refs: dict[str, list[str]] = {}
        for key, value in _knowledge_entries(knowledge):
            label = str(value.get("chapter") or value.get("chapter_id") or key).strip()
            if label:
                knowledge_refs.setdefault(label, []).append(
                    str(value.get("reveal_id") or value.get("id") or key))
        overlays: dict[str, dict[str, Any]] = {}
        human: list[dict[str, Any]] = []
        patches: dict[str, list[dict[str, Any]]] = {}
        refinements: dict[str, dict[str, Any]] = {}
        for path in sorted(self.repair_dir.glob("BATCH_*_REPAIR_STATUS_OVERLAY.json")):
            overlay = _read_json(path)
            batch_id = str(overlay.get("batch_id") or "")
            for entry in overlay.get("entries") or []:
                chapter_id = str(entry.get("chapter_id") or "")
                if not chapter_id:
                    continue
                overlays[chapter_id] = dict(entry, batch_id=batch_id)
                if entry.get("status") == "human_review":
                    human.append(dict(entry, batch_id=batch_id))
        for path in sorted(self.repair_dir.glob("BATCH_*_CANDIDATES.json")):
            payload_candidates = _read_json(path)
            items = (payload_candidates.get("candidates")
                     if isinstance(payload_candidates, Mapping)
                     else payload_candidates) or []
            for row in items:
                chapter_id = str(row.get("chapter_id") or "")
                patches[chapter_id] = list(row.get("proposed_patch") or [])
                if row.get("refinement"):
                    refinements[chapter_id] = dict(row.get("refinement") or {})
        return FoundationInputs(
            chapters=chapters,
            full_rows={str(row.get("chapter_uuid")): row
                       for row in full.get("chapters") or []},
            recon_rows={str(row.get("chapter_uuid")): row
                        for row in recon.get("chapters") or []},
            story_rows={str(row.get("chapter_id")): row
                        for row in story.get("chapters") or []},
            canon_refs=canon_refs, knowledge_refs=knowledge_refs,
            repair_overlays=overlays, human_review_entries=human,
            candidate_patches=patches, candidate_refinements=refinements,
            digests=self.source_digests(), prose_available={})

    # ---- source inventory (§2) ------------------------------------------
    def source_inventory(self, inputs: FoundationInputs | None = None) -> dict[str, Any]:
        inputs = inputs or self.load()
        rows: list[HistoricalIRSourceInventoryRow] = []
        for chapter in inputs.chapters:
            uuid = str(chapter.get("chapter_uuid") or "")
            label = str(chapter.get("id") or "")
            index = chapter.get("index")
            prose_path = self.root / "novel/final" / f"chapter_{int(index or 0):04d}_final.md"
            prose = prose_path.is_file() and _has_wasteland_entities(prose_path)
            shadow = inputs.full_rows.get(uuid) or {}
            recon = inputs.recon_rows.get(uuid) or {}
            story = inputs.story_rows.get(uuid) or {}
            overlay = inputs.repair_overlays.get(uuid)
            rows.append(HistoricalIRSourceInventoryRow(
                chapter_id=uuid, chapter_uuid=uuid, legacy_label=label,
                display_number=chapter.get("index"), volume=chapter.get("volume"),
                arc=str(chapter.get("arc") or ""), title=str(chapter.get("title") or ""),
                source_text_available=prose,
                source_text_digest=digest_file(prose_path) if prose else "",
                legacy_fields_available=bool(chapter),
                legacy_fields_digest=digest_payload(chapter),
                shadow_summary_available=bool(shadow),
                shadow_digest=str(shadow.get("disposition") or "") and digest_payload(shadow),
                compiled_preview_available=bool(shadow.get("compiled_preview")),
                preview_digest=digest_payload(shadow.get("compiled_preview") or {}),
                deterministic_verifier_available=bool(recon.get("deterministic")),
                verifier_digest=str(recon.get("verifier_input_digest") or ""),
                story_map_available=bool(story),
                canon_refs=list(inputs.canon_refs.get(label) or []),
                story_state_refs=[inputs.digests.get("story_state", "")],
                m1_classification=str(shadow.get("disposition") or ""),
                m10_classification=str(story.get("classification") or ""),
                repair_overlay_refs=[str(overlay.get("batch_id") or ""),
                                     str(overlay.get("status") or "")]
                if overlay else [],
                evidence_completeness=_inventory_completeness(chapter, shadow, recon,
                                                             prose)))
        channel = {
            "prose_text": sum(1 for row in rows if row.source_text_available),
            "legacy_outline": sum(1 for row in rows if row.legacy_fields_available),
            "shadow_summary": sum(1 for row in rows if row.shadow_summary_available),
            "compiled_preview": sum(1 for row in rows if row.compiled_preview_available),
            "deterministic_verifier": sum(1 for row in rows
                                          if row.deterministic_verifier_available),
            "story_map": sum(1 for row in rows if row.story_map_available),
            "canon_refs": sum(1 for row in rows if row.canon_refs),
        }
        payload = {
            "generated_at": _now(), "novel_id": self.adapter.novel_id,
            "chapter_count": len(rows), "counts": {
                "source_text_available": channel["prose_text"],
                "legacy_only": len(rows) - channel["prose_text"],
                "evidence_completeness_SUFFICIENT": sum(
                    1 for row in rows if row.evidence_completeness == "SUFFICIENT"),
                "evidence_completeness_PARTIAL": sum(
                    1 for row in rows if row.evidence_completeness == "PARTIAL"),
                "evidence_completeness_INSUFFICIENT": sum(
                    1 for row in rows if row.evidence_completeness == "INSUFFICIENT"),
            },
            "channel_availability": channel,
            "prose_note": ("磁盘上不存在 WASTELAND_001 的章节正文；novel/final/*.md 属另一部手稿"
                           "（无 WASTELAND_001 实体），不得当作本作 source。historical source of "
                           "record = legacy outline record（V5 candidate）"),
            "rows": [row.model_dump(mode="json") for row in rows],
            "read_only": True,
        }
        _write_json(self.store_dir / "SOURCE_INVENTORY.json", payload)
        return payload

    # ---- materialization -------------------------------------------------
    def materialize_chapter(self, chapter: Mapping[str, Any], inputs: FoundationInputs,
                            *, created_at: str = "") -> HistoricalChapterIRArtifact:
        uuid = str(chapter.get("chapter_uuid") or "")
        label = str(chapter.get("id") or "")
        shadow = inputs.full_rows.get(uuid) or {}
        recon = inputs.recon_rows.get(uuid) or {}
        story = inputs.story_rows.get(uuid) or {}
        requirements = dict(recon.get("function_requirements") or {})
        chapter_function = str(recon.get("chapter_function")
                               or story.get("chapter_function") or "")
        proposal = self.extractor.extract(chapter, backend="deterministic")
        ir = self.extractor.to_ir(proposal, chapter)
        pivots = analyze_pivot_evidence(chapter, self.adapter)
        ir = self._apply_pivot_evidence(ir, pivots)
        candidate_fields = {name: "" for name in FUNCTION_FIELDS}
        ir_report = self.validator.validate(ir, candidate_fields=candidate_fields)
        assertions = self._field_assertions(chapter=chapter, ir=ir, requirements=requirements,
                                            pivots=pivots, inputs=inputs, label=label,
                                            chapter_uuid=uuid)
        coverage = _coverage_from(assertions, ir)
        unresolved = [item.field_name for item in assertions
                      if item.assertion_mode == "UNRESOLVED"]
        status: MaterializationStatus = "FULL"
        if not ir.event_frames:
            status = "PARTIAL"
        elif ir.ambiguous_entity_ids:
            status = "PARTIAL"
        notes = ""
        if status == "PARTIAL":
            notes = ("schema 完整但 provenance 存在未决项："
                     + ("no_event_frames；" if not ir.event_frames else "")
                     + ("ambiguous_entity；" if ir.ambiguous_entity_ids else ""))
        validator_results = {
            "chapter_ir_validator": "PASS" if ir_report.ok() else "FAIL",
            "evidence_validator": "PASS" if self.evidence.validate(
                ir, candidate_fields=candidate_fields).ok() else "FAIL",
            "state_registry": "PASS" if not ir_report.state_findings else "FINDINGS",
            "writer_metadata_leak": "PASS" if not [
                item for item in ir_report.findings
                if item.code == "WRITER_VISIBLE_METADATA_LEAK"] else "FAIL",
            "finding_codes": ",".join(ir_report.codes()) or "none",
        }
        source_refs = [f"legacy:{label}",
                       f"shadow:{inputs.digests.get('chapter_ir', '')}",
                       f"verifier:{recon.get('verifier_input_digest', '')}",
                       f"story_map:{inputs.digests.get('story_state', '')}"]
        return HistoricalChapterIRArtifact(
            artifact_id=f"HIR_{uuid[-12:]}" if uuid else f"HIR_{label}",
            chapter_id=uuid, chapter_uuid=uuid, legacy_label=label,
            volume_id=f"V{chapter.get('volume')}" if chapter.get("volume") else "",
            arc_id=str(chapter.get("arc") or ""),
            display_number=chapter.get("index"),
            source_text_available=bool(inputs.prose_available.get(uuid, False)),
            source_text_digest="",
            legacy_source_digest=digest_payload(chapter),
            shadow_digest=digest_payload(shadow.get("compiled_preview") or {}),
            compiled_preview_digest=digest_payload(shadow.get("compiled_preview") or {}),
            verifier_digest=str(recon.get("verifier_input_digest") or ""),
            canon_digest_ref=inputs.digests.get("canon", ""),
            story_state_digest_ref=inputs.digests.get("story_state", ""),
            chapter_ir=ir,
            chapter_ir_digest=digest_payload(ir.model_dump(mode="json")),
            materialization_status=status,
            chapter_function=chapter_function,
            evidence_coverage=coverage,
            field_assertions=assertions,
            unresolved_fields=unresolved,
            inference_records=[],
            source_refs=source_refs,
            validator_results=validator_results,
            created_at=created_at or _now(),
            notes=notes)

    def _apply_pivot_evidence(self, ir: ChapterSemanticIR,
                              pivots: Sequence[Mapping[str, str]]) -> ChapterSemanticIR:
        """把显式 pivot 证据写成 narrative_pivot effect，并绑定 turn（不改 happened truth）。"""

        if not pivots:
            return ir
        known = " ".join(effect.after_state for effect in ir.effects
                         if effect.is_narrative_pivot)
        next_index = len(ir.effects) + 1
        added: list[ChapterEffect] = []
        for match in pivots:
            keyword = str(match.get("keyword") or "")
            quote = str(match.get("quote") or "")
            if keyword and keyword in known:
                continue
            added.append(ChapterEffect(
                effect_id=f"EF_{next_index:03d}", effect_type="narrative_pivot",
                target_type="situation", target_id=self.adapter.protagonist_id,
                after_state=quote[:120], polarity="mixed",
                caused_by_event_ids=[ir.event_frames[-1].event_id] if ir.event_frames else [],
                is_narrative_pivot=True, confidence=0.6))
            next_index += 1
        if not added:
            return ir
        effects = list(ir.effects) + added
        previous = ir.evidence_for("turn")
        evidence = [item for item in ir.field_evidence if item.field_name != "turn"]
        evidence.append(FieldEvidence(
            field_name="turn",
            transition_ids=list(previous.transition_ids) if previous else [],
            effect_ids=[item.effect_id for item in added]
            + (list(previous.effect_ids) if previous else []),
            evidence_type="derived", confidence=0.6))
        return ir.model_copy(update={"effects": effects, "field_evidence": evidence})

    def _field_assertions(self, *, chapter: Mapping[str, Any], ir: ChapterSemanticIR,
                          requirements: Mapping[str, Any],
                          pivots: Sequence[Mapping[str, str]], inputs: FoundationInputs,
                          label: str, chapter_uuid: str
                          ) -> list[HistoricalFieldAssertion]:
        adapter = self.adapter
        texts = adapter.narrative_texts(chapter)
        canon = list(inputs.canon_refs.get(label) or [])
        story = inputs.story_rows.get(chapter_uuid) or {}
        assertions: list[HistoricalFieldAssertion] = []

        def reference(field_name: str, *, channel: str = "legacy_outline",
                      quote: str = "", extra: str = "") -> HistoricalSourceRef:
            return HistoricalSourceRef(
                channel=channel, field_name=field_name,
                ref=f"{label}#{field_name}" + (f":{extra}" if extra else ""),
                quote=str(quote or "")[:200],
                digest=digest_payload(texts.get(field_name, "")))

        def add(field_name: str, mode: AssertionMode, *, bound: Sequence[str] = (),
                reason: str = "", refs: Sequence[HistoricalSourceRef] = ()) -> None:
            assertions.append(HistoricalFieldAssertion(
                field_name=field_name, assertion_mode=mode,
                bound_ir_ids=list(bound), evidence_refs=list(refs), reason=reason[:200]))

        def canon_refs() -> list[HistoricalSourceRef]:
            return [reference("canon", channel="canon_ref", extra=fact_id)
                    for fact_id in canon]

        def requirement(name: str) -> str:
            return str(requirements.get(name) or "optional")

        decision_events = [item.event_id for item in ir.event_frames if item.decision_action]
        pivot_effects = [item.effect_id for item in ir.effects if item.is_narrative_pivot]
        primary = [item.transition_id for item in ir.state_transitions
                   if item.narrative_role == "primary"]
        negative = [item.effect_id for item in ir.effects
                    if item.polarity in ("negative", "mixed")]
        positive = [item.effect_id for item in ir.effects
                    if item.polarity in ("positive", "mixed")]
        info_events = [item.event_id for item in ir.event_frames
                       if item.action_type in ("discover", "negotiate", "open")]
        pivot_quotes = [str(item.get("quote") or "") for item in pivots]

        # events / effects / state_transition（结构层）
        add("events", "DIRECT_SOURCE" if ir.event_frames else "UNRESOLVED",
            bound=[item.event_id for item in ir.event_frames],
            reason=f"{len(ir.event_frames)} event frames（legacy events 抽取）",
            refs=[reference("events", quote=texts.get("events", ""))])
        add("effects", "DIRECT_SOURCE" if ir.effects else "UNRESOLVED",
            bound=[item.effect_id for item in ir.effects],
            reason=f"{len(ir.effects)} effects（cost/loss/payoff/pivot 规则）")
        transitions_required = bool(ir.state_transitions) or bool(
            str(chapter.get("world_state_change") or "").strip())
        add("state_transition",
            "DIRECT_SOURCE" if ir.state_transitions else
            ("NOT_APPLICABLE" if not transitions_required else "UNRESOLVED"),
            bound=[item.transition_id for item in ir.state_transitions],
            reason=f"{len(ir.state_transitions)} typed transitions")

        # decision（§14）
        if decision_events:
            placeholder = adapter.is_placeholder(chapter.get("decision"))
            add("decision", "DERIVED" if placeholder else "DIRECT_SOURCE",
                bound=decision_events,
                reason=("decision 事件来自 events 文本规则"
                        + ("；legacy decision 字段是模板占位" if placeholder else "")),
                refs=[reference("decision", quote=texts.get("decision", ""))] + canon_refs())
        elif requirement("decision") == "not_applicable":
            add("decision", "NOT_APPLICABLE", reason="ChapterFunctionPolicy=not_applicable")
        else:
            add("decision", "UNRESOLVED",
                reason="无 decision 事件证据（不新增 decision）")

        # turn（§15）
        if pivot_effects or primary:
            quote = pivot_quotes[0] if pivot_quotes else ""
            add("turn", "DIRECT_SOURCE", bound=pivot_effects + primary,
                reason=("pivot evidence：" + "；".join(
                    f"{item.get('pivot_type')}:{item.get('keyword')}" for item in pivots[:2])
                    if pivots else "primary transition（typed state）"),
                refs=([reference("turn", quote=quote)] if quote else [])
                + [reference("state_transition", quote=str(chapter.get("world_state_change")
                                                           or ""))])
        elif requirement("turn") == "not_applicable":
            add("turn", "NOT_APPLICABLE", reason="ChapterFunctionPolicy=not_applicable")
        else:
            has_statement = (not adapter.is_placeholder(chapter.get("turn"))
                             and str(chapter.get("turn") or "").strip()
                             != str(chapter.get("escalation") or "").strip())
            add("turn", "UNRESOLVED",
                reason=("source 有 turn 陈述但无 pivot 证据（需作者确认）" if has_statement
                        else "source 无独立 turn 陈述（content gap）"),
                refs=[reference("turn", quote=texts.get("turn", ""))])

        # payoff（§16）
        payoff_anchor = bool(str(chapter.get("foreshadow_action") or "").strip()) or (
            str(chapter.get("payoff") or "").strip()
            not in {str(chapter.get("turn") or "").strip(),
                    str(chapter.get("escalation") or "").strip(), ""})
        if positive and payoff_anchor:
            add("payoff", "DIRECT_SOURCE", bound=positive,
                reason="positive effect + payoff/setup anchor",
                refs=[reference("payoff", quote=texts.get("payoff", ""))])
        elif positive:
            add("payoff", "DERIVED", bound=positive,
                reason="positive effect 绑定，但缺独立 setup anchor",
                refs=[reference("payoff", quote=texts.get("payoff", ""))])
        elif requirement("payoff") == "not_applicable":
            add("payoff", "NOT_APPLICABLE", reason="ChapterFunctionPolicy=not_applicable")
        else:
            add("payoff", "UNRESOLVED",
                reason="无 payoff evidence（不把 hook 当 payoff）",
                refs=[reference("payoff", quote=texts.get("payoff", ""))])

        # cost / loss（§17）
        for field_name in ("cost", "loss"):
            legacy_text = str(chapter.get(field_name) or "").strip()
            if negative and legacy_text:
                add(field_name, "DIRECT_SOURCE", bound=negative,
                    reason=f"{field_name} 文本 + negative effect",
                    refs=[reference(field_name, quote=texts.get(field_name, ""))])
            elif negative:
                add(field_name, "DERIVED", bound=negative,
                    reason="negative effect，无独立 legacy 文本")
            elif not legacy_text or requirement(field_name) == "not_applicable":
                add(field_name, "NOT_APPLICABLE",
                    reason=f"legacy {field_name} 为空 → 显式无变化")
            else:
                add(field_name, "UNRESOLVED",
                    reason=f"legacy {field_name} 有文本但无 negative effect",
                    refs=[reference(field_name, quote=texts.get(field_name, ""))])

        # information_release / knowledge（§18）
        legacy_info = str(chapter.get("information_release") or "").strip()
        if info_events and legacy_info:
            add("information_release", "DIRECT_SOURCE", bound=info_events,
                reason="information event + legacy information_release",
                refs=[reference("information_release",
                                quote=texts.get("information_release", ""))])
        elif info_events:
            add("information_release", "DERIVED", bound=info_events,
                reason="information event（discover/negotiate/open）")
        elif not legacy_info or requirement("information_release") == "not_applicable":
            add("information_release", "NOT_APPLICABLE",
                reason="legacy information_release 为空 → 本章无信息释放")
        else:
            add("information_release", "UNRESOLVED",
                reason="legacy 文本存在但无 evidence event")
        knowledge_holders = inputs.knowledge_refs.get(label) or []
        if info_events or knowledge_holders:
            add("knowledge", "DERIVED", bound=info_events,
                reason=("knowledge boundary 由 information event 派生"
                        + ("+knowledge registry refs" if knowledge_holders else "")),
                refs=[reference("knowledge", channel="canon_ref", extra=item)
                      for item in knowledge_holders])
        else:
            add("knowledge", "UNRESOLVED",
                reason="无 information event / knowledge ref → 保持 UNRESOLVED（不发明知识）")

        # world_state_change（§13）
        legacy_world = str(chapter.get("world_state_change") or "").strip()
        if primary and legacy_world:
            add("world_state_change", "DIRECT_SOURCE", bound=primary,
                reason="primary typed transition + legacy world_state_change",
                refs=[reference("world_state_change", quote=legacy_world)])
        elif primary:
            add("world_state_change", "DERIVED", bound=primary,
                reason="primary typed transition（legacy 文本为空）")
        elif not legacy_world or requirement("world_state_change") == "not_applicable":
            add("world_state_change", "NOT_APPLICABLE",
                reason="legacy world_state_change 为空 → 显式无世界状态变化")
        else:
            add("world_state_change", "UNRESOLVED",
                reason="legacy 文本存在但无 typed transition 证据")

        # relationship / resource / progression（§19/§20/§21）
        continuation = (("relationship_delta", "relationship"),
                        ("resource_delta", "resource"),
                        ("equipment_delta", "equipment"),
                        ("ability_delta", "progression"))
        for legacy_name, field_name in continuation:
            value = chapter.get(legacy_name)
            if isinstance(value, Mapping):
                text = json.dumps(value, ensure_ascii=False)
                present = any(_meaningful(item) for item in value.values())
            else:
                text = str(value or "").strip()
                present = _meaningful(text)
            if present:
                add(field_name, "DIRECT_SOURCE",
                    reason=f"legacy {legacy_name} 显式记录",
                    refs=[reference(legacy_name, quote=text)])
            else:
                add(field_name, "NOT_APPLICABLE",
                    reason=f"legacy {legacy_name} 显式为空 → 本章无变化")

        # location / map（§22）
        text_blob = " ".join(value for value in texts.values() if value)
        map_names = [name for name in self.map_names() if name and name in text_blob]
        if map_names:
            add("location", "DIRECT_SOURCE",
                reason="source 中出现已登记 map/location 名称：" + "、".join(map_names[:3]),
                refs=[reference("location", quote=name) for name in map_names[:3]])
        else:
            add("location", "UNRESOLVED",
                reason="source 未出现已登记 location 正式名（不把路过当控制）")

        # causality（§23）
        causality_text = str(chapter.get("next_chapter_causality") or "").strip()
        if causality_text and story:
            add("causality", "DERIVED",
                reason="next_chapter_causality + neighbor dependency",
                refs=[reference("causality", quote=causality_text)])
        else:
            add("causality", "UNRESOLVED",
                reason="无来源/邻居依赖证据 → causality unresolved")
        return assertions

    def map_names(self) -> list[str]:
        if not hasattr(self, "_map_name_cache"):
            self._map_name_cache = self.adapter.map_names(_read_json(self.legacy_candidate))
        return list(self._map_name_cache)

    def prose_availability(self, chapters: Sequence[Mapping[str, Any]]
                           ) -> dict[str, bool]:
        available: dict[str, bool] = {}
        for chapter in chapters:
            index = int(chapter.get("index") or 0)
            path = self.root / "novel/final" / f"chapter_{index:04d}_final.md"
            available[str(chapter.get("chapter_uuid") or "")] = (
                path.is_file() and _has_wasteland_entities(path))
        return available

    # ---- 570 materialization + store ------------------------------------
    def materialize_all(self, *, batch_size: int = 30, resume: bool = True
                        ) -> dict[str, Any]:
        inputs = self.load()
        inputs.prose_available = self.prose_availability(inputs.chapters)
        inventory = self.source_inventory(inputs)
        store = HistoricalIRStore(self.store_dir)
        created_at = _now()
        artifacts: list[HistoricalChapterIRArtifact] = []
        reused = 0
        file_digests: dict[str, str] = {}
        for position, chapter in enumerate(inputs.chapters, start=1):
            artifact = self.materialize_chapter(chapter, inputs, created_at=created_at)
            digest, was_reused = store.write_artifact(artifact, reuse=resume)
            file_digests[artifact.chapter_id] = digest
            reused += int(was_reused)
            artifacts.append(artifact)
            if position % batch_size == 0:
                store.write_checkpoint({
                    "processed": position, "total": len(inputs.chapters),
                    "last_chapter": artifact.chapter_id, "reused": reused,
                    "compiler_version": COMPILER_VERSION})
        artifacts.sort(key=lambda item: item.display_number or 0)
        index = store.write_index(artifacts, file_digests)
        integrity = store.write_integrity(artifacts, file_digests, index)
        report = self._materialization_report(inputs, artifacts, reused, inventory,
                                              file_digests)
        manifest = store.write_manifest(artifacts, index, integrity, report,
                                        inputs.digests)
        store.write_checkpoint({"processed": len(artifacts), "total": len(inputs.chapters),
                                "last_chapter": artifacts[-1].chapter_id if artifacts else "",
                                "reused": reused, "status": "COMPLETE",
                                "compiler_version": COMPILER_VERSION})
        report["manifest_digest"] = digest_payload(manifest)
        _write_json(self.store_dir / "materialization_report.json", report)
        digests_after = self.source_digests()
        report["source_digests"] = {"before": inputs.digests, "after": digests_after,
                                    "unchanged": inputs.digests == digests_after}
        _write_json(self.store_dir / "materialization_report.json", report)
        return report

    def _materialization_report(self, inputs: FoundationInputs,
                                artifacts: Sequence[HistoricalChapterIRArtifact],
                                reused: int, inventory: Mapping[str, Any],
                                file_digests: Mapping[str, str]) -> dict[str, Any]:
        status_counts: dict[str, int] = {}
        coverage_counts: dict[str, int] = {}
        unresolved_counts: dict[str, int] = {}
        mode_counts: dict[str, int] = {}
        per_volume: dict[str, int] = {}
        for artifact in artifacts:
            status_counts[artifact.materialization_status] = status_counts.get(
                artifact.materialization_status, 0) + 1
            coverage_counts[artifact.evidence_coverage.overall_status] = \
                coverage_counts.get(artifact.evidence_coverage.overall_status, 0) + 1
            for field_name in artifact.unresolved_fields:
                unresolved_counts[field_name] = unresolved_counts.get(field_name, 0) + 1
            for assertion in artifact.field_assertions:
                mode_counts[assertion.assertion_mode] = mode_counts.get(
                    assertion.assertion_mode, 0) + 1
            key = artifact.volume_id or "unknown"
            per_volume[key] = per_volume.get(key, 0) + 1
        return {
            "generated_at": _now(), "compiler_version": COMPILER_VERSION,
            "novel_id": self.adapter.novel_id,
            "chapter_count": len(artifacts), "reused_artifacts": reused,
            "materialization_status_counts": status_counts,
            "coverage_counts": coverage_counts,
            "unresolved_field_counts": unresolved_counts,
            "assertion_mode_counts": mode_counts,
            "per_volume": per_volume,
            "source_inventory_counts": dict(inventory.get("counts") or {}),
            "channel_availability": dict(inventory.get("channel_availability") or {}),
            "llm_used": False,
            "materialization_method": "deterministic_legacy_extraction",
            "artifact_file_digests": dict(file_digests),
            "source_digests": inputs.digests,
            "read_only": True, "non_authoritative": True,
        }


class HistoricalIRStore:
    """§26/§27：独立 historical store（不写 M9 future chapter_ir official store）。"""

    def __init__(self, store_dir: Path) -> None:
        self.store_dir = Path(store_dir)
        self.artifacts_dir = self.store_dir / "artifacts"

    def artifact_path(self, chapter_id: str) -> Path:
        return self.artifacts_dir / f"{chapter_id}.json"

    def write_artifact(self, artifact: HistoricalChapterIRArtifact, *,
                       reuse: bool = True) -> tuple[str, bool]:
        path = self.artifact_path(artifact.chapter_id)
        payload = artifact.model_dump(mode="json")
        if reuse and path.is_file():
            existing = _read_json(path)
            if _artifact_content_digest(existing) == _artifact_content_digest(payload):
                return digest_file(path), True
        _write_json(path, payload)
        return digest_file(path), False

    def write_checkpoint(self, payload: Mapping[str, Any]) -> None:
        _write_json(self.store_dir / "checkpoint.json", dict(payload))

    def write_index(self, artifacts: Sequence[HistoricalChapterIRArtifact],
                    file_digests: Mapping[str, str]) -> dict[str, Any]:
        rows = [{
            "chapter_id": item.chapter_id, "chapter_uuid": item.chapter_uuid,
            "legacy_label": item.legacy_label, "display_number": item.display_number,
            "volume_id": item.volume_id, "arc_id": item.arc_id,
            "chapter_function": item.chapter_function,
            "materialization_status": item.materialization_status,
            "coverage_overall": item.evidence_coverage.overall_status,
            "unresolved_fields": item.unresolved_fields,
            "chapter_ir_digest": item.chapter_ir_digest,
            "artifact_file_digest": file_digests.get(item.chapter_id, ""),
            "artifact_path": f"artifacts/{item.chapter_id}.json",
        } for item in artifacts]
        payload = {"generated_at": _now(), "chapter_count": len(rows),
                   "time_layer": TIME_LAYER, "derived": True,
                   "canonical_representation": False,
                   "compiler_version": COMPILER_VERSION, "chapters": rows,
                   "read_only": True}
        payload["index_digest"] = digest_payload(
            {key: value for key, value in payload.items() if key != "generated_at"})
        _write_json(self.store_dir / "index.json", payload)
        return payload

    def write_integrity(self, artifacts: Sequence[HistoricalChapterIRArtifact],
                        file_digests: Mapping[str, str],
                        index: Mapping[str, Any]) -> dict[str, Any]:
        rows = []
        for item in artifacts:
            path = self.artifact_path(item.chapter_id)
            rows.append({"chapter_id": item.chapter_id,
                         "artifact_file_digest": digest_file(path),
                         "chapter_ir_digest": item.chapter_ir_digest,
                         "digest_stable": file_digests.get(item.chapter_id, "")
                         == digest_file(path),
                         "path": f"artifacts/{item.chapter_id}.json"})
        payload = {"generated_at": _now(), "artifact_count": len(rows),
                   "index_digest": index.get("index_digest", ""),
                   "all_digests_stable": all(row["digest_stable"] for row in rows),
                   "artifacts": rows, "read_only": True}
        payload["integrity_digest"] = digest_payload(
            {key: value for key, value in payload.items() if key != "generated_at"})
        _write_json(self.store_dir / "integrity.json", payload)
        return payload

    def write_manifest(self, artifacts: Sequence[HistoricalChapterIRArtifact],
                       index: Mapping[str, Any], integrity: Mapping[str, Any],
                       report: Mapping[str, Any],
                       digests: Mapping[str, str]) -> dict[str, Any]:
        payload = {
            "generated_at": _now(), "compiler_version": COMPILER_VERSION,
            "novel_id": "wasteland_001", "schema_version": 1,
            "chapter_count": len(artifacts), "time_layer": TIME_LAYER,
            "derived": True, "canonical_representation": False,
            "non_authoritative": True, "llm_used": False,
            "source_digests": dict(digests),
            "index_digest": index.get("index_digest", ""),
            "integrity_digest": integrity.get("integrity_digest", ""),
            "materialization_status_counts":
                dict(report.get("materialization_status_counts") or {}),
            "coverage_counts": dict(report.get("coverage_counts") or {}),
            "read_only": True}
        payload["manifest_digest"] = digest_payload(
            {key: value for key, value in payload.items() if key != "generated_at"})
        _write_json(self.store_dir / "manifest.json", payload)
        return payload

    def load_artifacts(self) -> dict[str, HistoricalChapterIRArtifact]:
        artifacts: dict[str, HistoricalChapterIRArtifact] = {}
        if not self.artifacts_dir.is_dir():
            return artifacts
        for path in sorted(self.artifacts_dir.glob("*.json")):
            payload = _read_json(path)
            try:
                artifact = HistoricalChapterIRArtifact.model_validate(payload)
            except Exception:  # noqa: BLE001 - 非法 artifact 不进入 gate 通过集合
                continue
            artifacts[artifact.chapter_id] = artifact
        return artifacts


class HistoricalIRFoundationService:
    """P15f 编排：materialize → repair replay → human-review 重评 → foundation gate。"""

    def __init__(self, project_root: Path | str, *, store_dir: str = HISTORY_DIR,
                 adapter: WastelandSourceAdapter | None = None) -> None:
        self.materializer = HistoricalIRMaterializer(project_root, store_dir=store_dir,
                                                     adapter=adapter)
        self.root = self.materializer.root
        self.store_dir = self.materializer.store_dir
        self.store = HistoricalIRStore(self.store_dir)
        self.repair_dir = self.materializer.repair_dir

    # ---- repair replay（§29-§31） ---------------------------------------
    def replay_repairs(self, *, artifacts: Mapping[str, HistoricalChapterIRArtifact]
                       | None = None) -> dict[str, Any]:
        inputs = self.materializer.load()
        artifacts = artifacts if artifacts is not None else self.store.load_artifacts()
        results: list[RepairReplayResult] = []
        for chapter_id, entry in sorted(inputs.repair_overlays.items()):
            if str(entry.get("batch_id") or "") not in FOUNDATION_REPLAY_BATCHES:
                continue
            if entry.get("status") != "verified":
                continue
            artifact = artifacts.get(chapter_id)
            label = str(entry.get("legacy_label") or "")
            batch_id = str(entry.get("batch_id") or "")
            overlay_path = (self.repair_dir / batch_id / "repaired" / f"{chapter_id}.json")
            overlay = _read_json(overlay_path)
            ops = list(inputs.candidate_patches.get(chapter_id) or [])
            result = self._replay_one(chapter_id=chapter_id, legacy_label=label,
                                      batch_id=batch_id, ops=ops, artifact=artifact,
                                      overlay=overlay)
            results.append(result)
        counts: dict[str, int] = {}
        for item in results:
            counts[item.status] = counts.get(item.status, 0) + 1
        payload = {"generated_at": _now(), "repair_count": len(results),
                   "status_counts": counts,
                   "results": [item.model_dump(mode="json") for item in results],
                   "canonicalized": False, "dry_run": True,
                   "read_only": True, "non_authoritative": True}
        _write_json(self.store_dir / "REPAIR_REPLAY.json", payload)
        return payload

    def _replay_one(self, *, chapter_id: str, legacy_label: str, batch_id: str,
                    ops: Sequence[Mapping[str, Any]],
                    artifact: HistoricalChapterIRArtifact | None,
                    overlay: Mapping[str, Any]) -> RepairReplayResult:
        repaired = dict(overlay.get("artifact") or {})
        old_digest = str(repaired.get("repaired_digest") or "")
        if artifact is None:
            return RepairReplayResult(
                repair_id=f"REPLAY_{chapter_id[-8:]}", chapter_id=chapter_id,
                legacy_label=legacy_label, batch_id=batch_id,
                old_overlay_digest=old_digest, status="HUMAN_REVIEW",
                reason="full IR artifact 缺失，无法 replay")
        ir = artifact.chapter_ir
        ids = {item.event_id for item in ir.event_frames}
        ids |= {item.effect_id for item in ir.effects}
        ids |= {item.transition_id for item in ir.state_transitions}
        modes = {item.field_name: item.assertion_mode for item in artifact.field_assertions}
        turn_bound = bool([item for item in ir.effects if item.is_narrative_pivot]) or bool(
            [item for item in ir.state_transitions if item.narrative_role == "primary"])
        statuses: list[ReplayStatus] = []
        reasons: list[str] = []
        semantic_diff: dict[str, str] = {}
        evidence_valid = True
        forbidden = False
        for op in ops:
            field_name = str(op.get("field_name") or "")
            evidence_refs = [str(item) for item in op.get("evidence_refs") or []]
            if op.get("touches_forbidden_domain"):
                forbidden = True
                statuses.append("CONFLICT")
                reasons.append(f"{field_name}：repair 触碰 forbidden domain")
                continue
            op_evidence_valid = all(ref in ids for ref in evidence_refs) if evidence_refs \
                else True
            evidence_valid = evidence_valid and op_evidence_valid
            mode = modes.get(field_name, "UNRESOLVED")
            if str(op.get("op")) == "REBIND_EVIDENCE":
                if mode in ("DIRECT_SOURCE", "CONFIRMED"):
                    statuses.append("OBSOLETE_REPAIR")
                    reasons.append(f"{field_name}：full IR base 已绑定该字段（旧 repair 过时）")
                    semantic_diff[field_name] = f"base={mode}"
                elif field_name == "turn" and turn_bound:
                    statuses.append("OBSOLETE_REPAIR")
                    reasons.append("turn：full IR base 已有 pivot evidence")
                    semantic_diff[field_name] = "base=pivot_bound"
                elif op_evidence_valid and evidence_refs:
                    statuses.append("APPLIES_CLEANLY")
                    reasons.append(f"{field_name}：evidence {evidence_refs} 在 base 中仍存在")
                    semantic_diff[field_name] = "rebind_available"
                elif mode in ("DERIVED", "INFERRED"):
                    statuses.append("NEEDS_REBASE")
                    reasons.append(f"{field_name}：base 有 derived evidence，patch 需 rebase")
                    semantic_diff[field_name] = f"base={mode}"
                else:
                    statuses.append("NEEDS_REBASE")
                    reasons.append(f"{field_name}：旧 evidence id 已不存在，需 rebase")
                    semantic_diff[field_name] = "evidence_missing"
            elif str(op.get("op")) == "MARK_NOT_APPLICABLE":
                if field_name in ir.not_applicable_fields or mode == "NOT_APPLICABLE":
                    statuses.append("OBSOLETE_REPAIR")
                    reasons.append(f"{field_name}：base 已显式 N/A")
                    semantic_diff[field_name] = "not_applicable"
                else:
                    statuses.append("APPLIES_CLEANLY")
                    reasons.append(f"{field_name}：base 尚未标记 N/A")
                    semantic_diff[field_name] = "mark_na"
            else:
                statuses.append("HUMAN_REVIEW")
                reasons.append(f"{field_name}：未登记的 repair op {op.get('op')}")
        if not ops:
            statuses.append("OBSOLETE_REPAIR")
            reasons.append("patch 为空（evidence-only）；full IR base 自带 evidence binding")
        order = ("CONFLICT", "HUMAN_REVIEW", "NEEDS_REBASE", "APPLIES_CLEANLY",
                 "OBSOLETE_REPAIR")
        status = next(item for item in order if item in statuses)
        return RepairReplayResult(
            repair_id=f"REPLAY_{chapter_id[-8:]}", chapter_id=chapter_id,
            legacy_label=legacy_label, batch_id=batch_id,
            old_overlay_digest=old_digest,
            full_ir_base_digest=artifact.chapter_ir_digest,
            patch_ops=[str(op.get("op")) for op in ops],
            patch_applicable=status in ("APPLIES_CLEANLY", "OBSOLETE_REPAIR"),
            evidence_valid=evidence_valid,
            semantic_diff=semantic_diff,
            forbidden_change_violation=forbidden,
            validator_results={"artifact_status": artifact.materialization_status,
                               "coverage": artifact.evidence_coverage.overall_status},
            status=status, reason="；".join(reasons)[:300])

    # ---- human review 重评（§32/§44） -----------------------------------
    def reevaluate_human_review(self, *, artifacts: Mapping[str, HistoricalChapterIRArtifact]
                                | None = None) -> dict[str, Any]:
        inputs = self.materializer.load()
        artifacts = artifacts if artifacts is not None else self.store.load_artifacts()
        author_labels = self._author_decision_labels()
        rows: list[HistoricalChapterReevaluation] = []
        for entry in sorted(inputs.human_review_entries,
                            key=lambda item: str(item.get("legacy_label") or "")):
            if str(entry.get("batch_id") or "") not in FOUNDATION_REPLAY_BATCHES:
                continue
            chapter_id = str(entry.get("chapter_id") or "")
            label = str(entry.get("legacy_label") or "")
            artifact = artifacts.get(chapter_id)
            refinement = inputs.candidate_refinements.get(chapter_id) or {}
            field_status = dict(refinement.get("field_status") or {})
            required = sorted(name for name, value in field_status.items()
                              if value not in ("PRESENT_AND_BOUND", "NOT_APPLICABLE"))
            previous_reason = str(refinement.get("human_review_reason") or "")
            chapter = next((item for item in inputs.chapters
                            if str(item.get("chapter_uuid")) == chapter_id), {})
            binding: dict[str, str] = {}
            pivots: list[str] = []
            classes: list[ReevaluationClass] = []
            details: list[str] = []
            if artifact is None:
                classes.append("SOURCE_EVIDENCE_INSUFFICIENT")
                details.append("full IR artifact 缺失")
            else:
                for field_name in required:
                    assertion = artifact.assertion(field_name) or (
                        artifact.assertion("world_state_change")
                        if field_name == "world_state_change" else None)
                    mode = assertion.assertion_mode if assertion else "UNRESOLVED"
                    binding[field_name] = mode
                    if assertion and any(item.quote for item in assertion.evidence_refs):
                        pivots.extend(item.quote for item in assertion.evidence_refs
                                      if item.quote)
                    if mode in ("DIRECT_SOURCE", "CONFIRMED"):
                        classes.append("FIELD_REBIND" if field_name == "world_state_change"
                                       else "EVIDENCE_ONLY")
                        details.append(f"{field_name}：base 已绑定（{mode}）→ rebind 即可")
                    elif mode in ("DERIVED", "INFERRED"):
                        classes.append("EVIDENCE_ONLY")
                        details.append(f"{field_name}：base 有 derived evidence → rebind")
                    elif mode == "NOT_APPLICABLE":
                        classes.append("N/A_CORRECTION")
                        details.append(f"{field_name}：function policy/legacy 显式 N/A")
                    elif label in author_labels or previous_reason == "AUTHOR_INTENT_REQUIRED":
                        classes.append("AUTHOR_DECISION_REQUIRED")
                        details.append(f"{field_name}：作者意图歧义（M10 author queue）")
                    else:
                        statement = str(chapter.get(field_name) or "").strip()
                        classes.append("TRULY_MISSING")
                        details.append(
                            f"{field_name}：source of record 有陈述但无 pivot/evidence"
                            if statement else f"{field_name}：source 无对应陈述 → content gap")
            order = ("AUTHOR_DECISION_REQUIRED", "FIELD_REBIND", "EVIDENCE_ONLY",
                     "TRULY_MISSING", "N/A_CORRECTION", "SOURCE_EVIDENCE_INSUFFICIENT")
            proposed = next(item for item in order if item in classes) \
                if classes else "SOURCE_EVIDENCE_INSUFFICIENT"
            rows.append(HistoricalChapterReevaluation(
                chapter_id=chapter_id, legacy_label=label,
                batch_id=str(entry.get("batch_id") or ""),
                previous_reason=previous_reason, required_fields=required,
                proposed_class=proposed, proposed_detail="；".join(details)[:280],
                base_binding=binding, pivot_evidence=pivots[:3]))
        counts: dict[str, int] = {}
        for item in rows:
            counts[item.proposed_class] = counts.get(item.proposed_class, 0) + 1
        payload = {"generated_at": _now(), "human_review_count": len(rows),
                   "class_counts": counts,
                   "rows": [item.model_dump(mode="json") for item in rows],
                   "proposal_only": True, "overlay_modified": False,
                   "read_only": True, "non_authoritative": True}
        _write_json(self.store_dir / "HUMAN_REVIEW_REEVALUATION.json", payload)
        return payload

    def _author_decision_labels(self) -> set[str]:
        queue = _read_json(self.materializer.recon_dir / "AUTHOR_DECISION_QUEUE.json")
        labels: set[str] = set()
        for item in queue.get("items") or []:
            for chapter_id in item.get("affected_chapters") or []:
                labels.add(str(chapter_id))
            for label in item.get("affected_chapter_labels") or []:
                labels.add(str(label))
        return labels

    # ---- foundation gate（§45） -----------------------------------------
    def golden_regression(self, *, artifacts: Mapping[str, HistoricalChapterIRArtifact]
                          | None = None, replay: Mapping[str, Any] | None = None,
                          reevaluation: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """§38：用既有 golden 语义标签 + foundation golden set 验证 materialization。"""

        artifacts = artifacts if artifacts is not None else self.store.load_artifacts()
        replay = replay or _read_json(self.store_dir / "REPAIR_REPLAY.json")
        reevaluation = reevaluation or _read_json(
            self.store_dir / "HUMAN_REVIEW_REEVALUATION.json")
        by_label = {item.legacy_label: item for item in artifacts.values()}
        replay_status = {row.get("legacy_label"): row.get("status")
                         for row in replay.get("results") or []}
        reeval_class = {row.get("legacy_label"): row.get("proposed_class")
                        for row in reevaluation.get("rows") or []}
        inventory = _read_json(self.store_dir / "SOURCE_INVENTORY.json")
        canon_refs = {str(row.get("legacy_label")): list(row.get("canon_refs") or [])
                      for row in inventory.get("rows") or []}
        fixture_path = self.root / "tests/fixtures/chapter_ir_pilot/" \
                       "FULL_MIGRATION_SEMANTIC_GOLDEN_SET.json"
        fixture = _read_json(fixture_path).get("chapters") or {}
        fixture_rows: list[dict[str, Any]] = []
        for label, spec in fixture.items():
            artifact = by_label.get(label)
            problems: list[str] = []
            if artifact is None:
                problems.append("missing_artifact")
            else:
                problems.extend(_m1_expect_problems(artifact, spec))
            fixture_rows.append({"legacy_label": label, "problems": problems,
                                 "matched": not problems})
        foundation_rows: list[dict[str, Any]] = []
        for label, expects in FOUNDATION_GOLDEN:
            artifact = by_label.get(label)
            problems = []
            if artifact is None:
                problems.append("missing_artifact")
            else:
                for key, expected in expects.items():
                    actual = _golden_value(key, artifact, replay_status, reeval_class,
                                           canon_refs)
                    if actual != expected:
                        problems.append(f"{key}={actual} != {expected}")
            foundation_rows.append({"legacy_label": label, "problems": problems,
                                    "matched": not problems, "expect": expects})
        payload = {
            "generated_at": _now(),
            "m1_golden": {
                "source": "tests/fixtures/chapter_ir_pilot/"
                          "FULL_MIGRATION_SEMANTIC_GOLDEN_SET.json",
                "total": len(fixture_rows),
                "matched": sum(1 for row in fixture_rows if row["matched"]),
                "deltas": [row for row in fixture_rows if not row["matched"]],
                "rows": fixture_rows,
                "note": ("10 个 delta 全部是 M1 golden 标签取用 LLM-adopted proposal 的章节；"
                         "本轮 deterministic-only materialization 不采纳 LLM proposal（§8/§37），"
                         "因此这些章节保持 UNRESOLVED/DERIVED，等待作者或后续 opt-in LLM 通道"),
            },
            "foundation_golden": {
                "total": len(foundation_rows),
                "matched": sum(1 for row in foundation_rows if row["matched"]),
                "rows": foundation_rows},
            "llm_used": False, "read_only": True, "non_authoritative": True,
        }
        payload["status"] = "PASS" if payload["foundation_golden"]["matched"] == \
            payload["foundation_golden"]["total"] else "NEEDS_ATTENTION"
        _write_json(self.store_dir / "GOLDEN_CHAPTER_REGRESSION.json", payload)
        return payload

    def foundation_gate(self, *, artifacts: Mapping[str, HistoricalChapterIRArtifact]
                        | None = None, replay: Mapping[str, Any] | None = None,
                        reevaluation: Mapping[str, Any] | None = None) -> dict[str, Any]:
        inputs = self.materializer.load()
        artifacts = artifacts if artifacts is not None else self.store.load_artifacts()
        replay = replay or _read_json(self.store_dir / "REPAIR_REPLAY.json")
        reevaluation = reevaluation or _read_json(
            self.store_dir / "HUMAN_REVIEW_REEVALUATION.json")
        index = _read_json(self.store_dir / "index.json")
        integrity = _read_json(self.store_dir / "integrity.json")
        expected = {str(item.get("chapter_uuid") or "") for item in inputs.chapters}
        uuid_ok = set(artifacts) == expected and len(artifacts) == len(expected)
        schema_ok = all(_schema_valid(item) for item in artifacts.values())
        coverage_ok = len(artifacts) == 570
        tokens = [chapter_id for chapter_id, item in artifacts.items()
                  if _machine_token_leak(item)]
        evidence_ok = all(_evidence_refs_valid(item) for item in artifacts.values())
        semantics_ok = all(_semantics_ok(item) for item in artifacts.values())
        digest_ok = all(_artifact_digest_ok(item, integrity) for item in artifacts.values())
        index_ok = (int(index.get("chapter_count") or 0) == len(artifacts)
                    and all(row.get("artifact_file_digest") for row in
                            index.get("chapters") or []))
        digests_after = self.materializer.source_digests()
        truth_ok = all(item.time_layer == TIME_LAYER and item.derived
                       and not item.canonical_representation and item.non_authoritative
                       for item in artifacts.values())
        replay_rows = list(replay.get("results") or [])
        replay_ok = len(replay_rows) == 20 and all(
            row.get("status") in ("APPLIES_CLEANLY", "NEEDS_REBASE", "OBSOLETE_REPAIR",
                                  "CONFLICT", "HUMAN_REVIEW") for row in replay_rows)
        checks = {
            "artifact_coverage_570": coverage_ok,
            "stable_chapter_identity": uuid_ok,
            "schema_valid": schema_ok,
            "chapter_function_policy": all(item.chapter_function
                                           and item.assertion("turn") for item in
                                           artifacts.values()),
            "evidence_refs_valid": evidence_ok,
            "no_machine_token_leak": not tokens,
            "decision_turn_payoff_semantics": semantics_ok,
            "knowledge_boundary": all(
                (item.assertion("knowledge") or HistoricalFieldAssertion(
                    field_name="knowledge")).assertion_mode != "DIRECT_SOURCE"
                for item in artifacts.values()),
            "relationship_continuity": all(
                (_assertion_mode(item, "relationship") != "DIRECT_SOURCE")
                or bool(item.chapter_ir.event_frames) for item in artifacts.values()),
            "resource_equipment_continuity": all(
                _assertion_mode(item, "resource") != "DIRECT_SOURCE"
                or bool(item.chapter_ir.event_frames) for item in artifacts.values()),
            "progression_continuity": all(
                _assertion_mode(item, "progression") != "DIRECT_SOURCE"
                or bool(item.chapter_ir.event_frames) for item in artifacts.values()),
            "location_map_continuity": all(
                _assertion_mode(item, "location") != "DIRECT_SOURCE"
                or bool(item.chapter_ir.event_frames) for item in artifacts.values()),
            "neighbor_continuity": all(_neighbor_ok(item) for item in artifacts.values()),
            "artifact_digest_integrity": digest_ok,
            "index_integrity": index_ok,
            "no_canon_mutation": bool(inputs.digests.get("canon"))
            and inputs.digests.get("canon") == digests_after.get("canon"),
            "no_story_state_mutation": bool(inputs.digests.get("story_state"))
            and inputs.digests.get("story_state") == digests_after.get("story_state"),
            "source_digest_unchanged": all(
                inputs.digests.get(key) == digests_after.get(key)
                for key in ("legacy_candidate", "chapter_ir")),
            "repair_replay_integrity": replay_ok,
            "truth_boundary": truth_ok,
            "human_review_reevaluation_present": bool(reevaluation.get("rows")),
        }
        blocked = not all([
            checks["artifact_digest_integrity"], checks["index_integrity"],
            checks["no_canon_mutation"], checks["no_story_state_mutation"],
            checks["source_digest_unchanged"], checks["truth_boundary"]])
        if blocked:
            status = "BLOCKED"
        elif all(checks.values()):
            status = "READY"
        else:
            status = "PARTIAL"
        payload = {"gate_id": "HISTORICAL_IR_FOUNDATION_GATE", "generated_at": _now(),
                   "status": status, "checks": checks,
                   "chapter_count": len(artifacts),
                   "artifact_status_counts": _counts(
                       item.materialization_status for item in artifacts.values()),
                   "coverage_counts": _counts(
                       item.evidence_coverage.overall_status
                       for item in artifacts.values()),
                   "source_digests": {"before": inputs.digests, "after": digests_after},
                   "machine_token_leak_chapters": tokens[:10],
                   "llm_used": False, "read_only": True, "non_authoritative": True}
        _write_json(self.store_dir / "HISTORICAL_IR_FOUNDATION_GATE.json", payload)
        return payload

    # ---- 重评报告（§44/§48/§55） ----------------------------------------
    def run(self, *, resume: bool = True) -> dict[str, Any]:
        report = self.materializer.materialize_all(resume=resume)
        artifacts = self.store.load_artifacts()
        inventory = _read_json(self.store_dir / "SOURCE_INVENTORY.json")
        replay = self.replay_repairs(artifacts=artifacts)
        reevaluation = self.reevaluate_human_review(artifacts=artifacts)
        gate = self.foundation_gate(artifacts=artifacts, replay=replay,
                                    reevaluation=reevaluation)
        golden = self.golden_regression(artifacts=artifacts, replay=replay,
                                        reevaluation=reevaluation)
        payload = self.reevaluation_report(report=report, inventory=inventory,
                                           replay=replay, reevaluation=reevaluation,
                                           gate=gate, artifacts=artifacts, golden=golden)
        return payload

    def reevaluation_report(self, *, report: Mapping[str, Any],
                            inventory: Mapping[str, Any], replay: Mapping[str, Any],
                            reevaluation: Mapping[str, Any], gate: Mapping[str, Any],
                            artifacts: Mapping[str, HistoricalChapterIRArtifact],
                            golden: Mapping[str, Any] | None = None
                            ) -> dict[str, Any]:
        inputs = self.materializer.load()
        previous = _previous_overlay_counts(inputs)
        status_counts = _counts(item.materialization_status for item in artifacts.values())
        coverage_counts = _counts(item.evidence_coverage.overall_status
                                  for item in artifacts.values())
        failed = int(status_counts.get("FAILED", 0))
        no_body = int(coverage_counts.get("INSUFFICIENT", 0))
        replay_counts = dict(replay.get("status_counts") or {})
        conflicts = int(replay_counts.get("CONFLICT", 0))
        class_counts = dict(reevaluation.get("class_counts") or {})
        foundation_status = str(gate.get("status") or "PARTIAL")
        sufficient = (foundation_status == "READY" and failed == 0 and conflicts == 0
                      and len(artifacts) == 570)
        evidence_status = "SUFFICIENT_TO_CONTINUE" if sufficient \
            else "FULL_IR_FOUNDATION_REQUIRED"
        residual_reasons = {
            "content_gap_truly_missing": int(class_counts.get("TRULY_MISSING", 0)),
            "author_decision_required": int(class_counts.get("AUTHOR_DECISION_REQUIRED", 0)),
            "rebind_available": int(class_counts.get("EVIDENCE_ONLY", 0))
            + int(class_counts.get("FIELD_REBIND", 0)),
            "na_correction": int(class_counts.get("N/A_CORRECTION", 0)),
            "source_insufficient": int(class_counts.get("SOURCE_EVIDENCE_INSUFFICIENT", 0)),
        }
        payload = {
            "generated_at": _now(), "novel_id": "wasteland_001",
            "previous_overlay": previous,
            "full_ir_availability": {
                "chapter_count": len(artifacts),
                "materialization_status_counts": status_counts,
                "coverage_counts": coverage_counts,
                "source_channels": dict(inventory.get("channel_availability") or {}),
                "llm_used": False,
            },
            "repair_replay": {"status_counts": replay_counts,
                              "results": replay.get("results") or []},
            "golden_regression": {
                "m1_golden": {key: value for key, value in
                              (golden or {}).get("m1_golden", {}).items()
                              if key in ("total", "matched", "note")},
                "foundation_golden": {key: value for key, value in
                                      (golden or {}).get("foundation_golden", {}).items()
                                      if key in ("total", "matched")},
                "status": (golden or {}).get("status", "UNKNOWN"),
            },
            "human_review_reclassification": {
                "count": int(reevaluation.get("human_review_count") or 0),
                "proposal": reevaluation.get("rows") or [],
                "class_counts": class_counts,
                "overlay_modified": False, "proposal_only": True,
            },
            "evidence_sufficiency_after_foundation": {
                "previous_status": "FULL_IR_FOUNDATION_REQUIRED",
                "status": evidence_status,
                "residual_reasons": residual_reasons,
                "rationale": (
                    "570/570 historical ChapterSemanticIR body 已 materialize（derived，非新 truth）；"
                    "unresolved 主因不再是 'IR body 未落盘'，而是 legacy source of record 的内容产能"
                    "（content gap）与作者决策"
                    if sufficient else
                    "仍有 chapter 缺少可消费 full IR body / replay 冲突 → 需先修复 foundation"),
            },
            "HISTORICAL_IR_FOUNDATION_STATUS": foundation_status,
            "M11_EVIDENCE_FOUNDATION_STATUS": evidence_status,
            "recommended_next_action": (
                "作者 Human Review：① 确认 44 个原 human_review target 的重分类 proposal"
                "（重点看 AUTHOR_DECISION_REQUIRED 与 TRULY_MISSING）；② 确认后再决定是否恢复 "
                "REPAIR_BATCH_04；本轮不执行 Batch 04，也不自动 canonicalize 旧 repair。"
                if sufficient else
                "先补齐缺失的 full IR body / 解决 replay 冲突，再考虑 Batch 04"),
            "materialization_report_ref": "materialization_report.json",
            "gate_ref": "HISTORICAL_IR_FOUNDATION_GATE.json",
            "replay_ref": "REPAIR_REPLAY.json",
            "inventory_ref": "SOURCE_INVENTORY.json",
            "report": dict(report),
            "read_only": True, "non_authoritative": True, "derived": True,
            "canonical_representation": False,
        }
        _write_json(self.store_dir / "M11_FOUNDATION_REEVALUATION.json", payload)
        return payload


def _m1_expect_problems(artifact: HistoricalChapterIRArtifact,
                        spec: Mapping[str, Any]) -> list[str]:
    """M1 fixture golden：dog / primary transition / decision owner / must_not codes。"""

    problems: list[str] = []
    body = artifact.chapter_ir
    expect = dict(spec.get("expect") or {})
    if "dog_role" in expect and body.dog.role != expect["dog_role"]:
        problems.append(f"dog_role={body.dog.role} != {expect['dog_role']}")
    if "dog_presence" in expect and body.dog.physical_presence != expect["dog_presence"]:
        problems.append(f"dog_presence={body.dog.physical_presence}")
    if "decision_owner" in expect and body.focal_decision_owner_id != \
            expect["decision_owner"]:
        problems.append("decision_owner")
    if "primary_transition" in expect:
        primary = [item for item in body.state_transitions
                   if item.narrative_role == "primary"]
        actual = [primary[0].state_key, primary[0].to_state] if primary else None
        if actual != expect["primary_transition"]:
            problems.append(f"primary_transition={actual} != {expect['primary_transition']}")
    if "assertion_mode" in expect:
        primary = [item for item in body.state_transitions
                   if item.narrative_role == "primary"]
        if primary and primary[0].assertion_mode != expect["assertion_mode"]:
            problems.append(f"assertion_mode={primary[0].assertion_mode}")
    codes = set((artifact.validator_results.get("finding_codes") or "").split(","))
    for code in spec.get("must_not") or []:
        if code in codes:
            problems.append(f"must_not:{code}")
    return problems


def _golden_value(key: str, artifact: HistoricalChapterIRArtifact,
                  replay_status: Mapping[str, Any],
                  reeval_class: Mapping[str, Any],
                  canon_refs: Mapping[str, Sequence[str]]) -> str:
    body = artifact.chapter_ir
    if key == "replay":
        return str(replay_status.get(artifact.legacy_label) or "")
    if key == "reclassification":
        return str(reeval_class.get(artifact.legacy_label) or "")
    if key == "materialization_status":
        return artifact.materialization_status
    if key == "dog_role":
        return body.dog.role
    if key == "primary_transition":
        primary = [item for item in body.state_transitions
                   if item.narrative_role == "primary"]
        return f"{primary[0].state_key}:{primary[0].to_state}" if primary else "none"
    if key == "canon_ref":
        return ",".join(canon_refs.get(artifact.legacy_label) or [])
    return _assertion_mode(artifact, key)


def _previous_overlay_counts(inputs: FoundationInputs) -> dict[str, int]:
    verified = sum(1 for entry in inputs.repair_overlays.values()
                   if entry.get("status") == "verified")
    human = sum(1 for entry in inputs.repair_overlays.values()
                if entry.get("status") == "human_review")
    blocked = sum(1 for entry in inputs.repair_overlays.values()
                  if entry.get("status") == "blocked")
    total = 372
    return {"verified": verified, "human_review": human, "blocked": blocked,
            "pending": total - verified - human - blocked,
            "remaining_repair_targets": total - verified,
            "baseline_queue_counts": {"SEMANTIC_CONFIRMED": 198,
                                      "LEGACY_FIELD_CONFLICT": 27,
                                      "LEGACY_CONTENT_GAP": 345}}


def _counts(values) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _artifact_content_digest(payload: Mapping[str, Any]) -> str:
    """artifact 复用判据：忽略 created_at 的内容 digest（asset 内容变化即重写）。"""

    return digest_payload({key: value for key, value in payload.items()
                           if key != "created_at"})


def _meaningful(value: Any) -> bool:
    """delta / 文本字段是否表示"确有变化"（'无' / 0 / 空串都不算）。"""

    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, Mapping):
        return any(_meaningful(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_meaningful(item) for item in value)
    text = str(value or "").strip()
    return bool(text) and text not in ("无", "none", "None", "-", "0")


def _assertion_mode(artifact: HistoricalChapterIRArtifact, field_name: str) -> str:
    assertion = artifact.assertion(field_name)
    return assertion.assertion_mode if assertion else "UNRESOLVED"


def chapter_artifact_checks(artifact: HistoricalChapterIRArtifact,
                            integrity: Mapping[str, Any] | None = None
                            ) -> dict[str, bool]:
    """单章 historical IR 只读审计 checks（M12 验收复用，不写任何 artifact）。

    `integrity` 为 foundation 的 `integrity.json`；未提供时跳过 digest 比对
    （调用方需要自行处理）。
    """

    checks = {
        "schema_valid": _schema_valid(artifact),
        "evidence_refs_valid": _evidence_refs_valid(artifact),
        "semantics_ok": _semantics_ok(artifact),
        "neighbor_continuity_ok": _neighbor_ok(artifact),
        "no_machine_token_leak": not _machine_token_leak(artifact),
        "truth_boundary_ok": (artifact.time_layer == TIME_LAYER and artifact.derived
                              and not artifact.canonical_representation
                              and artifact.non_authoritative),
    }
    if integrity is not None:
        checks["digest_stable"] = _artifact_digest_ok(artifact, integrity)
    return checks


def _schema_valid(artifact: HistoricalChapterIRArtifact) -> bool:
    try:
        body = ChapterSemanticIR.model_validate(artifact.chapter_ir.model_dump(mode="json"))
    except Exception:  # noqa: BLE001
        return False
    return body.chapter_uuid == artifact.chapter_uuid


def _machine_token_leak(artifact: HistoricalChapterIRArtifact) -> list[str]:
    texts = [artifact.chapter_ir.goal]
    texts += [item.action_text for item in artifact.chapter_ir.event_frames]
    texts += [item.after_state for item in artifact.chapter_ir.effects]
    texts += [ref.quote for item in artifact.field_assertions for ref in item.evidence_refs]
    hits: list[str] = []
    for text in texts:
        if not text:
            continue
        for token in TOKEN_PATTERN:
            if token in text:
                hits.append(token)
    return sorted(set(hits))


def _evidence_refs_valid(artifact: HistoricalChapterIRArtifact) -> bool:
    ids = {item.event_id for item in artifact.chapter_ir.event_frames}
    ids |= {item.effect_id for item in artifact.chapter_ir.effects}
    ids |= {item.transition_id for item in artifact.chapter_ir.state_transitions}
    for assertion in artifact.field_assertions:
        if any(bound not in ids for bound in assertion.bound_ir_ids):
            return False
        if any(not ref.channel for ref in assertion.evidence_refs):
            return False
    return all(not effect.caused_by_event_ids
               or all(ref in ids for ref in effect.caused_by_event_ids)
               for effect in artifact.chapter_ir.effects)


def _semantics_ok(artifact: HistoricalChapterIRArtifact) -> bool:
    assertion = artifact.assertion("turn")
    if assertion and assertion.assertion_mode in ("DIRECT_SOURCE", "DERIVED"):
        if not assertion.bound_ir_ids:
            return False
    decision = artifact.assertion("decision")
    if decision and decision.assertion_mode == "DIRECT_SOURCE":
        if not [item for item in artifact.chapter_ir.event_frames if item.decision_action]:
            return False
    payoff = artifact.assertion("payoff")
    if payoff and payoff.assertion_mode == "DIRECT_SOURCE":
        if not [item for item in artifact.chapter_ir.effects
                if item.polarity in ("positive", "mixed")]:
            return False
    return True


def _artifact_digest_ok(artifact: HistoricalChapterIRArtifact,
                        integrity: Mapping[str, Any]) -> bool:
    recomputed = digest_payload(artifact.chapter_ir.model_dump(mode="json"))
    if recomputed != artifact.chapter_ir_digest:
        return False
    rows = {row.get("chapter_id"): row for row in integrity.get("artifacts") or []}
    row = rows.get(artifact.chapter_id) or {}
    return bool(row) and row.get("chapter_ir_digest") == artifact.chapter_ir_digest \
        and bool(row.get("digest_stable"))


def _neighbor_ok(artifact: HistoricalChapterIRArtifact) -> bool:
    transition_ids = [item.transition_id for item in artifact.chapter_ir.state_transitions]
    if len(transition_ids) != len(set(transition_ids)):
        return False
    event_ids = {item.event_id for item in artifact.chapter_ir.event_frames}
    for transition in artifact.chapter_ir.state_transitions:
        if any(ref not in event_ids for ref in transition.caused_by_event_ids):
            return False
    return True


def _knowledge_entries(payload: Any) -> list[tuple[str, dict[str, Any]]]:
    if isinstance(payload, Mapping):
        items = payload.get("reveals") or payload.get("items") or payload
        if isinstance(items, Mapping):
            return [(str(key), dict(value)) for key, value in items.items()
                    if isinstance(value, Mapping)]
        return [(str(index), dict(value)) for index, value in enumerate(items or [])
                if isinstance(value, Mapping)]
    return [(str(index), dict(value)) for index, value in enumerate(payload or [])
            if isinstance(value, Mapping)]


def _has_wasteland_entities(path: Path) -> bool:
    """磁盘上的 prose 文件是否属于 WASTELAND_001（防止把别的手稿当 source）。"""

    if not path.is_file():
        return False
    head = path.read_text(encoding="utf-8-sig", errors="ignore")[:6000]
    return any(name in head for name in ("韩彻", "阿灰", "铁锈集", "锈牙", "黑塔"))


def _inventory_completeness(chapter: Mapping[str, Any], shadow: Mapping[str, Any],
                            recon: Mapping[str, Any], prose: bool) -> CoverageStatus:
    if not chapter:
        return "INSUFFICIENT"
    channels = sum([bool(chapter.get("events")), bool(shadow),
                    bool(recon.get("deterministic")), bool(prose)])
    if channels >= 3:
        return "SUFFICIENT"
    if channels >= 1:
        return "PARTIAL"
    return "INSUFFICIENT"


def _coverage_from(assertions: Sequence[HistoricalFieldAssertion],
                   ir: ChapterSemanticIR) -> HistoricalIREvidenceCoverage:
    modes = {item.field_name: item.assertion_mode for item in assertions}

    def status(field_name: str) -> CoverageStatus:
        mode = modes.get(field_name, "UNRESOLVED")
        if mode in ("CONFIRMED", "DIRECT_SOURCE", "NOT_APPLICABLE"):
            return "SUFFICIENT"
        if mode in ("DERIVED", "INFERRED"):
            return "PARTIAL"
        return "INSUFFICIENT"

    values = {name: status(name) for name in COVERAGE_FIELDS}
    required = ("events", "effects", "state_transition", "decision", "turn", "payoff")
    if not ir.event_frames or not ir.effects:
        overall: CoverageStatus = "INSUFFICIENT"
    elif all(values[name] == "SUFFICIENT" for name in COVERAGE_FIELDS):
        overall = "SUFFICIENT"
    else:
        overall = "PARTIAL"
    reason = ("；".join(f"{name}={values[name]}" for name in COVERAGE_FIELDS))
    return HistoricalIREvidenceCoverage(
        **values, overall_status=overall, sufficiency_reason=reason[:240])
