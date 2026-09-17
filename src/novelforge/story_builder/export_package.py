"""M16A Planning Export：单一 export projection + serializer + validation。

repo 定义（V2 里程碑，见 docs/CHANGELOG.md）：M16A = 「Planning-aware Export +
Writer-ready Package + Story Bible / 卡片 / Timeline / Spine / 三部大纲」。

结构：

```text
Planning / Story Engine（既有 projection）
        ↓
Export Projection（本模块：单一真源）
        ↓
Serializer（json / markdown / docx，复用既有 docx_bytes）
        ↓
Artifact（filename + content / base64）+ validation
```

边界：导出只读；`preview/export != committed truth`，各 section 带 truth_layer 与来源。
"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from novelforge.story_engine.creator import DEFAULT_BRANCH, resolve_creator_context
from novelforge.story_engine.historical_ir import HISTORY_DIR, HistoricalIRStore
from novelforge.story_engine.m11_p15p import (
    FROZEN_FOUNDATION_DIGESTS,
    FROZEN_SOURCE_DIGESTS,
)
from novelforge.story_engine.outline_forge import load_forge_chain
from novelforge.story_engine.outline_revision import docx_bytes
from novelforge.story_engine.settings_gen import load_pack_draft, saved_pack_id
from novelforge.story_engine.world_view import world_snapshot

EXPORT_FORMAT_VERSION = "m16-export-1"
RECON_DIR = "workspace/wasteland_001_exports/reconstruction_v2"
PLANNING_INDEX = "novel/authoring/story_engine/planning/wasteland_001/index.json"

TRUTH_LAYER_LEGEND: dict[str, str] = {
    "occurred": "StoryState / Canon（已发生事实）",
    "planned": "规划 / 大纲（未提交为事实）",
    "historical_repair": "M11/M12 frozen repair lineage（历史修复证据）",
    "ui_derived": "导出派生（仅用于阅读，不成为 truth）",
}

# 作者可见的导出文档里只出现作者语言：`truth_layer` 与内部组件名（NovelProfile /
# StoryState / canon sqlite …）留在 JSON（机器可读）里，markdown / docx 用这张表。
TRUTH_LAYER_AUTHOR_LABEL: dict[str, str] = {
    "occurred": "已经发生的事实",
    "planned": "还在计划里",
    "historical_repair": "历史修复证据",
    "ui_derived": "阅读用派生信息",
}


def _read_json(path: Path) -> Any:
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _digest(payload: Any) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False,
                      default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def _section(section_id: str, title: str, truth_layer: str, *, source: str,
             identity: str, items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    rows = [dict(item) for item in items]
    return {"section_id": section_id, "title": title, "truth_layer": truth_layer,
            "source": source, "identity": identity or source, "item_count": len(rows),
            "digest": _digest(rows), "items": rows}


def _canon_refs(project_root: Path | str, novel_id: str) -> list[dict[str, Any]]:
    from novelforge.story_engine.canon.repository import CanonRepository

    db = Path(project_root) / "novel/authoring/story_engine/canon/wasteland_001.sqlite"
    if not db.is_file():
        return []
    repository = CanonRepository(db)
    try:
        facts = repository.facts(novel_id)
    finally:
        repository.close()
    return [{"id": row.fact_id, "category": row.category,
             "text": row.canonical_description or row.canonical_key,
             "status": row.status} for row in facts[:500]]


def build_export_projection(project_root: Path | str, novel_id: str, *,
                            branch_id: str = DEFAULT_BRANCH) -> dict[str, Any]:
    """M16A：单一 export projection（Story Bible / 卡片 / Timeline / Spine / 大纲 / Planning）。"""

    context = resolve_creator_context(project_root, novel_id)
    world = world_snapshot(context)
    profile = context.profile
    pack_id = saved_pack_id(project_root, novel_id)
    pack = load_pack_draft(project_root, pack_id) if pack_id else context.pack
    pack_payload = pack.model_dump(mode="json") if pack is not None else {}

    world_items = [
        {"id": "world.title", "text": context.title},
        *[{"id": f"rule_{index}", "text": str(text)}
          for index, text in enumerate(profile.story_rules or [], start=1)],
    ]
    character_items = [
        {"id": row["id"], "name": row["name"], "kind": row["kind"],
         "status": row["status"], "is_player": row["is_player"]}
        for row in world.get("characters") or []]
    if not character_items:
        character_items = [
            {"id": key, "name": entry.name, "kind": entry.kind, "status": "",
             "is_player": key == "protagonist"}
            for key, entry in (profile.cast or {}).items()]
    faction_items = [
        {"id": row["id"], "name": row["name"], "stance": row.get("stance", ""),
         "influence": row.get("influence")} for row in world.get("factions") or []]
    location_items = [
        {"id": row["id"], "name": row.get("name") or row["id"],
         "kind": row.get("kind", ""), "access": row.get("access", ""),
         "danger": row.get("danger"), "current": row.get("current", False)}
        for row in world["location"]["known"]]
    timeline_items = [
        {"tick": world["timeline"]["tick"],
         "current_time": world["timeline"]["current_time"],
         "elapsed": world["timeline"]["elapsed"],
         "markers": list(world["timeline"]["markers"])},
        *[{"tick": row["tick"], "event_id": row["event_id"], "title": row["title"],
           "kind": row["kind"]} for row in world.get("recent_world_events") or []],
    ]
    canon_items = _canon_refs(project_root, novel_id)

    spine_items: list[dict[str, Any]] = []
    for name in ("FULL_BOOK_FUTURE_SPINE.json", "HISTORICAL_CAUSAL_SPINE.json"):
        payload = _read_json(Path(project_root) / RECON_DIR / name)
        if payload:
            spine_items.append({"id": name, "digest": _digest(payload),
                                "source_ref": f"{RECON_DIR}/{name}"})

    chain = load_forge_chain(project_root, novel_id, branch_id=branch_id)
    outline_items: list[dict[str, Any]] = []
    for package in [chain["book"], *chain["volumes"], *chain["arcs"], *chain["chapters"]]:
        if package is None:
            continue
        for item in package.items:
            outline_items.append({
                "package_id": package.package_id, "level": package.level.value,
                "item_id": item.item_id, "title": item.title, "summary": item.summary,
                "goals": list(item.goals), "conflicts": list(item.conflicts),
                "major_turns": list(item.major_turns), "ending_hook": item.ending_hook,
                "must_keep": list(item.must_keep), "must_avoid": list(item.must_avoid)})

    planning_index = _read_json(Path(project_root) / PLANNING_INDEX)
    planning_items = [{"planning_revision": planning_index.get("head_revision_id")
                       or planning_index.get("current_revision_id") or "",
                       "revision_count": planning_index.get("revision_count"),
                       "source_ref": PLANNING_INDEX}]
    store_dir = Path(project_root) / HISTORY_DIR
    if not (store_dir / "index.json").is_file():
        store_dir = Path(__file__).resolve().parents[3] / HISTORY_DIR
    ir_index = _read_json(store_dir / "index.json")
    ir_items = ([{"chapter_count": ir_index.get("chapter_count"),
                  "index_digest": ir_index.get("index_digest"),
                  "source_ref": f"{HISTORY_DIR}/index.json"}] if ir_index else [])

    sections = [
        _section("story_bible", "Story Bible", "planned",
                 source="NovelProfile + ContentPack", identity=profile.novel_id,
                 items=world_items),
        _section("cards.characters", "角色卡片", "occurred",
                 source="StoryState.characters / NovelProfile.cast",
                 identity=context.runtime_id or novel_id, items=character_items),
        _section("cards.factions", "势力卡片", "occurred",
                 source="StoryState.factions", identity=context.runtime_id or novel_id,
                 items=faction_items),
        _section("cards.locations", "地点卡片", "occurred",
                 source="StoryState.location.known", identity=context.runtime_id or novel_id,
                 items=location_items),
        _section("timeline", "Timeline", "occurred", source="StoryState.timeline",
                 identity=context.runtime_id or novel_id, items=timeline_items),
        _section("spine", "StorySpine", "planned", source=RECON_DIR,
                 identity=branch_id, items=spine_items),
        _section("outline", "全书 / 卷 / 篇章 / 章节大纲", "planned",
                 source="outline_forge.load_forge_chain", identity=branch_id,
                 items=outline_items),
        _section("planning", "StoryPlanningIR", "planned", source=PLANNING_INDEX,
                 identity=planning_items[0]["planning_revision"] if planning_items else "",
                 items=planning_items),
        _section("canon_refs", "Canon 事实（只读引用）", "occurred",
                 source="canon/wasteland_001.sqlite", identity=novel_id, items=canon_items),
        _section("historical_ir", "570 章 historical IR", "historical_repair",
                 source=f"{HISTORY_DIR}/index.json", identity=novel_id, items=ir_items),
    ]
    manifest = {
        "export_id": f"export_{novel_id}_{branch_id}_{_digest([s['digest'] for s in sections])}",
        "format_version": EXPORT_FORMAT_VERSION,
        "novel_id": novel_id, "branch_id": branch_id,
        "pack_id": pack_id,
        "source_digests": {"canon": FROZEN_SOURCE_DIGESTS["canon"],
                           "story_state": FROZEN_SOURCE_DIGESTS["story_state"],
                           "legacy": FROZEN_SOURCE_DIGESTS["legacy"],
                           "chapter_ir": FROZEN_SOURCE_DIGESTS["chapter_ir"],
                           "historical_foundation": dict(FROZEN_FOUNDATION_DIGESTS),
                           "contract": "67559aa55442d69e",
                           "repair_gate": "e1eab4c33ae75b01"},
        "sections": [{"section_id": row["section_id"], "truth_layer": row["truth_layer"],
                      "item_count": row["item_count"], "digest": row["digest"]}
                     for row in sections],
        "truth_layer_legend": dict(TRUTH_LAYER_LEGEND),
        "non_authoritative": True,
    }
    return {"manifest": manifest, "sections": sections,
            "writer_ready": {
                "entry": "M16B WriterContextBuilder",
                "artifact_refs": [f"{row['section_id']}（{row['truth_layer']}）"
                                  for row in sections],
                "note": "本包是 writer-ready 的只读投影；写作输出另存 preview，不回写事实。",
            }}


def validate_export_package(projection: Mapping[str, Any]) -> dict[str, Any]:
    """M16A validation：schema / identity / provenance / truth separation / stability。"""

    manifest = dict(projection.get("manifest") or {})
    sections = list(projection.get("sections") or [])
    section_ids = [str(row.get("section_id")) for row in sections]
    required_ids = {"story_bible", "cards.characters", "cards.factions",
                    "cards.locations", "timeline", "spine", "outline", "planning"}
    digest_now = _digest([row.get("digest") for row in sections])
    checks = {
        "schema_sections_present": required_ids <= set(section_ids),
        "stable_identity": bool(manifest.get("export_id"))
        and manifest.get("export_id", "").endswith(digest_now),
        "provenance_present": all(row.get("source") and row.get("identity")
                                  for row in sections),
        "truth_layer_declared": all(row.get("truth_layer") in TRUTH_LAYER_LEGEND
                                    for row in sections),
        "truth_separation": (
            all(row["truth_layer"] == "historical_repair"
                for row in sections if row["section_id"] == "historical_ir")
            and all(row["truth_layer"] == "planned"
                    for row in sections if row["section_id"] in
                    ("story_bible", "outline", "planning", "spine"))),
        "source_digests_recorded": bool(manifest.get("source_digests")),
        "writer_ready_block": bool(projection.get("writer_ready")),
    }
    return {"validation_id": "M16A_EXPORT_VALIDATION",
            "status": "PASS" if all(checks.values()) else "FAIL",
            "checks": checks, "section_count": len(sections),
            "read_only": True, "non_authoritative": True}


def serialize_export(projection: Mapping[str, Any], fmt: str = "json") -> dict[str, Any]:
    """M16A serializer：json（canonical）/ markdown / docx（复用既有 docx_bytes）。"""

    manifest = dict(projection.get("manifest") or {})
    sections = list(projection.get("sections") or [])
    normalized = (fmt or "json").lower()
    base = f"{manifest.get('novel_id')}_{manifest.get('branch_id')}"
    if normalized == "json":
        payload = {"manifest": manifest, "sections": sections,
                   "writer_ready": projection.get("writer_ready")}
        return {"filename": f"planning_export_{base}.json", "format": "json",
                "content": json.dumps(payload, ensure_ascii=False, indent=2),
                "export_id": manifest.get("export_id")}
    if normalized in ("markdown", "md"):
        lines = [f"# {manifest.get('novel_id')} · Planning Export",
                 "",
                 f"- export_id：{manifest.get('export_id')}",
                 f"- 路线：{manifest.get('branch_id')}",
                 f"- 格式版本：{manifest.get('format_version')}", ""]
        for section in sections:
            # 作者语言：不把内部组件名 / sqlite 路径写进给人读的文档。
            layer = TRUTH_LAYER_AUTHOR_LABEL.get(section["truth_layer"],
                                                section["truth_layer"])
            lines.extend([f"## {section['title']}"
                          f"（{layer}｜{section['item_count']} 项）", ""])
            for item in section["items"][:200]:
                if section["section_id"] == "outline":
                    lines.append(f"- **[{item['level']}] {item['title']}**：{item['summary']}")
                elif section["section_id"] == "cards.characters":
                    lines.append(f"- {item.get('name') or item.get('id')}（{item.get('kind')}）")
                else:
                    label = (item.get("text") or item.get("name") or item.get("title")
                             or item.get("id") or "")
                    if label:
                        lines.append(f"- {label}")
            lines.append("")
        return {"filename": f"planning_export_{base}.md", "format": "markdown",
                "content": "\n".join(lines), "export_id": manifest.get("export_id")}
    if normalized == "docx":
        paragraphs: list[tuple[str, str]] = [
            ("title", f"{manifest.get('novel_id')} Planning Export"),
            ("text", f"export_id：{manifest.get('export_id')}｜路线 {manifest.get('branch_id')}")]
        for section in sections:
            paragraphs.append(("heading", f"{section['title']}（"
                                          f"{TRUTH_LAYER_AUTHOR_LABEL.get(section['truth_layer'], section['truth_layer'])}）"))
            for item in section["items"][:200]:
                label = (item.get("text") or item.get("title") or item.get("name")
                         or item.get("id") or "")
                if label:
                    paragraphs.append(("text", str(label)))
        content = docx_bytes(paragraphs)
        return {"filename": f"planning_export_{base}.docx", "format": "docx",
                "content_base64": base64.b64encode(content).decode("ascii"),
                "size": len(content), "export_id": manifest.get("export_id")}
    return {"filename": "", "format": normalized, "error": "EXPORT_FORMAT_UNSUPPORTED",
            "supported": ["json", "markdown", "docx"]}


def export_package(project_root: Path | str, novel_id: str, *, branch_id: str = DEFAULT_BRANCH,
                   fmt: str = "json", include_projection: bool = False
                   ) -> dict[str, Any]:
    """M16A 单一出口：projection → validation → serializer。"""

    projection = build_export_projection(project_root, novel_id, branch_id=branch_id)
    validation = validate_export_package(projection)
    artifact = serialize_export(projection, fmt)
    payload = {"novel_id": novel_id, "branch_id": branch_id,
               "validation": validation, "artifact": {key: row for key, row in
                                                      artifact.items() if key != "content"},
               "read_only": True, "non_authoritative": True}
    if "content" in artifact:
        payload["artifact"]["content"] = artifact["content"]
    if include_projection:
        payload["projection"] = projection
    return payload


__all__ = [
    "EXPORT_FORMAT_VERSION", "TRUTH_LAYER_AUTHOR_LABEL", "TRUTH_LAYER_LEGEND",
    "build_export_projection", "export_package", "serialize_export",
    "validate_export_package",
]
