"""V4-07 §26–§31、§34、§42、§49、§55–§57：compiler 与 JSON / Markdown / DOCX。"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from novelforge.application.services import ExportService
from novelforge.delivery import (
    NODE_TYPE_ORDER,
    VISIBLE_FIELDS,
    DeliveryRequest,
)
from novelforge.delivery.exporters import markdown_exporter
from novelforge.delivery.exporters.docx_exporter import paragraphs_for

from delivery_support import delivery_stack


def _deliver(stack: dict, formats: tuple[str, ...], **kwargs) -> dict:
    selection = ExportService(stack["root"], stack["novel_id"]).delivery_selection(
        formats=formats, **kwargs)
    result = stack["delivery"].deliver(DeliveryRequest(selection=selection))
    assert result.status == "delivered", result.notes
    return {artifact.format: artifact for artifact in result.artifacts}


def test_compiler_orders_deterministically(tmp_path: Path) -> None:
    stack = delivery_stack(tmp_path)
    selection = ExportService(tmp_path, stack["novel_id"]).delivery_selection(
        formats=("json",))
    outcome = stack["delivery"].selector.select(selection)
    compiled = stack["delivery"].compiler.compile(outcome.selected)
    ranks = [NODE_TYPE_ORDER.index(node.node_type) for node in compiled.nodes]
    assert ranks == sorted(ranks)                     # type 顺序唯一（§27）
    scenes = [node.node_id for node in compiled.by_type("scene")]
    assert scenes == sorted(scenes)
    again = stack["delivery"].compiler.compile(dict(reversed(
        list(outcome.selected.items()))))
    assert [node.node_id for node in again.nodes] == \
        [node.node_id for node in compiled.nodes]
    assert again.digest == compiled.digest


def test_every_node_type_has_visible_fields() -> None:
    for node_type in NODE_TYPE_ORDER:
        assert node_type in VISIBLE_FIELDS
        assert VISIBLE_FIELDS[node_type]


def test_json_export_is_versioned_and_revision_pinned(tmp_path: Path) -> None:
    stack = delivery_stack(tmp_path)
    artifacts = _deliver(stack, ("json",))
    document = json.loads(artifacts["json"].content.decode("utf-8"))
    assert document["schema"]["delivery_schema_version"] == 1
    assert document["schema"]["exporter_id"] == "delivery.json.v1"
    assert document["schema"]["blueprint_schema_version"] >= 1
    assert document["novel"]["novel_id"] == stack["novel_id"]
    assert document["manifest"]["selected_revisions"] == \
        document["blueprint"]["node_revisions"]
    assert document["blueprint"]["ordering"] == list(NODE_TYPE_ORDER)
    pinned = {str(node["node_id"]): int(node["revision"])
              for node in document["blueprint"]["nodes"]}
    assert pinned == {str(key): int(value) for key, value
                      in document["blueprint"]["node_revisions"].items()}
    assert document["quality_summary"]["nodes"] == len(pinned)
    # round-trip readability（§55）
    assert json.loads(json.dumps(document, ensure_ascii=False))["novel"]["snapshot_id"]


def test_json_is_reproducible(tmp_path: Path) -> None:
    """§42 / §79：同 snapshot + policy + exporter version → 同内容。"""

    stack = delivery_stack(tmp_path)
    first = _deliver(stack, ("json",))["json"]
    second = _deliver(stack, ("json",))["json"]
    assert first.checksum == second.checksum
    assert first.content == second.content


def test_markdown_has_sections_and_no_internal_metadata(tmp_path: Path) -> None:
    stack = delivery_stack(tmp_path)
    artifact = _deliver(stack, ("markdown",), profile="reader")["markdown"]
    text = artifact.content.decode("utf-8")
    for heading in ("# 阿尔法计划 故事蓝图", "## 故事前提", "## 章节", "## 场景",
                    "## 伏笔", "## 回收"):
        assert heading in text
    lowered = text.lower()
    for token in markdown_exporter.FORBIDDEN_TOKENS:
        assert token.lower() not in lowered, token
    assert "provider" not in lowered and "digest" not in lowered
    # 章节在场景之前（确定性顺序）
    assert text.index("## 章节") < text.index("## 场景")


def test_markdown_does_not_leak_node_ids(tmp_path: Path) -> None:
    stack = delivery_stack(tmp_path)
    artifact = _deliver(stack, ("markdown",), profile="author")["markdown"]
    text = artifact.content.decode("utf-8")
    for node in stack["repository"].all_nodes():
        assert node.node_id not in text


def test_docx_is_valid_ooxml_and_hides_internal_metadata(tmp_path: Path) -> None:
    stack = delivery_stack(tmp_path)
    artifact = _deliver(stack, ("docx",), profile="author")["docx"]
    assert artifact.text is False and artifact.size > 0
    with zipfile.ZipFile(io.BytesIO(artifact.content)) as archive:
        names = archive.namelist()
        assert "word/document.xml" in names and "_rels/.rels" in names
        xml = archive.read("word/document.xml").decode("utf-8")
    assert "故事前提" in xml and "章节" in xml
    for token in ("request_id", "context_digest", "provider", "generation_contract"):
        assert token not in xml
    for node in stack["repository"].all_nodes():
        assert node.node_id not in xml


def test_docx_is_deterministic(tmp_path: Path) -> None:
    stack = delivery_stack(tmp_path)
    first = _deliver(stack, ("docx",))["docx"]
    second = _deliver(stack, ("docx",))["docx"]
    assert first.content == second.content
    assert first.checksum == second.checksum


def test_export_makes_no_model_calls(tmp_path: Path) -> None:
    """§49：交付 0 次 LLM 调用（stub provider 计数不变）。"""

    stack = delivery_stack(tmp_path)
    calls_before = stack["provider"].calls
    _deliver(stack, ("json", "markdown", "docx", "nfpack"))
    assert stack["provider"].calls == calls_before


def test_visible_internal_separation_in_compiled_nodes(tmp_path: Path) -> None:
    stack = delivery_stack(tmp_path)
    selection = ExportService(tmp_path, stack["novel_id"]).delivery_selection(
        formats=("json",))
    outcome = stack["delivery"].selector.select(selection)
    compiled = stack["delivery"].compiler.compile(outcome.selected)
    chapter = compiled.by_type("chapter")[0]
    assert "title" in chapter.visible and "goal" in chapter.visible
    assert "characters" not in chapter.visible        # 结构字段不进 visible
    assert "characters" in chapter.payload            # 内部分支仍在
    row = chapter.as_dict(include_internal=False)
    assert "parent_id" not in row and "provenance" not in row
