"""M8B：Long Outline Autonomous Batch Compiler（Session / Task / Checkpoint / Resume +
Progressive Elaboration Orchestrator）。

M8A 解决"StorySpine → VolumePlan → ArcPlan"的单次确定性编译；M8B 解决几十卷 / 几百
PlotNode / 百万字级长篇如何**分 scope、分 batch、持续编译**，并保持：

- **每批一个 immutable revision**：R20 → Batch 01 → R21 → Batch 02 → R22 …，下一批的
  source 必须是上一批 promoted revision（禁止所有 batch 基于同一个旧 revision 最后覆盖合并）；
- **checkpoint 只保存编译过程状态**（refs / digests / 结果定位 / retry state），
  不是第二套 story truth：story truth 仍然只有 PlanningRepository 的 revisions；
- **Autonomous 的边界**：只表示"已经由 StorySpine / Route / M8A 决定的结构任务可以
  无人值守连续执行"。改变主路线、删除 must_happen、改 Canon / StoryState、重写
  CharacterArc endpoint、重切已定卷边界、替作者在两种同样合理的结构间选择 → 必须停下，
  状态 `human_review`。

M8B 最多把 detail_level 提升到 `arc`；`chapter_ready` 一律返回
`DETAIL_LEVEL_REQUIRES_M9`（Chapter Semantic IR 属于 M9）。本模块不生成章节列表、
不生成正文、不改既有长篇数据、不重写 StorySpine / Canon / StoryState。
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from novelforge.models import StrictModel

from .findings import PlanningFinding, add_finding
from .models import StoryPlanningIR, VolumePlan
from .outline_budget import ChapterBudgetEstimate
from .outline_compiler import (
    COMPILER_VERSION,
    CompilationScope,
    NodeAllocation,
    OutlineCompilationCandidate,
    OutlineCompiler,
)
from .plot_pressure import build_plot_pressure_inventory
from .repository import PlanningRepository, PlanningRevisionRecord
from .spine_analysis import topological_order
from .validator import PlanningValidator
from .versioning import planning_digest

CHECKPOINT_SCHEMA_VERSION = 1
BatchStatus = Literal["pending", "ready", "running", "compiled", "validated", "promoted",
                      "blocked", "retryable_failed", "failed", "human_review", "superseded",
                      "skipped"]
FailureClass = Literal["TRANSIENT_IO", "NETWORK", "PROVIDER", "PARSE", "SCHEMA",
                       "VALIDATION", "STALE_SOURCE", "CHECKPOINT_CONFLICT", "CONFIG_CHANGED",
                       "HUMAN_REVIEW", "INTERNAL_ERROR"]
DetailLevel = Literal["concept", "spine", "volume", "arc", "chapter_ready"]
DETAIL_ORDER: dict[str, int] = {"concept": 0, "spine": 1, "volume": 2, "arc": 3,
                                "chapter_ready": 4}
# 只有这些失败会自动 retry（结构错误 / Human Review 绝不自动重试）
RETRYABLE_FAILURES: tuple[str, ...] = ("TRANSIENT_IO", "NETWORK", "PROVIDER")
M8B_MAX_DETAIL: str = "arc"
# 这些 finding 一出现就必须停下来找作者（不是 compiler bug，也不允许 safe_auto 代选）
HUMAN_REVIEW_CODES: tuple[str, ...] = (
    "UNALLOCATED_MUST_HAPPEN_NODE", "ROUTE_CHANGE_REQUIRED", "BOUNDARY_REVISION_REQUIRED",
    "MAJOR_ARC_UNDISTRIBUTABLE", "TERMINAL_PATH_INSUFFICIENT", "MAJOR_PRESSURE_WITHOUT_HOME",
    "STRUCTURE_TOO_THIN_FOR_TARGET",
)
# 这些 finding 只在"节点落在当前 batch scope"时才算本批问题；scope 之外留给其它 batch
NODE_SCOPED_FINDING_CODES: tuple[str, ...] = (
    "UNALLOCATED_MUST_HAPPEN_NODE", "UNALLOCATED_OPTIONAL_NODE",
    "ALLOCATION_BREAKS_CAUSAL_ORDER", "REQUIREMENT_SATISFIER_SCHEDULED_TOO_LATE",
    "OUTLINE_INFORMATION_ORDER_BROKEN", "OUTLINE_FORESHADOW_ORDER_BROKEN",
    "LOCATION_CONTINUITY_WARNING", "EQUIPMENT_CONTINUITY_BROKEN",
)
# pressure 未解决状态：必须 resolved / scheduled / carryover / intentionally_unresolved / ignored
OPEN_PRESSURE_STATES: tuple[str, ...] = ("open", "blocked", "deferred")
CLOSED_CARRY_STATES: tuple[str, ...] = ("resolved", "scheduled", "ignored",
                                        "intentionally_unresolved")
# 只能按整本书判断的 finding（单批 scope 的预算不足以支撑结论）
TARGET_ALIGNMENT_CODES: tuple[str, ...] = ("STRUCTURE_TOO_THIN_FOR_TARGET",
                                           "STRUCTURE_TOO_DENSE_FOR_TARGET")


class SegmentationProfile(StrictModel):
    """边界 / 预算参数化（Core 中性默认；Genre Template / author config 可覆写）。

    只有"边界灵敏度 + 容忍度 + 章节目标词数"这类参数；Core 不做任何题材分支。
    """

    profile_id: str = Field(default="neutral", max_length=64)
    volume_boundary_sensitivity: float = Field(default=1.0, gt=0, le=5)
    arc_boundary_sensitivity: float = Field(default=1.0, gt=0, le=5)
    thin_structure_tolerance: float = Field(default=0.3, ge=0, le=1)
    dense_structure_tolerance: float = Field(default=0.3, ge=0, le=1)
    chapter_target_words: int = Field(default=3000, ge=500, le=20000)
    optional_node_bias: float = Field(default=0.0, ge=-1, le=1)
    carryover_tolerance: int = Field(default=3, ge=1, le=50)
    non_authoritative: bool = True


class CompilerConfig(StrictModel):
    """影响编译结果的配置（写入 session / checkpoint 的 digest，resume 时校验）。"""

    compiler_version: str = Field(default=COMPILER_VERSION, max_length=32)
    segmentation: SegmentationProfile = Field(default_factory=SegmentationProfile)
    budget_profile: dict[str, float] = Field(default_factory=dict)
    genre_template_id: str = Field(default="", max_length=64)
    author_overrides: dict[str, Any] = Field(default_factory=dict)
    target_words: int = Field(default=0, ge=0)
    strict: bool = False

    def digest(self) -> str:
        payload = self.model_dump(mode="json")
        return hashlib.sha256(json.dumps(payload, ensure_ascii=False,
                                         sort_keys=True).encode("utf-8")).hexdigest()[:16]


class WarningPolicy(StrictModel):
    """WARNING 不一律停批：按 finding code 分成三档。"""

    promotion_blocking_codes: list[str] = Field(default_factory=list)
    review_codes: list[str] = Field(default_factory=list)

    def classify(self, code: str) -> Literal["informational", "review_recommended",
                                             "promotion_blocking"]:
        if code in self.promotion_blocking_codes:
            return "promotion_blocking"
        if code in self.review_codes:
            return "review_recommended"
        return "informational"


class PromotionPolicy(StrictModel):
    """manual：每个 batch candidate 都等作者 approve；safe_auto：满足安全条件自动 promote。"""

    mode: Literal["manual", "safe_auto"] = "manual"
    max_attempts: int = Field(default=3, ge=1, le=10)
    warning_policy: WarningPolicy = Field(default_factory=WarningPolicy)


class BatchReviewFinding(StrictModel):
    """需要作者决策的结构问题（不是 compiler bug）。"""

    code: str = Field(min_length=3, max_length=64)
    message: str = Field(default="", max_length=300)
    severity: Literal["human_review"] = "human_review"
    related_ids: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class OutlineBatchTask(StrictModel):
    batch_id: str = Field(min_length=6, max_length=64)
    sequence: int = Field(default=1, ge=1)
    source_revision_id: str = Field(default="", max_length=64)
    source_digest: str = Field(default="", max_length=64)
    scope: CompilationScope = Field(default_factory=CompilationScope)
    source_detail_level: DetailLevel = "spine"
    target_detail_level: DetailLevel = "arc"
    dependency_batch_ids: list[str] = Field(default_factory=list)
    supersedes_batch_ids: list[str] = Field(default_factory=list)
    status: BatchStatus = "pending"
    attempt_count: int = 0
    candidate_id: str = Field(default="", max_length=64)
    promoted_revision_id: str = Field(default="", max_length=64)
    findings_digest: str = Field(default="", max_length=64)
    checkpoint_ref: str = Field(default="", max_length=200)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_class: FailureClass | None = None
    error_summary: str = Field(default="", max_length=300)
    non_authoritative: bool = True


class OutlineBatchCheckpoint(StrictModel):
    """checkpoint = 编译过程状态（refs / digests / 结果定位），不是第二套 story truth。"""

    schema_version: int = CHECKPOINT_SCHEMA_VERSION
    session_id: str = Field(default="", max_length=64)
    batch_id: str = Field(default="", max_length=64)
    source_revision_id: str = Field(default="", max_length=64)
    source_digest: str = Field(default="", max_length=64)
    scope: CompilationScope = Field(default_factory=CompilationScope)
    target_detail_level: DetailLevel = "arc"
    candidate_id: str = Field(default="", max_length=64)
    candidate_digest: str = Field(default="", max_length=64)
    validation_digest: str = Field(default="", max_length=64)
    promoted_revision_id: str = Field(default="", max_length=64)
    promoted_digest: str = Field(default="", max_length=64)
    config_digest: str = Field(default="", max_length=64)
    status: BatchStatus = "pending"
    attempt_count: int = 0
    completed_steps: list[str] = Field(default_factory=list)
    pending_steps: list[str] = Field(default_factory=list)
    findings: list[PlanningFinding] = Field(default_factory=list)
    review_findings: list[BatchReviewFinding] = Field(default_factory=list)
    error_class: FailureClass | None = None
    error_summary: str = Field(default="", max_length=300)
    last_attempt_at: datetime | None = None
    next_retry_at: datetime | None = None
    resume_state: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    non_authoritative: bool = True

    def blocking(self) -> bool:
        return any(item.severity == "ERROR" for item in self.findings)


class OutlineBatchSession(StrictModel):
    session_id: str = Field(default="", max_length=64)
    novel_id: str = Field(default="", max_length=96)
    root_planning_revision_id: str = Field(default="", max_length=64)
    root_digest: str = Field(default="", max_length=64)
    current_revision_id: str = Field(default="", max_length=64)
    current_digest: str = Field(default="", max_length=64)
    target_scope: CompilationScope = Field(default_factory=CompilationScope)
    target_detail_level: DetailLevel = "arc"
    batch_policy: dict[str, Any] = Field(default_factory=dict)
    promotion_policy: PromotionPolicy = Field(default_factory=PromotionPolicy)
    config_digest: str = Field(default="", max_length=64)
    status: BatchStatus = "pending"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_batch_ids: list[str] = Field(default_factory=list)
    pending_batch_ids: list[str] = Field(default_factory=list)
    failed_batch_ids: list[str] = Field(default_factory=list)
    retryable_batch_ids: list[str] = Field(default_factory=list)
    review_required_batch_ids: list[str] = Field(default_factory=list)
    final_revision_id: str = Field(default="", max_length=64)
    scope_complete: bool = False
    validation_summary: dict[str, Any] = Field(default_factory=dict)
    tasks: list[OutlineBatchTask] = Field(default_factory=list)
    last_error_class: FailureClass | None = None
    non_authoritative: bool = True


class OutlineBatchDiff(StrictModel):
    before_revision: str = Field(default="", max_length=64)
    after_revision: str = Field(default="", max_length=64)
    volumes_added: list[str] = Field(default_factory=list)
    volumes_modified: list[str] = Field(default_factory=list)
    arcs_added: list[str] = Field(default_factory=list)
    arcs_modified: list[str] = Field(default_factory=list)
    allocations_changed: list[str] = Field(default_factory=list)
    budget_changes: dict[str, list[int]] = Field(default_factory=dict)
    boundary_changes: list[str] = Field(default_factory=list)
    carryover_changes: list[str] = Field(default_factory=list)
    detail_level_changes: list[str] = Field(default_factory=list)
    findings_changes: dict[str, int] = Field(default_factory=dict)
    non_authoritative: bool = True


class OutlineBatchManifest(StrictModel):
    """M13 Compile Center 直接显示的数据（只读汇总，不是 truth）。"""

    session_id: str = Field(default="", max_length=64)
    novel_id: str = Field(default="", max_length=96)
    status: BatchStatus = "pending"
    scope_complete: bool = False
    batch_order: list[str] = Field(default_factory=list)
    revision_chain: list[dict[str, str]] = Field(default_factory=list)
    scope: CompilationScope = Field(default_factory=CompilationScope)
    target_detail_level: DetailLevel = "arc"
    detail_changes: list[str] = Field(default_factory=list)
    findings_count: dict[str, int] = Field(default_factory=dict)
    retry_count: int = 0
    human_reviews: list[str] = Field(default_factory=list)
    carryover: list[dict[str, Any]] = Field(default_factory=list)
    final_revision_id: str = Field(default="", max_length=64)
    non_authoritative: bool = True


class ElaborationStatus(StrictModel):
    """Progressive Elaboration 派生状态（detail_level 仍来自 Planning 对象）。"""

    object_id: str = Field(default="", max_length=64)
    object_kind: str = Field(default="volume", max_length=32)
    current_detail_level: DetailLevel = "spine"
    target_detail_level: DetailLevel = "arc"
    ready: bool = False
    blocked_by: list[str] = Field(default_factory=list)
    source_revision: str = Field(default="", max_length=64)
    last_compiled_revision: str = Field(default="", max_length=64)
    non_authoritative: bool = True


class OutlineBatchFailure(RuntimeError):
    """编译器 / provider 抛出的、带结构化分类的失败（供 retry taxonomy 使用）。"""

    def __init__(self, error_class: FailureClass, summary: str = "") -> None:
        self.error_class = error_class
        self.summary = summary or error_class
        super().__init__(f"{error_class}: {self.summary}")


class OutlineBatchError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


class OutlineBatchStore:
    """checkpoint / session / manifest / candidate 独立持久化（原子写，绝不与 revisions 混放）。"""

    def __init__(self, project_root: Path, novel_id: str,
                 *, root: Path | str = "novel/authoring/story_engine/planning") -> None:
        base = (Path(root).resolve() if Path(root).is_absolute()
                else (project_root / Path(root)).resolve())
        self.root = base / novel_id / "batch_sessions"

    def session_dir(self, session_id: str) -> Path:
        return self.root / session_id

    def path(self, session_id: str, name: str) -> Path:
        return self.session_dir(session_id) / name

    def list_sessions(self) -> list[str]:
        if not self.root.is_dir():
            return []
        return sorted(item.name for item in self.root.iterdir()
                      if item.is_dir() and (item / "session.json").is_file())

    def save_session(self, session: OutlineBatchSession) -> OutlineBatchSession:
        self._atomic_write(self.path(session.session_id, "session.json"),
                           session.model_dump(mode="json"))
        return session

    def load_session(self, session_id: str) -> OutlineBatchSession:
        path = self.path(session_id, "session.json")
        if not path.is_file():
            raise OutlineBatchError("BATCH_SESSION_NOT_FOUND", session_id)
        return OutlineBatchSession.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def save_checkpoint(self, checkpoint: OutlineBatchCheckpoint) -> OutlineBatchCheckpoint:
        self._atomic_write(self.path(checkpoint.session_id,
                                     f"checkpoint_{checkpoint.batch_id}.json"),
                           checkpoint.model_dump(mode="json"))
        return checkpoint

    def load_checkpoint(self, session_id: str,
                        batch_id: str) -> OutlineBatchCheckpoint | None:
        path = self.path(session_id, f"checkpoint_{batch_id}.json")
        if not path.is_file():
            return None
        try:
            return OutlineBatchCheckpoint.model_validate(
                json.loads(path.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001 - 半个 JSON 视为缺失（原子写应当避免）
            return None

    def save_manifest(self, manifest: OutlineBatchManifest) -> OutlineBatchManifest:
        self._atomic_write(self.path(manifest.session_id, "manifest.json"),
                           manifest.model_dump(mode="json"))
        return manifest

    def save_candidate(self, session_id: str,
                       candidate: OutlineCompilationCandidate) -> OutlineCompilationCandidate:
        self._atomic_write(self.path(session_id, f"candidate_{candidate.candidate_id}.json"),
                           candidate.model_dump(mode="json"))
        return candidate

    def load_candidate(self, session_id: str,
                       candidate_id: str) -> OutlineCompilationCandidate | None:
        if not candidate_id:
            return None
        path = self.path(session_id, f"candidate_{candidate_id}.json")
        if not path.is_file():
            return None
        try:
            return OutlineCompilationCandidate.model_validate(
                json.loads(path.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _atomic_write(path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        body = json.dumps(payload, ensure_ascii=False, indent=1) + "\n"
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(body)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


# ---------------------------------------------------------------- 派生 / 计划
def plan_elaboration_status(plan: StoryPlanningIR, *, target: str = "arc",
                            revision_id: str = "") -> list[ElaborationStatus]:
    """Progressive Elaboration 状态：detail_level 来自 Planning 对象，不另建 truth。"""

    rows: list[ElaborationStatus] = []
    volumes = list(plan.volumes or [])
    if not volumes:
        return [ElaborationStatus(object_id=plan.planning_id or plan.novel_id,
                                  object_kind="book",
                                  current_detail_level=(plan.intent.detail_level
                                                        if plan.intent else "spine"),
                                  target_detail_level=target, source_revision=revision_id)]
    for volume in volumes:
        rows.append(ElaborationStatus(
            object_id=volume.volume_id, object_kind="volume",
            current_detail_level=volume.detail_level, target_detail_level=target,
            ready=DETAIL_ORDER.get(volume.detail_level, 0) >= DETAIL_ORDER.get(target, 3),
            source_revision=revision_id))
    return rows


def check_detail_target(target: str) -> None:
    """M8B 最多提升到 arc；chapter_ready 属于 M9。"""

    if target not in DETAIL_ORDER:
        raise OutlineBatchError("DETAIL_LEVEL_UNKNOWN", target)
    if DETAIL_ORDER[target] > DETAIL_ORDER[M8B_MAX_DETAIL]:
        raise OutlineBatchError("DETAIL_LEVEL_REQUIRES_M9",
                                f"{target} 需要 M9 Chapter Semantic IR compiler")


def plan_batch_scopes(session: OutlineBatchSession, plan: StoryPlanningIR, *,
                      profile: SegmentationProfile | None = None) -> list[OutlineBatchTask]:
    """按当前 detail level 生成待办任务（不做 full_book；只推进 scope 内未达标的卷）。"""

    check_detail_target(session.target_detail_level)
    _ = profile or SegmentationProfile()
    volumes = list(plan.volumes or [])
    scope = session.target_scope
    target_rank = DETAIL_ORDER.get(session.target_detail_level, 3)
    if not volumes:
        return [OutlineBatchTask(
            batch_id="BATCH_001", sequence=1,
            source_revision_id=session.current_revision_id,
            source_digest=session.current_digest,
            scope=CompilationScope(kind="spine_segment",
                                   node_ids=[node.node_id for node in plan.plot_nodes],
                                   note="spine_to_volumes"),
            source_detail_level="spine", target_detail_level=session.target_detail_level)]
    scope_nodes = set(scope.node_ids)
    scope_indexes = set(scope.volume_indexes)
    if scope.note:
        scope_nodes.add(scope.note)

    def in_scope(volume: VolumePlan) -> bool:
        if scope.kind in ("full_book", "next_volume", "next_arc"):
            return True
        if scope.kind == "volume_range":
            if not scope_nodes and not scope_indexes:
                return True
            return volume.volume_id in scope_nodes or volume.index in scope_indexes
        return bool(set(volume.major_nodes) & scope_nodes) or volume.volume_id in scope_nodes

    pending = [volume for volume in volumes
               if in_scope(volume) and volume.major_nodes
               and DETAIL_ORDER.get(volume.detail_level, 0) < target_rank]
    if scope.kind in ("next_volume", "next_arc"):
        pending = pending[:1]
    tasks: list[OutlineBatchTask] = []
    for sequence, volume in enumerate(pending, start=1):
        node_ids = list(volume.major_nodes)
        if volume.climax_node_id and volume.climax_node_id not in node_ids:
            node_ids.append(volume.climax_node_id)
        tasks.append(OutlineBatchTask(
            batch_id=f"BATCH_{sequence:03d}", sequence=sequence,
            source_revision_id=session.current_revision_id,
            source_digest=session.current_digest,
            scope=CompilationScope(kind="volume_range", node_ids=node_ids,
                                   volume_indexes=[volume.index], note=volume.volume_id),
            source_detail_level=volume.detail_level,
            target_detail_level=session.target_detail_level,
            dependency_batch_ids=[f"BATCH_{sequence - 1:03d}"] if sequence > 1 else []))
    return tasks


def _volume_order(plan: StoryPlanningIR) -> list[VolumePlan]:
    return sorted(plan.volumes or [], key=lambda item: (item.index, item.volume_id))


def _next_volume_id(plan: StoryPlanningIR, volume_id: str) -> str:
    order = _volume_order(plan)
    for index, volume in enumerate(order):
        if volume.volume_id == volume_id:
            return order[index + 1].volume_id if index + 1 < len(order) else ""
    return ""


def _batch_note(session_id: str, batch_id: str, candidate_id: str = "") -> str:
    tail = f" candidate {candidate_id}" if candidate_id else ""
    return f"M8B {session_id} {batch_id}{tail}"


class OutlineBatchCompiler:
    """确定性 batch orchestrator：compile → validate → (safe) promote → checkpoint → next。"""

    def __init__(self, repository: PlanningRepository, *,
                 store: OutlineBatchStore | None = None,
                 compiler: OutlineCompiler | None = None) -> None:
        self.repository = repository
        self.store = store or OutlineBatchStore(repository.project_root, repository.novel_id)
        self.compiler = compiler

    # ---------------------------------------------------------------- config
    def _compiler_for(self, config: CompilerConfig) -> OutlineCompiler:
        if self.compiler is not None:
            return self.compiler
        return OutlineCompiler(average_chapter_words=config.segmentation.chapter_target_words)

    def _config_of(self, session: OutlineBatchSession) -> CompilerConfig:
        payload = session.batch_policy.get("config") or {}
        return CompilerConfig.model_validate(payload) if payload else CompilerConfig()

    # ---------------------------------------------------------------- session
    def create_session(self, *, target_detail_level: str = "arc",
                       scope: CompilationScope | None = None,
                       promotion_policy: PromotionPolicy | None = None,
                       config: CompilerConfig | None = None,
                       root_revision_id: str = "",
                       session_id: str = "") -> OutlineBatchSession:
        check_detail_target(target_detail_level)
        head = (self.repository.load(root_revision_id) if root_revision_id
                else self.repository.resolve_branch_head())
        if head is None:
            raise OutlineBatchError("BATCH_SESSION_NO_HEAD", "repository 没有 revision")
        config = config or CompilerConfig(
            target_words=head.plan.intent.target_words if head.plan.intent else 0)
        policy = promotion_policy or PromotionPolicy()
        session = OutlineBatchSession(
            session_id=session_id or f"BATCHSESS_{uuid.uuid4().hex[:10].upper()}",
            novel_id=head.novel_id, root_planning_revision_id=head.revision_id,
            root_digest=head.content_digest, current_revision_id=head.revision_id,
            current_digest=head.content_digest,
            target_scope=scope or CompilationScope(kind="next_volume"),
            target_detail_level=target_detail_level,  # type: ignore[arg-type]
            batch_policy={"max_attempts": policy.max_attempts,
                          "config": config.model_dump(mode="json"),
                          "execution_registry": {}, "carry_registry": {}},
            promotion_policy=policy, config_digest=config.digest(), status="pending")
        session.tasks = plan_batch_scopes(session, head.plan, profile=config.segmentation)
        session.pending_batch_ids = [task.batch_id for task in session.tasks]
        return self.store.save_session(session)

    def _verify_session(self, session: OutlineBatchSession) -> CompilerConfig:
        """resume 前校验：branch head / digest / config（不按 batch 序号猜）。"""

        head = self.repository.resolve_branch_head()
        if head is None or head.revision_id != session.current_revision_id:
            raise OutlineBatchError(
                "STALE_BATCH_SESSION",
                "branch head 已被外部推进；选项：resume_on_original_branch / rebase / "
                "restart_batch_session（不会自动 merge）")
        current = self.repository.load(session.current_revision_id)
        if current.content_digest != session.current_digest:
            raise OutlineBatchError("STALE_BATCH_SESSION",
                                    "current revision digest 不匹配（revision 被改写？）")
        config = self._config_of(session)
        if config.digest() != session.config_digest:
            raise OutlineBatchError("CONFIG_CHANGED_SINCE_CHECKPOINT",
                                    "编译配置在 checkpoint 之后发生变化；请显式 recompile / restart")
        return config

    def repair_session(self, session_id: str) -> OutlineBatchSession:
        """崩溃一致性：repository 已 promote 但 checkpoint / session 没来得及写 → 先补记。

        只补写 checkpoint 与派生注册表，绝不重新 promote（不生成重复 revision）。
        """

        session = self.store.load_session(session_id)
        changed = False
        for task in sorted(session.tasks, key=lambda item: item.sequence):
            checkpoint = self.store.load_checkpoint(session.session_id, task.batch_id)
            if checkpoint is not None and checkpoint.status == "promoted":
                continue
            for meta in self.repository.list_revisions():
                note = meta.note or ""
                if session.session_id not in note or task.batch_id not in note:
                    continue
                record = self.repository.load(meta.revision_id)
                recovered = OutlineBatchCheckpoint(
                    session_id=session.session_id, batch_id=task.batch_id,
                    source_revision_id=record.source_revision or task.source_revision_id,
                    source_digest=task.source_digest, scope=task.scope,
                    target_detail_level=task.target_detail_level,
                    config_digest=session.config_digest, status="promoted",
                    attempt_count=task.attempt_count or 1,
                    promoted_revision_id=record.revision_id,
                    promoted_digest=record.content_digest,
                    completed_steps=["compile", "validate", "promote"], pending_steps=[],
                    resume_state={"recovered": True, "promoted_note": note})
                self.store.save_checkpoint(recovered)
                session = self._update_session(session, task.model_copy(update={
                    "status": "promoted", "promoted_revision_id": record.revision_id,
                    "completed_at": datetime.now(timezone.utc)}))
                changed = True
                break
        if changed:
            session = self._rebuild_registries(session)
            self.store.save_manifest(self.manifest(session_id))
        return session

    def extend_plan(self, session_id: str) -> OutlineBatchSession:
        """按当前 head 重新规划待办 batch（Progressive Elaboration 前进式扩展）。"""

        session = self.store.load_session(session_id)
        config = self._verify_session(session)
        head = self.repository.load(session.current_revision_id)
        block = plan_batch_scopes(session, head.plan, profile=config.segmentation)
        covered = {task.scope.note for task in session.tasks
                   if task.status not in ("superseded", "skipped") and task.scope.note}
        offset = max([task.sequence for task in session.tasks] or [0])
        previous = ""
        renamed: list[OutlineBatchTask] = []
        for task in block:
            if task.scope.note and task.scope.note in covered:
                continue
            batch_id = f"BATCH_{offset + len(renamed) + 1:03d}"
            renamed.append(task.model_copy(update={
                "batch_id": batch_id, "sequence": offset + len(renamed) + 1,
                "source_revision_id": head.revision_id, "source_digest": head.content_digest,
                "dependency_batch_ids": [previous] if previous else []}))
            previous = renamed[-1].batch_id
        if not renamed:
            return session
        tasks = list(session.tasks) + renamed
        session = session.model_copy(update={
            "tasks": tasks,
            "pending_batch_ids": [task.batch_id for task in tasks
                                  if task.status in ("pending", "ready", "retryable_failed")],
            "updated_at": datetime.now(timezone.utc)})
        return self.store.save_session(session)

    def restart_batch_session(self, session_id: str, *,
                              base_revision_id: str = "") -> OutlineBatchSession:
        """STALE_BATCH_SESSION 的显式选项之一：以当前（或指定）head 重新开一轮 session。

        不做自动 merge：旧 session 标记 superseded，其 revisions 全部保留在历史里。
        """

        old = self.store.load_session(session_id)
        head = (self.repository.load(base_revision_id) if base_revision_id
                else self.repository.resolve_branch_head())
        if head is None:
            raise OutlineBatchError("BATCH_SESSION_NO_HEAD", "repository 没有 revision")
        restarted = self.create_session(
            target_detail_level=old.target_detail_level, scope=old.target_scope,
            promotion_policy=old.promotion_policy, config=self._config_of(old),
            root_revision_id=head.revision_id,
            session_id=f"{old.session_id}_R{uuid.uuid4().hex[:6].upper()}")
        restarted.batch_policy["restarted_from"] = old.session_id
        old = old.model_copy(update={"status": "superseded",
                                     "updated_at": datetime.now(timezone.utc)})
        self.store.save_session(old)
        return self.store.save_session(restarted)

    # ---------------------------------------------------------------- batch
    def run_batch(self, session_id: str, batch_id: str, *,
                  approve: bool | None = None
                  ) -> tuple[OutlineBatchTask, OutlineBatchCheckpoint]:
        self.repair_session(session_id)      # crash 后先补记，再做 stale / config 判定
        session = self.store.load_session(session_id)
        config = self._verify_session(session)
        task = next((item for item in session.tasks if item.batch_id == batch_id), None)
        if task is None:
            raise OutlineBatchError("BATCH_NOT_FOUND", batch_id)
        unmet = [dep for dep in task.dependency_batch_ids
                 if dep not in session.completed_batch_ids]
        if unmet:
            return self._halt(session, task, "blocked", "VALIDATION",
                              f"依赖 batch 尚未 promote：{unmet}")
        checkpoint = self.store.load_checkpoint(session_id, batch_id)
        if checkpoint is not None and checkpoint.status == "promoted":
            return task, checkpoint          # idempotency：已 promote 的 batch 绝不重跑
        if checkpoint is not None and checkpoint.config_digest \
                and checkpoint.config_digest != config.digest():
            raise OutlineBatchError("CONFIG_CHANGED_SINCE_CHECKPOINT",
                                    f"{batch_id} 的 checkpoint 使用了不同配置")
        recovered = self._recover_from_promotion(session, task, checkpoint)
        if recovered is not None:
            return task, recovered
        base = self.repository.load(session.current_revision_id)   # 链条：永远基于当前 head
        task = task.model_copy(update={"source_revision_id": base.revision_id,
                                       "source_digest": base.content_digest})
        candidate: OutlineCompilationCandidate | None = None
        if checkpoint is not None and checkpoint.status == "validated" \
                and checkpoint.source_revision_id == base.revision_id \
                and checkpoint.candidate_id:
            # manual 模式 approve 时复用已编译 candidate；human_review / blocked 后必须重编
            candidate = self.store.load_candidate(session_id, checkpoint.candidate_id)
        if candidate is None:
            task = task.model_copy(update={"status": "running",
                                           "attempt_count": task.attempt_count + 1,
                                           "started_at": datetime.now(timezone.utc)})
            try:
                candidate = self._compiler_for(config).compile(
                    base.plan, revision_id=base.revision_id, scope=task.scope,
                    route_provenance={"session_id": session_id, "batch_id": batch_id,
                                      "compiler": "m8b"})
            except OutlineBatchFailure as exc:
                return self._halt(session, task, self._status_for(exc.error_class, task),
                                  exc.error_class, exc.summary)
            except ValueError as exc:
                return self._halt(session, task, "failed", "VALIDATION", str(exc)[:200])
            except (OSError, TimeoutError) as exc:
                return self._halt(session, task, self._status_for("TRANSIENT_IO", task),
                                  "TRANSIENT_IO", str(exc)[:200])
            except OutlineBatchError as exc:
                review = exc.code in HUMAN_REVIEW_CODES
                return self._halt(session, task, "human_review" if review else "failed",
                                  "HUMAN_REVIEW" if review else "INTERNAL_ERROR",
                                  f"{exc.code}: {exc.message}"[:200])
            except Exception as exc:  # noqa: BLE001
                return self._halt(session, task, "failed", "INTERNAL_ERROR",
                                  f"{type(exc).__name__}: {exc}"[:200])
            candidate = self._retag_candidate(candidate, session, task, base.plan)
            self.store.save_candidate(session_id, candidate)
        full_book = len(set(task.scope.node_ids)) >= len(base.plan.plot_nodes)
        findings = self._scope_findings(candidate, task, full_book=full_book)
        findings.extend(self._cross_batch_check(session, base.plan, task, candidate, config))
        status, review = self._classify(findings, config)
        checkpoint = self._checkpoint(session, task, candidate, findings,
                                      status=status, config=config,
                                      attempt=task.attempt_count, review=review)
        self.store.save_checkpoint(checkpoint)
        task = task.model_copy(update={
            "status": status, "candidate_id": candidate.candidate_id,
            "findings_digest": planning_digest(
                [item.model_dump(mode="json") for item in findings]),
            "checkpoint_ref": f"checkpoint_{batch_id}.json",
            "completed_at": datetime.now(timezone.utc)})
        session = self._update_session(session, task)
        if status != "validated":
            return task, checkpoint
        should_promote = (approve if approve is not None
                          else session.promotion_policy.mode == "safe_auto")
        if not should_promote:
            session = session.model_copy(update={"status": "validated",
                                                 "updated_at": datetime.now(timezone.utc)})
            self.store.save_session(session)
            return task, checkpoint
        return self._promote(session, task, candidate, findings, checkpoint,
                             config=config, review=review)

    def approve_batch(self, session_id: str, batch_id: str
                      ) -> tuple[OutlineBatchTask, OutlineBatchCheckpoint]:
        """manual 模式：作者 approve 后 promote（复用已有 candidate，不重新生成结构）。"""

        return self.run_batch(session_id, batch_id, approve=True)

    def retry_batch(self, session_id: str, batch_id: str) -> OutlineBatchTask:
        """作者已解决 review / blocker 后，显式把该 batch 放回队列。

        Human Review 绝不自动 retry：只有作者调用这个方法（或 resume(retry_review=True)）
        才会重新编译。
        """

        self.repair_session(session_id)
        session = self.store.load_session(session_id)
        task = next((item for item in session.tasks if item.batch_id == batch_id), None)
        if task is None:
            raise OutlineBatchError("BATCH_NOT_FOUND", batch_id)
        if task.status == "promoted":
            raise OutlineBatchError("BATCH_ALREADY_PROMOTED", batch_id)
        updated = task.model_copy(update={"status": "ready", "error_class": None,
                                          "error_summary": "", "completed_at": None})
        tasks = [updated if item.batch_id == batch_id else item for item in session.tasks]
        session = session.model_copy(update={
            "tasks": tasks, "status": "pending",
            "pending_batch_ids": [item.batch_id for item in tasks
                                  if item.status in ("pending", "ready", "retryable_failed")],
            # review 历史保留（audit trail）：只把 batch 放回队列，不抹掉它曾经需要作者判断
            "failed_batch_ids": [item for item in session.failed_batch_ids
                                 if item != batch_id],
            "retryable_batch_ids": [item for item in session.retryable_batch_ids
                                    if item != batch_id],
            "updated_at": datetime.now(timezone.utc)})
        self.store.save_session(session)
        return updated

    # ---------------------------------------------------------------- helpers
    @staticmethod
    def _status_for(error_class: str, task: OutlineBatchTask) -> BatchStatus:
        if error_class in RETRYABLE_FAILURES:
            return "retryable_failed"
        if error_class == "HUMAN_REVIEW":
            return "human_review"
        return "failed"

    def _review_findings(self, findings: list[PlanningFinding],
                         config: CompilerConfig) -> list[BatchReviewFinding]:
        policy = config_warning_policy(config)
        rows: list[BatchReviewFinding] = []
        for finding in findings:
            if finding.severity == "ERROR" and finding.code in HUMAN_REVIEW_CODES:
                rows.append(BatchReviewFinding(
                    code=finding.code, message=finding.message,
                    related_ids=list(finding.related_ids)))
            elif policy.classify(finding.code) == "review_recommended":
                rows.append(BatchReviewFinding(
                    code=finding.code,
                    message=f"{finding.code}: {finding.message}"[:300],
                    related_ids=list(finding.related_ids)))
        return rows

    def _scope_ids(self, task: OutlineBatchTask,
                   candidate: OutlineCompilationCandidate) -> set[str]:
        ids = set(task.scope.node_ids)
        if task.scope.note:
            ids.add(task.scope.note)
        ids.update(volume.volume_id for volume in candidate.volume_plans)
        ids.update(arc.arc_id for arc in candidate.arc_plans)
        ids.add(candidate.candidate_id)
        ids.add(task.batch_id)
        return ids

    def _scope_findings(self, candidate: OutlineCompilationCandidate,
                        task: OutlineBatchTask, *, full_book: bool = False
                        ) -> list[PlanningFinding]:
        """单批 validation：scope 之外节点的 unallocated 等不算本批问题（留给对应 batch）。"""

        scope_ids = self._scope_ids(task, candidate)
        kept: list[PlanningFinding] = []
        for finding in candidate.validation_findings:
            if finding.code in TARGET_ALIGNMENT_CODES and not full_book:
                # 目标词数对齐只能按全书判断；单批 scope 的预算不构成结论（session gate 复核）
                continue
            if finding.code not in NODE_SCOPED_FINDING_CODES:
                kept.append(finding)
                continue
            related = set(finding.related_ids)
            if finding.source_id:
                related.add(finding.source_id)
            if related & scope_ids:
                kept.append(finding)
        return kept

    def _cross_batch_check(self, session: OutlineBatchSession, plan: StoryPlanningIR,
                           task: OutlineBatchTask, candidate: OutlineCompilationCandidate,
                           config: CompilerConfig) -> list[PlanningFinding]:
        """增量跨批校验：边界冻结、execution 唯一、carryover 不消失。"""

        findings: list[PlanningFinding] = []
        scope_nodes = set(task.scope.node_ids)
        target_rank = DETAIL_ORDER.get(task.target_detail_level, 3)
        replaced = self._replaced_volume_ids(plan, task, candidate)
        for volume in plan.volumes:
            if DETAIL_ORDER.get(volume.detail_level, 0) < target_rank:
                continue      # 还没到 arc 的卷允许被本批重新切
            overlap = set(volume.major_nodes) & scope_nodes
            if overlap and not set(volume.major_nodes) <= scope_nodes:
                add_finding(findings, "BOUNDARY_REVISION_REQUIRED", "ERROR", "outline",
                            volume.volume_id,
                            "本批 scope 与已 promote 的卷边界只部分重叠；已定边界默认冻结",
                            related=tuple(sorted(overlap)[:10]))
        existing = {node_id for volume in plan.volumes
                    if volume.volume_id not in replaced for node_id in volume.major_nodes}
        duplicates = sorted({item.node_id for item in candidate.node_allocations} & existing)
        if duplicates:
            add_finding(findings, "CROSS_BATCH_DUPLICATE_EXECUTION_NODE", "ERROR", "outline",
                        candidate.candidate_id,
                        "batch 重复分配了已经 execution 的 PlotNode",
                        related=tuple(duplicates[:10]))
        carry_findings, _ = self._carry_updates(session, task, plan, candidate, config)
        findings.extend(carry_findings)
        return findings

    def _replaced_volume_ids(self, plan: StoryPlanningIR, task: OutlineBatchTask,
                             candidate: OutlineCompilationCandidate) -> set[str]:
        scope_nodes = set(task.scope.node_ids)
        if task.scope.note:
            scope_nodes.add(task.scope.note)
        new_ids = {volume.volume_id for volume in candidate.volume_plans}
        replaced: set[str] = set()
        for volume in plan.volumes:
            if volume.volume_id in new_ids:
                replaced.add(volume.volume_id)
            elif volume.major_nodes and set(volume.major_nodes) <= scope_nodes:
                replaced.add(volume.volume_id)
        return replaced

    def _future_volume_order(self, plan: StoryPlanningIR, task: OutlineBatchTask,
                             candidate: OutlineCompilationCandidate) -> list[str]:
        """本批 promote 之后的卷顺序（用于 carryover chain 指向下一卷）。"""

        replaced = self._replaced_volume_ids(plan, task, candidate)
        order = {node_id: index for index, node_id in enumerate(topological_order(plan))}

        def rank(volume: VolumePlan) -> tuple[int, str]:
            positions = [order.get(node_id, len(order)) for node_id in volume.major_nodes]
            return (min(positions) if positions else len(order), volume.volume_id)

        kept = [volume for volume in plan.volumes if volume.volume_id not in replaced]
        merged = sorted(kept + list(candidate.volume_plans), key=rank)
        return [volume.volume_id for volume in merged]

    def _volume_replacements(self, plan: StoryPlanningIR, task: OutlineBatchTask,
                             candidate: OutlineCompilationCandidate) -> dict[str, str]:
        """被替换的旧卷 → 承接它的新卷（用于把 carryover 目标翻译到新 revision）。"""

        replacements: dict[str, str] = {}
        order = {node_id: index for index, node_id in enumerate(topological_order(plan))}

        def rank(volume: VolumePlan) -> tuple[int, str]:
            positions = [order.get(node_id, len(order)) for node_id in volume.major_nodes]
            return (min(positions) if positions else len(order), volume.volume_id)

        ordered_new = sorted(candidate.volume_plans, key=rank)
        replaced = self._replaced_volume_ids(plan, task, candidate)
        for volume in plan.volumes:
            if volume.volume_id not in replaced:
                continue
            touched = [new for new in ordered_new
                       if set(new.major_nodes) & set(volume.major_nodes)]
            replacements[volume.volume_id] = (touched[0].volume_id if touched
                                              else volume.volume_id)
        return replacements

    def _carry_updates(self, session: OutlineBatchSession, task: OutlineBatchTask,
                       plan: StoryPlanningIR,
                       candidate: OutlineCompilationCandidate, config: CompilerConfig
                       ) -> tuple[list[PlanningFinding], dict[str, dict[str, Any]]]:
        """carryover chain：V1→V2→V3 必须显式可见；重大 pressure 长期未处理给 WARNING。"""

        findings: list[PlanningFinding] = []
        registry = dict(session.batch_policy.get("carry_registry") or {})
        updates: dict[str, dict[str, Any]] = {}
        new_volume_ids = {volume.volume_id for volume in candidate.volume_plans}
        replacements = self._volume_replacements(plan, task, candidate)
        future_order = self._future_volume_order(plan, task, candidate)

        def next_of(volume_id: str) -> str:
            if volume_id in future_order:
                position = future_order.index(volume_id)
                return future_order[position + 1] if position + 1 < len(future_order) else ""
            return _next_volume_id(plan, volume_id)

        inventory = build_plot_pressure_inventory(plan, revision_id=session.current_revision_id)
        tolerance = config.segmentation.carryover_tolerance
        ignored = set(candidate.ignored_pressure_ids)
        for pressure_id, row in sorted(registry.items()):
            if row.get("status") in CLOSED_CARRY_STATES:
                continue
            target = row.get("to_volume", "")
            if not target or (target not in new_volume_ids and target not in replacements):
                continue      # 还没轮到这一批
            current = replacements.get(target, target)
            pressure = inventory.by_id(pressure_id)
            if pressure is None:
                add_finding(findings, "PRESSURE_LOST_AT_BATCH_BOUNDARY", "ERROR", "outline",
                            pressure_id, "batch boundary 让未解决 pressure 消失（不在任何清单里）",
                            related=tuple(sorted(new_volume_ids)))
                continue
            if pressure.state in ("resolved", "scheduled"):
                updates[pressure_id] = {**row, "status": pressure.state,
                                        "last_seen_volume": current}
                continue
            if pressure_id in ignored or pressure.state == "ignored":
                updates[pressure_id] = {**row, "status": "ignored"}
                continue
            count = int(row.get("carry_count", 0)) + 1
            updates[pressure_id] = {
                "pressure_id": pressure_id,
                "origin_volume": row.get("origin_volume") or current,
                "last_seen_volume": current, "to_volume": next_of(current),
                "carry_count": count, "reason": row.get("reason", ""),
                "status": pressure.state,
                "author_intent_ref": row.get("author_intent_ref", "")}
            if count > tolerance:
                add_finding(findings, "LONG_RUNNING_PRESSURE", "WARNING", "outline",
                            pressure_id, "重大 pressure 连续过多 Volume 未处理",
                            carry_count=count, tolerance=tolerance)
        for row in candidate.carryover_pressures:
            pressure_id = row.pressure_id
            if pressure_id in updates:
                continue
            existing = registry.get(pressure_id) or {}
            if existing and existing.get("status") not in CLOSED_CARRY_STATES:
                count = int(existing.get("carry_count", 0)) + 1
                updates[pressure_id] = {
                    **existing, "last_seen_volume": row.from_volume,
                    "to_volume": row.to_volume or existing.get("to_volume", ""),
                    "carry_count": count, "status": row.status,
                    "reason": row.reason or existing.get("reason", "")}
                if count > tolerance:
                    add_finding(findings, "LONG_RUNNING_PRESSURE", "WARNING", "outline",
                                pressure_id, "重大 pressure 连续过多 Volume 未处理",
                                carry_count=count, tolerance=tolerance)
                continue
            updates[pressure_id] = {
                "pressure_id": pressure_id, "origin_volume": row.from_volume,
                "last_seen_volume": row.from_volume, "to_volume": row.to_volume,
                "carry_count": 1, "reason": row.reason, "status": row.status,
                "author_intent_ref": row.author_intent_ref}
        return findings, updates

    def _classify(self, findings: list[PlanningFinding], config: CompilerConfig
                  ) -> tuple[BatchStatus, list[BatchReviewFinding]]:
        policy = config_warning_policy(config)
        review = self._review_findings(findings, config)
        errors = [item for item in findings if item.severity == "ERROR"]
        blocking_warnings = [item for item in findings
                             if policy.classify(item.code) == "promotion_blocking"]
        if review:
            return "human_review", review
        if errors or blocking_warnings:
            return "blocked", []
        return "validated", []

    def _retag_candidate(self, candidate: OutlineCompilationCandidate,
                         session: OutlineBatchSession, task: OutlineBatchTask,
                         plan: StoryPlanningIR) -> OutlineCompilationCandidate:
        """batch 级稳定 id + 本批 provenance：跨批不撞 id，重复执行 digest 不变。"""

        key = task.batch_id.split("_", 1)[-1]
        volume_map = {volume.volume_id: f"VOL_B{key}_{index:02d}"
                      for index, volume in enumerate(candidate.volume_plans, start=1)}
        arc_map: dict[str, str] = {}
        for volume in candidate.volume_plans:
            volume_arcs = [arc for arc in candidate.arc_plans
                           if arc.volume_id == volume.volume_id]
            for index, arc in enumerate(volume_arcs, start=1):
                arc_map[arc.arc_id] = (f"ARC_B{key}_{volume_map[volume.volume_id][-2:]}"
                                       f"_{index:02d}")
        note = _batch_note(session.session_id, task.batch_id)
        volumes = [volume.model_copy(update={
            "volume_id": volume_map[volume.volume_id],
            "arc_ids": [arc_map[arc_id] for arc_id in volume.arc_ids if arc_id in arc_map],
            "source": "outline_batch", "note": f"{note} | {volume.note}"[:300]})
            for volume in candidate.volume_plans]
        arcs = [arc.model_copy(update={
            "arc_id": arc_map[arc.arc_id], "volume_id": volume_map[arc.volume_id],
            "source": "outline_batch",
            "note": f"{note} | {arc.note}"[:300]}) for arc in candidate.arc_plans]
        allocations = [item.model_copy(update={
            "execution_volume_id": volume_map.get(item.execution_volume_id,
                                                  item.execution_volume_id),
            "primary_arc_id": arc_map.get(item.primary_arc_id, item.primary_arc_id)})
            for item in candidate.node_allocations]
        sequence = [volume.volume_id for volume in volumes]
        tail = _next_volume_id(plan, task.scope.note) if task.scope.note else ""
        if tail:
            sequence.append(tail)
        carryover = []
        for row in candidate.carryover_pressures:
            from_volume = volume_map.get(row.from_volume, row.from_volume)
            to_volume = row.to_volume
            if from_volume in sequence:
                position = sequence.index(from_volume)
                to_volume = sequence[position + 1] if position + 1 < len(sequence) else ""
            elif to_volume:
                to_volume = volume_map.get(to_volume, to_volume)
            carryover.append(row.model_copy(update={"from_volume": from_volume,
                                                    "to_volume": to_volume}))
        seed = "|".join([session.session_id, task.batch_id, candidate.source_revision_id,
                         candidate.source_digest,
                         json.dumps(task.scope.model_dump(mode="json"), sort_keys=True,
                                    ensure_ascii=False),
                         session.config_digest])
        digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:10].upper()
        return candidate.model_copy(update={
            "candidate_id": f"CAND_BATCH_{key}_{digest}",
            "volume_plans": volumes, "arc_plans": arcs,
            "node_allocations": allocations, "carryover_pressures": carryover,
            "route_provenance": {**dict(candidate.route_provenance),
                                 "session_id": session.session_id,
                                 "batch_id": task.batch_id, "batch_key": key}})

    def _checkpoint(self, session: OutlineBatchSession, task: OutlineBatchTask,
                    candidate: OutlineCompilationCandidate, findings: list[PlanningFinding],
                    *, status: BatchStatus, config: CompilerConfig, attempt: int,
                    review: list[BatchReviewFinding] | None = None,
                    promoted: PlanningRevisionRecord | None = None
                    ) -> OutlineBatchCheckpoint:
        previous = self.store.load_checkpoint(session.session_id, task.batch_id)
        return OutlineBatchCheckpoint(
            session_id=session.session_id, batch_id=task.batch_id,
            source_revision_id=task.source_revision_id or session.current_revision_id,
            source_digest=task.source_digest or session.current_digest,
            scope=task.scope, target_detail_level=task.target_detail_level,
            candidate_id=candidate.candidate_id,
            candidate_digest=planning_digest(candidate.model_dump(mode="json")),
            validation_digest=planning_digest(
                [item.model_dump(mode="json") for item in findings]),
            promoted_revision_id=promoted.revision_id if promoted else "",
            promoted_digest=promoted.content_digest if promoted else "",
            config_digest=config.digest(), status=status, attempt_count=attempt,
            completed_steps=(["compile", "validate"] + (["promote"] if promoted else [])),
            pending_steps=[] if promoted else ["approve", "promote"],
            findings=findings, review_findings=list(review or []),
            next_retry_at=(datetime.now(timezone.utc) if status == "retryable_failed" else None),
            last_attempt_at=datetime.now(timezone.utc),
            created_at=previous.created_at if previous else datetime.now(timezone.utc))

    def _update_session(self, session: OutlineBatchSession,
                        task: OutlineBatchTask) -> OutlineBatchSession:
        tasks = [task if item.batch_id == task.batch_id else item for item in session.tasks]
        promoted_digest = session.current_digest
        if task.promoted_revision_id:
            promoted_digest = self.repository.load(task.promoted_revision_id).content_digest
        status: BatchStatus = session.status
        if any(item.status == "human_review" for item in tasks):
            status = "human_review"
        elif any(item.status in ("blocked", "failed") for item in tasks):
            status = "blocked"
        elif any(item.status in ("pending", "ready", "retryable_failed") for item in tasks):
            status = "running"
        elif any(item.status == "validated" for item in tasks):
            status = "validated"
        elif tasks and all(item.status in ("promoted", "skipped") for item in tasks):
            status = "promoted"
        updated = session.model_copy(update={
            "tasks": tasks,
            "pending_batch_ids": [item.batch_id for item in tasks
                                  if item.status in ("pending", "ready", "retryable_failed")],
            "completed_batch_ids": sorted(
                set(session.completed_batch_ids)
                | {item.batch_id for item in tasks if item.status == "promoted"}),
            "failed_batch_ids": sorted(
                set(session.failed_batch_ids)
                | {item.batch_id for item in tasks if item.status in ("blocked", "failed")}),
            "retryable_batch_ids": sorted(
                set(session.retryable_batch_ids)
                | {item.batch_id for item in tasks if item.status == "retryable_failed"}),
            "review_required_batch_ids": sorted(
                set(session.review_required_batch_ids)
                | {item.batch_id for item in tasks if item.status == "human_review"}),
            "status": status,
            "current_revision_id": task.promoted_revision_id or session.current_revision_id,
            "current_digest": promoted_digest,
            "final_revision_id": task.promoted_revision_id or session.final_revision_id,
            "updated_at": datetime.now(timezone.utc)})
        return self.store.save_session(updated)

    # ---------------------------------------------------------------- promote
    def _promote(self, session: OutlineBatchSession, task: OutlineBatchTask,
                 candidate: OutlineCompilationCandidate, findings: list[PlanningFinding],
                 checkpoint: OutlineBatchCheckpoint, *, config: CompilerConfig,
                 review: list[BatchReviewFinding]
                 ) -> tuple[OutlineBatchTask, OutlineBatchCheckpoint]:
        record: PlanningRevisionRecord | None = None
        base = self.repository.load(candidate.source_revision_id)
        try:
            payload = self._merged_plan_payload(task, candidate)
            merged_plan = StoryPlanningIR.model_validate(payload)
        except OutlineBatchError:
            raise
        except ValueError as exc:
            return self._halt(session, task, "failed", "VALIDATION", str(exc)[:200])
        structural = [item for item in self._structural_findings(merged_plan)
                      if item.severity == "ERROR"]
        if structural:
            summary = "; ".join(f"{item.code}@{item.source_id}" for item in structural[:5])
            return self._halt(session, task, "blocked", "VALIDATION",
                              f"merge 后的 revision 未通过结构校验：{summary}"[:300])
        record = self.repository.create(
            merged_plan, branch_id=base.branch_id, status="proposed",
            note=_batch_note(session.session_id, task.batch_id, candidate.candidate_id),
            parent_revision_id=base.revision_id, source_revision=base.revision_id)
        promoted = task.model_copy(update={
            "status": "promoted" if record else "blocked",
            "promoted_revision_id": record.revision_id if record else "",
            "completed_at": datetime.now(timezone.utc)})
        checkpoint = self._checkpoint(session, promoted, candidate, findings,
                                      status=promoted.status, config=config,
                                      attempt=promoted.attempt_count,
                                      review=review, promoted=record)
        if record is not None:
            checkpoint = checkpoint.model_copy(update={
                "resume_state": {"recovered": False, "promoted_note": record.note}})
        self.store.save_checkpoint(checkpoint)
        session = self._update_session(session, promoted)
        if record is not None:
            session = self._apply_registries(session, task, candidate)
        self.store.save_manifest(self.manifest(session.session_id))
        return promoted, checkpoint

    def _apply_registries(self, session: OutlineBatchSession, task: OutlineBatchTask,
                          candidate: OutlineCompilationCandidate) -> OutlineBatchSession:
        """execution / carryover 只作为派生缓存（truth 仍在 revisions 里）。"""

        execution = dict(session.batch_policy.get("execution_registry") or {})
        for item in candidate.node_allocations:
            execution[item.node_id] = task.batch_id
        # carry 用 promote 前的 base plan 计算，才能把旧卷 id 翻译到新卷
        plan = self.repository.load(candidate.source_revision_id).plan
        _, carry_updates = self._carry_updates(session, task, plan, candidate,
                                               self._config_of(session))
        carry = {**(session.batch_policy.get("carry_registry") or {}), **carry_updates}
        updated = session.model_copy(update={
            "batch_policy": {**session.batch_policy, "execution_registry": execution,
                             "carry_registry": carry},
            "updated_at": datetime.now(timezone.utc)})
        return self.store.save_session(updated)

    def _halt(self, session: OutlineBatchSession, task: OutlineBatchTask, status: BatchStatus,
              error_class: FailureClass, summary: str
              ) -> tuple[OutlineBatchTask, OutlineBatchCheckpoint]:
        previous = self.store.load_checkpoint(session.session_id, task.batch_id)
        max_attempts = int(session.batch_policy.get("max_attempts", 3))
        if error_class in RETRYABLE_FAILURES and task.attempt_count >= max_attempts:
            status = "failed"
        halted = task.model_copy(update={
            "status": status, "error_class": error_class, "error_summary": summary[:300],
            "completed_at": datetime.now(timezone.utc)})
        now = datetime.now(timezone.utc)
        checkpoint = OutlineBatchCheckpoint(
            session_id=session.session_id, batch_id=task.batch_id,
            source_revision_id=task.source_revision_id or session.current_revision_id,
            source_digest=task.source_digest or session.current_digest,
            scope=task.scope, target_detail_level=task.target_detail_level,
            candidate_id=(previous.candidate_id if previous else ""),
            candidate_digest=(previous.candidate_digest if previous else ""),
            config_digest=session.config_digest, status=status,
            attempt_count=task.attempt_count, error_class=error_class,
            error_summary=summary[:300],
            completed_steps=(previous.completed_steps if previous else ["compile"]),
            pending_steps=["validate", "promote"],
            findings=(list(previous.findings) if previous else []),
            last_attempt_at=now, next_retry_at=(now if status == "retryable_failed" else None),
            created_at=previous.created_at if previous else now)
        self.store.save_checkpoint(checkpoint)
        self._update_session(session, halted)
        self.store.save_manifest(self.manifest(session.session_id))
        return halted, checkpoint

    def _recover_from_promotion(self, session: OutlineBatchSession, task: OutlineBatchTask,
                                checkpoint: OutlineBatchCheckpoint | None
                                ) -> OutlineBatchCheckpoint | None:
        """crash consistency：candidate 已 promote 但 checkpoint 未写 → 补写，不重复 promote。"""

        if checkpoint is not None:
            return None
        for meta in self.repository.list_revisions():
            note = meta.note or ""
            if session.session_id not in note or task.batch_id not in note:
                continue
            record = self.repository.load(meta.revision_id)
            recovered = OutlineBatchCheckpoint(
                session_id=session.session_id, batch_id=task.batch_id,
                source_revision_id=record.source_revision or task.source_revision_id,
                source_digest=task.source_digest, scope=task.scope,
                target_detail_level=task.target_detail_level,
                config_digest=session.config_digest, status="promoted",
                attempt_count=task.attempt_count or 1,
                promoted_revision_id=record.revision_id,
                promoted_digest=record.content_digest,
                completed_steps=["compile", "validate", "promote"], pending_steps=[],
                resume_state={"recovered": True, "promoted_note": note})
            self.store.save_checkpoint(recovered)
            promoted_task = task.model_copy(update={
                "status": "promoted", "promoted_revision_id": record.revision_id,
                "completed_at": datetime.now(timezone.utc)})
            session = self._update_session(session, promoted_task)
            self._rebuild_registries(session)
            self.store.save_manifest(self.manifest(session.session_id))
            return recovered
        return None

    def _rebuild_registries(self, session: OutlineBatchSession) -> OutlineBatchSession:
        """崩溃 / resume 后从 revisions + checkpoint refs 重建派生注册表（不新增 truth）。"""

        execution: dict[str, str] = {}
        for task in sorted(session.tasks, key=lambda item: item.sequence):
            checkpoint = self.store.load_checkpoint(session.session_id, task.batch_id)
            if checkpoint is None or checkpoint.status != "promoted":
                continue
            candidate = self.store.load_candidate(session.session_id, checkpoint.candidate_id)
            if candidate is None:
                continue
            for item in candidate.node_allocations:
                execution[item.node_id] = task.batch_id
        carry = dict(session.batch_policy.get("carry_registry") or {})
        updated = session.model_copy(update={
            "batch_policy": {**session.batch_policy, "execution_registry": execution,
                             "carry_registry": carry}})
        return self.store.save_session(updated)

    # ---------------------------------------------------------------- run / resume
    def run_session(self, session_id: str, *, approve: bool | None = None,
                    max_batches: int = 50, auto_extend: bool | None = None
                    ) -> OutlineBatchSession:
        """连续编译：compile → validate → safe promote → checkpoint → next，直到阻塞。"""

        session = self.store.load_session(session_id)
        if auto_extend is None:
            auto_extend = session.target_scope.kind not in ("next_volume", "next_arc")
        for _ in range(max_batches):
            session = self.store.load_session(session_id)
            pending = sorted([task for task in session.tasks
                              if task.status in ("pending", "ready", "retryable_failed")],
                             key=lambda item: item.sequence)
            if not pending:
                if not auto_extend:
                    break
                session = self.extend_plan(session_id)
                pending = sorted([task for task in session.tasks
                                  if task.status in ("pending", "ready", "retryable_failed")],
                                 key=lambda item: item.sequence)
                if not pending:
                    break
            task_after, _ = self.run_batch(session_id, pending[0].batch_id, approve=approve)
            if task_after.status in ("human_review", "blocked", "failed"):
                break
            if session.promotion_policy.mode == "manual" and approve is None \
                    and task_after.status == "validated":
                break
        session = self.store.load_session(session_id)
        if session.status == "promoted":
            session = self.finalize_session(session_id)
        else:
            self.store.save_manifest(self.manifest(session_id))
        return session

    def resume_batch_session(self, session_id: str, *, approve: bool | None = None,
                             retry_review: bool = False) -> OutlineBatchSession:
        """按 checkpoint + repository 判断真实续跑位置（不按 batch 序号猜）。

        `retry_review=True` 表示作者已经处理完 human_review / blocked 的 batch，
        显式让它们重新进入队列；默认不碰（Human Review 绝不自动 retry）。
        """

        self.repair_session(session_id)
        session = self.store.load_session(session_id)
        self._verify_session(session)
        if retry_review:
            for task in sorted(session.tasks, key=lambda item: item.sequence):
                if task.status in ("human_review", "blocked", "failed"):
                    self.retry_batch(session_id, task.batch_id)
            session = self.store.load_session(session_id)
        for task in sorted(session.tasks, key=lambda item: item.sequence):
            checkpoint = self.store.load_checkpoint(session_id, task.batch_id)
            if checkpoint is None or checkpoint.status != "promoted":
                continue
            if not checkpoint.promoted_revision_id \
                    or not self.repository.exists(checkpoint.promoted_revision_id):
                raise OutlineBatchError(
                    "BLOCKED_CHECKPOINT_REVISION_MISSING",
                    f"checkpoint 指向的 revision 不存在：{checkpoint.promoted_revision_id}")
        session = self._rebuild_registries(session)
        return self.run_session(session_id, approve=approve)

    def recompile_scope(self, session_id: str, scope: CompilationScope
                        ) -> OutlineBatchSession:
        """显式重编指定 scope：旧 batch artifact 保留为 superseded（不覆盖历史）。"""

        session = self.store.load_session(session_id)
        self._verify_session(session)
        scope_nodes = set(scope.node_ids)
        if scope.note:
            scope_nodes.add(scope.note)
        affected: list[str] = []
        tasks: list[OutlineBatchTask] = []
        for task in session.tasks:
            touch = bool((set(task.scope.node_ids) & scope_nodes)
                         or (task.scope.note and task.scope.note in scope_nodes))
            if touch:
                affected.append(task.batch_id)
                tasks.append(task.model_copy(update={"status": "superseded"}))
            else:
                tasks.append(task)
        head = self.repository.load(session.current_revision_id)
        sequence = max([task.sequence for task in tasks] or [0]) + 1
        new_task = OutlineBatchTask(
            batch_id=f"BATCH_{sequence:03d}", sequence=sequence,
            source_revision_id=head.revision_id, source_digest=head.content_digest,
            scope=scope, target_detail_level=session.target_detail_level,
            supersedes_batch_ids=affected)
        tasks.append(new_task)
        session = session.model_copy(update={
            "tasks": tasks,
            "pending_batch_ids": [task.batch_id for task in tasks
                                  if task.status in ("pending", "ready", "retryable_failed")],
            "status": "pending", "scope_complete": False,
            "updated_at": datetime.now(timezone.utc)})
        return self.store.save_session(session)

    # ---------------------------------------------------------------- merge / validation
    def _merged_plan_payload(self, task: OutlineBatchTask,
                             candidate: OutlineCompilationCandidate) -> dict[str, Any]:
        """把本批结果合并进 source revision：已 promote 边界冻结，只替换 scope 内对象。"""

        base = self.repository.load(candidate.source_revision_id)
        plan = base.plan
        payload = plan.model_dump(mode="json")
        replaced = self._replaced_volume_ids(plan, task, candidate)
        new_volumes = list(candidate.volume_plans)
        new_arcs = list(candidate.arc_plans)
        kept_volumes = [volume for volume in plan.volumes
                        if volume.volume_id not in replaced]
        kept_arcs = [arc for arc in plan.arcs if arc.volume_id not in replaced]
        order = {node_id: index for index, node_id in enumerate(topological_order(plan))}

        def rank(volume: VolumePlan) -> tuple[int, str]:
            positions = [order.get(node_id, len(order)) for node_id in volume.major_nodes]
            return (min(positions) if positions else len(order), volume.volume_id)

        merged = sorted(kept_volumes + new_volumes, key=rank)
        merged = [volume.model_copy(update={"index": index})
                  for index, volume in enumerate(merged, start=1)]
        node_volume: dict[str, str] = {}
        for volume in new_volumes:
            for node_id in volume.major_nodes:
                node_volume[node_id] = volume.volume_id
        nodes: list[dict[str, Any]] = []
        for node in payload.get("plot_nodes") or []:
            scheduled = node.get("scheduled_volume_id", "")
            node_id = node.get("node_id")
            if node_id in node_volume and (not scheduled or scheduled in replaced):
                node = {**node, "scheduled_volume_id": node_volume[node_id]}
            elif scheduled and scheduled in replaced:
                # 被替换的卷不再承担这个节点：先清空排期，交给后续 batch / 作者重新排
                node = {**node, "scheduled_volume_id": ""}
            nodes.append(node)
        payload["plot_nodes"] = nodes
        payload["volumes"] = [volume.model_dump(mode="json") for volume in merged]
        payload["arcs"] = [arc.model_dump(mode="json") for arc in (kept_arcs + new_arcs)]
        pacing = payload.get("pacing")
        if pacing and pacing.get("bands"):
            by_id = {volume.volume_id: volume for volume in plan.volumes}
            bands = []
            for band in pacing["bands"]:
                volume_id = band.get("volume_id", "")
                if volume_id in replaced:
                    old_nodes = set(by_id[volume_id].major_nodes) if volume_id in by_id else set()
                    mapped = next((volume.volume_id for volume in new_volumes
                                   if old_nodes and set(volume.major_nodes) >= old_nodes), "")
                    if not mapped:
                        continue
                    band = {**band, "volume_id": mapped}
                bands.append(band)
            payload["pacing"] = {**pacing, "bands": bands}
        return payload

    def _frozen_candidate(self, session: OutlineBatchSession,
                          plan: StoryPlanningIR) -> OutlineCompilationCandidate:
        """把当前 revision 的既有结构折成 candidate，用于 session 级 full validation。"""

        arcs_by_volume: dict[str, list[str]] = {}
        for arc in plan.arcs:
            arcs_by_volume.setdefault(arc.volume_id, []).append(arc.arc_id)
        allocations = [
            NodeAllocation(node_id=node_id, execution_volume_id=volume.volume_id,
                           primary_arc_id=(arcs_by_volume.get(volume.volume_id) or [""])[0],
                           role="execution",
                           allocation_reason="session final gate（frozen structure）")
            for volume in plan.volumes for node_id in volume.major_nodes]
        total = sum(volume.chapter_budget for volume in plan.volumes)
        budget = ChapterBudgetEstimate(minimum=total, preferred=total, maximum=total,
                                       note="session final gate")
        return OutlineCompilationCandidate(
            candidate_id=f"CAND_FINAL_{session.session_id[-12:]}",
            source_revision_id=session.current_revision_id,
            source_digest=planning_digest(plan), scope=CompilationScope(kind="full_book"),
            volume_plans=list(plan.volumes), arc_plans=list(plan.arcs),
            node_allocations=allocations, plan_budget=budget,
            route_provenance={"mode": "session_final_gate", "session_id": session.session_id})

    def _finding_in_scope(self, finding: PlanningFinding, scope_ids: set[str]) -> bool:
        if finding.code not in NODE_SCOPED_FINDING_CODES:
            return True
        related = set(finding.related_ids)
        if finding.source_id:
            related.add(finding.source_id)
        return bool(related & scope_ids)

    def _full_validation(self, session: OutlineBatchSession,
                         plan: StoryPlanningIR) -> list[PlanningFinding]:
        compiler = self._compiler_for(self._config_of(session))
        rows = compiler.validate(plan, self._frozen_candidate(session, plan))
        rows.extend(self._structural_findings(plan))
        return rows

    def _structural_findings(self, plan: StoryPlanningIR) -> list[PlanningFinding]:
        """M2A 结构 validator 的统一映射（session gate / promote 前置检查共用）。"""

        report = PlanningValidator().validate(plan)
        return [PlanningFinding(
            code=item.code,
            severity=("ERROR" if item.severity == "error" else "WARNING"),
            domain="planning", source_id=item.path, message=item.message,
            evidence=({"detail": item.detail} if item.detail else {}))
            for item in report.findings]

    def session_gate(self, session_id: str) -> dict[str, Any]:
        """M8B Session Final Gate：全部条件逐条可查（不只看百分比）。"""

        session = self.store.load_session(session_id)
        plan = self.repository.load(session.current_revision_id).plan
        scope_nodes: set[str] = set()
        for task in session.tasks:
            scope_nodes.update(task.scope.node_ids)
            if task.scope.note:
                scope_nodes.add(task.scope.note)
        scope_volumes = [volume for volume in plan.volumes
                         if not scope_nodes or volume.volume_id in scope_nodes
                         or set(volume.major_nodes) & scope_nodes]
        volume_ids = {volume.volume_id for volume in scope_volumes}
        scope_ids = scope_nodes | volume_ids
        scope_ids |= {arc.arc_id for arc in plan.arcs if arc.volume_id in volume_ids}
        allocated = {node_id for volume in plan.volumes for node_id in volume.major_nodes}
        allocated |= {volume.climax_node_id for volume in plan.volumes if volume.climax_node_id}
        executions: dict[str, set[str]] = {}
        for volume in plan.volumes:
            for node_id in volume.major_nodes:
                executions.setdefault(node_id, set()).add(volume.volume_id)
        duplicates = sorted(node_id for node_id, volumes in executions.items()
                            if len(volumes) > 1)
        chain: list[tuple[str, str]] = []
        previous = session.root_planning_revision_id
        chain_ok = True
        for task in sorted(session.tasks, key=lambda item: item.sequence):
            if not task.promoted_revision_id:
                continue
            if not self.repository.exists(task.promoted_revision_id):
                chain_ok = False
                continue
            record = self.repository.load(task.promoted_revision_id)
            if record.parent_revision_id != previous:
                chain_ok = False
            previous = record.revision_id
            chain.append((task.batch_id, record.revision_id))
        if session.final_revision_id and previous != session.final_revision_id:
            chain_ok = False
        target_rank = DETAIL_ORDER.get(session.target_detail_level, 3)
        detail_ok = all(DETAIL_ORDER.get(volume.detail_level, 0) >= target_rank
                        for volume in scope_volumes) if scope_volumes else False
        uncovered_must = sorted(node.node_id for node in plan.plot_nodes
                                if node.must_happen and node.node_id in scope_nodes
                                and node.node_id not in allocated)
        carry = dict(session.batch_policy.get("carry_registry") or {})
        carry_open = sorted(pressure_id for pressure_id, row in carry.items()
                            if row.get("status") not in CLOSED_CARRY_STATES)
        findings = self._full_validation(session, plan)
        blocking = [item for item in findings if item.severity == "ERROR"
                    and self._finding_in_scope(item, scope_ids)]
        deferred = [item for item in findings if item.severity == "ERROR"
                    and not self._finding_in_scope(item, scope_ids)]
        if any(DETAIL_ORDER.get(volume.detail_level, 0) < target_rank
               for volume in plan.volumes):
            # 部分 session：整本结构还没推进到 target，目标词数对齐只能推迟判断
            moved = [item for item in blocking if item.code in TARGET_ALIGNMENT_CODES]
            blocking = [item for item in blocking if item not in moved]
            deferred.extend(moved)
        checkpoints = [self.store.load_checkpoint(session.session_id, task.batch_id)
                       for task in session.tasks]
        checks = {
            "all_batches_promoted": bool(session.tasks) and all(
                task.status in ("promoted", "skipped") for task in session.tasks),
            "no_blocking_finding": not blocking,
            "no_unresolved_retryable": not any(task.status == "retryable_failed"
                                               for task in session.tasks),
            "no_stale_checkpoint": all(
                checkpoint is None or checkpoint.status != "promoted"
                or (checkpoint.promoted_revision_id
                    and self.repository.exists(checkpoint.promoted_revision_id))
                for checkpoint in checkpoints),
            "no_duplicate_execution_allocation": not duplicates,
            "must_happen_covered_in_scope": not uncovered_must,
            "revision_chain_valid": chain_ok and bool(chain or not session.tasks),
            "detail_targets_achieved": detail_ok,
            "carryover_visible": True,
            "full_validation_pass": not blocking,
        }
        summary = {"checks": checks, "blocking": [item.code for item in blocking],
                   "deferred_scope": [item.code for item in deferred],
                   "findings": {"ERROR": len([i for i in findings if i.severity == "ERROR"]),
                                "WARNING": len([i for i in findings
                                                if i.severity == "WARNING"]),
                                "INFO": len([i for i in findings if i.severity == "INFO"])},
                   "duplicate_nodes": duplicates[:10],
                   "uncovered_must_happen": uncovered_must[:10],
                   "carryover_open": carry_open[:10], "revision_chain": chain}
        return {"session_id": session_id, "ok": all(checks.values()), "checks": checks,
                "summary": summary, "blocking_findings": blocking,
                "deferred_scope_findings": deferred}

    def finalize_session(self, session_id: str) -> OutlineBatchSession:
        """Session 完成时跑 full outline validation，并记录 gate 结果（不自动进入 M9）。"""

        gate = self.session_gate(session_id)
        session = self.store.load_session(session_id)
        session = session.model_copy(update={
            "validation_summary": dict(gate["summary"]),
            "scope_complete": bool(gate["ok"]),
            "status": "promoted" if gate["ok"] else "blocked",
            "last_error_class": None if gate["ok"] else "VALIDATION",
            "updated_at": datetime.now(timezone.utc)})
        self.store.save_session(session)
        self.store.save_manifest(self.manifest(session_id))
        return session

    # ---------------------------------------------------------------- reports
    def batch_diff(self, before_revision_id: str,
                   after_revision_id: str) -> OutlineBatchDiff:
        before = self.repository.load(before_revision_id).plan
        after = self.repository.load(after_revision_id).plan
        before_volumes = {item.volume_id: item for item in before.volumes}
        after_volumes = {item.volume_id: item for item in after.volumes}
        before_arcs = {item.arc_id: item for item in before.arcs}
        after_arcs = {item.arc_id: item for item in after.arcs}
        before_allocations = [node for volume in before.volumes
                              for node in volume.major_nodes]
        after_allocations = [node for volume in after.volumes for node in volume.major_nodes]

        def node_levels(plan: StoryPlanningIR) -> dict[str, str]:
            rows: dict[str, str] = {}
            for volume in plan.volumes:
                for node_id in volume.major_nodes:
                    rows[node_id] = volume.detail_level
                if volume.climax_node_id:
                    rows.setdefault(volume.climax_node_id, volume.detail_level)
            return rows

        before_levels = node_levels(before)
        after_levels = node_levels(after)
        detail_changes = sorted(
            f"{node_id}:{before_levels[node_id]}→{after_levels[node_id]}"
            for node_id in set(before_levels) & set(after_levels)
            if before_levels[node_id] != after_levels[node_id])
        carry_before = _carry_signatures(before)
        carry_after = _carry_signatures(after)
        return OutlineBatchDiff(
            before_revision=before_revision_id, after_revision=after_revision_id,
            volumes_added=sorted(set(after_volumes) - set(before_volumes)),
            volumes_modified=sorted(volume_id for volume_id in set(before_volumes)
                                    & set(after_volumes)
                                    if before_volumes[volume_id].model_dump(mode="json")
                                    != after_volumes[volume_id].model_dump(mode="json")),
            arcs_added=sorted(set(after_arcs) - set(before_arcs)),
            arcs_modified=sorted(arc_id for arc_id in set(before_arcs) & set(after_arcs)
                                 if before_arcs[arc_id].model_dump(mode="json")
                                 != after_arcs[arc_id].model_dump(mode="json")),
            allocations_changed=sorted(set(after_allocations) ^ set(before_allocations)),
            budget_changes={arc_id: [before_arcs[arc_id].chapter_budget,
                                     after_arcs[arc_id].chapter_budget]
                            for arc_id in set(before_arcs) & set(after_arcs)
                            if before_arcs[arc_id].chapter_budget
                            != after_arcs[arc_id].chapter_budget},
            boundary_changes=[volume_id for volume_id in after_volumes
                              if volume_id not in before_volumes
                              or before_volumes[volume_id].climax_node_id
                              != after_volumes[volume_id].climax_node_id],
            carryover_changes=sorted(carry_after - carry_before),
            detail_level_changes=detail_changes,
            findings_changes={"volumes_before": len(before.volumes),
                              "volumes_after": len(after.volumes),
                              "arcs_before": len(before.arcs),
                              "arcs_after": len(after.arcs),
                              "carryover_before": len(carry_before),
                              "carryover_after": len(carry_after)})

    def session_diff(self, session_id: str) -> OutlineBatchDiff:
        """session start revision vs final revision：本轮推进到底改变了什么。"""

        session = self.store.load_session(session_id)
        before = session.root_planning_revision_id
        after = session.final_revision_id or session.current_revision_id
        return self.batch_diff(before, after)

    def manifest(self, session_id: str) -> OutlineBatchManifest:
        session = self.store.load_session(session_id)
        chain = []
        for task in sorted(session.tasks, key=lambda item: item.sequence):
            if task.promoted_revision_id:
                chain.append({"batch_id": task.batch_id,
                              "source": task.source_revision_id,
                              "promoted": task.promoted_revision_id,
                              "digest": self.repository.load(
                                  task.promoted_revision_id).content_digest})
        findings_count: dict[str, int] = {}
        retries = 0
        human_reviews: list[str] = []
        for task in session.tasks:
            checkpoint = self.store.load_checkpoint(session_id, task.batch_id)
            retries += max(0, task.attempt_count - 1)
            if checkpoint is not None and checkpoint.review_findings:
                human_reviews.append(task.batch_id)
            for finding in (checkpoint.findings if checkpoint else []):
                findings_count[finding.code] = findings_count.get(finding.code, 0) + 1
        carry = list((session.batch_policy.get("carry_registry") or {}).values())
        return OutlineBatchManifest(
            session_id=session_id, novel_id=session.novel_id, status=session.status,
            scope_complete=session.scope_complete,
            batch_order=[item.batch_id for item in session.tasks],
            revision_chain=chain, scope=session.target_scope,
            target_detail_level=session.target_detail_level,
            detail_changes=[f"{item.batch_id}:{item.source_detail_level}→"
                            f"{item.target_detail_level}" for item in session.tasks
                            if item.status == "promoted"],
            findings_count=findings_count, retry_count=retries,
            human_reviews=sorted(set(human_reviews)
                                 | set(session.review_required_batch_ids)),
            carryover=sorted(carry, key=lambda row: str(row.get("pressure_id", ""))),
            final_revision_id=session.final_revision_id)

    def invalidation_analysis(self, plan: StoryPlanningIR, changed_node_ids: list[str]
                              ) -> dict[str, Any]:
        """依赖感知失效范围：local / downstream / full（不是任何修改都全书重编）。"""

        changed = set(changed_node_ids)
        adjacency: dict[str, set[str]] = {node.node_id: set() for node in plan.plot_nodes}
        for edge in (plan.spine.edges if plan.spine else []):
            adjacency.setdefault(edge.from_node_id, set()).add(edge.to_node_id)
        for node in plan.plot_nodes:
            for ref in (node.requirements.requirements if node.requirements else []):
                for satisfier in ref.satisfied_by:
                    adjacency.setdefault(satisfier, set()).add(node.node_id)
        downstream: set[str] = set()
        queue = list(changed)
        while queue:
            current = queue.pop()
            for target in adjacency.get(current, ()):
                if target not in downstream:
                    downstream.add(target)
                    queue.append(target)
        volumes = sorted({volume.volume_id for volume in plan.volumes
                          if set(volume.major_nodes) & (changed | downstream)})
        scope = ("full" if volumes and len(volumes) > max(2, len(plan.volumes) // 2)
                 else "downstream" if downstream else "local")
        return {"scope": [scope], "changed": sorted(changed),
                "downstream": sorted(downstream), "volumes": volumes}

    def invalidation_for_session(self, session_id: str, changed_node_ids: list[str]
                                 ) -> dict[str, Any]:
        """session 视角：哪些 batch 必须 invalidate（scope 命中 downstream 即为 stale）。"""

        session = self.store.load_session(session_id)
        plan = self.repository.load(session.current_revision_id).plan
        analysis = self.invalidation_analysis(plan, changed_node_ids)
        touched = set(analysis["changed"]) | set(analysis["downstream"])
        stale = [task.batch_id for task in session.tasks
                 if set(task.scope.node_ids) & touched]
        return {**analysis, "session_id": session_id, "stale_batch_ids": sorted(stale)}


def config_warning_policy(config: CompilerConfig) -> WarningPolicy:
    """WarningPolicy 来自 author config（写在 batch_policy.config.author_overrides）。"""

    payload = config.author_overrides.get("warning_policy") or {}
    return WarningPolicy.model_validate(payload) if payload else WarningPolicy()


def _carry_signatures(plan: StoryPlanningIR) -> set[str]:
    rows: set[str] = set()
    for volume in plan.volumes:
        for item in volume.next_volume_pressure.split(";"):
            value = item.strip()
            if value:
                rows.add(f"{volume.volume_id}:{value}")
    return rows


__all__ = [
    "CHECKPOINT_SCHEMA_VERSION",
    "CLOSED_CARRY_STATES",
    "DETAIL_ORDER",
    "HUMAN_REVIEW_CODES",
    "M8B_MAX_DETAIL",
    "NODE_SCOPED_FINDING_CODES",
    "OPEN_PRESSURE_STATES",
    "RETRYABLE_FAILURES",
    "BatchReviewFinding",
    "BatchStatus",
    "CompilerConfig",
    "ElaborationStatus",
    "FailureClass",
    "OutlineBatchCheckpoint",
    "OutlineBatchCompiler",
    "OutlineBatchDiff",
    "OutlineBatchError",
    "OutlineBatchFailure",
    "OutlineBatchManifest",
    "OutlineBatchSession",
    "OutlineBatchStore",
    "OutlineBatchTask",
    "PromotionPolicy",
    "SegmentationProfile",
    "WarningPolicy",
    "check_detail_target",
    "config_warning_policy",
    "plan_batch_scopes",
    "plan_elaboration_status",
]
