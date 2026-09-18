"""Agent Ports（V4-11 §10、§32、§91）：Agent core 只认识这些窄 Protocol。

实现放在 application 层（composition）。Agent 因此**不** import
BlueprintRepository / QualityStore / EditorStore / DeliveryStore / provider / api / mcp。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from ..contracts import AgentContextSnapshot


@dataclass(frozen=True)
class NodeRef:
    """节点引用（只读形状；不含 repository / 内部路径）。"""

    node_id: str
    node_type: str
    revision: int
    status: str = ""
    parent_id: str = ""
    quality_status: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"node_id": self.node_id, "node_type": self.node_type,
                "revision": int(self.revision), "status": self.status,
                "parent_id": self.parent_id, "quality_status": self.quality_status}


@dataclass(frozen=True)
class GenerationOutcome:
    node: NodeRef | None = None
    usage: Mapping[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    contract: str = ""


@dataclass(frozen=True)
class EditOutcome:
    node_id: str
    revision: int = 0
    status: str = ""
    changed_fields: tuple[str, ...] = ()
    quality_status: str = ""
    usage: Mapping[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class QualityOutcome:
    status: str
    report_id: str = ""
    issues: tuple[Mapping[str, Any], ...] = ()
    blocker_count: int = 0
    needs_human_review: bool = False
    usage: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RepairOutcome:
    status: str
    plan: Mapping[str, Any] = field(default_factory=dict)
    result: Mapping[str, Any] = field(default_factory=dict)
    verification: Mapping[str, Any] = field(default_factory=dict)
    added_steps: int = 0
    warnings: tuple[str, ...] = ()
    usage: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DeliveryOutcome:
    status: str
    snapshot_id: str = ""
    manifest_id: str = ""
    validation: Mapping[str, Any] = field(default_factory=dict)
    artifacts: tuple[Mapping[str, Any], ...] = ()
    notes: tuple[str, ...] = ()


@runtime_checkable
class AgentReadPort(Protocol):
    def snapshot(self, novel_id: str) -> AgentContextSnapshot: ...

    def node(self, node_id: str) -> NodeRef | None: ...


@runtime_checkable
class AgentGenerationPort(Protocol):
    def generate(self, *, task: str, parent_id: str = "", index: int = 0,
                 sequence: int = 0, instruction: str = "", unit_type: str = "",
                 idempotency_key: str = "") -> GenerationOutcome: ...

    def regenerate(self, *, node_id: str, task: str = "",
                   expected_revision: int | None = None, instruction: str = "",
                   preserve: Sequence[str] = (),
                   idempotency_key: str = "") -> GenerationOutcome: ...


@runtime_checkable
class AgentEditorPort(Protocol):
    def node(self, node_id: str) -> NodeRef | None: ...

    def children(self, parent_id: str, node_type: str = "") -> tuple[NodeRef, ...]: ...

    def patch(self, *, node_id: str, changes: Mapping[str, Any],
              expected_revision: int | None, idempotency_key: str = "",
              reason: str = "") -> EditOutcome: ...

    def rewrite(self, *, node_id: str, target_fields: Sequence[str],
                instruction: str, expected_revision: int | None,
                preserve_fields: Sequence[str] = (),
                idempotency_key: str = "") -> EditOutcome: ...

    def accept(self, *, node_id: str, revision: int | None,
               expected_revision: int | None = None,
               idempotency_key: str = "", reason: str = "") -> EditOutcome: ...

    def reject(self, *, node_id: str, revision: int | None = None,
               reason: str = "", idempotency_key: str = "") -> EditOutcome: ...


@runtime_checkable
class AgentQualityPort(Protocol):
    def evaluate(self, *, gates: Sequence[str] = (),
                 node_ids: Sequence[str] = ()) -> QualityOutcome: ...

    def plan_repair(self, *, issue_ids: Sequence[str]) -> Mapping[str, Any]: ...

    def repair(self, *, issue_ids: Sequence[str],
               idempotency_key: str = "") -> RepairOutcome: ...

    def verify(self, *, issue_ids: Sequence[str]) -> RepairOutcome: ...


@runtime_checkable
class AgentDeliveryPort(Protocol):
    def formats(self) -> tuple[Mapping[str, Any], ...]: ...

    def validate(self, *, selection_mode: str = "accepted", profile: str = "author",
                 formats: Sequence[str] = ("json",)) -> DeliveryOutcome: ...

    def deliver(self, *, selection_mode: str = "accepted", profile: str = "author",
                formats: Sequence[str] = ("json",),
                idempotency_key: str = "") -> DeliveryOutcome: ...


@runtime_checkable
class AgentPlannerModel(Protocol):
    """可选的模型规划器（§25、§75）：只返回候选步骤，必须通过同一套校验。"""

    def propose_plan(self, *, goal: Mapping[str, Any], snapshot: Mapping[str, Any],
                     policy: Mapping[str, Any],
                     action_catalog: Sequence[str]) -> Mapping[str, Any]: ...


__all__ = [
    "AgentDeliveryPort", "AgentEditorPort", "AgentGenerationPort",
    "AgentPlannerModel", "AgentQualityPort", "AgentReadPort", "DeliveryOutcome",
    "EditOutcome", "GenerationOutcome", "NodeRef", "QualityOutcome",
    "RepairOutcome",
]
