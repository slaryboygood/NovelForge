"""Milestone acceptance 公共基础件：phase snapshot 发布 + freeze guard 读法。

M12–M17 的 milestone service 各自实现了几乎相同的 `_publish_snapshot`
（write-once + maintenance refresh + digest 校验）。M18 把它收敛到这一处，
行为完全一致（artifact schema 不变、replay 不变），后续 milestone 只调用这里。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from novelforge.story_engine.phase_snapshot import (
    snapshot_exists,
    verify_phase_snapshot,
    write_phase_snapshot,
)


def head_commit(root: Path | str) -> str:
    head = Path(root).resolve() / ".git" / "HEAD"
    if not head.is_file():
        return ""
    text = head.read_text(encoding="utf-8").strip()
    if text.startswith("ref:"):
        ref = Path(root).resolve() / ".git" / text.split(" ", 1)[1].strip()
        return ref.read_text(encoding="utf-8").strip() if ref.is_file() else ""
    return text


def publish_phase_snapshot(root: Path | str, phase_id: str,
                           data: Mapping[str, Any], *,
                           evidence_sources: Sequence[str] = (),
                           refresh_reason: str = "") -> dict[str, Any]:
    """首次写入（write-once）；已存在时只校验，`refresh_reason` 为显式维护重建。"""

    root = Path(root).resolve()
    if snapshot_exists(root, phase_id):
        if refresh_reason:
            manifest = write_phase_snapshot(
                root, phase_id, dict(data), overwrite=True, reconstructed=True,
                source_commit=head_commit(root),
                evidence_sources=[f"maintenance:{refresh_reason}",
                                  *list(evidence_sources)])
            return {"snapshot_id": phase_id, "snapshot_written": True,
                    "snapshot_refreshed": True, "snapshot_status": "PASS",
                    "snapshot_digest": manifest["snapshot_digest"]}
        verification = verify_phase_snapshot(root, phase_id)
        return {"snapshot_id": phase_id, "snapshot_written": False,
                "snapshot_status": verification["status"],
                "snapshot_digest": verification["snapshot_digest"]}
    manifest = write_phase_snapshot(root, phase_id, dict(data),
                                    source_commit=head_commit(root),
                                    evidence_sources=list(evidence_sources))
    return {"snapshot_id": phase_id, "snapshot_written": True,
            "snapshot_status": "PASS",
            "snapshot_digest": manifest["snapshot_digest"]}


__all__ = ["head_commit", "publish_phase_snapshot"]
