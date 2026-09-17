"""M11 phase 历史证据 helper。

M11 closure（372/372 terminal）之后，早期 phase 的 live 值已经被 closure 合法推进。
phase 测试里的历史期望值必须来自 **frozen 历史记录**（phase report / frozen snapshot），
不能要求 live production state 回到旧 timepoint。

使用约定：

```python
report_records("BLOCKER_00", "| non-terminal | 149 | ✓ |")   # 历史证据仍被记录
assert overlay["content_design_required"] == closed(58, 0)   # [M11-CLOSURE] 显式双值
```

`closed(historical, current)` 显式写出"历史值 → closure 后 live 值"，避免静默改写，
也避免把永久 invariant 弱化成模糊断言。
"""

from __future__ import annotations

# 通用能力（closed / snapshot helpers / report evidence）放在 phase_history；
# 这里 re-export，保持 M11 测试既有的 `from m11_phase_history import ...` 不破。
from phase_history import (  # noqa: F401
    ROOT,
    PhaseSnapshotExists,
    assert_doc_records,
    closed,
    load_current_state,
    load_phase_snapshot,
    load_snapshot_manifest,
    phase,
    snapshot_exists,
    verify_phase_snapshot,
    write_phase_snapshot,
)

PHASE_REPORTS: dict[str, str] = {
    "BLOCKER_00": "docs/WASTELAND_001_M11_BLOCKER_00_REPORT.md",
    "BLOCKER_00A": "docs/WASTELAND_001_M11_BLOCKER_00A_REPORT.md",
    "CONTENT_DESIGN_01": "docs/WASTELAND_001_M11_CONTENT_DESIGN_01_REPORT.md",
    "AUTHOR_CONTENT_01": "docs/WASTELAND_001_M11_AUTHOR_CONTENT_01_REPORT.md",
    "AUTO_SAFE_SWEEP_CLOSEOUT":
        "docs/WASTELAND_001_M11_AUTO_SAFE_SWEEP_CLOSEOUT_REPORT.md",
    "FINAL_CLOSURE": "docs/WASTELAND_001_M11_FINAL_CLOSURE_REPORT.md",
    "P15O": "docs/WASTELAND_001_M11_MICRO_WAVE_02_AND_REWRITE_HARDENING_REPORT.md",
    "P15P": "docs/NOVELFORGE_P15_REPAIR_SYSTEM_FINAL_CLOSEOUT.md",
    "CONTENT_REWRITE": "docs/WASTELAND_001_M11_CONTENT_REWRITE_POLICY_PILOT_REPORT.md",
    "BATCH05": "docs/WASTELAND_001_M11_BATCH_05_REPORT.md",
    "MICRO_PILOT": "docs/WASTELAND_001_M11_MICRO_CONTENT_REPAIR_PILOT_REPORT.md",
}

# CONTENT_REWRITE phase report §3：新增 event 只能填补 before → missing middle → after。
FROZEN_REWRITE_PILOT_REASON = (
    "confirmed before → missing causal middle → confirmed after")


def phase_report(phase: str) -> str:
    if phase not in PHASE_REPORTS:
        raise KeyError(f"unknown phase report: {phase}")
    return assert_doc_records(PHASE_REPORTS[phase], label=phase)


def report_records(phase: str, *needles: str) -> None:
    """历史值必须仍被 frozen phase report 记录（历史证据不被静默改写）。"""

    assert_doc_records(PHASE_REPORTS[phase], *needles, label=phase)


def assert_m12_projection(payload: dict, criteria: dict) -> None:
    """Validate the live projection against its criteria, including blocking semantics."""

    rows = criteria["criteria"]
    assert len(rows) == criteria["criteria_count"] == 9
    assert len({row["criterion"] for row in rows}) == 9
    satisfied = sum(row["satisfied"] is True for row in rows)
    blocking = sum(row["blocking"] and not row["satisfied"] for row in rows)
    assert payload["satisfied_count"] == criteria["satisfied_count"] == satisfied
    assert payload["unsatisfied_count"] == criteria["unsatisfied_count"] == 9 - satisfied
    assert payload["blocking_count"] == criteria["blocking_count"] == blocking
    assert payload["criteria_count"] == 9
    assert payload["satisfied_count"] + payload["unsatisfied_count"] == 9
    assert payload["entry_allowed"] == criteria["m12_entry_allowed"]


def rewrite_pilot_rows() -> list[dict[str, str]]:
    """从 frozen CONTENT_REWRITE phase report 解析 5 个 pilot proposal 行。

    报告 §4 的表格是 pilot scope 的 frozen evidence（章节 / class / frontier /
    direct blocker / proposal id / new event id）。proposal 数量、class、frontier 与
    生成的 identity 全部以该表为准，不从已 closure 的 live requirement surface 反推。
    """

    import re

    pattern = re.compile(r"^\|\s*(ch\d{3})\s*\|(.*)\|\s*$")
    rows: list[dict[str, str]] = []
    previous_class = ""
    for line in phase_report("CONTENT_REWRITE").splitlines():
        match = pattern.match(line.strip())
        if not match:
            continue
        cells = [cell.strip().strip("`") for cell in match.group(2).split("|")]
        klass_cell = cells[0]
        # 报告用“同上”继承上一行的 rewrite class。
        klass = previous_class if klass_cell in ("同上", "") else klass_cell
        previous_class = klass
        rows.append({
            "chapter": match.group(1),
            "rewrite_class": klass,
            "frontier": cells[1],
            "direct_blockers": cells[2],
            "proposal_id": cells[3],
            "new_event_id": cells[4],
        })
    return rows


def historical_rewrite_proposals(inputs):
    """Exercise retired proposal rules in memory using the report's five pilot cases.

    These are reconstructed test inputs, never current execution eligibility or
    production proposals. Chapter content comes from unchanged legacy evidence; the
    pilot scope / class / identity come from the frozen phase report. The live
    requirement surface for these labels was legitimately retired at M11 closure, so
    only the non-asserted ``why_required`` reason is reconstructed from the frozen
    policy text (报告 §3).
    """
    from novelforge.story_engine.m11_content_rewrite import _rewrite_proposals

    rows = rewrite_pilot_rows()
    report_records("CONTENT_REWRITE",
                   FROZEN_REWRITE_PILOT_REASON,
                   *(row["proposal_id"] for row in rows),
                   *(row["new_event_id"] for row in rows))
    assert len(rows) == 5, rows
    by_label = {row["id"]: cid for cid, row in inputs.legacy.items()}
    proposals = []
    for row in rows:
        label = row["chapter"]
        cid = by_label[label]
        spec = inputs.requirements.get(label) or {
            "why_required": FROZEN_REWRITE_PILOT_REASON,
            "reconstructed_from": "docs/WASTELAND_001_M11_CONTENT_REWRITE_POLICY_"
                                  "PILOT_REPORT.md"}
        proposals.extend(_rewrite_proposals(
            label=label, chapter_id=cid, klass=row["rewrite_class"],
            legacy=inputs.legacy[cid], spec=spec,
            item={"frontier": row["frontier"]}))
    assert [row.legacy_label for row in proposals] == [row["chapter"] for row in rows]
    for proposal, row in zip(proposals, rows):
        assert proposal.proposal_id == row["proposal_id"]
        assert proposal.new_event["proposed_event_id"] == row["new_event_id"]
        assert proposal.rewrite_class == row["rewrite_class"]
    return proposals


PHASE_IDS: tuple[str, ...] = (
    "BLOCKER_00", "BLOCKER_00A", "CONTENT_DESIGN_01", "AUTHOR_CONTENT_01",
    "AUTO_SAFE_SWEEP_CLOSEOUT", "P15O", "P15P", "CONTENT_REWRITE",
    "APPROVED_EVENT", "BATCH05", "MICRO_PILOT", "READINESS_V2",
    *(f"M11_RUN_{index:02d}" for index in range(1, 13)))
