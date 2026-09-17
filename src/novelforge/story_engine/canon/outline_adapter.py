"""C10：既有 Outline 仓库适配器 —— 复用 OutlinePackage / OutlineItem，不建第二套存储。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .context import sanitize_writer_text
from .planner import PlanResult


def item_payload_from_chapter(chapter: dict[str, Any]) -> dict[str, Any]:
    """把 ChapterPlan payload 映射成既有 OutlineItem 字段 + Canon-aware 增量字段。"""

    events = [str(e) for e in (chapter.get("concrete_events") or [])]
    summary = chapter.get("goal") or (events[0] if events else chapter.get("title", ""))
    payload: dict[str, Any] = {
        "item_id": _item_id(chapter),
        "title": sanitize_writer_text(str(chapter.get("title", ""))) or "未命名章节",
        "summary": sanitize_writer_text("；".join(events[:3]) or summary),
        "start_state": sanitize_writer_text(str(chapter.get("start_state", ""))),
        "end_state": sanitize_writer_text(str(chapter.get("end_state", ""))),
        "goals": [sanitize_writer_text(summary)],
        "conflicts": [sanitize_writer_text(str(chapter.get("opposition", "")))] if
        chapter.get("opposition") else [],
        "major_turns": [sanitize_writer_text(str(chapter.get("turn", "")))] if
        chapter.get("turn") else [],
        "ending_hook": sanitize_writer_text(str(chapter.get("hook", ""))),
        "location": sanitize_writer_text(str(chapter.get("location", ""))),
        "participants": list(chapter.get("participants") or []),
        "information_changes": [sanitize_writer_text(str(chapter.get("information_release", ""))) ]
        if chapter.get("information_release") else [],
        "costs": [sanitize_writer_text(str(chapter.get("cost", "")))] if chapter.get("cost") else [],
        "chapter_uuid": str(chapter.get("chapter_uuid", "")),
        "canon_fact_ids": list(chapter.get("canon_fact_ids") or []),
        "canon_event_ids": list(chapter.get("canon_event_ids") or []),
        "canon_source_refs": [ref if isinstance(ref, dict) else {"source_id": str(ref)}
                              for ref in (chapter.get("canon_source_refs") or [])],
        "context_manifest_id": str(chapter.get("context_manifest_id", "")),
    }
    return payload


def _item_id(chapter: dict[str, Any]) -> str:
    raw = str(chapter.get("chapter_uuid") or "chapter")
    slug = "".join(ch if ch.isalnum() else "_" for ch in raw.lower())[:40] or "chapter"
    return f"item_{slug}"


class OutlineRepositoryAdapter:
    """把 Canon-aware 结果写进既有 `StoryOutlineRepository`（同 contract 供 shadow 复用）。"""

    level = "CHAPTER"

    def __init__(self, project_root: Path, *, outlines_path: Path | str | None = None) -> None:
        self.project_root = Path(project_root)
        self.outlines_path = outlines_path

    def _repository(self):
        from novelforge.story_builder.outlines import StoryOutlineRepository
        return (StoryOutlineRepository(self.project_root, self.outlines_path)
                if self.outlines_path else StoryOutlineRepository(self.project_root))

    def build_package(self, result: PlanResult, *, project_id: str, blueprint_id: str,
                      blueprint_version: int, parent_package_id: str, version: int = 1,
                      route_source: dict[str, str] | None = None):
        from novelforge.story_builder.models import OutlineItem, OutlineLevel, OutlinePackage
        items = [OutlineItem.model_validate(item_payload_from_chapter(chapter))
                 for chapter in result.payload]
        return OutlinePackage(
            package_id=f"ol_canon_{result.arc_id.lower()}",
            project_id=project_id, blueprint_id=blueprint_id,
            blueprint_version=blueprint_version, level=OutlineLevel[self.level],
            version=version, parent_package_id=parent_package_id, items=items,
            route_source=route_source or {})

    def write(self, result: PlanResult, **package_kwargs: Any) -> str:
        package = self.build_package(result, **package_kwargs)
        saved = self._repository().save(package)
        result.persisted_path = saved.package_id
        return saved.package_id
