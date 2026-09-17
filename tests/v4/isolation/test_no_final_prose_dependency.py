"""永久守卫：不再依赖旧正文（V4-01，作者决策 A + ADR-011）。

断言：

1. `novel/final/**` 已删除且没有产品引用；
2. 产品链路在旧正文缺席时完全可用（作品创建 → 投影 → 导出）；
3. `WriterContextBuilder` 不再包含 historical_repair 上下文块，
   也不再回退到历史 writer 目录（正文 draft 仅 preview）。
"""

from __future__ import annotations

from pathlib import Path

from _guard_utils import ROOT, python_files, string_literals, write_minimal_novel


def test_final_prose_is_deleted_and_unreferenced() -> None:
    assert not (ROOT / "novel" / "final").exists(), "旧正文目录已删除"
    offenders: list[str] = []
    for path in python_files("api", "application", "story_builder", "persistence",
                             "core", "legacy"):
        for value, line in string_literals(path):
            if value.strip().strip("`").replace("\\", "/").startswith("novel/final"):
                offenders.append(f"{path.relative_to(ROOT)}:{line} → {value!r}")
    assert offenders == [], (
        "产品侧模块不得把已删除的旧正文当作路径使用：\n" + "\n".join(offenders))


def test_writer_context_has_no_historical_block(tmp_path: Path) -> None:
    write_minimal_novel(tmp_path, "novel_ctx_only", title="上下文测试")
    from novelforge.story_builder.writer_integration import (
        TRUTH_BLOCKS,
        WriterContextBuilder,
    )

    block_ids = [row[0] for row in TRUTH_BLOCKS]
    assert "historical_repair" not in block_ids

    context = WriterContextBuilder(tmp_path, "novel_ctx_only").build()
    assert context["validation"]["status"] == "PASS"
    assert context["validation"]["checks"]["required_blocks_present"] is True
    assert all(row["block_id"] != "historical_repair" for row in context["blocks"])
    assert "historical_repair" not in context["truth_layer_legend"]


def test_writer_drafts_do_not_fall_back_to_legacy_dir(tmp_path: Path) -> None:
    from novelforge.story_builder.writer_integration import WriterDraftService

    novel_id = "novel_no_legacy"
    legacy = tmp_path / "workspace" / "wasteland_001_exports" / "writer_v1" / novel_id
    (legacy / "drafts").mkdir(parents=True, exist_ok=True)
    (legacy / "drafts" / "draft_old.json").write_text(
        '{"draft_id": "draft_old", "generated_at": "2026-01-01T00:00:00+00:00"}',
        encoding="utf-8")

    assert WriterDraftService(tmp_path, novel_id).list_drafts() == []


def test_pipeline_works_without_prose(tmp_path: Path) -> None:
    write_minimal_novel(tmp_path, "novel_no_prose", title="无正文作品")
    from novelforge.application.services import JourneyService

    projection = JourneyService(tmp_path, "novel_no_prose").projection()
    assert projection["journey"]["current_stage"]
    assert projection["profile"].novel_id == "novel_no_prose"
