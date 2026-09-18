"""Delivery Store（V4-07 §62–§66）：交付快照 / manifest / artifact 落盘。

```text
novel/authoring/story_engine/delivery/<novel_id>/
├── snapshots/<snapshot_id>.json
├── manifests/<snapshot_id>.json
├── requests/<idempotency_key>.json     幂等重放
└── packages/<snapshot_id>/…            最终交付物（先 staging，后原子发布）
```

原子性（§64）：先在 `<snapshot_id>.staging` 下写完所有 artifact 并校验 checksum，
再整体 rename 成 `<snapshot_id>`；失败时删除 staging，**不留下伪成功 package**。
路径全部经 `persistence.paths`（§62）。
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Mapping

from novelforge.persistence.paths import (
    delivery_artifact_path,
    delivery_dir,
    delivery_manifest_path,
    delivery_manifests_dir,
    delivery_packages_dir,
    delivery_snapshot_path,
    delivery_snapshots_dir,
)

from .errors import DeliveryError, DeliveryExportError, DeliveryOwnershipError


def _safe_relative(relative_path: str) -> str:
    text = str(relative_path or "").replace("\\", "/").strip()
    parts = [part for part in text.split("/") if part]
    if not parts or text.startswith("/") or ":" in text or \
            any(part in ("..", ".") for part in parts):
        raise DeliveryError(f"artifact 路径不安全：{relative_path!r}",
                            details={"path": text})
    return "/".join(parts)


class DeliveryStore:
    """按 novel_id 隔离的交付存储。"""

    def __init__(self, project_root: Path | str, novel_id: str) -> None:
        if not str(novel_id or "").strip():
            raise DeliveryOwnershipError("DeliveryStore 需要显式 novel_id")
        self.project_root = Path(project_root)
        self.novel_id = str(novel_id)

    # ------------------------------------------------------------------ 基础
    @property
    def root(self) -> Path:
        return delivery_dir(self.project_root, self.novel_id)

    @staticmethod
    def _write(path: Path, payload: Mapping[str, Any]) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(dict(payload), ensure_ascii=False, indent=1,
                                  sort_keys=True) + "\n",
                       encoding="utf-8", newline="\n")
        tmp.replace(path)
        return path

    @staticmethod
    def _read(path: Path) -> dict[str, Any]:
        if not path.is_file():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def _assert_ownership(self, novel_id: str) -> None:
        if str(novel_id) != self.novel_id:
            raise DeliveryOwnershipError(
                f"拒绝跨作品写入：{novel_id} != {self.novel_id}",
                details={"novel_id": self.novel_id})

    # --------------------------------------------------------------- snapshot
    def save_snapshot(self, snapshot: Any) -> Path:
        self._assert_ownership(snapshot.novel_id)
        return self._write(delivery_snapshot_path(self.project_root, self.novel_id,
                                                  snapshot.snapshot_id),
                           snapshot.as_dict())

    def get_snapshot(self, snapshot_id: str) -> dict[str, Any]:
        return self._read(delivery_snapshot_path(self.project_root, self.novel_id,
                                                 snapshot_id))

    def list_snapshots(self) -> list[dict[str, Any]]:
        folder = delivery_snapshots_dir(self.project_root, self.novel_id)
        if not folder.is_dir():
            return []
        rows = [self._read(path) for path in sorted(folder.glob("*.json"))]
        return [row for row in rows if row]

    # --------------------------------------------------------------- manifest
    def save_manifest(self, manifest: Any) -> Path:
        self._assert_ownership(manifest.novel_id)
        return self._write(delivery_manifest_path(self.project_root, self.novel_id,
                                                  manifest.snapshot_id),
                           manifest.as_dict())

    def get_manifest(self, snapshot_id: str) -> dict[str, Any]:
        return self._read(delivery_manifest_path(self.project_root, self.novel_id,
                                                 snapshot_id))

    def list_manifests(self) -> list[dict[str, Any]]:
        folder = delivery_manifests_dir(self.project_root, self.novel_id)
        if not folder.is_dir():
            return []
        rows = [self._read(path) for path in sorted(folder.glob("*.json"))]
        return [row for row in rows if row]

    # ------------------------------------------------------------- artifacts
    def staging_dir(self, snapshot_id: str) -> Path:
        return delivery_packages_dir(self.project_root, self.novel_id) / \
            f"{snapshot_id}.staging"

    def package_dir(self, snapshot_id: str) -> Path:
        return delivery_packages_dir(self.project_root, self.novel_id) / snapshot_id

    def write_staged(self, snapshot_id: str, relative_path: str, data: bytes) -> Path:
        safe = _safe_relative(relative_path)
        path = self.staging_dir(snapshot_id) / safe
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(bytes(data))
        return path

    def publish(self, snapshot_id: str) -> Path:
        """staging → final（原子 rename，§64）。"""

        staging = self.staging_dir(snapshot_id)
        final = self.package_dir(snapshot_id)
        if final.is_dir():
            shutil.rmtree(final)
        staging.parent.mkdir(parents=True, exist_ok=True)
        staging.replace(final)
        return final

    def discard(self, snapshot_id: str) -> None:
        """删除 staging（失败路径：不留下伪成功 package）。"""

        staging = self.staging_dir(snapshot_id)
        if staging.is_dir():
            shutil.rmtree(staging)

    def read_artifact(self, snapshot_id: str, relative_path: str) -> bytes:
        safe = _safe_relative(relative_path)
        path = delivery_artifact_path(self.project_root, self.novel_id,
                                      snapshot_id, safe)
        if not path.is_file():
            raise DeliveryExportError(f"artifact 不存在：{relative_path}",
                                      details={"snapshot_id": snapshot_id,
                                               "path": safe})
        return path.read_bytes()

    def artifact_file(self, snapshot_id: str, relative_path: str) -> Path:
        safe = _safe_relative(relative_path)
        return delivery_artifact_path(self.project_root, self.novel_id,
                                      snapshot_id, safe)

    def is_published(self, snapshot_id: str) -> bool:
        return self.package_dir(snapshot_id).is_dir()

    # -------------------------------------------------------------- idempotency
    def record_request(self, idempotency_key: str, snapshot_id: str) -> Path:
        safe = "".join(ch for ch in str(idempotency_key) if ch.isalnum() or
                       ch in "_-")[:96]
        return self._write(self.root / "requests" / f"{safe}.json",
                           {"idempotency_key": str(idempotency_key),
                            "snapshot_id": str(snapshot_id),
                            "novel_id": self.novel_id})

    def find_request(self, idempotency_key: str) -> dict[str, Any]:
        safe = "".join(ch for ch in str(idempotency_key) if ch.isalnum() or
                       ch in "_-")[:96]
        return self._read(self.root / "requests" / f"{safe}.json")

    def stats(self) -> dict[str, Any]:
        return {"novel_id": self.novel_id,
                "snapshots": len(self.list_snapshots()),
                "manifests": len(self.list_manifests()),
                "packages": len([path for path in
                                 delivery_packages_dir(self.project_root,
                                                       self.novel_id).glob("*")
                                 if path.is_dir()]) if
                delivery_packages_dir(self.project_root, self.novel_id).is_dir()
                else 0}


__all__ = ["DeliveryStore"]
