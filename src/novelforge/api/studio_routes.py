"""V4-10：Story Studio 最小 REST（thin routes）。

UI 只经 HTTP 访问 application services（`V4_UI_CONTRACT.md` §5）。本模块只做协议转换与
稳定错误码映射；**不** import blueprint / quality / editor / delivery internals，
也不 import `novelforge.plugins`（插件平台由宿主在 composition 处注入）。

```text
GET  /api/story-builder/studio/overview            总览（状态 / 计数 / 下一步 / 交付）
GET  /api/story-builder/studio/blueprint           Blueprint 节点（可见字段 + 状态 + 质量）
POST /api/story-builder/studio/generate            逐级生成（premise…scene）
GET  /api/story-builder/studio/quality             Quality Center（gates / report / issues）
POST /api/story-builder/studio/quality/evaluate    整体评估
POST /api/story-builder/studio/quality/repair      修复预览（dry_run）或执行
POST /api/story-builder/studio/quality/verify      修复复核
GET  /api/story-builder/studio/delivery/formats    可用交付格式（含插件 exporter）
GET  /api/story-builder/studio/plugins             插件只读状态（含 trust model）
```

写操作（patch / rewrite / accept / reject / restore / delivery）**不在这里重复**：
直接复用 `/editor/*`（V4-06）与 `/delivery`（V4-07）已冻结的 wire contract。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from fastapi import APIRouter, FastAPI, Query
from pydantic import Field

from novelforge.application.services.facade import application_services
from novelforge.models import StrictModel

#: 生成任务 id（= generation TaskRegistry 的 task 名，UI 只允许这些值）
STUDIO_TASK_IDS: tuple[str, ...] = (
    "premise", "theme", "world", "character", "character_arc", "story_arc",
    "structural_unit", "chapter", "scene",
)

#: node_type → 生成任务（逐级生成的默认映射；UI 传 node_type 时用）
NODE_TYPE_TO_TASK: Mapping[str, str] = {
    "premise": "premise", "theme": "theme", "world": "world",
    "character": "character", "character_arc": "character_arc",
    "story_arc": "story_arc", "structural_unit": "structural_unit",
    "chapter": "chapter", "scene": "scene",
}

#: 插件信任模型说明（与 `novelforge.plugins.permissions.permission_note()` 一致；
#: 由 `tests/plugins/test_plugin_security.py` 断言两者相同，避免文案漂移）。
#: api 层不 import `novelforge.plugins`（模块边界），因此这里保存同一份诚实声明。
TRUST_MODEL = "trusted_in_process"
TRUST_MODEL_NOTE = ("permission 是 Host API capability governance，"
                    "不是 Python / OS sandbox；"
                    "恶意 in-process 插件仍可直接访问解释器能力")

#: 业务 error code → HTTP 状态（只读 UI 需要稳定语义；未知 code → 400）
_SIBLING_NODE_TYPES: Mapping[str, str] = {
    "chapter": "chapter", "scene": "scene", "structural_unit": "structural_unit",
    "character": "character", "character_arc": "character_arc",
}

#: 需要「兄弟序号」才能产生稳定节点 id 的生成任务（§15）
SIBLING_TASKS: tuple[str, ...] = ("chapter", "scene", "structural_unit", "character")


def _sibling_ordinal(services: Any, task: str, parent_id: str) -> int:
    """该父节点下同类型子节点数 + 1（Host 侧推导，不由 UI 猜）。"""

    node_type = _SIBLING_NODE_TYPES.get(task, "")
    blueprint = getattr(services, "blueprint", None)
    if not node_type or blueprint is None or not parent_id:
        return 1
    try:
        rows = blueprint.children(parent_id, node_type=node_type)
    except Exception:  # noqa: BLE001 - 读不到就当第一个，不阻断生成
        return 1
    return len(list(rows)) + 1


def _chapter_ordinal(node_id: str) -> int:
    """`ch_007` → 7（scene node id 需要 chapter 序号）。"""

    digits = "".join(ch for ch in str(node_id).split("_")[-1] if ch.isdigit())
    return int(digits) if digits else 0


_CODE_STATUS: Mapping[str, int] = {
    "EDITOR_NODE_NOT_FOUND": 404,
    "BLUEPRINT_NODE_NOT_FOUND": 404,
    "REVISION_CONFLICT": 409,
    "EDITOR_REVISION_CONFLICT": 409,
    "EDITOR_PRESERVE_VIOLATION": 409,
    "DELIVERY_EXPORT_FAILED": 409,
    "EDITOR_OWNERSHIP_MISMATCH": 403,
    "BLUEPRINT_OWNERSHIP_VIOLATION": 403,
    "DELIVERY_OWNERSHIP_MISMATCH": 403,
    "GENERATION_UNAVAILABLE": 422,
    "EDITOR_VALIDATION_FAILED": 422,
    "EDITOR_OPERATION_REJECTED": 422,
    "GENERATION_VALIDATION_FAILED": 422,
    "QUALITY_POLICY_INVALID": 422,
    "REPAIR_PLAN_INVALID": 422,
    "REPAIR_CONTRACT_CONFLICT": 409,
    "REPAIR_NOT_ALLOWED": 409,
    "REPAIR_ROUND_LIMIT": 409,
}


class GenerateBody(StrictModel):
    novel_id: str = Field(min_length=1, max_length=96)
    task: str = Field(default="", max_length=48)
    node_type: str = Field(default="", max_length=48)
    parent_id: str = Field(default="", max_length=96)
    node_id: str = Field(default="", max_length=96)
    expected_revision: int | None = Field(default=None, ge=1)
    instruction: str = Field(default="", max_length=600)
    sequence: int = Field(default=0, ge=0, le=999)
    index: int = Field(default=0, ge=0, le=999)
    unit_type: str = Field(default="", max_length=24)
    idempotency_key: str = Field(default="", max_length=128)
    dry_run: bool = False


class EvaluateBody(StrictModel):
    novel_id: str = Field(min_length=1, max_length=96)
    gates: list[str] = Field(default_factory=list, max_length=12)
    node_ids: list[str] = Field(default_factory=list, max_length=200)


class RepairBody(StrictModel):
    novel_id: str = Field(min_length=1, max_length=96)
    issue_ids: list[str] = Field(default_factory=list, max_length=50)
    node_id: str = Field(default="", max_length=96)
    dry_run: bool = True
    idempotency_key: str = Field(default="", max_length=128)


class VerifyBody(StrictModel):
    novel_id: str = Field(min_length=1, max_length=96)
    issue_ids: list[str] = Field(default_factory=list, max_length=50)


def _error_code(exc: BaseException) -> str:
    code = str(getattr(exc, "code", "") or "")
    if code:
        return code
    name = type(exc).__name__
    if "NotFound" in name:
        return "STUDIO_NOT_FOUND"
    if "Conflict" in name:
        return "STUDIO_CONFLICT"
    if "Validation" in name or "ValueError" == name:
        return "STUDIO_VALIDATION_FAILED"
    if "Unavailable" in name:
        return "GENERATION_UNAVAILABLE"
    return "STUDIO_OPERATION_FAILED"


def _message(exc: BaseException) -> str:
    return str(getattr(exc, "message", "") or exc)[:300]


def install_studio_api(app: FastAPI, project_root: Path, *,
                       gateway: Any = None, memory: Any = None,
                       exporter_registry: Any = None,
                       evaluator_registry: Any = None,
                       plugin_service: Any = None) -> None:
    """装配 Story Studio 路由（gateway / memory / registry / plugin_service 由宿主注入）。"""

    from fastapi import HTTPException

    router = APIRouter(prefix="/api/story-builder/studio", tags=["studio"])

    def services_for(novel_id: str) -> Any:
        return application_services(project_root, novel_id, gateway=gateway,
                                    memory=memory,
                                    exporter_registry=exporter_registry,
                                    evaluator_registry=evaluator_registry)

    def call(fn: Callable[[], Any]) -> Any:
        """统一错误映射：稳定 code + 短消息（不泄漏 traceback / 路径）。"""

        try:
            return fn()
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001 - 接口层统一映射
            code = _error_code(exc)
            raise HTTPException(status_code=_CODE_STATUS.get(code, 400),
                                detail={"code": code, "message": _message(exc)}) from exc

    # ------------------------------------------------------------------ 总览
    @router.get("/overview")
    def overview(novel_id: str = Query(min_length=3, max_length=96),
                 mode: str = Query(default="current", max_length=24)) -> dict[str, Any]:
        def build() -> dict[str, Any]:
            services = services_for(novel_id)
            view = services.export.blueprint_view(selection_mode=mode)
            nodes = list((view.get("blueprint") or {}).get("nodes") or [])
            by_type: dict[str, int] = {}
            by_status: dict[str, int] = {}
            setups = {"open": 0, "partially_paid": 0, "paid": 0, "abandoned": 0}
            payoffs = {"planned": 0, "paid": 0, "abandoned": 0}
            for row in nodes:
                node_type = str(row.get("node_type") or "")
                by_type[node_type] = by_type.get(node_type, 0) + 1
                status = str(row.get("status") or "")
                by_status[status] = by_status.get(status, 0) + 1
                visible = dict(row.get("visible") or {})
                if node_type == "setup":
                    key = str(visible.get("status") or "open")
                    setups[key] = setups.get(key, 0) + 1
                if node_type == "payoff":
                    key = str(visible.get("status") or "planned")
                    payoffs[key] = payoffs.get(key, 0) + 1
            quality = services.review.stats()
            report = services.review.latest_report()
            gates = _gate_rows(report, services.review.registered_gates())
            delivery = services.export.delivery().stats()
            snapshots = services.export.delivery_snapshots()
            profile: Mapping[str, Any] = {}
            try:
                profile = services.project.get_novel(novel_id)
            except Exception:  # noqa: BLE001 - 没有 profile 时用 novel_id 兜底
                profile = {}
            return {
                "novel_id": novel_id,
                "title": str(profile.get("title") or novel_id),
                "genre": str(profile.get("genre") or ""),
                "blueprint": {
                    "node_count": int((view.get("blueprint") or {}).get("node_count")
                                      or len(nodes)),
                    "by_type": dict(sorted(by_type.items())),
                    "by_status": dict(sorted(by_status.items())),
                    "accepted": by_status.get("accepted", 0),
                    "proposed": by_status.get("proposed", 0),
                    "draft": by_status.get("draft", 0),
                    "digest": str((view.get("blueprint") or {}).get("digest") or ""),
                    "selection_mode": mode,
                },
                "quality": {
                    "status": str(report.get("status") or "unevaluated"),
                    "issues": int(quality.get("open_issues") or 0),
                    "gates": gates,
                    "open_blockers": sum(1 for row in gates if row["blockers"] > 0),
                    "summary": dict(quality),
                },
                "setup": {"counts": setups,
                          "unpaid_required": sum(1 for row in nodes
                                                 if str(row.get("node_type")) == "setup"
                                                 and str((row.get("visible") or {})
                                                         .get("status")) != "paid")},
                "payoff": {"counts": payoffs},
                "delivery": {"snapshots": len(snapshots),
                             "stats": dict(delivery),
                             "last": (snapshots[0] if snapshots else None)},
                "next_action": dict(services.journey.next_action() or {}),
                "read_only": True,
            }

        return call(build)

    # -------------------------------------------------------------- blueprint
    @router.get("/blueprint")
    def blueprint(novel_id: str = Query(min_length=3, max_length=96),
                  node_type: str = Query(default="", max_length=48),
                  mode: str = Query(default="current", max_length=24),
                  include_internal: bool = Query(default=False)
                  ) -> dict[str, Any]:
        def build() -> dict[str, Any]:
            services = services_for(novel_id)
            view = services.export.blueprint_view(selection_mode=mode)
            nodes = [dict(row) for row in
                     ((view.get("blueprint") or {}).get("nodes") or [])]
            if node_type:
                nodes = [row for row in nodes if str(row.get("node_type")) == node_type]
            if not include_internal:
                for row in nodes:
                    for key in ("context_digest", "source_ids", "generation_contract",
                                "generation_contract_version"):
                        row.pop(key, None)
            return {"novel_id": novel_id, "selection_mode": mode,
                    "node_type": node_type,
                    "ordering": list((view.get("blueprint") or {}).get("ordering") or []),
                    "count": len(nodes), "nodes": nodes,
                    "excluded": [dict(row) for row in (view.get("excluded") or [])],
                    "quality_summary": dict(view.get("quality_summary") or {}),
                    "read_only": True}

        return call(build)

    # ------------------------------------------------------------- generation
    @router.post("/generate")
    def generate(body: GenerateBody) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            services = services_for(body.novel_id)
            if services.blueprint is None:
                raise HTTPException(
                    status_code=422,
                    detail={"code": "GENERATION_UNAVAILABLE",
                            "message": "当前未配置模型能力，无法生成（§58 稳定错误码）"})
            task = body.task or NODE_TYPE_TO_TASK.get(body.node_type, "")
            if task not in STUDIO_TASK_IDS:
                raise ValueError(f"未知生成任务：{task or body.node_type}")
            task_input: dict[str, Any] = {}
            if body.instruction:
                task_input["task"] = body.instruction
            if body.unit_type:
                task_input["unit_type"] = body.unit_type
            # 父节点存在时补齐「兄弟序号」：节点 id 由契约决定
            # （chapter→ch_<index>，scene→sc_<chapter_index>_<seq>），
            # 缺省时由 Host 取“该父节点下已有同类型子节点数 + 1”，
            # 避免第二次生成覆盖第一个节点（§15）。
            index = int(body.index or 0)
            sequence = int(body.sequence or 0)
            if body.parent_id and task in SIBLING_TASKS and not (index or sequence):
                computed = _sibling_ordinal(services, task, body.parent_id)
                if task == "scene":
                    sequence = sequence or computed
                else:
                    index = index or computed
            if index:
                task_input["index"] = index
            if sequence:
                task_input["sequence"] = sequence
                task_input.setdefault("seq", sequence)
            if task == "scene":
                chapter_index = _chapter_ordinal(body.parent_id)
                if chapter_index:
                    task_input["chapter_index"] = chapter_index
            if body.node_id and body.expected_revision:
                result = services.blueprint.regenerate(
                    task=task, node_id=body.node_id,
                    expected_revision=body.expected_revision,
                    idempotency_key=body.idempotency_key, **task_input)
            else:
                result = services.blueprint.generate_task(
                    task, parent_id=body.parent_id,
                    idempotency_key=body.idempotency_key,
                    expected_revision=body.expected_revision,
                    sequence=sequence,
                    task_input=task_input)
            payload = result.as_dict()
            payload["next_status"] = "proposed"
            return payload

        return call(run)

    # ---------------------------------------------------------------- quality
    @router.get("/quality")
    def quality(novel_id: str = Query(min_length=3, max_length=96),
                gate: str = Query(default="", max_length=8),
                status: str = Query(default="", max_length=24)) -> dict[str, Any]:
        def build() -> dict[str, Any]:
            services = services_for(novel_id)
            report = services.review.latest_report()
            registered = services.review.registered_gates()
            return {"novel_id": novel_id,
                    "status": str(report.get("status") or "unevaluated"),
                    "gates": _gate_rows(report, registered, gate=gate),
                    "issues": services.review.list_issues(gate=gate, status=status),
                    "report": report,
                    "summary": dict(services.review.stats()),
                    "policy": dict(report.get("policy") or {})}

        return call(build)

    @router.post("/quality/evaluate")
    def quality_evaluate(body: EvaluateBody) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            services = services_for(body.novel_id)
            report = services.review.evaluate(
                gates=tuple(body.gates) or None,
                node_ids=tuple(body.node_ids))
            payload = report.as_dict()
            payload["summary"] = {
                "status": report.status, "issues": len(report.issues),
                "blockers": len(report.blockers),
                "gates": _gate_rows(payload, services.review.registered_gates())}
            return payload

        return call(run)

    @router.post("/quality/repair")
    def quality_repair(body: RepairBody) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            services = services_for(body.novel_id)
            if body.dry_run:
                preview = services.editor.plan_repair(
                    node_id=body.node_id, issue_ids=tuple(body.issue_ids), dry_run=True)
                return {"status": "planned", "dry_run": True,
                        "preview": preview,
                        "issue_ids": list(body.issue_ids)}
            outcome = services.editor.repair(tuple(body.issue_ids), dry_run=False,
                                            idempotency_key=body.idempotency_key)
            return outcome

        return call(run)

    @router.post("/quality/verify")
    def quality_verify(body: VerifyBody) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            services = services_for(body.novel_id)
            return services.editor.verify_repair(issue_ids=tuple(body.issue_ids))

        return call(run)

    # --------------------------------------------------------------- delivery
    @router.get("/delivery/formats")
    def delivery_formats(novel_id: str = Query(min_length=3, max_length=96)
                         ) -> dict[str, Any]:
        def build() -> dict[str, Any]:
            services = services_for(novel_id)
            registry = getattr(services.export, "exporter_registry", None)
            if registry is None:
                from novelforge.delivery import build_default_registry

                registry = build_default_registry()
            rows = [spec.as_dict() for spec in registry.specs()]
            return {"novel_id": novel_id, "formats": rows,
                    "format_ids": [str(row["format"]) for row in rows],
                    "profiles": ["reader", "author", "machine", "audit"],
                    "default_formats": ["json", "markdown"],
                    "default_selection_mode": "accepted",
                    "read_only": True}

        return call(build)

    # ---------------------------------------------------------------- plugins
    @router.get("/plugins")
    def plugins() -> dict[str, Any]:
        def build() -> dict[str, Any]:
            if plugin_service is None:
                return {"available": False, "plugins": [],
                        "trust_model": TRUST_MODEL, "note": TRUST_MODEL_NOTE,
                        "hint": "宿主未装配插件平台（本页只读）",
                        "permissions": []}
            return {"available": True,
                    "plugins": plugin_service.list_plugins(),
                    "status": plugin_service.status(),
                    "permissions": plugin_service.permission_model().get("permissions", []),
                    "trust_model": plugin_service.permission_model().get("trust_model",
                                                                        ""),
                    "note": plugin_service.permission_model().get("note", ""),
                    "read_only": True}

        return call(build)

    app.include_router(router)


def _gate_rows(report: Mapping[str, Any], registered: Sequence[str], *,
               gate: str = "") -> list[dict[str, Any]]:
    """把 QualityReport 的 gate 结果整理成 UI 需要的形状（不改语义）。"""

    rows: dict[str, dict[str, Any]] = {
        str(name): {"gate": str(name), "status": "unevaluated", "issues": 0,
                    "blockers": 0, "duration_ms": 0, "evaluator_ids": []}
        for name in registered}
    for row in (report.get("gates") or []):
        name = str(row.get("gate") or "")
        if not name:
            continue
        rows[name] = {**rows.get(name, {"gate": name}),
                      "status": str(row.get("status") or "unevaluated"),
                      "issues": int(row.get("issue_count") or 0),
                      "blockers": int(row.get("blocker_count") or 0)
                      if row.get("blocker_count") is not None else 0,
                      "duration_ms": int(row.get("duration_ms") or 0),
                      "evaluator_ids": list(row.get("evaluator_ids") or []),
                      "skipped_reason": str(row.get("skipped_reason") or "")}
    if report.get("issues"):
        counts: dict[str, dict[str, int]] = {}
        for issue in report["issues"]:
            name = str(issue.get("gate") or "")
            bucket = counts.setdefault(name, {"issues": 0, "blockers": 0})
            bucket["issues"] += 1
            if str(issue.get("severity")) == "blocker":
                bucket["blockers"] += 1
        for name, bucket in counts.items():
            row = rows.setdefault(name, {"gate": name, "status": "unevaluated"})
            row.setdefault("issues", bucket["issues"])
            row.setdefault("blockers", bucket["blockers"])
    ordered = [rows[name] for name in sorted(rows)]
    if gate:
        ordered = [row for row in ordered if row["gate"] == gate]
    return ordered


__all__ = ["NODE_TYPE_TO_TASK", "STUDIO_TASK_IDS", "TRUST_MODEL",
           "TRUST_MODEL_NOTE", "install_studio_api"]
