"""Agent 审计（V4-11 §53–§54、§58）：orchestration metadata，走 persistence.paths。

与 `EditorOperationRecord`（Blueprint mutation 审计）**分开存储**，通过
`request_id` / `step_id` 关联；Agent audit 永远不是 story truth。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from novelforge.persistence.paths import agent_audit_path

from .contracts import utc_now


@dataclass(frozen=True)
class AgentAuditRecord:
    session_id: str
    operation: str
    goal_id: str = ""
    run_id: str = ""
    plan_id: str = ""
    plan_revision: int = 1
    step_id: str = ""
    target: Mapping[str, Any] = field(default_factory=dict)
    status: str = ""
    request_id: str = ""
    idempotency_key: str = ""
    business_result_refs: Mapping[str, Any] = field(default_factory=dict)
    error_code: str = ""
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            object.__setattr__(self, "timestamp", utc_now())

    def as_dict(self) -> dict[str, Any]:
        return {"session_id": self.session_id, "run_id": self.run_id,
                "plan_id": self.plan_id, "plan_revision": int(self.plan_revision),
                "step_id": self.step_id, "goal_id": self.goal_id,
                "operation": self.operation, "target": dict(self.target),
                "status": self.status, "request_id": self.request_id,
                "idempotency_key": self.idempotency_key,
                "business_result_refs": dict(self.business_result_refs),
                "error_code": self.error_code, "timestamp": self.timestamp}


class AgentAuditLog:
    """按 (novel_id, session_id) 落盘的审计（append-only JSON 列表，容量上限）。"""

    def __init__(self, project_root: Path | str, novel_id: str, session_id: str, *,
                 max_records: int = 1000) -> None:
        self.project_root = Path(project_root)
        self.novel_id = str(novel_id)
        self.session_id = str(session_id)
        self.max_records = max(1, int(max_records))

    @property
    def path(self) -> Path:
        return agent_audit_path(self.project_root, self.novel_id, self.session_id)

    def records(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return [dict(row) for row in (payload.get("records") or [])]

    def record(self, entry: AgentAuditRecord) -> dict[str, Any]:
        rows = self.records()
        rows.append(entry.as_dict())
        rows = rows[-self.max_records:]
        path = self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"schema_version": 1, "records": rows},
                                  ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                       encoding="utf-8", newline="\n")
        tmp.replace(path)
        return rows[-1]


__all__ = ["AgentAuditLog", "AgentAuditRecord"]
