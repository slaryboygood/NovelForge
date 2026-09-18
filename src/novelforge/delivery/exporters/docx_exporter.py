"""DOCX exporter（V4-07 §34、§57）：Story Blueprint Document。

数据结构来自 `DeliverySnapshot` / `BlueprintCompiler`（不是 legacy outline 路径）；
这里独立实现最小 OOXML 写出（思路 ADAPT 自 `story_engine/outline_revision.docx_bytes`，
但不复用其数据源，也不依赖 outline 模块）。

不输出内部 metadata（§30）；不使用任何第三方依赖。
"""

from __future__ import annotations

import io
import zipfile
from typing import Any, Iterable, Mapping, Sequence
from xml.sax.saxutils import escape

from . import ExporterRegistry, ExporterSpec
from .markdown_exporter import FIELD_LABELS, SECTION_TITLES, _fmt, _node_title

EXPORTER_ID = "delivery.docx.v1"
EXPORTER_VERSION = 1

#: ZIP 内固定时间戳 → OOXML 产物 deterministic（§42）
_FIXED_DATE = (1980, 1, 1, 0, 0, 0)


def _paragraph(style: str, text: str) -> str:
    runs = ('<w:rPr><w:b/><w:sz w:val="32"/></w:rPr>' if style == "title"
            else '<w:rPr><w:b/></w:rPr>' if style == "heading" else "")
    return (f'<w:p><w:pPr><w:spacing w:after="120"/></w:pPr>'
            f'<w:r>{runs}<w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>')


def paragraphs_for(context: Mapping[str, Any]
                   ) -> list[tuple[str, str]]:
    """把交付表示编译成 (style, text) 段落（visible 内容 only）。"""

    blueprint = dict(context.get("blueprint") or {})
    nodes = [dict(row) for row in (blueprint.get("nodes") or [])]
    title = str(context.get("title") or context.get("novel_id") or "Story Blueprint")
    rows: list[tuple[str, str]] = [("title", f"{title} 故事蓝图")]
    for node_type, section_title in SECTION_TITLES:
        section_nodes = [row for row in nodes if str(row.get("node_type")) == node_type]
        if not section_nodes:
            continue
        rows.append(("heading", section_title))
        for row in section_nodes:
            visible = dict(row.get("visible") or {})
            rows.append(("heading", _node_title(row)))
            for field, value in visible.items():
                if field in ("title", "name", "premise", "theme", "result") and \
                        str(value).strip() == _node_title(row):
                    continue
                if value in ("", [], {}, None):
                    continue
                rows.append(("text", f"{FIELD_LABELS.get(field, field)}：{_fmt(value)}"))
    return rows


def docx_bytes(paragraphs: Sequence[tuple[str, str]]) -> bytes:
    """写出最小但合法的 OOXML 文档（zip + document.xml），产物 deterministic。"""

    body = "".join(_paragraph(style, text) for style, text in paragraphs)
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f'<w:body>{body}<w:sectPr/></w:body></w:document>')
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '</Types>')
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/></Relationships>')
    document_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>')
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, payload in (("[Content_Types].xml", content_types),
                              ("_rels/.rels", rels),
                              ("word/document.xml", document),
                              ("word/_rels/document.xml.rels", document_rels)):
            info = zipfile.ZipInfo(name, date_time=_FIXED_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, payload.encode("utf-8"))
    return buffer.getvalue()


def export(context: Mapping[str, Any]) -> bytes:
    return docx_bytes(paragraphs_for(context))


def register(registry: ExporterRegistry) -> ExporterSpec:
    return registry.register(ExporterSpec(
        format="docx", exporter_id=EXPORTER_ID, version=EXPORTER_VERSION,
        mime_type="application/vnd.openxmlformats-officedocument."
                  "wordprocessingml.document",
        extension="docx", text=False,
        description="Story Blueprint document（DOCX，非小说正文）"), export)


__all__ = ["EXPORTER_ID", "EXPORTER_VERSION", "docx_bytes", "export",
           "paragraphs_for", "register"]
