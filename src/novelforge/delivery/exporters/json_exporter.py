"""JSON exporter（V4-07 §28、§31、§55）：versioned structured export。

```text
schema / manifest / novel / blueprint / quality_summary / provenance
```

机器消费（未来 MCP / Agent / Plugin）读取本格式；内部 metadata 只在这里出现。
"""

from __future__ import annotations

import json
from typing import Any, Mapping

from ..contracts import DELIVERY_SCHEMA_VERSION, PACKAGE_VERSION
from . import ExporterRegistry, ExporterSpec

EXPORTER_ID = "delivery.json.v1"
EXPORTER_VERSION = 1


def _profile_block(context: Mapping[str, Any]) -> dict[str, Any]:
    selection = dict(context.get("selection") or {})
    profile = str(selection.get("profile") or "author")
    return {"profile": profile,
            "include_quality": bool(selection.get("include_quality_report")),
            "include_provenance": bool(selection.get("include_provenance")),
            "include_revision_history": bool(
                selection.get("include_revision_history")),
            "include_review_metadata": bool(
                selection.get("include_review_metadata"))}


def build_document(context: Mapping[str, Any]) -> dict[str, Any]:
    """统一 JSON 结构（exporter 只做序列化，不做内容决策）。"""

    blueprint = dict(context.get("blueprint") or {})
    document: dict[str, Any] = {
        "schema": {"delivery_schema_version": DELIVERY_SCHEMA_VERSION,
                   "package_version": PACKAGE_VERSION,
                   "blueprint_schema_version": int(
                       context.get("blueprint_schema_version") or 0),
                   "format": "json", "exporter_id": EXPORTER_ID,
                   "exporter_version": EXPORTER_VERSION},
        "manifest": dict(context.get("manifest") or {}),
        "novel": {"novel_id": context.get("novel_id"),
                  "project_id": context.get("project_id") or context.get("novel_id"),
                  "snapshot_id": context.get("snapshot_id"),
                  "title": context.get("title") or ""},
        "profile": _profile_block(context),
        "blueprint": {"ordering": list(blueprint.get("ordering") or []),
                      "node_count": int(blueprint.get("node_count") or 0),
                      "node_revisions": dict(blueprint.get("node_revisions") or {}),
                      "nodes": [dict(row) for row in (blueprint.get("nodes") or [])]},
    }
    if context.get("quality"):
        document["quality_summary"] = dict(context.get("quality") or {})
    if context.get("review"):
        document["review"] = dict(context.get("review") or {})
    if context.get("provenance"):
        document["provenance"] = dict(context.get("provenance") or {})
    if context.get("history"):
        document["revision_history"] = dict(context.get("history") or {})
    return document


def export(context: Mapping[str, Any]) -> bytes:
    document = build_document(context)
    return (json.dumps(document, ensure_ascii=False, indent=1, sort_keys=True)
            + "\n").encode("utf-8")


def register(registry: ExporterRegistry) -> ExporterSpec:
    return registry.register(ExporterSpec(
        format="json", exporter_id=EXPORTER_ID, version=EXPORTER_VERSION,
        mime_type="application/json", extension="json", text=True,
        description="versioned structured Story Blueprint export"), export)


__all__ = ["EXPORTER_ID", "EXPORTER_VERSION", "build_document", "export", "register"]
