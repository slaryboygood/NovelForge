"""C07：CanonAwareOutlinePlanner —— Canon-aware 的大纲规划路径（旧 forge 保持不动）。"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import Field

from novelforge.models import StrictModel

from .chapters import ChapterLineage, ChapterLineageStore
from .context import CanonContextBuilder, contains_writer_metadata, sanitize_writer_text
from .gate import SchemaGateError, validate_chapter_plan
from .ids import new_random_key
from .models import CanonSourceRef
from .repository import CanonRepository
from .schemas import NarrativeBeat
from .validator import SourceReferenceValidator

REQUIRED_GRAPH_FIELDS = ("participants", "locations", "temporal_position",
                         "requires_abilities", "grants_abilities", "requires_identities",
                         "grants_identities", "character_state_effects", "knowledge_changes",
                         "relationship_changes", "resource_changes", "ability_changes",
                         "identity_changes", "foreshadow_actions")

# writer-visible 字段全集：任一字段出现内部元数据都必须拒绝（C11 加固，避免只看 subset）
WRITER_VISIBLE_FIELDS = ("title", "goal", "start_state", "concrete_events", "trigger",
                         "protagonist_action", "opposition", "escalation", "decision",
                         "decision_result", "turn", "payoff", "cost", "loss", "dog_action",
                         "npc_autonomous_action", "world_state_change", "information_release",
                         "foreshadow_action", "end_state", "hook", "next_chapter_causality")


def writer_visible_text(plan: Any) -> str:
    parts: list[str] = []
    for field in WRITER_VISIBLE_FIELDS:
        value = getattr(plan, field, None)
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, (list, tuple)):
            parts.extend(str(item) for item in value)
    return " ".join(parts)


class CanonOutlineFlags(StrictModel):
    """默认全部关闭：旧项目行为必须完全不变。"""

    canon_outline_v1: bool = False
    canon_outline_shadow_mode: bool = False

    @classmethod
    def from_env(cls) -> "CanonOutlineFlags":
        def flag(name: str) -> bool:
            return str(os.environ.get(name, "")).strip().lower() in ("1", "true", "yes")
        return cls(canon_outline_v1=flag("CANON_OUTLINE_V1"),
                   canon_outline_shadow_mode=flag("CANON_OUTLINE_SHADOW_MODE"))


class ArcIntent(StrictModel):
    arc_id: str = Field(min_length=3, max_length=64)
    novel_id: str = Field(min_length=1, max_length=96)
    goal: str = Field(default="", max_length=300)
    volume_ref: str = Field(default="", max_length=64)
    participant_ids: list[str] = Field(default_factory=list)
    location_ids: list[str] = Field(default_factory=list)
    temporal_position: int | None = Field(default=None, ge=0)
    constraints: list[str] = Field(default_factory=list)


class PlanFinding(StrictModel):
    code: str
    detail: str = Field(default="", max_length=300)
    target: str = Field(default="", max_length=160)


class PlanResult(StrictModel):
    ok: bool = False
    mode: Literal["legacy", "canon", "shadow"] = "canon"
    arc_id: str = ""
    findings: list[PlanFinding] = Field(default_factory=list)
    chapter_uuids: list[str] = Field(default_factory=list)
    context_manifest_id: str = ""
    payload: list[dict[str, Any]] = Field(default_factory=list)
    persisted_path: str = ""

    def fail(self, code: str, detail: str = "", target: str = "") -> "PlanResult":
        self.findings.append(PlanFinding(code=code, detail=detail, target=target))
        return self


class OutlineSink(Protocol):
    def write(self, result: PlanResult) -> str:  # pragma: no cover - 协议
        ...


class FileOutlineSink:
    """隔离落盘（shadow / candidate）：绝不写正式 outline 仓库，也不污染正式 Canon。"""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def write(self, result: PlanResult) -> str:
        path = self.root / f"{result.arc_id or 'arc'}.json"
        path.write_text(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=1),
                        encoding="utf-8")
        return str(path)


class CanonAwareOutlinePlanner:
    def __init__(self, repository: CanonRepository, *, flags: CanonOutlineFlags | None = None,
                 sink: OutlineSink | None = None, shadow_sink: OutlineSink | None = None) -> None:
        self.repository = repository
        self.flags = flags or CanonOutlineFlags()
        self.sink = sink
        self.shadow_sink = shadow_sink
        self.context_builder = CanonContextBuilder(repository)
        self.validator = SourceReferenceValidator(repository)
        self.lineage = ChapterLineageStore(repository)

    # ---- 主流程 -----------------------------------------------------------
    def plan(self, intent: ArcIntent, *, beats_raw: list[dict[str, Any]],
             chapters_raw: list[dict[str, Any]], mode: str = "canon") -> PlanResult:
        result = PlanResult(mode=mode, arc_id=intent.arc_id)  # type: ignore[arg-type]
        context = self.context_builder.planner_context(
            intent.novel_id, arc_intent=intent.goal,
            focus_entity_ids=tuple(intent.participant_ids),
            focus_location_ids=tuple(intent.location_ids),
            temporal_cutoff=intent.temporal_position)
        result.context_manifest_id = context.manifest.context_id
        with self.repository.transaction() as connection:
            connection.execute(
                "INSERT INTO canon_context_manifests(context_id, novel_id, purpose, payload) "
                "VALUES (?,?,?,?) ON CONFLICT(context_id) DO NOTHING",
                (context.manifest.context_id, intent.novel_id, context.manifest.purpose,
                 json.dumps(context.manifest.model_dump(mode="json"), ensure_ascii=False)))
        beats: list[NarrativeBeat] = []
        for index, raw in enumerate(beats_raw, start=1):
            try:
                beats.append(NarrativeBeat.model_validate(raw, strict=True))
            except Exception as exc:  # noqa: BLE001
                result.fail("BEAT_SCHEMA_INVALID", str(exc)[:200], f"beat#{index}")
        if result.findings:
            return result
        plans = []
        for index, raw in enumerate(chapters_raw, start=1):
            missing = [field for field in REQUIRED_GRAPH_FIELDS if field not in raw]
            if missing:
                result.fail("GRAPH_METADATA_MISSING", ", ".join(missing), f"chapter#{index}")
                continue
            try:
                plan = validate_chapter_plan(raw)
            except SchemaGateError as exc:
                result.fail("CHAPTER_SCHEMA_INVALID", "; ".join(exc.issues[:3]), f"chapter#{index}")
                continue
            if contains_writer_metadata(writer_visible_text(plan)):
                result.fail("WRITER_VISIBLE_METADATA_LEAK", "writer-visible 含内部 ID / 章节号",
                            plan.chapter_uuid)
                continue
            plans.append(plan)
        if result.findings:
            return result
        facts = {f.fact_id: f for f in self.repository.facts(intent.novel_id)}
        events = {e.event_id: e for e in self.repository.events(intent.novel_id)}
        for plan in plans:
            for fact_id in plan.canon_fact_ids:
                fact = facts.get(fact_id)
                if fact is None:
                    result.fail("CANON_FACT_UNKNOWN", fact_id, plan.chapter_uuid)
                elif fact.status == "happened" and plan.temporal_position is not None \
                        and fact.first_occurrence_ref is not None \
                        and fact.first_occurrence_ref.display_number is not None \
                        and plan.temporal_position < fact.first_occurrence_ref.display_number:
                    result.fail("HAPPENED_FACT_REWRITE", fact_id, plan.chapter_uuid)
            for event_id in plan.canon_event_ids:
                if event_id not in events:
                    result.fail("CANON_EVENT_UNKNOWN", event_id, plan.chapter_uuid)
            refs = list(plan.canon_source_refs) or [
                CanonSourceRef(source_type="outline", source_uuid=str(ref),
                               chapter_uuid=str(ref)) for ref in plan.source_refs]
            report = self.validator.validate_refs(
                intent.novel_id, refs=refs, claimed_fact_ids=plan.canon_fact_ids,
                temporal_cutoff=intent.temporal_position)
            for finding in report.findings:
                result.fail(finding.code, finding.detail, plan.chapter_uuid)
        if result.findings:
            return result
        uuids = [plan.chapter_uuid for plan in plans]
        base_number = intent.temporal_position or 0
        if mode != "shadow":
            for offset, plan in enumerate(plans, start=1):
                self.lineage.register(ChapterLineage(
                    chapter_uuid=plan.chapter_uuid, novel_id=intent.novel_id,
                    display_number=plan.display_number or (base_number + offset),
                    context_manifest_id=result.context_manifest_id, title=plan.title))
        result.chapter_uuids = uuids
        result.payload = [plan.model_dump(mode="json") for plan in plans]
        result.ok = True
        target = self.shadow_sink if mode == "shadow" else self.sink
        if target is not None:
            result.persisted_path = target.write(result)
        return result

    # ---- shadow -----------------------------------------------------------
    def shadow_plan(self, intent: ArcIntent, *, beats_raw: list[dict[str, Any]],
                    chapters_raw: list[dict[str, Any]]) -> PlanResult:
        if not self.flags.canon_outline_shadow_mode or self.shadow_sink is None:
            return PlanResult(mode="shadow", arc_id=intent.arc_id,
                              findings=[PlanFinding(code="SHADOW_DISABLED")])
        return self.plan(intent, beats_raw=beats_raw, chapters_raw=chapters_raw, mode="shadow")

    # ---- legacy 兼容 ------------------------------------------------------
    def should_use_canon_path(self) -> bool:
        return bool(self.flags.canon_outline_v1)
