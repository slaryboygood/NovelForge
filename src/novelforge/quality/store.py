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
from typing import Any, Iterable, Mapping, Sequence

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

    def reports(self) -> list[dict[str, Any]]:
        """全部质量报告（V4-07 交付需要按 revision 核对质量结论）。"""

        folder = quality_reports_dir(self.project_root, self.novel_id)
        if not folder.is_dir():
            return []
        rows: list[dict[str, Any]] = []
        for path in sorted(folder.glob("*.json")):
            payload = self._read(path)
            if payload:
                rows.append(payload)
        return rows

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

    # -------------------------------------------------------- issue 生命周期
    def latest_coverage(self) -> dict[str, dict[str, Any]]:
        """`node_id` → **最新一份覆盖它的质量报告**（V4.0.2 PB-1 / §45 语义）。

        "最新"按 `(generated_at, report_id)` 判定：新报告取代旧报告后，旧报告里的
        issue 不再代表当前真相（GAP-010：issue 生命周期此前没有"随最新报告失效"的语义）。
        """

        coverage: dict[str, dict[str, Any]] = {}
        for report in self.reports():
            generated = str(report.get("generated_at") or "")
            report_id = str(report.get("report_id") or "")
            issue_ids = {str(row.get("issue_id"))
                         for row in (report.get("issues") or [])}
            for raw_node_id, raw_revision in (report.get("node_revisions") or {}).items():
                node_id = str(raw_node_id)
                current = coverage.get(node_id)
                if current is not None and (
                        str(current["generated_at"]),
                        str(current["report_id"])) >= (generated, report_id):
                    continue
                coverage[node_id] = {
                    "report_id": report_id, "generated_at": generated,
                    "revision": int(raw_revision or 0), "issue_ids": issue_ids}
        return coverage

    def live_issues(self, *, node_id: str = "", revision: int | None = None,
                    gate: str = "", codes: Sequence[str] = (),
                    statuses: Sequence[str] = ("open", "repairing")
                    ) -> list[dict[str, Any]]:
        """仍是**当前质量真相**的 issue（V4.0.2 PB-1 的核心语义）。

        判定条件（全部满足）：

        ```text
        1. status ∈ statuses（resolved / accepted_risk / ignored 不再算 live）
        2. issue 仍出现在**最新一份覆盖其 scope 节点**的报告里
           （被新报告取代的历史 issue 不代表当前真相）
        3. 可选过滤：node_id（scope 必须包含它）/ gate / codes
        4. 给定 revision 时，覆盖报告评估的必须正是该 revision
        ```

        返回行是 issue 的副本，并附 `live_report_id` / `live_revision` 证据字段，
        便于调用方在 issue 证据里说明"为什么它现在仍然有效"。
        """

        allowed = {str(value) for value in statuses}
        wanted_codes = {str(value) for value in codes if str(value)}
        coverage = self.latest_coverage()
        rows: list[dict[str, Any]] = []
        for issue in self.list_issues():
            if allowed and str(issue.get("status")) not in allowed:
                continue
            if gate and str(issue.get("gate")) != str(gate):
                continue
            code = str(issue.get("code"))
            if wanted_codes and code not in wanted_codes:
                continue
            scope_nodes = [str(value) for value in
                           ((issue.get("scope") or {}).get("node_ids") or []) if value]
            if node_id:
                if str(node_id) not in scope_nodes:
                    continue
                cover = coverage.get(str(node_id))
                if cover is None or str(issue.get("issue_id")) not in cover["issue_ids"]:
                    continue
                if revision is not None and int(cover["revision"]) != int(revision):
                    continue
                rows.append({**issue, "live_report_id": cover["report_id"],
                             "live_revision": int(cover["revision"])})
                continue
            covers = [coverage[value] for value in scope_nodes
                      if value in coverage
                      and str(issue.get("issue_id")) in coverage[value]["issue_ids"]]
            if not covers:
                continue
            rows.append({**issue, "live_report_id": covers[0]["report_id"],
                         "live_revision": int(covers[0]["revision"])})
        return rows

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
