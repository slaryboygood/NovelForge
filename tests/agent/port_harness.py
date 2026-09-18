"""Port-level 测试替身（V4-11 §86–§90）：不经真实业务层，验证编排语义。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from novelforge.agent.audit import AgentAuditLog
from novelforge.agent.checkpoint import CheckpointStore
from novelforge.agent.contracts import AgentContextSnapshot
from novelforge.agent.executor import AgentExecutor
from novelforge.agent.ports import (
    DeliveryOutcome,
    EditOutcome,
    GenerationOutcome,
    NodeRef,
    QualityOutcome,
    RepairOutcome,
)
from novelforge.agent.verifier import AgentVerifier


@dataclass
class FakeRead:
    revisions: dict[str, int] = field(default_factory=lambda: {"ch_001": 1})
    status: str = "proposed"
    open_issues: tuple[Mapping[str, Any], ...] = ()

    def snapshot(self, novel_id: str) -> AgentContextSnapshot:
        return AgentContextSnapshot(
            novel_id=novel_id, blueprint_revisions=dict(self.revisions),
            node_types={key: ("chapter" if key.startswith("ch_") else "scene")
                        for key in self.revisions},
            node_status={key: self.status for key in self.revisions},
            parent_ids={}, open_issues=self.open_issues)

    def node(self, node_id: str) -> NodeRef | None:
        if node_id not in self.revisions:
            return None
        return NodeRef(node_id=node_id, node_type="chapter",
                       revision=int(self.revisions[node_id]), status=self.status)


@dataclass
class FakeGeneration:
    calls: int = 0
    usage: Mapping[str, Any] = field(default_factory=lambda: {"calls": 1,
                                                             "total_tokens": 100,
                                                             "cost": 0.01})

    def generate(self, *, task: str, parent_id: str = "", index: int = 0,
                 sequence: int = 0, instruction: str = "", unit_type: str = "",
                 idempotency_key: str = "") -> GenerationOutcome:
        self.calls += 1
        node_id = f"ch_{int(index or sequence or self.calls):03d}"
        return GenerationOutcome(node=NodeRef(node_id=node_id, node_type="chapter",
                                              revision=1, status="proposed"),
                                 usage=dict(self.usage))

    def regenerate(self, **_kwargs: Any) -> GenerationOutcome:
        self.calls += 1
        return GenerationOutcome(node=NodeRef(node_id="ch_001", node_type="chapter",
                                              revision=2, status="proposed"),
                                 usage=dict(self.usage))


@dataclass
class FakeEditor:
    revisions: dict[str, int] = field(default_factory=lambda: {"ch_001": 1})

    def node(self, node_id: str) -> NodeRef | None:
        if node_id not in self.revisions:
            return None
        return NodeRef(node_id=node_id, node_type="chapter",
                       revision=int(self.revisions[node_id]), status="proposed")

    def children(self, parent_id: str, node_type: str = "") -> tuple[NodeRef, ...]:
        return ()

    def patch(self, *, node_id: str, changes: Mapping[str, Any],
              expected_revision: int | None, idempotency_key: str = "",
              reason: str = "") -> EditOutcome:
        self.revisions[node_id] = int(expected_revision or 0) + 1
        return EditOutcome(node_id=node_id, revision=self.revisions[node_id],
                           status="applied",
                           changed_fields=tuple(sorted(changes)))

    def rewrite(self, **_kwargs: Any) -> EditOutcome:
        raise AssertionError("not used")

    def accept(self, *, node_id: str, revision: int | None,
               expected_revision: int | None = None, idempotency_key: str = "",
               reason: str = "") -> EditOutcome:
        return EditOutcome(node_id=node_id, revision=int(revision or 1),
                           status="accepted", changed_fields=("status",))

    def reject(self, **_kwargs: Any) -> EditOutcome:
        return EditOutcome(node_id="", revision=0, status="rejected")


@dataclass
class FakeQuality:
    status: str = "failed"
    needs_human: bool = False
    repair_calls: int = 0

    def evaluate(self, *, gates: Sequence[str] = (),
                 node_ids: Sequence[str] = ()) -> QualityOutcome:
        return QualityOutcome(status=self.status, report_id="QR_test", issues=(),
                              blocker_count=0, needs_human_review=self.needs_human,
                              usage={"calls": 0})

    def plan_repair(self, *, issue_ids: Sequence[str]) -> Mapping[str, Any]:
        return {"status": "planned", "steps": [{"node_id": "ch_001"}],
                "issue_ids": list(issue_ids)}

    def repair(self, *, issue_ids: Sequence[str],
               idempotency_key: str = "") -> RepairOutcome:
        self.repair_calls += 1
        return RepairOutcome(status="repaired", plan={"status": "planned"},
                             result={"status": "applied"},
                             verification={
                                 "status": "needs_human_review"
                                 if self.needs_human else "resolved",
                                 "needs_human_review": self.needs_human})

    def verify(self, *, issue_ids: Sequence[str]) -> RepairOutcome:
        return RepairOutcome(status="verified",
                             verification={"status": "resolved"})


@dataclass
class FakeDelivery:
    deliver_calls: int = 0

    def formats(self) -> tuple[Mapping[str, Any], ...]:
        return ({"format": "json"},)

    def validate(self, *, selection_mode: str = "accepted", profile: str = "author",
                 formats: Sequence[str] = ("json",)) -> DeliveryOutcome:
        return DeliveryOutcome(status="validated", validation={"ok": True})

    def deliver(self, *, selection_mode: str = "accepted", profile: str = "author",
                formats: Sequence[str] = ("json",),
                idempotency_key: str = "") -> DeliveryOutcome:
        self.deliver_calls += 1
        return DeliveryOutcome(status="delivered", snapshot_id="DS_1",
                               manifest_id="DM_1", validation={"ok": True})


def harness(tmp_path: Path) -> dict[str, Any]:
    read, generation = FakeRead(), FakeGeneration()
    editor, quality, delivery = FakeEditor(), FakeQuality(), FakeDelivery()
    executor = AgentExecutor(
        read=read, generation=generation, editor=editor, quality=quality,
        delivery=delivery,
        verifier=AgentVerifier(read=read, editor=editor, quality=quality,
                               delivery=delivery, generation=generation),
        audit_factory=lambda novel_id, session_id:
            AgentAuditLog(tmp_path, novel_id, session_id),
        checkpoints=CheckpointStore(tmp_path, "alpha"))
    return {"read": read, "generation": generation, "editor": editor,
            "quality": quality, "delivery": delivery, "executor": executor,
            "root": tmp_path}


__all__ = ["FakeDelivery", "FakeEditor", "FakeGeneration", "FakeQuality", "FakeRead",
           "harness"]
