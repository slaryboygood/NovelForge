"""BlueprintRepository —— Story Blueprint 的 canonical store（V4-04 §30–§32）。

```text
蓝图节点（append-only revision）
  blueprint/<novel_id>/nodes/<node_id>/r%06d.json
索引
  blueprint/<novel_id>/index.json      current revision / 子节点顺序 / idempotency 记录
manifest
  blueprint/<novel_id>/MANIFEST.json   schema_version / novel_id / updated_at / counts
```

规则：

```text
· 每个节点独立 revision（append-only，不覆盖历史）
· 写入必须携带 expected_revision（不匹配 → RevisionConflict）
· idempotency_key 命中时返回已存在的 revision（不产生重复写入）
· 只经 persistence.paths 获取路径（不自行拼路径）
```
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from novelforge.core.revision import RevisionConflict, check_expected_revision
from novelforge.persistence.paths import (
    blueprint_dir,
    blueprint_index_path,
    blueprint_manifest_path,
    blueprint_node_dir,
    blueprint_node_path,
)

from .contracts import BLUEPRINT_SCHEMA_VERSION, BlueprintNode, utc_now
from .errors import BlueprintNodeNotFound, BlueprintOwnershipError


class BlueprintRepository:
    """按 novel_id 隔离的 Blueprint 节点存储（唯一写入口）。"""

    def __init__(self, project_root: Path | str, novel_id: str) -> None:
        if not str(novel_id or "").strip():
            raise BlueprintOwnershipError("BlueprintRepository 需要显式 novel_id")
        self.project_root = Path(project_root)
        self.novel_id = str(novel_id)

    # ------------------------------------------------------------------ 路径
    @property
    def root(self) -> Path:
        return blueprint_dir(self.project_root, self.novel_id)

    def _index_file(self) -> Path:
        return blueprint_index_path(self.project_root, self.novel_id)

    # ------------------------------------------------------------------ 索引
    def _read_index(self) -> dict[str, Any]:
        path = self._index_file()
        if not path.is_file():
            return {"schema_version": BLUEPRINT_SCHEMA_VERSION,
                    "novel_id": self.novel_id, "nodes": {}, "children": {},
                    "idempotency": {}}
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload.setdefault("nodes", {})
        payload.setdefault("children", {})
        payload.setdefault("idempotency", {})
        return payload

    def _write_index(self, payload: Mapping[str, Any]) -> None:
        path = self._index_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        body = {**dict(payload), "novel_id": self.novel_id,
                "schema_version": BLUEPRINT_SCHEMA_VERSION, "updated_at": utc_now()}
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(body, ensure_ascii=False, indent=1) + "\n",
                       encoding="utf-8", newline="\n")
        tmp.replace(path)
        manifest = blueprint_manifest_path(self.project_root, self.novel_id)
        manifest.write_text(json.dumps(
            {"schema_version": BLUEPRINT_SCHEMA_VERSION, "novel_id": self.novel_id,
             "node_count": len(body.get("nodes") or {}),
             "updated_at": body["updated_at"]}, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8", newline="\n")

    # ------------------------------------------------------------------ 读取
    def exists(self, node_id: str) -> bool:
        return node_id in (self._read_index().get("nodes") or {})

    def current_revision(self, node_id: str) -> int:
        row = (self._read_index().get("nodes") or {}).get(node_id)
        return int(row["revision"]) if row else 0

    def get_current(self, node_id: str) -> BlueprintNode | None:
        revision = self.current_revision(node_id)
        if revision <= 0:
            return None
        return self.get_revision(node_id, revision)

    def get_revision(self, node_id: str, revision: int) -> BlueprintNode | None:
        path = blueprint_node_path(self.project_root, self.novel_id, node_id,
                                   revision)
        if not path.is_file():
            return None
        raw = json.loads(path.read_text(encoding="utf-8"))
        if str(raw.get("novel_id")) != self.novel_id:
            raise BlueprintOwnershipError(
                f"节点归属不符：{raw.get('novel_id')} != {self.novel_id}",
                details={"node_id": node_id})
        return BlueprintNode.from_dict(raw)

    def require_current(self, node_id: str) -> BlueprintNode:
        node = self.get_current(node_id)
        if node is None:
            raise BlueprintNodeNotFound(f"Blueprint 节点不存在：{node_id}",
                                        details={"node_id": node_id})
        return node

    def list_revisions(self, node_id: str) -> list[int]:
        folder = blueprint_node_dir(self.project_root, self.novel_id, node_id)
        if not folder.is_dir():
            return []
        rows: list[int] = []
        for path in sorted(folder.glob("r*.json")):
            try:
                rows.append(int(path.stem[1:]))
            except ValueError:  # pragma: no cover - 非标准文件名
                continue
        return rows

    def list_children(self, parent_id: str, *, node_type: str = "") -> list[BlueprintNode]:
        index = self._read_index()
        child_ids: list[str] = list((index.get("children") or {}).get(parent_id) or [])
        if not child_ids:
            child_ids = [node_id for node_id, row in (index.get("nodes") or {}).items()
                         if str(row.get("parent_id") or "") == parent_id]
        nodes: list[BlueprintNode] = []
        for node_id in child_ids:
            node = self.get_current(node_id)
            if node is None:
                continue
            if node_type and node.node_type != node_type:
                continue
            nodes.append(node)
        return sorted(nodes, key=lambda item: (item.sequence, item.node_id))

    def list_by_type(self, node_type: str) -> list[BlueprintNode]:
        index = self._read_index()
        rows: list[BlueprintNode] = []
        for node_id, row in (index.get("nodes") or {}).items():
            if str(row.get("node_type")) != node_type:
                continue
            node = self.get_current(node_id)
            if node is not None:
                rows.append(node)
        return sorted(rows, key=lambda item: (item.sequence, item.node_id))

    def all_nodes(self) -> list[BlueprintNode]:
        index = self._read_index()
        rows = [self.get_current(node_id) for node_id in (index.get("nodes") or {})]
        return sorted((row for row in rows if row is not None),
                      key=lambda item: (item.node_type, item.sequence, item.node_id))

    def index_snapshot(self) -> dict[str, Any]:
        return self._read_index()

    def find_by_idempotency(self, idempotency_key: str) -> BlueprintNode | None:
        """按 idempotency_key 查找已写入的节点（幂等命中时不再调用模型，§39）。"""

        if not idempotency_key:
            return None
        row = (self._read_index().get("idempotency") or {}).get(idempotency_key)
        if not row:
            return None
        return self.get_revision(str(row.get("node_id")), int(row.get("revision")))

    # ------------------------------------------------------------------ 写入
    def save_revision(self, node: BlueprintNode, *, expected_revision: int | None = None,
                      idempotency_key: str = "") -> BlueprintNode:
        """保存一个新 revision（append-only）。

        · `expected_revision` 与当前 revision 不一致 → RevisionConflict
        · `idempotency_key` 命中 → 直接返回既有 revision（不重复写入）
        """

        if str(node.novel_id) != self.novel_id:
            raise BlueprintOwnershipError(
                f"拒绝跨作品写入：{node.novel_id} != {self.novel_id}",
                details={"node_id": node.node_id})

        index = self._read_index()
        idempotency = index.get("idempotency") or {}
        if idempotency_key and idempotency_key in idempotency:
            existing = idempotency[idempotency_key]
            stored = self.get_revision(str(existing["node_id"]),
                                       int(existing["revision"]))
            if stored is not None:
                return stored

        current = self.current_revision(node.node_id)
        check_expected_revision(expected_revision, current or None,
                                artifact_id=node.node_id)
        next_revision = current + 1
        parent_revision = current or 0

        stored_node = BlueprintNode(
            node_id=node.node_id, novel_id=node.novel_id, node_type=node.node_type,
            payload=node.payload, parent_id=node.parent_id, revision=next_revision,
            parent_revision=parent_revision, status=node.status,
            source_ids=tuple(node.source_ids), context_digest=node.context_digest,
            created_at=node.created_at, updated_at=utc_now(),
            generation_contract=node.generation_contract,
            generation_contract_version=node.generation_contract_version,
            provenance=dict(node.provenance), quality_status=node.quality_status,
            schema_version=BLUEPRINT_SCHEMA_VERSION, sequence=node.sequence)

        path = blueprint_node_path(self.project_root, self.novel_id, node.node_id,
                                   next_revision)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(stored_node.as_dict(), ensure_ascii=False, indent=1)
                       + "\n", encoding="utf-8", newline="\n")
        tmp.replace(path)

        nodes = dict(index.get("nodes") or {})
        nodes[node.node_id] = {"node_type": node.node_type, "revision": next_revision,
                               "parent_id": node.parent_id, "status": node.status,
                               "sequence": node.sequence}
        children = {key: list(value) for key, value in
                    (index.get("children") or {}).items()}
        if node.parent_id:
            rows = children.setdefault(node.parent_id, [])
            if node.node_id not in rows:
                rows.append(node.node_id)
        self._write_index({"nodes": nodes, "children": children,
                           "idempotency": idempotency})
        if idempotency_key:
            index = self._read_index()
            mapping = dict(index.get("idempotency") or {})
            mapping[idempotency_key] = {"node_id": node.node_id,
                                        "revision": next_revision,
                                        "saved_at": utc_now()}
            self._write_index({"nodes": nodes, "children": children,
                               "idempotency": mapping})
        return stored_node

    def set_status(self, node_id: str, status: str, *,
                   expected_revision: int | None = None) -> BlueprintNode:
        """状态流转（proposed → draft → accepted → superseded），不改 payload。"""

        from .lifecycle import ALLOWED_STATUS_TRANSITIONS

        node = self.require_current(node_id)
        if status not in ALLOWED_STATUS_TRANSITIONS.get(node.status, ()):
            from .errors import BlueprintStatusError

            raise BlueprintStatusError(
                f"不允许的状态流转：{node.status} → {status}",
                details={"node_id": node_id, "from": node.status, "to": status})
        updated = BlueprintNode(
            node_id=node.node_id, novel_id=node.novel_id, node_type=node.node_type,
            payload=node.payload, parent_id=node.parent_id, revision=node.revision,
            parent_revision=node.parent_revision, status=status,
            source_ids=tuple(node.source_ids), context_digest=node.context_digest,
            created_at=node.created_at, updated_at=utc_now(),
            generation_contract=node.generation_contract,
            generation_contract_version=node.generation_contract_version,
            provenance=dict(node.provenance), quality_status=node.quality_status,
            schema_version=node.schema_version, sequence=node.sequence)
        return self.save_revision(updated, expected_revision=node.revision)

    def delete_novel_store(self) -> None:
        """仅供测试 / 归档使用：删除本作品的 Blueprint 目录。"""

        import shutil

        root = self.root
        if root.is_dir():
            shutil.rmtree(root)

    # ------------------------------------------------------------------ 便捷
    def current_refs(self, nodes: Iterable[BlueprintNode]) -> dict[str, int]:
        return {node.node_id: self.current_revision(node.node_id) for node in nodes}


__all__ = ["BlueprintRepository"]
