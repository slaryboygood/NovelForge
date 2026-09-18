"""Agent Checkpoint（V4-11 §55–§56）：pause / approval / restart 后可恢复。

恢复前必须重新校验 revision（drift → 不允许盲目继续）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from novelforge.persistence.paths import agent_checkpoint_path

from .contracts import utc_now


@dataclass(frozen=True)
class AgentCheckpoint:
    session_id: str
    plan_id: str
    plan_revision: int = 1
    run_id: str = ""
    status: str = ""
    next_step_sequence: int = 0
    completed_steps: tuple[str, ...] = ()
    approved_steps: tuple[str, ...] = ()
    budget_used: Mapping[str, Any] = field(default_factory=dict)
    revision_refs: Mapping[str, int] = field(default_factory=dict)
    stop_reason: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        if not self.updated_at:
            object.__setattr__(self, "updated_at", utc_now())

    def as_dict(self) -> dict[str, Any]:
        return {"session_id": self.session_id, "plan_id": self.plan_id,
                "plan_revision": int(self.plan_revision), "run_id": self.run_id,
                "status": self.status,
                "next_step_sequence": int(self.next_step_sequence),
                "completed_steps": list(self.completed_steps),
                "approved_steps": list(self.approved_steps),
                "budget_used": dict(self.budget_used),
                "revision_refs": {key: int(value) for key, value
                                  in sorted(self.revision_refs.items())},
                "stop_reason": self.stop_reason, "updated_at": self.updated_at}

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "AgentCheckpoint":
        row = dict(raw or {})
        return cls(session_id=str(row.get("session_id") or ""),
                   plan_id=str(row.get("plan_id") or ""),
                   plan_revision=int(row.get("plan_revision") or 1),
                   run_id=str(row.get("run_id") or ""),
                   status=str(row.get("status") or ""),
                   next_step_sequence=int(row.get("next_step_sequence") or 0),
                   completed_steps=tuple(str(value) for value in
                                         (row.get("completed_steps") or ())),
                   approved_steps=tuple(str(value) for value in
                                        (row.get("approved_steps") or ())),
                   budget_used=dict(row.get("budget_used") or {}),
                   revision_refs={str(key): int(value) for key, value in
                                  dict(row.get("revision_refs") or {}).items()},
                   stop_reason=str(row.get("stop_reason") or ""),
                   updated_at=str(row.get("updated_at") or ""))


class CheckpointStore:
    def __init__(self, project_root: Path | str, novel_id: str) -> None:
        self.project_root = Path(project_root)
        self.novel_id = str(novel_id)

    def path_for(self, session_id: str) -> Path:
        return agent_checkpoint_path(self.project_root, self.novel_id, session_id)

    def save(self, checkpoint: AgentCheckpoint) -> Path:
        path = self.path_for(checkpoint.session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(checkpoint.as_dict(), ensure_ascii=False, indent=1,
                                  sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        tmp.replace(path)
        return path

    def load(self, session_id: str) -> AgentCheckpoint | None:
        path = self.path_for(session_id)
        if not path.is_file():
            return None
        return AgentCheckpoint.from_dict(json.loads(path.read_text(encoding="utf-8")))


__all__ = ["AgentCheckpoint", "CheckpointStore"]
