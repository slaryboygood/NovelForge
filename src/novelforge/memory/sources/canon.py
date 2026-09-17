"""Canon retrieval view（V4-03 §5）。

Canon Memory **不是** Canon 数据库：它只把 Canon 的只读事实投影成可检索条目。
禁止写 Canon / 自动覆盖 / 让 LLM 输出直接成为 Canon。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from novelforge.persistence.paths import canon_db_path

from ..contracts import MemoryItem, MemorySource, memory_id_for
from ..errors import MemorySourceError


def _fact_text(row: Any) -> str:
    return str(row.canonical_description or row.canonical_key or row.fact_id)


class CanonMemorySource:
    """从 Canon SQLite 读取 facts / entities（只读，按 novel_id 打开）。"""

    source_prefix = "canon"

    def __init__(self, project_root: Path | str, *, revision: int | None = None,
                 limit: int = 500) -> None:
        self.project_root = Path(project_root)
        self.revision = revision
        self.limit = int(limit)

    # ------------------------------------------------------------------ 读取
    def available(self, novel_id: str) -> bool:
        return canon_db_path(self.project_root, novel_id).is_file()

    def current_revisions(self, novel_id: str) -> dict[str, int]:
        """Canon 当前 revision：以 facts 行数 + 最新 fact revision 的简单确定性摘要。

        Canon 目前没有整库 revision 概念；这里用"事实条数 + 最新 fact_id"作为
        可比较的稳定版本标识，仅用于 stale 判定（不写入 Canon）。
        """

        facts = self.provide(novel_id)
        count = len([row for row in facts if row.source.source_type == "canon_fact"])
        return {f"canon:{novel_id}": count}

    def provide(self, novel_id: str) -> Sequence[MemoryItem]:
        path = canon_db_path(self.project_root, novel_id)
        if not path.is_file():
            return []
        from novelforge.story_engine.canon.repository import CanonRepository

        repository = CanonRepository(path)
        try:
            facts = repository.facts(novel_id)[: self.limit]
            entities = repository.entities(novel_id)[: self.limit]
        except Exception as exc:  # noqa: BLE001 - 读取失败必须显式暴露
            raise MemorySourceError(f"Canon 读取失败：{exc}",
                                    details={"novel_id": novel_id}) from exc
        finally:
            repository.close()

        revision = self.revision if self.revision is not None else len(facts)
        revision_key = f"canon:{novel_id}"
        rows: list[MemoryItem] = []
        for row in facts:
            rows.append(MemoryItem(
                memory_id=memory_id_for("canon_fact", row.fact_id),
                memory_type="canon",
                text=f"{_fact_text(row)}（{row.category}，{row.status}）",
                source=MemorySource(source_type="canon_fact", source_id=row.fact_id,
                                    revision=revision, label=row.category,
                                    metadata={"revision_key": revision_key}),
                metadata={"entities": [row.fact_id], "status": row.status,
                          "category": row.category,
                          "revision_key": revision_key}))
        for row in entities:
            rows.append(MemoryItem(
                memory_id=memory_id_for("canon_entity", row.entity_id),
                memory_type="canon",
                text=f"{row.display_name or row.canonical_key}（{row.kind}）",
                source=MemorySource(source_type="canon_entity", source_id=row.entity_id,
                                    revision=revision, label=row.kind,
                                    metadata={"revision_key": revision_key}),
                metadata={"entities": [row.entity_id], "kind": row.kind,
                          "revision_key": revision_key}))
        return rows


__all__ = ["CanonMemorySource"]
