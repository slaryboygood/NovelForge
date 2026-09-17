"""M11 phase snapshot store（phase-scoped / write-once / digest 保护）。

问题（ANALYSIS_SNAPSHOT_NOT_WRITE_ONCE）：phase service 的重跑会覆盖自己的
machine-readable 输出（例如 BLOCKER-00 的 root inventory、BLOCKER-00A 的 canonical
inventory），导致历史 phase 测试只能读到 current live state，产生大规模
timepoint drift。

本模块提供最小内部实现：

```text
write_phase_snapshot(root, phase_id, data)   # 首次写入；已存在则拒绝覆盖
load_phase_snapshot(root, phase_id)          # 读历史 snapshot（immutable）
load_current_state(root)                     # 读当前 closure production state
snapshot_exists(root, phase_id)
```

目录结构：

```text
workspace/wasteland_001_exports/repair_adoption_v1/phase_snapshots/<phase_id>/
    snapshot.json      # phase 历史数据（不含 volatile 字段）
    manifest.json      # phase_id / source_commit / created_at / digest / 来源证据
```

只有显式 ``overwrite=True``（maintenance / migration）才允许重建既有 snapshot。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from novelforge.story_engine.historical_adoption import ADOPTION_DIR

SNAPSHOT_ROOT = "phase_snapshots"
SCHEMA_VERSION = "M11_PHASE_SNAPSHOT_V1"


class PhaseSnapshotExists(RuntimeError):
    """snapshot 已存在（write-once 保护）。"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _digest(payload: Any) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False,
                      default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def phase_dir(root: Path | str, phase_id: str) -> Path:
    return Path(root).resolve() / ADOPTION_DIR / SNAPSHOT_ROOT / str(phase_id)


def snapshot_exists(root: Path | str, phase_id: str) -> bool:
    return (phase_dir(root, phase_id) / "snapshot.json").is_file()


def write_phase_snapshot(root: Path | str, phase_id: str, data: Mapping[str, Any],
                         *, source_commit: str = "",
                         evidence_sources: Sequence[str] = (),
                         reconstructed: bool = False,
                         overwrite: bool = False) -> dict[str, Any]:
    """写入 phase 历史 snapshot（默认 write-once）。"""

    directory = phase_dir(root, phase_id)
    snapshot_path = directory / "snapshot.json"
    if snapshot_path.is_file() and not overwrite:
        raise PhaseSnapshotExists(
            f"phase snapshot 已存在，拒绝覆盖：{snapshot_path}"
            "（write-once；如需重建请显式 overwrite=True / maintenance 模式）")
    payload = dict(data)
    payload.setdefault("phase_id", str(phase_id))
    payload["schema_version"] = SCHEMA_VERSION
    payload["read_only"] = True
    payload["non_authoritative"] = True
    manifest = {
        "phase_id": str(phase_id), "schema_version": SCHEMA_VERSION,
        "created_at": _now(), "source_commit": str(source_commit),
        "snapshot_digest": _digest(payload),
        "reconstructed": bool(reconstructed),
        "evidence_sources": list(evidence_sources),
        "artifact_digests": {
            key: _digest(value) for key, value in payload.items()
            if isinstance(value, (dict, list))},
        "read_only": True, "non_authoritative": True,
    }
    directory.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                             encoding="utf-8")
    (directory / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def load_phase_snapshot(root: Path | str, phase_id: str) -> dict[str, Any]:
    """读取历史 phase snapshot（缺失即报错，绝不静默回退到 live state）。"""

    snapshot_path = phase_dir(root, phase_id) / "snapshot.json"
    if not snapshot_path.is_file():
        raise FileNotFoundError(
            f"phase snapshot 不存在：{snapshot_path}"
            "（历史 phase 测试必须读取 frozen snapshot，不得读 current live state）")
    return json.loads(snapshot_path.read_text(encoding="utf-8"))


def load_snapshot_manifest(root: Path | str, phase_id: str) -> dict[str, Any]:
    manifest_path = phase_dir(root, phase_id) / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"phase snapshot manifest 不存在：{manifest_path}")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def verify_phase_snapshot(root: Path | str, phase_id: str) -> dict[str, Any]:
    """校验 snapshot 与其 manifest digest 一致（immutability 证据，只读）。

    write-once 只保证不会被覆盖；本函数额外证明「磁盘上的 snapshot 仍等于当初写入的
    payload」，即历史 phase 证据没有被静默改写。任何 digest 不一致即 FAIL。
    """

    payload = load_phase_snapshot(root, phase_id)
    manifest = load_snapshot_manifest(root, phase_id)
    actual = _digest(payload)
    expected = str(manifest.get("snapshot_digest") or "")
    artifact_mismatch = sorted(
        key for key, value in (manifest.get("artifact_digests") or {}).items()
        if key not in payload or _digest(payload[key]) != value)
    checks = {
        "payload_digest_matches_manifest": bool(expected) and actual == expected,
        "artifact_digests_match_manifest": not artifact_mismatch,
    }
    return {
        "phase_id": str(phase_id),
        "verification_id": "PHASE_SNAPSHOT_IMMUTABILITY_VERIFICATION",
        "snapshot_digest": actual,
        "manifest_digest": expected,
        "artifact_digest_mismatches": artifact_mismatch,
        "checks": checks,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "read_only": True, "non_authoritative": True,
    }


def load_current_state(root: Path | str) -> dict[str, Any]:
    """读取当前（closure 后）production state 摘要；只读。"""

    design = Path(root).resolve() / ADOPTION_DIR

    def read(name: str) -> dict[str, Any]:
        path = design / name
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}

    overlay = read("M11_OVERLAY_V2.json")
    ledger = read("M11_REPAIR_SUBTYPE_LEDGER.json")
    readiness = read("M11_READINESS_V2.json")
    backlog = read("M11_PRODUCTION_BACKLOG.json")
    queue = read("M11_CONTENT_DESIGN_QUEUE_V3.json")
    reconciliation = read("M11_FINAL_CLOSURE_RECONCILIATION.json")
    identity = sorted(
        (str(row.get("canonical_root_id")), str(row.get("chapter_id")),
         str(row.get("new_resolution_status")))
        for row in reconciliation.get("records") or [])
    count = lambda rows, status: sum(  # noqa: E731
        1 for row in rows or [] if str(row.get("status")) == status)
    return {
        "state_id": "M11_CURRENT_STATE",
        "terminal_targets": overlay.get("resolved_total"),
        "non_terminal_targets": overlay.get("remaining_repair_targets"),
        "overlay_buckets": dict(overlay.get("primary_resolution_status_counts") or {}),
        "overlay_conservation": dict(overlay.get("conservation") or {}),
        "ledger_entries": len(ledger.get("ledger") or []),
        "ledger_resolved": sum((ledger.get("resolved_subtype_counts") or {}).values()),
        "readiness_completion": dict(readiness.get("completion_status_counts") or {}),
        "readiness_execution": dict(readiness.get("execution_status_counts") or {}),
        "backlog_done": sum(1 for row in backlog.get("items") or []
                            if str(row.get("status")) in ("DONE", "RESOLVED")),
        "backlog_backlog": count(backlog.get("items"), "BACKLOG"),
        "cdq_active": count(queue.get("requirements"), "ACTIVE"),
        "reconciliation_identity_digest": _digest(identity),
        "reconciliation_identity_count": len(identity),
        "read_only": True, "non_authoritative": True,
    }


__all__ = [
    "SCHEMA_VERSION",
    "SNAPSHOT_ROOT",
    "PhaseSnapshotExists",
    "load_current_state",
    "load_phase_snapshot",
    "load_snapshot_manifest",
    "phase_dir",
    "snapshot_exists",
    "verify_phase_snapshot",
    "write_phase_snapshot",
]
