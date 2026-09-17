"""V3-P5 Review / Repair / Export 投影回归。

守卫 P5 的核心规则：

* Primary Review UI 只出现作者语言（问题是什么 / 为什么重要 / 能不能自动修），
  不出现 Canon Inspector / Truth Layer / raw patch / repair opcode；
* 只有真正阻止下一阶段的问题才叫 BLOCKING；
* 导出就绪度必须来自真实状态，并明确说明「还缺什么」。
"""

from __future__ import annotations

from pathlib import Path

from novelforge.story_builder.v3_projection import command_center
from test_v3_ui_projection import client_for, new_novel, save_brief, save_seed

REPAIR_KEYS = {"available", "issue_count", "blocking_count", "issues", "reason"}
EXPORT_KEYS = {"ready", "headline", "steps", "missing", "blockers", "chapter_count",
               "writer_drafts", "bundle"}


def _started(tmp_path: Path, novel_id: str):
    client = client_for(tmp_path)
    new_novel(client, novel_id)
    save_brief(client, novel_id)
    save_seed(client, novel_id)
    started = client.post(f"/api/story-builder/runtime/start?novel_id={novel_id}", json={})
    assert started.status_code == 200, started.text
    return client, novel_id


def test_risk_levels_are_limited_to_the_v3_model(tmp_path: Path) -> None:
    client, novel_id = _started(tmp_path, "novel_v3_p5_levels")
    payload = command_center(tmp_path, novel_id)

    assert set(payload["risks"] and {row["level"] for row in payload["risks"]}) <= {
        "INFO", "WARNING", "BLOCKING"}
    for row in payload["risks"]:
        assert row["title"], "每个发现必须有作者可读标题"
        assert row["deep_link"]["view"], "每个发现必须能跳到处理它的地方"


def test_repair_view_speaks_author_language(tmp_path: Path) -> None:
    client, novel_id = _started(tmp_path, "novel_v3_p5_repair")
    payload = command_center(tmp_path, novel_id)
    repair = payload["repair"]

    assert set(repair) == REPAIR_KEYS
    assert isinstance(repair["available"], bool)
    assert repair["issue_count"] >= len(repair["issues"])
    if not repair["available"]:
        assert repair["reason"], "没有问题时必须解释为什么没有"
    for row in repair["issues"]:
        # 作者语言：不暴露 raw patch / payload / opcode / execution api。
        blob = " ".join(str(value) for value in row.values())
        for banned in ("POST ", "payload", "opcode", "execution_api", "truth_layer"):
            assert banned not in blob, f"修复视图泄漏内部概念 {banned}：{blob}"
        assert row["approval_label"], "必须说明这次修复是否需要作者确认"


def test_export_readiness_reports_real_missing_steps(tmp_path: Path) -> None:
    client, novel_id = _started(tmp_path, "novel_v3_p5_export")
    payload = command_center(tmp_path, novel_id)
    export = payload["export"]

    assert set(export) == EXPORT_KEYS
    assert export["ready"] is False, "还没有确认大纲时不能算准备好"
    assert export["missing"], "必须列出真实缺失的步骤"
    missing_ids = {row["step_id"] for row in export["missing"]}
    assert "outline_confirmed" in missing_ids
    assert "chapters_ready" in missing_ids
    # NF-012：存在真实 blocker 时标题必须说清阻塞原因，不能写「还差 0 步」。
    if export["blockers"]:
        assert export["headline"] == export["blockers"][0]
    else:
        assert export["headline"].startswith("还差")
    for row in export["steps"]:
        assert row["why"], "每一步都要说清为什么重要"
        assert row["view"], "每一步都要能跳到处理它的工作区"


def test_export_readiness_changes_after_real_outline_and_confirm(tmp_path: Path) -> None:
    """state A → 真实锻造 + 确认 → state B：导出就绪度必须真实变化。"""

    client, novel_id = _started(tmp_path, "novel_v3_p5_state")
    before = command_center(tmp_path, novel_id)["export"]
    assert before["ready"] is False

    forged = client.post(f"/api/story-builder/outline/forge?novel_id={novel_id}",
                         json={"branch_id": "main", "volumes": 1, "arcs_per_volume": 1,
                               "chapters_per_arc": 2})
    assert forged.status_code == 200, forged.text
    confirmed = client.post(f"/api/story-builder/outline/confirm?novel_id={novel_id}",
                            json={"branch_id": "main"})
    assert confirmed.status_code == 200, confirmed.text

    after = command_center(tmp_path, novel_id)["export"]
    assert after["chapter_count"] > 0
    assert after["missing"] != before["missing"], "缺失步骤必须真实减少"
    assert len(after["missing"]) < len(before["missing"]), (
        f"确认大纲后缺失步骤必须减少：{before['missing']} → {after['missing']}")
    assert after["chapter_count"] > before["chapter_count"]
    assert after["bundle"], "导出必须说明会导出什么"
