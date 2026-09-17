"""V3 章节投影回归。

章节不是新的 Domain：它是既有 outline chain（book → volumes → arcs → chapters）
的只读投影。这些用例守卫三件事：

* 章级包（level=CHAPTER）的 items 才是真实章节，必须被摊平成有序列表；
* 投影只暴露作者可读字段，不泄漏内部 enum / provenance；
* 没有章纲时必须是明确的空结果（而不是错误或占位数字）。
"""

from __future__ import annotations

from novelforge.story_builder.models import (
    OutlineItem,
    OutlineLevel,
    OutlinePackage,
    OutlineStatus,
)
from novelforge.story_builder.v3_projection import _chapter_rows, _outline_view


def _item(item_id: str, title: str, summary: str = "本章目的") -> OutlineItem:
    return OutlineItem(item_id=item_id, title=title, summary=summary)


def _package(package_id: str, level: OutlineLevel, items: list[OutlineItem], *,
             parent: str = "", status: OutlineStatus = OutlineStatus.DRAFT,
             version: int = 1) -> OutlinePackage:
    return OutlinePackage(
        package_id=package_id,
        project_id="novel_chapter_projection",
        blueprint_id="bp_chapter_projection",
        blueprint_version=1,
        level=level,
        status=status,
        version=version,
        parent_package_id=parent or None,
        items=items,
    )


def _chain() -> dict:
    book = _package("ol_book_1", OutlineLevel.BOOK, [_item("book_1", "全书主线")])
    volume = _package("ol_vol_1", OutlineLevel.VOLUME, [_item("vol_1", "第一卷")],
                      parent=book.package_id)
    arc = _package("ol_arc_1", OutlineLevel.ARC, [_item("arc_1", "第一篇")],
                   parent=volume.package_id)
    chapter_a = _package("ol_ch_a", OutlineLevel.CHAPTER,
                         [_item("ch_1", "雨里的伞"), _item("ch_2", "第二次重写")],
                         parent=arc.package_id)
    chapter_b = _package("ol_ch_b", OutlineLevel.CHAPTER, [_item("ch_3", "雨的源头")],
                         parent=arc.package_id)
    return {"book": book, "volumes": [volume], "arcs": [arc],
            "chapters": [chapter_a, chapter_b], "error": ""}


def test_chapter_rows_flatten_chapter_packages_in_order() -> None:
    rows = _chapter_rows(_chain())

    assert [row["title"] for row in rows] == ["雨里的伞", "第二次重写", "雨的源头"]
    assert [row["order"] for row in rows] == [1, 2, 3]
    assert [row["item_id"] for row in rows] == ["ch_1", "ch_2", "ch_3"]
    # 章节必须能追溯到它所属的章级包（编辑入口需要它）。
    assert rows[0]["package_id"] == "ol_ch_a"
    assert rows[2]["package_id"] == "ol_ch_b"
    assert rows[0]["parent_package_id"] == "ol_arc_1"


def test_outline_view_exposes_author_readable_layers() -> None:
    view = _outline_view(_chain())

    assert view["started"] is True
    assert view["chapter_count"] == 3
    assert len(view["chapters"]) == 3
    assert view["book"]["title"] == "全书主线"
    assert [row["title"] for row in view["volumes"]] == ["第一卷"]
    assert [row["title"] for row in view["arcs"]] == ["第一篇"]
    assert len(view["chapter_packages"]) == 2
    # 只读投影：不把内部 provenance / 蓝图字段暴露给 UI。
    assert "blueprint_id" not in view["book"]
    assert "route_source" not in view["chapters"][0]
    # 状态是可读 enum 值，不是内部对象。
    assert view["chapters"][0]["status"] == "DRAFT"
    assert view["chapters"][0]["confirmed"] is False


def test_confirmed_chapter_package_marks_chapters_confirmed() -> None:
    chain = _chain()
    chain["chapters"][0] = chain["chapters"][0].model_copy(
        update={"status": OutlineStatus.CONFIRMED})

    rows = _chapter_rows(chain)

    assert [row["confirmed"] for row in rows] == [True, True, False]


def test_outline_view_is_empty_result_when_no_chain() -> None:
    view = _outline_view({"book": None, "volumes": [], "arcs": [], "chapters": [],
                          "error": ""})

    assert view["started"] is False
    assert view["chapter_count"] == 0
    assert view["chapters"] == []
    assert view["book"] is None


# --------------------------------------------------- V3-P4 Outline & Chapter Workspace
def test_outline_view_reports_real_structure_and_gaps() -> None:
    """P4：结构必须来自真实层级；缺口只描述真实缺失，不造进度数字。"""

    view = _outline_view(_chain())
    # 草稿层级 = 全书 + 1 卷 + 1 篇章 + 2 章级包 = 5 个真实存在的草稿层。
    assert view["gaps"] == ["5 个大纲层级还是草稿：确认后才算这本书的正式结构。"]
    assert view["warnings"] == []
    assert view["stale"] is False


def test_outline_view_reports_missing_levels() -> None:
    book = _package("ol_book_1", OutlineLevel.BOOK, [_item("book_1", "全书主线")])
    view = _outline_view({"book": book, "volumes": [], "arcs": [], "chapters": [],
                          "error": ""})

    assert view["started"] is True
    assert any("卷纲" in row for row in view["gaps"])
    assert any("篇章纲" in row for row in view["gaps"])
    assert any("详细章纲" in row for row in view["gaps"])


def test_outline_view_surfaces_stale_and_pending_questions() -> None:
    """故事推进过 → 大纲过期必须是显式警告，而不是静默沿用旧结构。"""

    chain = _chain()
    chain["fresh"] = False
    chain["book"] = chain["book"].model_copy(update={
        "pending_questions": ["NO_HAPPENED_CHAPTERS: 还没有任何已发生事实"]})
    view = _outline_view(chain)

    assert view["stale"] is True
    codes = {row["code"] for row in view["warnings"]}
    assert "NO_HAPPENED_CHAPTERS" in codes
    assert "OUTLINE_STALE" in codes
    assert all(row["message"] and ":" not in row["code"] for row in view["warnings"])


def test_chapter_rows_use_real_character_names_for_participants() -> None:
    """章节参与者必须是作者可读的角色名，而不是引擎角色 id。"""

    chain = _chain()
    chapters = chain["chapters"][0]
    chapters.items[0].participants = ["protagonist", "npc_1"]
    rows = _chapter_rows(chain, {"protagonist": "普通执行者", "npc_1": "同行者"})

    assert rows[0]["participants"] == ["普通执行者", "同行者"]
    # 未登记的 id 保留原文（宁可不翻译，也不编造名字）。
    assert rows[0]["arc_title"] == "第一篇"


def test_chapter_rows_translate_engine_ids_in_narrative_text() -> None:
    """大纲原文里的行动 / 事件 id 必须翻成作者语言（P4 作者语言要求）。"""

    chain = _chain()
    item = chain["chapters"][0].items[0]
    item.summary = "已发生：act_ask（这本小说的前提：一个修伞匠的雨）"
    item.goals = ["完成 act_ask"]
    item.ending_hook = "下一章：act_investigate"
    labels = {"act_ask": "向身边人打听", "act_investigate": "查证记录"}

    rows = _chapter_rows(chain, labels)

    assert "act_ask" not in rows[0]["summary"]
    assert "向身边人打听" in rows[0]["summary"]
    assert rows[0]["goals"] == ["完成 向身边人打听"]
    assert rows[0]["ending_hook"] == "下一章：查证记录"
