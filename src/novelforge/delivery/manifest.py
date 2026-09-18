"""DeliveryManifest 与 checksum（V4-07 §39–§41、§43）。

```text
manifest 是"这次交付物是什么"的唯一清单：
  novel / snapshot / selected revisions / formats / exporters / policy /
  quality summary / artifacts{path, mime, checksum, size} / excluded
```

checksum 用 sha256（稳定、可验证）；manifest 内容本身 deterministic。
"""

from __future__ import annotations

import hashlib
from typing import Any, Iterable, Mapping, Sequence

from .contracts import (
    DELIVERY_SCHEMA_VERSION,
    PACKAGE_VERSION,
    DeliveryManifest,
    DeliverySnapshot,
    ExportArtifact,
    utc_now,
)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(bytes(data)).hexdigest()


def artifact_row(artifact: ExportArtifact) -> dict[str, Any]:
    return {"path": artifact.relative_path, "filename": artifact.filename,
            "format": artifact.format, "mime_type": artifact.mime_type,
            "size": int(artifact.size), "checksum": artifact.checksum,
            "exporter_id": artifact.exporter_id,
            "exporter_version": int(artifact.exporter_version),
            "owned_by": "delivery"}


def build_manifest(*, snapshot: DeliverySnapshot, artifacts: Sequence[ExportArtifact],
                   exporters: Sequence[Mapping[str, Any]],
                   quality_summary: Mapping[str, Any],
                   blueprint_schema_version: int,
                   project_id: str = "", manifest_id: str = "",
                   created_at: str = "", extra: Mapping[str, Any] | None = None
                   ) -> DeliveryManifest:
    source_ids: set[str] = set()
    for artifact in artifacts:
        source_ids.add(artifact.relative_path)
    return DeliveryManifest(
        manifest_id=manifest_id or f"DM_{snapshot.snapshot_id}",
        novel_id=snapshot.novel_id, project_id=project_id or snapshot.novel_id,
        snapshot_id=snapshot.snapshot_id, created_at=created_at or utc_now(),
        blueprint_schema_version=int(blueprint_schema_version),
        delivery_schema_version=DELIVERY_SCHEMA_VERSION,
        package_version=PACKAGE_VERSION,
        selected_revisions=dict(snapshot.node_revisions),
        formats=tuple(str(fmt) for fmt in snapshot.formats),
        exporters=tuple(dict(row) for row in exporters),
        quality_policy=dict(snapshot.policy),
        quality_summary=dict(quality_summary),
        review_policy={"selection_mode": snapshot.selection_mode,
                       "profile": snapshot.profile,
                       "review_refs": dict(sorted(snapshot.review_refs.items()))},
        source_ids=tuple(sorted(source_ids)),
        artifacts=tuple(artifact_row(artifact) for artifact in artifacts),
        excluded=tuple(dict(row) for row in snapshot.excluded),
        input_digest=snapshot.input_digest,
        extra=dict(extra or {}))


def verify_artifacts(artifacts: Iterable[Any]) -> dict[str, str]:
    """重算 checksum（post-build 校验用）。返回 path → 期望 checksum。"""

    rows: dict[str, str] = {}
    for artifact in artifacts:
        rows[str(artifact.relative_path)] = sha256_hex(artifact.content)
    return rows


__all__ = ["artifact_row", "build_manifest", "sha256_hex", "verify_artifacts"]
