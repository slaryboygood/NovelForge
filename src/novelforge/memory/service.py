"""MemoryService —— Story Memory 的唯一检索入口（V4-03 §9–§10）。

```python
memory.search(query=MemoryQuery(...))   # 唯一检索入口
memory.rebuild()                        # 从 canonical artifacts 重建派生索引
memory.stale_report()                   # 失效报告（§13–§14）
```

边界：

```text
· 不拥有 Canon / StoryState（只读投影）
· 不写任何 truth；派生记忆可重建、可失效
· novel_id 过滤发生在打分之前（§31）
```
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .contracts import (
    MemoryItem,
    MemoryQuery,
    MemoryResult,
    RetrievalPolicy,
    result_digest,
)
from .errors import MemoryError, MemoryIsolationError
from .episodic import EpisodicStore
from .index import MemoryIndex
from .scoring import rank_items
from .semantic import SemanticIndex


class MemoryService:
    """按 novel_id 绑定的 Story Memory 服务。"""

    def __init__(self, novel_id: str, *, project_root: Path | str | None = None,
                 sources: Sequence[Any] = (), index: MemoryIndex | None = None,
                 episodic: EpisodicStore | None = None,
                 semantic: SemanticIndex | None = None,
                 policy: RetrievalPolicy | None = None,
                 preferences: Any | None = None) -> None:
        if not str(novel_id or "").strip():
            raise MemoryIsolationError("MemoryService 需要显式 novel_id")
        self.novel_id = str(novel_id)
        self.project_root = Path(project_root) if project_root else None
        self.sources = list(sources)
        self.index = index or MemoryIndex()
        self.episodic = episodic or EpisodicStore()
        self.semantic = semantic or SemanticIndex()
        self.policy = policy or RetrievalPolicy()
        self.preferences = preferences

    # ------------------------------------------------------------------ 装配
    def add_items(self, items: Iterable[MemoryItem], *, novel_id: str = "") -> int:
        """登记派生条目（供 source adapter / 测试 / 未来 Blueprint adapter 使用）。"""

        target = str(novel_id or self.novel_id)
        self._assert_same_novel(target)
        return self.index.upsert(target, items)

    def add_episodes(self, entries: Iterable[Any]) -> int:
        count = 0
        for entry in entries:
            self._assert_same_novel(entry.novel_id)
            self.episodic.add(entry)
            count += 1
        if count:
            self.index.upsert(self.novel_id,
                              [entry.to_item() for entry in entries])
        return count

    def add_semantic(self, entries: Iterable[Any]) -> int:
        """登记语义条目：同时进入 semantic index 与检索索引。"""

        added: list[Any] = []
        for entry in entries:
            self._assert_same_novel(entry.novel_id)
            added.append(self.semantic.add(entry))
        if added:
            self.index.upsert(self.novel_id, [entry.to_item() for entry in added])
        return len(added)

    def search_semantic(self, *, task: str = "", entities: Iterable[str] = (),
                        top_k: int = 8) -> list[MemoryItem]:
        """语义检索（只返回**命中**的条目；不做全量回退）。"""

        rows = self.semantic.search(self.novel_id, task=task,
                                    entities=tuple(entities), top_k=top_k)
        return [entry.to_item() for entry, _score, _reason in rows]

    def _assert_same_novel(self, novel_id: str) -> None:
        if str(novel_id) != self.novel_id:
            raise MemoryIsolationError(
                f"跨作品访问被拒绝：service={self.novel_id}，请求={novel_id}",
                details={"service_novel": self.novel_id, "requested": str(novel_id)})

    # ------------------------------------------------------------------ 重建
    def rebuild(self) -> dict[str, Any]:
        """从 canonical sources 与派生 store 重建索引（幂等、可重复）。"""

        self.index.clear(self.novel_id)
        counts: dict[str, int] = {}
        for source in self.sources:
            items = list(source.provide(self.novel_id))
            by_type: dict[str, int] = {}
            for item in items:
                by_type[item.source.source_type] = by_type.get(
                    item.source.source_type, 0) + 1
            for key, value in by_type.items():
                counts[key] = counts.get(key, 0) + value
            self.index.upsert(self.novel_id, items)
            # episodic：来源 adapter 负责从 canonical artifacts 推导（可重建）
            episodes_provider = getattr(source, "episodes", None)
            if callable(episodes_provider):
                derived = list(episodes_provider(self.novel_id))
                for entry in derived:
                    self._assert_same_novel(entry.novel_id)
                    self.episodic.add(entry)
                if derived:
                    counts["episode"] = counts.get("episode", 0) + len(derived)
        episode_items = self.episodic.to_items(self.novel_id)
        if episode_items:
            self.index.upsert(self.novel_id, episode_items)
        semantic_entries = self.semantic.entries(self.novel_id)
        if semantic_entries:
            counts["semantic"] = len(semantic_entries)
            self.index.upsert(self.novel_id, [entry.to_item()
                                              for entry in semantic_entries])
        return {"novel_id": self.novel_id, "counts": dict(sorted(counts.items())),
                "indexed": self.index.count(self.novel_id),
                "digest": self.index.digest(self.novel_id),
                "rebuildable": True}

    # ------------------------------------------------------------------ 失效
    def current_revisions(self) -> dict[str, int]:
        revisions: dict[str, int] = {}
        for source in self.sources:
            getter = getattr(source, "current_revisions", None)
            if callable(getter):
                revisions.update({str(key): int(value)
                                  for key, value in getter(self.novel_id).items()})
        revisions.update(self.episodic.current_revisions(self.novel_id))
        return revisions

    def stale_report(self) -> list[dict[str, Any]]:
        return self.index.stale_report(self.novel_id, self.current_revisions())

    def refresh_staleness(self) -> int:
        """按 canonical revision 自动标记失效（返回新标记数量）。"""

        return self.index.apply_revision_check(self.novel_id,
                                               self.current_revisions())

    # ------------------------------------------------------------------ 检索
    def search(self, query: MemoryQuery | None = None, *, novel_id: str = "",
               revision: int | None = None, task: str = "",
               entities: Iterable[str] = (), locations: Iterable[str] = (),
               source_types: Iterable[str] = (),
               policy: RetrievalPolicy | None = None,
               required_source_ids: Iterable[str] = (),
               token_budget: int | None = None) -> MemoryResult:
        resolved_query = query or MemoryQuery(
            novel_id=novel_id or self.novel_id, revision=revision, task=task,
            entities=tuple(entities), locations=tuple(locations),
            source_types=tuple(source_types),
            required_source_ids=tuple(required_source_ids),
            token_budget=token_budget,
            policy=policy or self.policy)
        self._assert_same_novel(resolved_query.novel_id)
        effective_policy = policy or resolved_query.effective_policy()
        self.refresh_staleness()

        candidates = self.index.items(
            self.novel_id,
            source_types=resolved_query.source_types,
            include_stale=effective_policy.include_stale)
        allowed = {str(value) for value in effective_policy.include_source_types}
        banned = {str(value) for value in effective_policy.exclude_source_types}
        if allowed:
            candidates = [item for item in candidates
                          if item.source.source_type in allowed]
        if banned:
            candidates = [item for item in candidates
                          if item.source.source_type not in banned]

        required = {str(value) for value in resolved_query.required_source_ids}
        required_items = [item for item in candidates
                          if item.source.source_id in required
                          or item.source.ref in required]
        ranked = rank_items(candidates, task=resolved_query.task,
                            entities=resolved_query.entities,
                            locations=resolved_query.locations,
                            required_source_ids=tuple(required))
        selected: list[MemoryItem] = []
        per_type: dict[str, int] = {}
        for item in ranked:
            if item.relevance < effective_policy.min_relevance:
                continue
            limit = int(effective_policy.max_per_source_type or 0)
            if limit and per_type.get(item.source.source_type, 0) >= limit:
                continue
            per_type[item.source.source_type] = per_type.get(
                item.source.source_type, 0) + 1
            selected.append(item)
        # required 条目必须入选（即使分数低于阈值）
        for item in required_items:
            if item.memory_id not in {row.memory_id for row in selected}:
                selected.append(item)

        dropped: list[dict[str, Any]] = [
            {"memory_id": item.memory_id, "reason": "below_min_relevance",
             "relevance": item.relevance}
            for item in ranked if item.relevance < effective_policy.min_relevance]
        top_k = max(1, int(effective_policy.top_k))
        if len(selected) > top_k:
            required_ids = {item.memory_id for item in required_items}
            keep = [item for item in selected[:top_k]]
            for item in selected[top_k:]:
                if item.memory_id in required_ids:
                    keep.append(item)
                    continue
                dropped.append({"memory_id": item.memory_id, "reason": "top_k_cutoff",
                                "relevance": item.relevance})
            selected = keep
        selected.sort(key=lambda item: (-item.relevance, item.source.source_type,
                                        item.source.source_id))

        budget: dict[str, Any] = {}
        if resolved_query.token_budget:
            from .context.budget import item_tokens

            used = 0
            kept: list[MemoryItem] = []
            for item in selected:
                tokens = item_tokens(item)
                if used + tokens > int(resolved_query.token_budget):
                    dropped.append({"memory_id": item.memory_id,
                                    "reason": "token_budget_exceeded",
                                    "token_estimate": tokens})
                    continue
                kept.append(item)
                used += tokens
            selected = kept
            budget = {"limit": int(resolved_query.token_budget), "used": used}

        stale_rows = [
            {"memory_id": entry.item.memory_id,
             "source_id": entry.item.source.source_id,
             "reason": "stale_excluded"}
            for entry in self.index.entries(self.novel_id)
            if entry.stale and not effective_policy.include_stale]
        provenance = tuple(
            {"memory_id": item.memory_id, "source_id": item.source.source_id,
             "source_type": item.source.source_type,
             "revision": item.source.revision,
             "retrieval_reason": item.selection_reason,
             "relevance": item.relevance}
            for item in selected)
        return MemoryResult(
            query=resolved_query.as_dict(), items=tuple(selected),
            provenance=provenance, dropped=tuple(dropped),
            stale=tuple(stale_rows),
            budget=budget or {"limit": None, "used": sum(
                item.token_estimate for item in selected)},
            digest=result_digest(selected,
                                 scope_digest=str(resolved_query.novel_id)))

    # ------------------------------------------------------------------ 统计
    def stats(self) -> dict[str, Any]:
        entries = self.index.entries(self.novel_id)
        by_type: dict[str, int] = {}
        stale = 0
        for entry in entries:
            by_type[entry.item.source.source_type] = by_type.get(
                entry.item.source.source_type, 0) + 1
            stale += int(entry.stale)
        return {"novel_id": self.novel_id, "indexed": len(entries),
                "by_source_type": dict(sorted(by_type.items())),
                "episodes": self.episodic.count(self.novel_id),
                "semantic": self.semantic.count(self.novel_id),
                "stale": stale,
                "index_digest": self.index.digest(self.novel_id),
                "sources": [getattr(source, "source_prefix", "")
                            for source in self.sources]}

    def require_novel(self, novel_id: str) -> None:
        self._assert_same_novel(novel_id)


def build_default_service(novel_id: str, project_root: Path | str, *,
                          revision: int | None = None,
                          preferences: Any | None = None) -> MemoryService:
    """按默认装配构建 service：Canon + StoryState 只读视图。"""

    from .sources import CanonMemorySource, StoryStateMemorySource

    sources = [CanonMemorySource(project_root, revision=revision),
               StoryStateMemorySource(project_root, revision=revision)]
    return MemoryService(novel_id, project_root=project_root, sources=sources,
                         preferences=preferences)


__all__ = ["MemoryService", "build_default_service"]
