"""Quality Store（V4-05 §45）：质量结果独立存储，是 **quality truth**（不是 story truth）。

```text
quality/<novel_id>/
├── reports/<report_id>.json
├── issues/<issue_id>.json
├── repair_history/<plan_id>.json
└── MANIFEST.json
```

路径只能经 `persistence.paths`。Blueprint 节点的 `quality_status` 只是本 store 的**投影**（§46）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from novelforge.persistence.paths import (
    quality_issues_dir,
    quality_manifest_path,
    quality_repair_history_dir,
    quality_reports_dir,
)

from .contracts import QUALITY_SCHEMA_VERSION, QualityIssue, QualityReport, utc_now
from .errors import QualityScopeError


class QualityStore:
    """按 novel_id 隔离的质量结果存储。"""

    def __init__(self, project_root: Path | str, novel_id: str) -> None:
        if not str(novel_id or "").strip():
            raise QualityScopeError("QualityStore 需要显式 novel_id")
        self.project_root = Path(project_root)
        self.novel_id = str(novel_id)

    # ------------------------------------------------------------------ 内部
    def _write(self, path: Path, payload: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(dict(payload), ensure_ascii=False, indent=1) + "\n",
                       encoding="utf-8", newline="\n")
        tmp.replace(path)

    def _read(self, path: Path) -> dict[str, Any]:
        if not path.is_file():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def _touch_manifest(self) -> None:
        issues = self.list_issues()
        payload = {"schema_version": QUALITY_SCHEMA_VERSION,
                   "novel_id": self.novel_id, "updated_at": utc_now(),
                   "issue_count": len(issues),
                   "open_issue_count": sum(1 for row in issues
                                           if row.get("status") == "open"),
                   "report_count": len(list(quality_reports_dir(
                       self.project_root, self.novel_id).glob("*.json")))
                   if quality_reports_dir(self.project_root,
                                          self.novel_id).is_dir() else 0}
        self._write(quality_manifest_path(self.project_root, self.novel_id), payload)

    # ------------------------------------------------------------------ 报告
    def save_report(self, report: QualityReport) -> Path:
        path = quality_reports_dir(self.project_root, self.novel_id) / \
            f"{report.report_id}.json"
        self._write(path, report.as_dict())
        self._touch_manifest()
        return path

    def latest_report(self) -> dict[str, Any]:
        folder = quality_reports_dir(self.project_root, self.novel_id)
        if not folder.is_dir():
            return {}
        rows = sorted(folder.glob("*.json"), key=lambda item: item.stat().st_mtime)
        return self._read(rows[-1]) if rows else {}

    # ------------------------------------------------------------------ issues
    def save_issues(self, issues: Iterable[QualityIssue]) -> int:
        count = 0
        for issue in issues:
            path = quality_issues_dir(self.project_root, self.novel_id) / \
                f"{issue.issue_id}.json"
            self._write(path, issue.as_dict())
            count += 1
        if count:
            self._touch_manifest()
        return count

    def get_issue(self, issue_id: str) -> dict[str, Any]:
        path = quality_issues_dir(self.project_root, self.novel_id) / f"{issue_id}.json"
        return self._read(path)

    def list_issues(self, *, status: str = "", gate: str = "") -> list[dict[str, Any]]:
        folder = quality_issues_dir(self.project_root, self.novel_id)
        if not folder.is_dir():
            return []
        rows: list[dict[str, Any]] = []
        for path in sorted(folder.glob("*.json")):
            payload = self._read(path)
            if not payload:
                continue
            if status and payload.get("status") != status:
                continue
            if gate and payload.get("gate") != gate:
                continue
            rows.append(payload)
        return rows

    def issue_objects(self, *, status: str = "", gate: str = "") -> tuple[QualityIssue, ...]:
        """读回 `QualityIssue` 对象（Application / Repair / MCP 消费，不重新评估）。"""

        return tuple(QualityIssue.from_dict(row)
                     for row in self.list_issues(status=status, gate=gate))

    def update_issue_status(self, issue_id: str, status: str, *,
                            note: str = "") -> dict[str, Any]:
        from .contracts import ISSUE_STATUSES

        if status not in ISSUE_STATUSES:
            raise QualityScopeError(f"未知 issue status：{status}")
        payload = self.get_issue(issue_id)
        if not payload:
            return {}
        payload["status"] = status
        payload["updated_at"] = utc_now()
        if note:
            payload["status_note"] = note
        self._write(quality_issues_dir(self.project_root, self.novel_id) /
                    f"{issue_id}.json", payload)
        self._touch_manifest()
        return payload

    # -------------------------------------------------------- repair history
    def save_repair_history(self, plan_id: str, payload: Mapping[str, Any]) -> Path:
        path = quality_repair_history_dir(self.project_root, self.novel_id) / \
            f"{plan_id}.json"
        self._write(path, {**dict(payload), "novel_id": self.novel_id,
                           "updated_at": utc_now()})
        return path

    def repair_history(self) -> list[dict[str, Any]]:
        folder = quality_repair_history_dir(self.project_root, self.novel_id)
        if not folder.is_dir():
            return []
        return [self._read(path) for path in sorted(folder.glob("*.json"))]

    def stats(self) -> dict[str, Any]:
        issues = self.list_issues()
        by_gate: dict[str, int] = {}
        for row in issues:
            by_gate[str(row.get("gate"))] = by_gate.get(str(row.get("gate")), 0) + 1
        return {"novel_id": self.novel_id, "issues": len(issues),
                "open": sum(1 for row in issues if row.get("status") == "open"),
                "by_gate": dict(sorted(by_gate.items())),
                "repair_rounds": len(self.repair_history())}


__all__ = ["QualityStore"]
