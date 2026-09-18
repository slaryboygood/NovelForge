"""V4-11：Agent Mode 最小 REST（thin routes，§97）。

Route 只做协议转换与稳定错误码映射；业务能力全部来自
`application.services.agent.AgentService`。UI / MCP 只能调用这个 facade。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from fastapi import APIRouter, FastAPI, HTTPException, Query
from pydantic import Field

from novelforge.agent import AgentError
from novelforge.application.services.agent import agent_service
from novelforge.models import StrictModel

_CODE_STATUS: Mapping[str, int] = {
    "AGENT_PLAN_INVALID": 422,
    "AGENT_POLICY_DENIED": 403,
    "AGENT_STEP_FAILED": 400,
    "AGENT_REVISION_CONFLICT": 409,
    "AGENT_APPROVAL_REQUIRED": 409,
    "AGENT_APPROVAL_STALE": 409,
    "AGENT_BUDGET_EXHAUSTED": 409,
    "AGENT_MAX_STEPS_REACHED": 409,
    "AGENT_CANCELLED": 409,
    "AGENT_NEEDS_HUMAN_REVIEW": 409,
    "AGENT_NOT_FOUND": 404,
}


class AgentPlanBody(StrictModel):
    novel_id: str = Field(min_length=1, max_length=96)
    instruction: str = Field(min_length=1, max_length=600)
    scope_kind: str = Field(default="novel", max_length=32)
    scope_unit_id: str = Field(default="", max_length=96)
    scope_node_ids: list[str] = Field(default_factory=list, max_length=64)
    constraints: list[str] = Field(default_factory=list, max_length=24)
    success_criteria: list[str] = Field(default_factory=list, max_length=24)
    policy: dict[str, Any] | None = None
    dry_run: bool = True


class AgentStartBody(StrictModel):
    session_id: str = Field(min_length=1, max_length=96)
    max_batch_steps: int | None = Field(default=None, ge=1, le=64)
    policy: dict[str, Any] | None = None


class AgentDecisionBody(StrictModel):
    approval_id: str = Field(min_length=1, max_length=96)
    reason: str = Field(default="", max_length=400)
    actor: str = Field(default="author", max_length=64)


class AgentSessionBody(StrictModel):
    session_id: str = Field(min_length=1, max_length=96)
    max_batch_steps: int | None = Field(default=None, ge=1, le=64)
    reason: str = Field(default="", max_length=400)


def _status_for(exc: AgentError) -> int:
    return _CODE_STATUS.get(exc.code, 400)


def install_agent_api(app: FastAPI, project_root: Path, *,
                      gateway: Any = None, memory: Any = None) -> None:
    router = APIRouter(prefix="/api/story-builder/agent", tags=["agent"])

    def service_for(novel_id: str) -> Any:
        return agent_service(project_root, novel_id, gateway=gateway,
                             memory=memory)

    def call(fn: Any) -> Any:
        try:
            return fn()
        except HTTPException:
            raise
        except AgentError as exc:
            raise HTTPException(status_code=_status_for(exc),
                                detail=exc.as_dict()) from exc
        except Exception as exc:  # noqa: BLE001 - 统一映射，不外泄 traceback
            raise HTTPException(status_code=400, detail={
                "code": "AGENT_STEP_FAILED",
                "message": f"{type(exc).__name__}: {exc}"[:200]}) from exc

    @router.post("/plan")
    def plan(body: AgentPlanBody) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            from novelforge.agent import AgentGoal, AgentScope

            goal = AgentGoal(novel_id=body.novel_id, instruction=body.instruction,
                             scope=AgentScope(kind=body.scope_kind,
                                              unit_id=body.scope_unit_id,
                                              node_ids=tuple(body.scope_node_ids)),
                             constraints=tuple(body.constraints),
                             success_criteria=tuple(body.success_criteria))
            return service_for(body.novel_id).plan(goal, policy=body.policy,
                                                   dry_run=body.dry_run)

        return call(run)

    @router.post("/start")
    def start(body: AgentStartBody) -> dict[str, Any]:
        return call(lambda: _service_for_session(body.session_id, service_for)
                    .start(body.session_id, max_batch_steps=body.max_batch_steps,
                           policy=body.policy))

    @router.get("/sessions")
    def sessions(novel_id: str = Query(min_length=3, max_length=96)
                 ) -> dict[str, Any]:
        return call(lambda: {"novel_id": novel_id,
                             "sessions": service_for(novel_id).history()})

    @router.get("/{session_id}")
    def status(session_id: str,
               novel_id: str = Query(min_length=3, max_length=96)) -> dict[str, Any]:
        return call(lambda: service_for(novel_id).status(session_id))

    @router.post("/{session_id}/approve")
    def approve(session_id: str, body: AgentDecisionBody) -> dict[str, Any]:
        return call(lambda: _service_for_session(session_id, service_for)
                    .approve(session_id, body.approval_id, actor=body.actor,
                             reason=body.reason))

    @router.post("/{session_id}/reject")
    def reject(session_id: str, body: AgentDecisionBody) -> dict[str, Any]:
        return call(lambda: _service_for_session(session_id, service_for)
                    .reject(session_id, body.approval_id, actor=body.actor,
                            reason=body.reason))

    @router.post("/{session_id}/resume")
    def resume(session_id: str, body: AgentSessionBody) -> dict[str, Any]:
        return call(lambda: _service_for_session(session_id, service_for)
                    .resume(session_id, max_batch_steps=body.max_batch_steps))

    @router.post("/{session_id}/cancel")
    def cancel(session_id: str, body: AgentSessionBody) -> dict[str, Any]:
        return call(lambda: _service_for_session(session_id, service_for)
                    .cancel(session_id, reason=body.reason))

    app.include_router(router)

    def _service_for_session(session_id: str, factory: Any) -> Any:
        """session → novel：从已存 session 记录里解析 novel_id（不猜当前作品）。"""

        from novelforge.application.services.agent import session_novel_id

        novel_id = session_novel_id(project_root, session_id)
        if novel_id:
            return factory(novel_id)
        raise HTTPException(status_code=404, detail={
            "code": "AGENT_NOT_FOUND", "message": f"未知 agent session：{session_id}"})


__all__ = ["install_agent_api"]
