"""Memory Public Contract（V4-03 §9–§10）。

核心原则（§3）：

```text
Memory is not the database / not Canon / not StoryState.
Memory 只做：索引 / 摘要 / 检索 / 关联 / 压缩 / 上下文选择。
Memory 必须：可重建、可失效、可追溯 source_ids、可判断 revision。
```

本模块只定义**稳定概念**（source_type / source_id / revision / metadata），
不绑定尚未实现的 Story Blueprint class（§27）——未来 Blueprint 节点只需以
`source_type="blueprint_node"` + `source_id` + `revision` 进入同一契约。
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Any, Literal, Mapping, Sequence

from novelforge.core.ids import digest_payload

from .errors import MemoryError, MemoryIsolationError

#: 派生记忆 schema 版本（§13：所有派生 Memory 必须带 memory_schema_version）
MEMORY_SCHEMA_VERSION = 1

SourceType = Literal[
    "canon_fact", "canon_entity", "canon_event", "canon_relationship",
    "canon_foreshadow", "canon_knowledge",
    "story_state", "episode", "semantic",
    "blueprint_node", "chapter_ir", "planning_ir", "outline", "preference",
]

MemoryType = Literal["canon", "story_state", "episodic", "semantic", "preference",
                     "blueprint"]

SOURCE_TYPE_TO_MEMORY_TYPE: dict[str, str] = {
    "canon_fact": "canon",
    "canon_entity": "canon",
    "canon_event": "canon",
    "canon_relationship": "canon",
    "canon_foreshadow": "canon",
    "canon_knowledge": "canon",
    "story_state": "story_state",
    "episode": "episodic",
    "semantic": "semantic",
    "preference": "preference",
    "blueprint_node": "blueprint",
    "chapter_ir": "blueprint",
    "planning_ir": "blueprint",
    "outline": "blueprint",
}

#: 相关性命中的来源优先级（只影响排序，不影响"是否有资格"）
SOURCE_TYPE_PRIORITY: dict[str, float] = {
    "canon_fact": 0.30,
    "canon_entity": 0.26,
    "canon_event": 0.24,
    "canon_relationship": 0.20,
    "canon_foreshadow": 0.18,
    "canon_knowledge": 0.18,
    "story_state": 0.26,
    "episode": 0.18,
    "blueprint_node": 0.16,
    "chapter_ir": 0.14,
    "planning_ir": 0.12,
    "outline": 0.12,
    "semantic": 0.10,
    "preference": 0.05,
}


def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


@dataclass(frozen=True)
class MemorySource:
    """派生记忆的 provenance 基元（§13 / §29）。"""

    source_type: str
    source_id: str
    revision: int | None = None
    label: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not str(self.source_type or "").strip():
            raise MemoryError("MemorySource 需要 source_type")
        if not str(self.source_id or "").strip():
            raise MemoryError("MemorySource 需要 source_id")

    @property
    def memory_type(self) -> str:
        return SOURCE_TYPE_TO_MEMORY_TYPE.get(self.source_type, "semantic")

    @property
    def ref(self) -> str:
        return self.source_id if self.revision is None else f"{self.source_id}@{self.revision}"

    def as_dict(self) -> dict[str, Any]:
        return {"source_type": self.source_type, "source_id": self.source_id,
                "revision": self.revision, "label": self.label,
                "ref": self.ref}


@dataclass(frozen=True)
class MemoryScope:
    """检索范围（§6：必须能按 novel_id / revision / entity / scope 查询）。"""

    novel_id: str
    project_id: str = ""
    revision: int | None = None
    entities: tuple[str, ...] = ()
    locations: tuple[str, ...] = ()
    source_types: tuple[str, ...] = ()
    time_range: tuple[str, str] | None = None

    def __post_init__(self) -> None:
        if not str(self.novel_id or "").strip():
            raise MemoryIsolationError(
                "MemoryScope 必须显式携带 novel_id（禁止隐式当前作品）")

    def as_dict(self) -> dict[str, Any]:
        return {"novel_id": self.novel_id, "project_id": self.project_id,
                "revision": self.revision, "entities": list(self.entities),
                "locations": list(self.locations),
                "source_types": list(self.source_types),
                "time_range": list(self.time_range) if self.time_range else None}


@dataclass(frozen=True)
class RetrievalPolicy:
    """检索策略（调用方只看到策略，看不到底层实现 —— §8）。"""

    top_k: int = 8
    min_relevance: float = 0.0
    include_source_types: tuple[str, ...] = ()
    exclude_source_types: tuple[str, ...] = ()
    max_per_source_type: int = 0
    allow_embeddings: bool = False
    include_stale: bool = False

    def __post_init__(self) -> None:
        if int(self.top_k) < 1:
            raise MemoryError("top_k 必须 >= 1")
        if not 0.0 <= float(self.min_relevance) <= 1.0:
            raise MemoryError("min_relevance 必须在 0..1")

    def as_dict(self) -> dict[str, Any]:
        return {"top_k": self.top_k, "min_relevance": self.min_relevance,
                "include_source_types": list(self.include_source_types),
                "exclude_source_types": list(self.exclude_source_types),
                "max_per_source_type": self.max_per_source_type,
                "allow_embeddings": self.allow_embeddings,
                "include_stale": self.include_stale}


@dataclass(frozen=True)
class MemoryItem:
    """一条可检索记忆（不是字符串 —— §9）。"""

    memory_id: str
    memory_type: str
    text: str
    source: MemorySource
    relevance: float = 0.0
    selection_reason: str = ""
    token_estimate: int = 0
    stale: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not str(self.memory_id or "").strip():
            raise MemoryError("MemoryItem 需要 memory_id")
        if int(self.token_estimate) < 0:
            raise MemoryError("token_estimate 不能为负")

    def with_relevance(self, relevance: float, *, reason: str = "") -> "MemoryItem":
        from dataclasses import replace

        return replace(self, relevance=round(float(relevance), 6),
                       selection_reason=reason or self.selection_reason)

    def as_dict(self) -> dict[str, Any]:
        return {"memory_id": self.memory_id, "memory_type": self.memory_type,
                "text": self.text, "source": self.source.as_dict(),
                "relevance": self.relevance,
                "selection_reason": self.selection_reason,
                "token_estimate": self.token_estimate,
                "stale": self.stale, "metadata": dict(self.metadata)}


def memory_id_for(source_type: str, source_id: str, *, suffix: str = "") -> str:
    base = f"{source_type}:{source_id}"
    return f"{base}#{suffix}" if suffix else base


@dataclass(frozen=True)
class MemoryQuery:
    """统一检索请求（§9）。"""

    novel_id: str
    revision: int | None = None
    task: str = ""
    entities: tuple[str, ...] = ()
    locations: tuple[str, ...] = ()
    source_types: tuple[str, ...] = ()
    time_range: tuple[str, str] | None = None
    top_k: int | None = None
    token_budget: int | None = None
    required_source_ids: tuple[str, ...] = ()
    policy: RetrievalPolicy = field(default_factory=RetrievalPolicy)

    def __post_init__(self) -> None:
        if not str(self.novel_id or "").strip():
            raise MemoryIsolationError(
                "MemoryQuery 必须显式携带 novel_id（禁止隐式当前作品）")

    @property
    def scope(self) -> MemoryScope:
        return MemoryScope(novel_id=self.novel_id, revision=self.revision,
                           entities=tuple(self.entities),
                           locations=tuple(self.locations),
                           source_types=tuple(self.source_types),
                           time_range=self.time_range)

    def effective_policy(self) -> RetrievalPolicy:
        if self.top_k is None:
            return self.policy
        from dataclasses import replace

        return replace(self.policy, top_k=int(self.top_k))

    def as_dict(self) -> dict[str, Any]:
        return {"novel_id": self.novel_id, "revision": self.revision,
                "task": self.task, "entities": list(self.entities),
                "locations": list(self.locations),
                "source_types": list(self.source_types),
                "time_range": list(self.time_range) if self.time_range else None,
                "top_k": self.top_k, "token_budget": self.token_budget,
                "required_source_ids": list(self.required_source_ids),
                "policy": self.policy.as_dict()}


@dataclass(frozen=True)
class MemoryResult:
    """检索结果：不是字符串列表（§9）。"""

    query: Mapping[str, Any]
    items: tuple[MemoryItem, ...] = ()
    provenance: tuple[Mapping[str, Any], ...] = ()
    dropped: tuple[Mapping[str, Any], ...] = ()
    stale: tuple[Mapping[str, Any], ...] = ()
    budget: Mapping[str, Any] = field(default_factory=dict)
    digest: str = ""
    memory_schema_version: int = MEMORY_SCHEMA_VERSION
    generated_at: str = ""

    def __post_init__(self) -> None:
        if not self.generated_at:
            object.__setattr__(self, "generated_at", utc_now())

    @property
    def texts(self) -> tuple[str, ...]:
        return tuple(item.text for item in self.items)

    @property
    def source_ids(self) -> tuple[str, ...]:
        seen: list[str] = []
        for item in self.items:
            ref = item.source.ref
            if ref not in seen:
                seen.append(ref)
        return tuple(seen)

    def as_dict(self) -> dict[str, Any]:
        return {"query": dict(self.query),
                "items": [item.as_dict() for item in self.items],
                "provenance": [dict(row) for row in self.provenance],
                "dropped": [dict(row) for row in self.dropped],
                "stale": [dict(row) for row in self.stale],
                "budget": dict(self.budget), "digest": self.digest,
                "memory_schema_version": self.memory_schema_version,
                "generated_at": self.generated_at}


def result_digest(items: Sequence[MemoryItem], *, scope_digest: str = "") -> str:
    """结果摘要（用于确定性断言：同一 query 必须得到同一 digest）。"""

    payload = {"scope": scope_digest,
               "items": [{"id": item.memory_id, "relevance": item.relevance,
                          "reason": item.selection_reason} for item in items]}
    return digest_payload(payload)


__all__ = [
    "MEMORY_SCHEMA_VERSION", "MemoryItem", "MemoryQuery", "MemoryResult",
    "MemoryScope", "MemorySource", "MemoryType", "RetrievalPolicy",
    "SOURCE_TYPE_PRIORITY", "SOURCE_TYPE_TO_MEMORY_TYPE", "SourceType",
    "memory_id_for", "result_digest", "utc_now",
]

