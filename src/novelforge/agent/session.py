"""Agent Session / Run 持久化（V4-11 §19、§55–§58）。

```text
AgentSession  一次作者目标上下文（goal / policy / plan history / approvals / runs）
AgentRun      一次实际执行尝试（step results / usage / stop reason）
```

全部走 `persistence.paths.agent_*`；Agent 数据是 **orchestration metadata**，
永远不是 story truth（§58）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from novelforge.core.ids import new_request_id
from novelforge.persistence.paths import (
    agent_run_path,
    agent_runs_dir,
    agent_session_path,
    agent_sessions_dir,
)

from .contracts import (
    AgentApprovalRequest,
    AgentGoal,
    AgentPlan,
    AgentPolicy,
    AgentRun,
    AgentStepResult,
    utc_now,
)
from .errors import AgentNotFound


@dataclass
class AgentSessionRecord:
    """会话记录（可序列化；不包含任何 story truth）。"""

    novel_id: str
    goal: Mapping[str, Any] = field(default_factory=dict)
    policy: Mapping[str, Any] = field(default_factory=dict)
    status: str = "created"
    session_id: str = ""
    plan: Mapping[str, Any] = field(default_factory=dict)
    plan_history: list[dict[str, Any]] = field(default_factory=list)
    approvals: list[dict[str, Any]] = field(default_factory=list)
    decisions: list[dict[str, Any]] = field(default_factory=list)
    run_ids: list[str] = field(default_factory=list)
    budget: Mapping[str, Any] = field(default_factory=dict)
    checkpoint: Mapping[str, Any] = field(default_factory=dict)
    stop_reason: str = ""
    error_code: str = ""
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        if not self.session_id:
            self.session_id = new_request_id("session")
        if not self.created_at:
            self.created_at = utc_now()
        self.updated_at = utc_now()

    @property
    def goal_obj(self) -> AgentGoal:
        return AgentGoal.from_dict(self.goal)

    @property
    def plan_obj(self) -> AgentPlan | None:
        return AgentPlan.from_dict(self.plan) if self.plan else None

    @property
    def policy_obj(self) -> AgentPolicy:
        return AgentPolicy.from_dict(self.policy)

    @property
    def pending_approvals(self) -> list[dict[str, Any]]:
        decided = {str(row.get("approval_id")) for row in self.decisions}
        return [row for row in self.approvals
                if str(row.get("approval_id")) not in decided]

    def as_dict(self) -> dict[str, Any]:
        return {"session_id": self.session_id, "novel_id": self.novel_id,
                "goal": dict(self.goal), "policy": dict(self.policy),
                "status": self.status, "plan": dict(self.plan),
                "plan_history": [dict(row) for row in self.plan_history],
                "approvals": [dict(row) for row in self.approvals],
                "decisions": [dict(row) for row in self.decisions],
                "run_ids": list(self.run_ids), "budget": dict(self.budget),
                "checkpoint": dict(self.checkpoint),
                "stop_reason": self.stop_reason, "error_code": self.error_code,
                "created_at": self.created_at, "updated_at": self.updated_at}

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "AgentSessionRecord":
        row = dict(raw or {})
        return cls(novel_id=str(row.get("novel_id") or ""),
                   goal=dict(row.get("goal") or {}),
                   policy=dict(row.get("policy") or {}),
                   status=str(row.get("status") or "created"),
                   session_id=str(row.get("session_id") or ""),
                   plan=dict(row.get("plan") or {}),
                   plan_history=[dict(item) for item in (row.get("plan_history") or [])],
                   approvals=[dict(item) for item in (row.get("approvals") or [])],
                   decisions=[dict(item) for item in (row.get("decisions") or [])],
                   run_ids=[str(item) for item in (row.get("run_ids") or [])],
                   budget=dict(row.get("budget") or {}),
                   checkpoint=dict(row.get("checkpoint") or {}),
                   stop_reason=str(row.get("stop_reason") or ""),
                   error_code=str(row.get("error_code") or ""),
                   created_at=str(row.get("created_at") or ""),
                   updated_at=str(row.get("updated_at") or ""))

    # ------------------------------------------------------------------ 便捷
    def set_plan(self, plan: AgentPlan) -> None:
        if self.plan:
            self.plan_history.append(dict(self.plan))
        self.plan = plan.as_dict()

    def add_approval(self, request: AgentApprovalRequest) -> None:
        self.approvals.append(request.as_dict())

    def add_decision(self, decision: Mapping[str, Any]) -> None:
        self.decisions.append(dict(decision))

    def approved_step_ids(self) -> tuple[str, ...]:
        approved: list[str] = []
        for row in self.decisions:
            if str(row.get("decision")) == "approved":
                approval_id = str(row.get("approval_id") or "")
                match = next((item for item in self.approvals
                              if str(item.get("approval_id")) == approval_id), None)
                if match is not None:
                    approved.append(str(match.get("step_id") or ""))
        return tuple(sorted({row for row in approved if row}))


class AgentSessionStore:
    """Session / Run 的 JSON 持久化（经 persistence.paths）。"""

    def __init__(self, project_root: Path | str) -> None:
        self.project_root = Path(project_root)

    # ------------------------------------------------------------- sessions
    def save_session(self, record: AgentSessionRecord) -> Path:
        record.updated_at = utc_now()
        path = agent_session_path(self.project_root, record.novel_id,
                                  record.session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(record.as_dict(), ensure_ascii=False, indent=1,
                                  sort_keys=True) + "\n",
                       encoding="utf-8", newline="\n")
        tmp.replace(path)
        return path

    def load_session(self, novel_id: str, session_id: str) -> AgentSessionRecord:
        path = agent_session_path(self.project_root, novel_id, session_id)
        if not path.is_file():
            raise AgentNotFound(f"未知 agent session：{session_id}",
                                session_id=session_id)
        return AgentSessionRecord.from_dict(
            json.loads(path.read_text(encoding="utf-8")))

    def list_sessions(self, novel_id: str) -> list[dict[str, Any]]:
        base = agent_sessions_dir(self.project_root, novel_id)
        if not base.is_dir():
            return []
        rows: list[dict[str, Any]] = []
        for path in sorted(base.glob("*.json")):
            try:
                record = AgentSessionRecord.from_dict(
                    json.loads(path.read_text(encoding="utf-8")))
            except Exception:  # noqa: BLE001 - 损坏文件不影响其它 session
                continue
            rows.append({"session_id": record.session_id, "status": record.status,
                         "goal": dict(record.goal), "created_at": record.created_at,
                         "updated_at": record.updated_at,
                         "stop_reason": record.stop_reason,
                         "error_code": record.error_code})
        return sorted(rows, key=lambda row: str(row["created_at"]), reverse=True)

    # ----------------------------------------------------------------- runs
    def save_run(self, novel_id: str, run: AgentRun) -> Path:
        path = agent_run_path(self.project_root, novel_id, run.session_id, run.run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(run.as_dict(), ensure_ascii=False, indent=1,
                                  sort_keys=True) + "\n",
                       encoding="utf-8", newline="\n")
        tmp.replace(path)
        return path

    def load_run(self, novel_id: str, session_id: str, run_id: str) -> AgentRun:
        path = agent_run_path(self.project_root, novel_id, session_id, run_id)
        if not path.is_file():
            raise AgentNotFound(f"未知 agent run：{run_id}", session_id=session_id,
                                details={"run_id": run_id})
        return self._run_from_dict(json.loads(path.read_text(encoding="utf-8")))

    def runs_for(self, novel_id: str, session_id: str) -> list[AgentRun]:
        base = agent_runs_dir(self.project_root, novel_id, session_id)
        if not base.is_dir():
            return []
        rows = [self._run_from_dict(json.loads(path.read_text(encoding="utf-8")))
                for path in sorted(base.glob("*.json"))]
        return sorted(rows, key=lambda row: row.started_at)

    @staticmethod
    def _run_from_dict(raw: Mapping[str, Any]) -> AgentRun:
        row = dict(raw or {})
        run = AgentRun(session_id=str(row.get("session_id") or ""),
                       plan_id=str(row.get("plan_id") or ""),
                       plan_revision=int(row.get("plan_revision") or 1),
                       run_id=str(row.get("run_id") or ""),
                       status=str(row.get("status") or "created"),
                       started_at=str(row.get("started_at") or ""),
                       finished_at=str(row.get("finished_at") or ""),
                       stop_reason=str(row.get("stop_reason") or ""),
                       cancel_requested=bool(row.get("cancel_requested")),
                       usage=dict(row.get("usage") or {}))
        run.step_results = [AgentStepResult(
            step_id=str(item.get("step_id") or ""),
            status=str(item.get("status") or ""),
            action=str(item.get("action") or ""),
            started_at=str(item.get("started_at") or ""),
            finished_at=str(item.get("finished_at") or ""),
            request_id=str(item.get("request_id") or ""),
            idempotency_key=str(item.get("idempotency_key") or ""),
            revision_before=int(item.get("revision_before") or 0),
            revision_after=int(item.get("revision_after") or 0),
            result_refs=dict(item.get("result_refs") or {}),
            issues=tuple(str(value) for value in (item.get("issues") or ())),
            warnings=tuple(str(value) for value in (item.get("warnings") or ())),
            usage=dict(item.get("usage") or {}),
            changed_nodes=tuple(str(value) for value in
                                (item.get("changed_nodes") or ())),
            error_code=str(item.get("error_code") or ""),
            message=str(item.get("message") or ""))
            for item in (row.get("step_results") or [])]
        return run


__all__ = ["AgentSessionRecord", "AgentSessionStore"]
