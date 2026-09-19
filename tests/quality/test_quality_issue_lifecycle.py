"""V4.0.2 PB-1：Quality Store 的 issue 生命周期语义（`live_issues` / `latest_coverage`）。

背景（dogfood GAP-010 / PB-1）：重新评估会产生**新报告 + 新 issue 集合**，但历史 issue
仍留在 store 里且 status 仍是 `open`。于是"修好之后"的消费者（delivery preflight）
必须能判断：某条 issue 现在是否仍代表当前真相。

语义（唯一 owner = Quality Store）：

```text
live = status ∈ {open, repairing}
       AND 该 issue 仍出现在**最新一份覆盖其 scope 节点**的报告里
       AND （可选）给定 revision 时，覆盖报告评估的正是该 revision
```
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from quality_support import quality_stack

NODE_ID = "sc_001_02"


def _defect_rows(store) -> list[dict]:
    return store.list_issues(gate="Q8")


def _placeholder_issue(stack, *, revision: int | None = None) -> dict:
    """用真实评估产出（不伪造 issue 文件）拿到一条占位符 issue。"""

    repository = stack["repository"]
    node = repository.get_current(NODE_ID)
    payload = dict(node.payload.model_dump(mode="json"))
    payload["scene_purpose"] = "TODO：待补写"
    repository.save_revision(
        replace(node, payload=type(node.payload)(**payload)),
        expected_revision=repository.current_revision(NODE_ID))
    report = stack["quality"].evaluate(gates=("Q8",))
    rows = [row for row in report.issues if row.code == "BLUEPRINT_PLACEHOLDER_TEXT"]
    assert rows, [row.code for row in report.issues]
    return {"issue_id": rows[0].issue_id, "revision": report.node_revisions[NODE_ID]}


def test_live_issue_is_reported_with_report_evidence(tmp_path: Path) -> None:
    stack = quality_stack(tmp_path, script=None)
    issue = _placeholder_issue(stack)
    rows = stack["quality"].store.live_issues(node_id=NODE_ID)
    assert [row["issue_id"] for row in rows] == [issue["issue_id"]]
    assert rows[0]["live_report_id"]
    assert rows[0]["live_revision"] == issue["revision"]


def test_resolved_issue_is_not_live(tmp_path: Path) -> None:
    stack = quality_stack(tmp_path, script=None)
    issue = _placeholder_issue(stack)
    store = stack["quality"].store
    store.update_issue_status(issue["issue_id"], "resolved", note="verified")
    assert store.live_issues(node_id=NODE_ID) == []


def test_superseded_issue_is_not_live_after_new_report(tmp_path: Path) -> None:
    """新报告不再包含旧 issue → 旧 issue 不再 live（即使 status 还是 open）。"""

    stack = quality_stack(tmp_path, script=None)
    issue = _placeholder_issue(stack)
    store = stack["quality"].store
    repository = stack["repository"]
    # 改回无占位内容的版本（用 fixture 的 repaired payload）
    from quality_support import repaired_scene_payload

    fixed = repaired_scene_payload(sequence=1)
    current = repository.get_current(NODE_ID)
    payload = dict(current.payload.model_dump(mode="json"))
    payload["scene_purpose"] = str(fixed["scene_purpose"])
    repository.save_revision(
        replace(current, payload=type(current.payload)(**payload)),
        expected_revision=repository.current_revision(NODE_ID))
    report = stack["quality"].evaluate(gates=("Q8",))
    assert "BLUEPRINT_PLACEHOLDER_TEXT" not in [row.code for row in report.issues]
    # 历史 issue 仍在 store 里且 status 仍为 open（这正是 PB-1 的前提）
    assert store.get_issue(issue["issue_id"])["status"] == "open"
    assert store.live_issues(node_id=NODE_ID) == []
    assert store.live_issues(node_id=NODE_ID,
                            revision=int(report.node_revisions[NODE_ID])) == []


def test_revision_filter_distinguishes_coverage(tmp_path: Path) -> None:
    """给定 revision 时，只有覆盖该 revision 的最新报告才算 live。"""

    stack = quality_stack(tmp_path, script=None)
    issue = _placeholder_issue(stack)
    store = stack["quality"].store
    covered = issue["revision"]
    assert store.live_issues(node_id=NODE_ID, revision=covered)
    assert store.live_issues(node_id=NODE_ID, revision=covered + 1) == []


def test_latest_coverage_tracks_newest_report_per_node(tmp_path: Path) -> None:
    stack = quality_stack(tmp_path, script=None)
    issue = _placeholder_issue(stack)
    store = stack["quality"].store
    coverage = store.latest_coverage()
    assert coverage[NODE_ID]["revision"] == issue["revision"]
    assert issue["issue_id"] in coverage[NODE_ID]["issue_ids"]


def test_unrelated_gate_issues_are_ignored_by_gate_filter(tmp_path: Path) -> None:
    stack = quality_stack(tmp_path, script=None)
    _placeholder_issue(stack)
    store = stack["quality"].store
    assert store.live_issues(node_id=NODE_ID, gate="Q9") == []
    assert store.live_issues(node_id=NODE_ID, codes=("DELIVERY_PLACEHOLDER",)) == []
