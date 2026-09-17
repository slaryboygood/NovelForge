"""Revision primitive（V4-01，ADR-006）。

注意（V4-01 作者决策 C）：本 primitive 服务的对象是 **Story Blueprint 节点 / StoryState /
Quality-Repair / Agent mutation**，**不是**"小说正文版本历史"
（ADR-003 已被 ADR-011 取代）。

本阶段只提供最小能力：

```text
revision / expected_revision / parent_revision
revision conflict（不覆盖、不自动合并）
operation id / request id
```

本阶段**不**提供完整 revision history 系统（存储、diff、restore 属于 V4-06）。
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .ids import digest_payload, new_request_id


class RevisionConflict(RuntimeError):
    """写入时 revision 不匹配（不覆盖、不自动合并）。"""

    def __init__(self, *, expected: int | None, actual: int | None,
                 artifact_id: str = "", message: str = "") -> None:
        self.code = "REVISION_CONFLICT"
        self.expected = expected
        self.actual = actual
        self.artifact_id = artifact_id
        self.message = message or (
            f"revision 冲突：期望 {expected}，实际 {actual}" +
            (f"（{artifact_id}）" if artifact_id else ""))
        super().__init__(self.message)

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message,
                "artifact_id": self.artifact_id,
                "expected_revision": self.expected, "actual_revision": self.actual}


@dataclass(frozen=True)
class OperationContext:
    """一次写入操作的上下文（请求 id + 幂等 key + 操作名 + 执行者）。"""

    operation: str
    request_id: str = ""
    idempotency_key: str = ""
    actor: str = "author"

    def __post_init__(self) -> None:
        if not str(self.operation or "").strip():
            raise ValueError("OperationContext 需要显式 operation 名")
        if not self.request_id:
            object.__setattr__(self, "request_id", new_request_id(
                f"op_{self.operation}"))

    def as_dict(self) -> dict[str, str]:
        return {"operation": self.operation, "request_id": self.request_id,
                "idempotency_key": self.idempotency_key, "actor": self.actor}


@dataclass(frozen=True)
class RevisionRef:
    """一个 artifact 在某个 revision 上的稳定引用。"""

    artifact_id: str
    revision: int
    kind: str = ""
    parent_revision: int | None = None
    created_at: str = ""
    operation: str = ""
    request_id: str = ""
    source_ids: tuple[str, ...] = field(default_factory=tuple)
    changed_nodes: tuple[str, ...] = field(default_factory=tuple)
    digest: str = ""

    def __post_init__(self) -> None:
        if not str(self.artifact_id or "").strip():
            raise ValueError("RevisionRef 需要显式 artifact_id")
        if int(self.revision) < 0:
            raise ValueError("revision 不能为负")
        if not self.created_at:
            object.__setattr__(self, "created_at",
                               _dt.datetime.now(_dt.timezone.utc).isoformat())

    def as_dict(self) -> dict[str, Any]:
        return {"artifact_id": self.artifact_id, "kind": self.kind,
                "revision": self.revision, "parent_revision": self.parent_revision,
                "created_at": self.created_at, "operation": self.operation,
                "request_id": self.request_id,
                "source_ids": list(self.source_ids),
                "changed_nodes": list(self.changed_nodes),
                "digest": self.digest}


def check_expected_revision(expected_revision: int | None, current_revision: int | None,
                            *, artifact_id: str = "") -> None:
    """写入前的 revision 校验。

    规则（ADR-006）：

    ```text
    expected_revision is None  → 调用方未声明并发意图：允许（兼容期）
    expected_revision == current → 允许，调用方随后必须产生**新** revision
    其它                        → RevisionConflict（不得覆盖、不得自动合并）
    ```
    """

    if expected_revision is None:
        return
    if current_revision is None:
        raise RevisionConflict(expected=expected_revision, actual=None,
                               artifact_id=artifact_id,
                               message=(f"{artifact_id or 'artifact'} 还不存在，"
                                        f"但请求声明 expected_revision={expected_revision}"))
    if int(expected_revision) != int(current_revision):
        raise RevisionConflict(expected=int(expected_revision),
                               actual=int(current_revision), artifact_id=artifact_id)


def new_revision(*, artifact_id: str, current_revision: int | None,
                 expected_revision: int | None = None, operation: str = "",
                 kind: str = "", actor: str = "author",
                 request_id: str = "", source_ids: Sequence[str] = (),
                 changed_nodes: Sequence[str] = (), payload: Any = None
                 ) -> RevisionRef:
    """校验后产生**下一个** revision（append-only，不覆盖旧 revision）。"""

    check_expected_revision(expected_revision, current_revision,
                            artifact_id=artifact_id)
    parent = int(current_revision) if current_revision is not None else None
    next_revision = (parent + 1) if parent is not None else 1
    context = OperationContext(operation=operation or "mutate", request_id=request_id,
                               actor=actor)
    digest = digest_payload(payload) if payload is not None else ""
    return RevisionRef(artifact_id=artifact_id, kind=kind, revision=next_revision,
                       parent_revision=parent, operation=context.operation,
                       request_id=context.request_id,
                       source_ids=tuple(str(item) for item in source_ids),
                       changed_nodes=tuple(str(item) for item in changed_nodes),
                       digest=digest)


def revision_view(raw: Mapping[str, Any]) -> RevisionRef:
    """把已存储的 revision 载荷读回 `RevisionRef`（只读，不改变语义）。"""

    return RevisionRef(
        artifact_id=str(raw.get("artifact_id") or raw.get("id") or ""),
        kind=str(raw.get("kind") or ""),
        revision=int(raw.get("revision") or 0),
        parent_revision=(int(raw["parent_revision"])
                         if raw.get("parent_revision") is not None else None),
        created_at=str(raw.get("created_at") or ""),
        operation=str(raw.get("operation") or ""),
        request_id=str(raw.get("request_id") or ""),
        source_ids=tuple(str(item) for item in (raw.get("source_ids") or [])),
        changed_nodes=tuple(str(item) for item in (raw.get("changed_nodes") or [])),
        digest=str(raw.get("digest") or ""))


__all__ = [
    "OperationContext", "RevisionConflict", "RevisionRef",
    "check_expected_revision", "new_revision", "revision_view",
]

