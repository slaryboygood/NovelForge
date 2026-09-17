"""M15 Canon Inspector / Repair Center 的只读 application 层。

repo 定义（V2 里程碑，见 docs/CHANGELOG.md）：M15 = 「Canon 检查器 + 修复中心 UI」。
本模块提供 **只读** 查询与诊断；任何写入都必须走既有正式 API
（`settings/check(repair=true)`、`outline/revise|restore|merge-versions`），
UI 不得直接改 Canon / StoryState。

V4-01 变更（作者决策 B / ADR-011）：

* 删除 570 章 historical IR 层（`historical_repair`）与 REPAIR_REPLAY 引用；
  Inspector 现在只检查 **本作品** 的 Canon 与 StoryState。
* Canon DB 路径按 `novel_id` 解析（`persistence.paths.canon_db_path`），
  不再写死 `wasteland_001`，也不再回落到别的作品。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from novelforge.persistence.paths import canon_db_path
from novelforge.story_engine.canon.repository import CanonRepository
from novelforge.story_engine.creator import CreatorContextError, resolve_creator_context
from novelforge.story_engine.memory_view import memory_snapshot
from novelforge.story_engine.creator import DEFAULT_BRANCH
from novelforge.story_engine.outline_forge import (
    OutlineForgeError,
    StructureSpec,
    assess_forge_plan,
    build_forge_plan,
)
from novelforge.story_engine.settings_check import run_settings_check
from novelforge.story_engine.settings_gen import load_pack_draft, saved_pack_id
from novelforge.story_engine.world_view import world_snapshot

LAYERS: tuple[str, ...] = ("occurred", "planned", "ui_derived")


def _read_json(path: Path) -> Any:
    import json

    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _context(project_root: Path | str, novel_id: str):
    try:
        return resolve_creator_context(project_root, novel_id)
    except CreatorContextError:
        return None


def _canon_rows(project_root: Path | str, novel_id: str) -> dict[str, Any]:
    """Canon 只读读取（DB 不存在时返回空，不创建文件）。"""

    db_path = canon_db_path(project_root, novel_id)
    if not db_path.is_file():
        return {"available": False, "facts": [], "entities": [], "events": []}
    repository = CanonRepository(db_path)
    try:
        facts = repository.facts(novel_id)
        entities = repository.entities(novel_id)
    finally:
        repository.close()
    return {
        "available": True,
        "facts": [{"fact_id": row.fact_id, "category": row.category,
                   "ref_id": row.fact_id,
                   "label": row.canonical_description or row.canonical_key,
                   "summary": row.canonical_description,
                   "description": row.canonical_description, "status": row.status,
                   "source_refs": [_ref(item) for item in (row.source_refs or [])],
                   "truth_layer": "occurred", "record_kind": "canon_fact",
                   "kind": row.category} for row in facts],
        "entities": [{"entity_id": row.entity_id,
                      "ref_id": row.entity_id,
                      "name": row.display_name or row.canonical_key,
                      "label": row.display_name or row.canonical_key,
                      "kind": row.kind, "truth_layer": "occurred",
                      "record_kind": "canon_entity",
                      "source_refs": [_ref(item)
                                      for item in (row.source_refs or [])],
                      "record_kind": "canon_entity"}
                     for row in entities],
        "events": [],
    }


def _ref(item: Any) -> str:
    """CanonSourceRef → 稳定的可展示引用串（只读）。"""

    if isinstance(item, str):
        return item
    kind = getattr(item, "source_type", "") or getattr(item, "kind", "")
    stable = getattr(item, "stable_key", "") or getattr(item, "ref", "")
    label = getattr(item, "label", "") or getattr(item, "quote", "")
    return ":".join(part for part in (str(kind), str(stable), str(label)) if part)


def inspector_overview(project_root: Path | str, novel_id: str) -> dict[str, Any]:
    """M15-01：Canon Inspector 总览（各层数量 + 出处摘要，只读）。"""

    canon = _canon_rows(project_root, novel_id)
    context = _context(project_root, novel_id)
    state_rows: list[dict[str, Any]] = []
    if context is not None:
        world = world_snapshot(context)
        memory = memory_snapshot(context)
        for row in world["resources"]:
            state_rows.append({"record_kind": "resource", "ref_id": row["id"],
                               "label": f"{row['id']} = {row['amount']} {row['unit']}",
                               "truth_layer": "occurred",
                               "source_refs": ["StoryState.resources"]})
        for row in memory.get("knowledge_index") or []:
            state_rows.append({"record_kind": "knowledge", "ref_id": row["id"],
                               "label": f"{row['id']}（{row['certainty']}）",
                               "truth_layer": "occurred",
                               "source_refs": [f"StoryState.knowledge:{row['source']}"]})
    return {
        "novel_id": novel_id,
        "canon": {"available": canon["available"],
                  "fact_count": len(canon["facts"]),
                  "entity_count": len(canon["entities"]),
                  "db_ref": f"canon/{novel_id}.sqlite"},
        "story_state": {"available": context is not None,
                        "record_count": len(state_rows),
                        "records": state_rows[:50]},
        # V4-01：570 章 historical IR 层已删除；本字段保留为显式 null，
        # 让消费者能区分"没有这一层"与"这一层是空的"。
        "chapter_ir": None,
        "layers": list(LAYERS),
        "read_only": True, "non_authoritative": True,
    }


def inspector_search(project_root: Path | str, novel_id: str, *, query: str = "",
                     layer: str = "", record_kind: str = "", limit: int = 50
                     ) -> dict[str, Any]:
    """M15-01：跨层检索（Canon 事实 / 实体 / StoryState；V4-01 起不含 historical IR）。"""

    rows: list[dict[str, Any]] = []
    canon = _canon_rows(project_root, novel_id)
    rows.extend(canon["facts"])
    rows.extend(canon["entities"])
    context = _context(project_root, novel_id)
    if context is not None:
        world = world_snapshot(context)
        for row in world["location"]["known"]:
            rows.append({"record_kind": "location", "ref_id": str(row["id"]),
                         "label": f"{row.get('name') or row['id']}",
                         "summary": str(row.get("access") or ""),
                         "truth_layer": "occurred",
                         "source_refs": ["StoryState.location.known"]})
        for row in world["factions"]:
            rows.append({"record_kind": "faction", "ref_id": str(row["id"]),
                         "label": str(row["name"]),
                         "summary": str(row.get("stance") or ""),
                         "truth_layer": "occurred",
                         "source_refs": ["StoryState.factions"]})
    text = query.strip().lower()
    filtered = []
    for row in rows:
        if layer and row.get("truth_layer") != layer:
            continue
        if record_kind and row.get("record_kind") != record_kind:
            continue
        if text:
            blob = " ".join(str(row.get(key) or "") for key in
                            ("label", "summary", "ref_id", "description"))
            if text not in blob.lower():
                continue
        row.setdefault("summary", row.get("description", ""))
        filtered.append(row)
    return {
        "novel_id": novel_id, "query": query, "layer": layer,
        "record_kind": record_kind, "total": len(filtered),
        "rows": filtered[:limit],
        "kinds": sorted({str(row.get("record_kind")) for row in rows}),
        "layers": list(LAYERS),
        "read_only": True, "non_authoritative": True,
    }


def inspector_record(project_root: Path | str, novel_id: str, *, ref_id: str
                     ) -> dict[str, Any]:
    """M15-01：单条记录详情 + provenance / lineage（只读）。"""

    search = inspector_search(project_root, novel_id, query=ref_id, limit=200)
    match = next((row for row in search["rows"]
                  if str(row.get("ref_id")) == ref_id), None)
    if match is None:
        return {"novel_id": novel_id, "ref_id": ref_id, "found": False,
                "note": "未找到该记录（换一个 ref_id 或用 /search 先检索）",
                "read_only": True, "non_authoritative": True}
    provenance = [{"ref": ref, "kind": "source"} for ref in
                  (match.get("source_refs") or ["（未记录来源）"])]
    return {
        "novel_id": novel_id, "ref_id": ref_id, "found": True,
        "record": match, "provenance": provenance,
        "truth_layer": match.get("truth_layer"),
        "read_only": True, "non_authoritative": True,
    }


def repair_diagnosis(project_root: Path | str, novel_id: str) -> dict[str, Any]:
    """M15-02：修复中心诊断（只读）——问题 → 证据 → 建议动作 → 审批要求 → 影响。"""

    issues: list[dict[str, Any]] = []
    pack_id = saved_pack_id(project_root, novel_id)
    if pack_id:
        report = run_settings_check(project_root, novel_id)
        for finding in report.findings:
            fixes_available = bool(report.repairable)
            issues.append({
                "issue_id": f"SETTINGS_{finding.code}_{finding.target or 'pack'}",
                "source": "settings_check", "severity": finding.severity,
                "message": finding.message, "hint": finding.hint,
                "target": finding.target or report.pack_id,
                "proposed_action": ("POST /story-builder/settings/check "
                                    "{repair:true}（数据层兜底后重新自检）"
                                    if fixes_available else "需要作者补充内容"),
                "execution_api": ("settings/check" if fixes_available else ""),
                "requires_approval": False if fixes_available else True,
                "approval_note": ("" if fixes_available else
                                  "内容缺失需要作者提供设定，不由系统代写"),
                "impact": {"packs": [report.pack_id],
                           "actions": len(report.available_candidates)},
                "truth_layer": "planned",
                "evidence": [f"settings/check:{finding.code}"],
            })
    try:
        plan = build_forge_plan(project_root, novel_id, branch_id=DEFAULT_BRANCH,
                                structure=StructureSpec())
        quality = assess_forge_plan(plan).as_dict()
    except OutlineForgeError:
        quality = {}
    if quality:
        for finding in quality.get("findings") or []:
            issues.append({
                "issue_id": f"OUTLINE_{finding.get('code')}_{finding.get('target')}",
                "source": "outline_quality", "severity": finding.get("severity", "warning"),
                "message": finding.get("message", ""), "hint": "",
                "target": str(finding.get("target") or ""),
                "proposed_action": "在大纲锻造里改写 / 回退版本（outline/revise|restore）",
                "execution_api": "outline/revise",
                "requires_approval": True,
                "approval_note": "改写大纲属于规划内容，需作者确认",
                "impact": {"packages": [finding.get("target")],
                           "pacing": list(quality.get("pacing") or [])},
                "truth_layer": "planned",
                "evidence": [f"outline/plan:quality:{finding.get('code')}"],
            })
        return {
            "novel_id": novel_id, "issue_count": len(issues), "issues": issues,
            "outline_quality_ok": bool(quality.get("ok")),
            "execution_boundary": ("Repair Center 只调用既有 API；不直接写 Canon / "
                                   "StoryState"),
            "read_only": True, "non_authoritative": True,
        }
    return {
        "novel_id": novel_id, "issue_count": len(issues), "issues": issues,
        "outline_quality_ok": None,
        "execution_boundary": "Repair Center 只调用既有 API；不直接写 Canon / StoryState",
        "read_only": True, "non_authoritative": True,
    }


def repair_history(project_root: Path | str, novel_id: str) -> dict[str, Any]:
    """M15-02：修复历史 / reconciliation（只读）。"""

    context = _context(project_root, novel_id)
    entries: list[dict[str, Any]] = []
    if context is not None:
        effects = getattr(context.state, "effect_log", []) or []
        for row in list(effects)[-50:]:
            entries.append({
                "order": getattr(row, "order", 0),
                "op": str(getattr(row, "op", "")),
                "target": str(getattr(row, "target", "")),
                "source": str(getattr(row, "source", "")),
                "truth_layer": "occurred",
            })
    return {
        "novel_id": novel_id, "effect_log": entries,
        "outline_versions_ref": "outline/versions（在大纲锻造面板查看版本历史）",
        "read_only": True, "non_authoritative": True,
    }


__all__ = [
    "LAYERS", "inspector_overview", "inspector_record",
    "inspector_search", "repair_diagnosis", "repair_history",
]
