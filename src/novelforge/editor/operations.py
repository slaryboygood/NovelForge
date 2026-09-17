"""Editor Store（V4-06 §47–§50）：只存 editor metadata。

```text
novel/authoring/story_engine/editor/<novel_id>/
├── operations/<operation_id>.json     EditorOperationRecord（审计）
├── reviews/<node_id>__r<revision>.json ReviewDecision（accept / reject）
└── MANIFEST.json
```

**不是第二套 Blueprint truth**（§5 / §49）：canonical 内容永远在
`BlueprintRepository`；这里只有操作与评审记录。路径全部经 `persistence.paths`（§50）。
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from novelforge.persistence.paths import (
    editor_manifest_path,
    editor_operations_dir,
    editor_reviews_dir,
)

from .contracts import EditorOperationRecord, ReviewDecision
from .errors import EditorOwnershipError


def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


class EditorStore:
    """按 novel_id 隔离的 editor metadata 存储。"""

    def __init__(self, project_root: Path | str, novel_id: str) -> None:
        if not str(novel_id or "").strip():
            raise EditorOwnershipError("EditorStore 需要显式 novel_id")
        self.project_root = Path(project_root)
        self.novel_id = str(novel_id)

    # ------------------------------------------------------------------ 内部
    def _write(self, path: Path, payload: Mapping[str, Any]) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(dict(payload), ensure_ascii=False, indent=1) + "\n",
                       encoding="utf-8", newline="\n")
        tmp.replace(path)
        return path

    def _read(self, path: Path) -> dict[str, Any]:
        if not path.is_file():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    # ------------------------------------------------------------- operations
    def record_operation(self, record: EditorOperationRecord) -> Path:
        if record.novel_id != self.novel_id:
            raise EditorOwnershipError(
                f"拒绝跨作品写入：{record.novel_id} != {self.novel_id}",
                details={"operation_id": record.operation_id})
        payload = {**record.as_dict(),
                   "created_at": record.created_at or utc_now()}
        path = self._write(
            editor_operations_dir(self.project_root, self.novel_id) /
            f"{record.operation_id}.json", payload)
        self.touch_manifest()
        return path

    def get_operation(self, operation_id: str) -> dict[str, Any]:
        return self._read(editor_operations_dir(self.project_root, self.novel_id) /
                          f"{operation_id}.json")

    def operations(self, *, node_id: str = "") -> list[dict[str, Any]]:
        folder = editor_operations_dir(self.project_root, self.novel_id)
        if not folder.is_dir():
            return []
        rows: list[dict[str, Any]] = []
        for path in sorted(folder.glob("*.json")):
            payload = self._read(path)
            if not payload:
                continue
            if node_id and str(payload.get("node_id") or "") != node_id:
                continue
            rows.append(payload)
        return sorted(rows, key=lambda row: str(row.get("created_at") or ""))

    def find_by_idempotency(self, key: str) -> dict[str, Any]:
        """§46：同一 idempotency_key 的重放不得产生第二个 revision。"""

        if not str(key or "").strip():
            return {}
        for row in reversed(self.operations()):
            if str(row.get("idempotency_key") or "") == str(key):
                return row
        return {}

    # ---------------------------------------------------------------- reviews
    @staticmethod
    def _review_name(node_id: str, revision: int) -> str:
        safe = str(node_id).replace("/", "_")
        return f"{safe}__r{int(revision):06d}.json"

    def record_review(self, decision: ReviewDecision) -> Path:
        if decision.novel_id != self.novel_id:
            raise EditorOwnershipError(
                f"拒绝跨作品写入：{decision.novel_id} != {self.novel_id}")
        payload = {**decision.as_dict(),
                   "created_at": decision.created_at or utc_now()}
        path = self._write(
            editor_reviews_dir(self.project_root, self.novel_id) /
            self._review_name(decision.node_id, decision.revision), payload)
        self.touch_manifest()
        return path

    def review_for(self, node_id: str, revision: int) -> dict[str, Any]:
        return self._read(editor_reviews_dir(self.project_root, self.novel_id) /
                          self._review_name(node_id, revision))

    def reviews(self, *, node_id: str = "") -> list[dict[str, Any]]:
        folder = editor_reviews_dir(self.project_root, self.novel_id)
        if not folder.is_dir():
            return []
        rows: list[dict[str, Any]] = []
        for path in sorted(folder.glob("*.json")):
            payload = self._read(path)
            if not payload:
                continue
            if node_id and str(payload.get("node_id") or "") != node_id:
                continue
            rows.append(payload)
        return rows

    def latest_review(self, node_id: str) -> dict[str, Any]:
        rows = self.reviews(node_id=node_id)
        if not rows:
            return {}
        return max(rows, key=lambda row: (int(row.get("revision") or 0),
                                          str(row.get("created_at") or "")))

    # ---------------------------------------------------------------- 统计
    def touch_manifest(self) -> Path:
        operations = self.operations()
        reviews = self.reviews()
        return self._write(editor_manifest_path(self.project_root, self.novel_id), {
            "novel_id": self.novel_id, "updated_at": utc_now(),
            "operation_count": len(operations), "review_count": len(reviews),
            "rejected_revisions": sum(1 for row in reviews
                                      if row.get("decision") == "rejected"),
            "accepted_revisions": sum(1 for row in reviews
                                      if row.get("decision") == "accepted"),
            "canonical_blueprint_store": "blueprint/<novel_id>（editor 不持有第二套 truth）",
        })

    def stats(self) -> dict[str, Any]:
        operations = self.operations()
        by_operation: dict[str, int] = {}
        for row in operations:
            key = str(row.get("operation") or "")
            by_operation[key] = by_operation.get(key, 0) + 1
        return {"novel_id": self.novel_id, "operations": len(operations),
                "by_operation": dict(sorted(by_operation.items())),
                "reviews": len(self.reviews())}

    def operation_summaries(self, *, node_id: str = "") -> Sequence[dict[str, Any]]:
        return tuple(self.operations(node_id=node_id))


__all__ = ["EditorStore", "utc_now"]
