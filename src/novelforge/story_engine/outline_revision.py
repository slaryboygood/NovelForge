"""W4：大纲修改联动、版本比较与导出扩展。

规则（沿用既有约束，不新造状态）：

- **历史不可改写**：已确认版本不能被覆盖（`StoryOutlineRepository` 保证），已发生事实来自 StoryState，
  章纲编辑只能改写作设计字段，不能改来源；
- **改上层提示下层**：改全书 / 卷目标后，受影响的下游包会被列出（父链遍历），需要作者决定是否重新锻造；
- **版本只追加**：回退 / 合并都会生成新版本，旧版本继续可读；
- **导出**：Markdown（已有）、结构化 JSON、最小 DOCX（无第三方依赖）。
"""

from __future__ import annotations

import base64
import io
import json
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from pydantic import Field

from novelforge.models import StrictModel
from novelforge.story_builder.models import (
    OutlineItem,
    OutlineLevel,
    OutlinePackage,
    OutlineStatus,
)
from novelforge.story_builder.outlines import StoryOutlineError, StoryOutlineRepository

from .outline_forge import (
    _chain_prefix,
    _latest_by_prefix,
    _strip_source_prefix,
    export_forge_markdown,
    load_forge_chain,
    naming_table,
)
from .creator import resolve_creator_context

LEVEL_ORDER = (OutlineLevel.BOOK, OutlineLevel.VOLUME, OutlineLevel.ARC, OutlineLevel.CHAPTER)
EDITABLE_FIELDS = ("title", "summary", "start_state", "end_state", "ending_hook", "goals",
                   "conflicts", "major_turns", "pov", "time", "location", "participants",
                   "information_changes", "costs")


class RevisionError(ValueError):
    def __init__(self, code: str, message: str, *, target: str = "") -> None:
        self.code = code
        self.message = message
        self.target = target
        super().__init__(message)

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message, "target": self.target}


class VersionRow(StrictModel):
    version: int
    status: str
    confirmed_by_author: bool = False
    item_count: int = 0
    item_titles: list[str] = Field(default_factory=list)
    route_digest: str = ""
    created_at: str = ""


class ItemDiff(StrictModel):
    item_id: str
    status: str
    changed_fields: list[str] = Field(default_factory=list)
    before: dict[str, Any] = Field(default_factory=dict)
    after: dict[str, Any] = Field(default_factory=dict)


class VersionDiff(StrictModel):
    package_id: str
    level: str
    from_version: int
    to_version: int
    items: list[ItemDiff] = Field(default_factory=list)
    added: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def _item_kind(item: OutlineItem) -> str:
    """这一条大纲是「已发生」还是「规划」。

    NF-004：来源 id 已经移出作者可见文本、进入 `source_ids`，所以这里优先读结构化
    来源；旧包（没有 source_ids）继续按原有文本特征判断，保持 legacy 兼容。
    """

    refs = [str(value) for value in item.source_ids]
    if any(value.startswith(("planned_", "suggested_")) for value in refs):
        return "planned"
    if any(value.startswith(("route_", "plot_")) for value in refs):
        return "happened"
    joined = " ".join(item.must_keep + item.must_avoid)
    if "future_plan" in joined or "尚未发生" in joined or "还没发生" in joined:
        return "planned"
    if "（happened）" in joined or "route_" in joined:
        return "happened"
    return "outline"


def list_versions(project_root: Path, novel_id: str, package_id: str) -> dict[str, Any]:
    repository = StoryOutlineRepository(project_root)
    folder = None
    for level in LEVEL_ORDER:
        candidate = repository.outlines_dir / level.value.lower() / package_id
        if candidate.is_dir():
            folder = (level, candidate)
            break
    if folder is None:
        raise RevisionError("OUTLINE_NOT_FOUND", "找不到这个大纲包", target=package_id)
    level, path = folder
    rows: list[VersionRow] = []
    for item in sorted(path.glob("v*.json")):
        version = int(item.stem[1:])
        package = repository.load(package_id, version)
        rows.append(VersionRow(
            version=version, status=package.status.value,
            confirmed_by_author=package.confirmed_by_author,
            item_count=len(package.items),
            item_titles=[entry.title for entry in package.items][:6],
            route_digest=package.route_source.get("digest", ""),
            created_at=package.created_at.isoformat()))
    return {"novel_id": novel_id, "package_id": package_id, "level": level.value,
            "versions": [row.model_dump(mode="json") for row in rows]}


def diff_versions(project_root: Path, novel_id: str, package_id: str, *,
                  from_version: int, to_version: int) -> VersionDiff:
    repository = StoryOutlineRepository(project_root)
    try:
        before = repository.load(package_id, from_version)
        after = repository.load(package_id, to_version)
    except StoryOutlineError as exc:
        raise RevisionError(exc.code, exc.message, target=package_id) from exc
    rows: list[ItemDiff] = []
    before_by_id = {item.item_id: item for item in before.items}
    after_by_id = {item.item_id: item for item in after.items}
    for item_id in sorted(set(before_by_id) | set(after_by_id)):
        old, new = before_by_id.get(item_id), after_by_id.get(item_id)
        if old is None and new is not None:
            rows.append(ItemDiff(item_id=item_id, status="added",
                                 after={"title": new.title}))
            continue
        if new is None and old is not None:
            rows.append(ItemDiff(item_id=item_id, status="removed",
                                 before={"title": old.title}))
            continue
        assert old is not None and new is not None
        changed = [field for field in EDITABLE_FIELDS
                   if getattr(old, field) != getattr(new, field)]
        if not changed:
            continue
        rows.append(ItemDiff(
            item_id=item_id, status="changed", changed_fields=changed,
            before={field: getattr(old, field) for field in changed},
            after={field: getattr(new, field) for field in changed}))
    return VersionDiff(package_id=package_id, level=before.level.value,
                       from_version=from_version, to_version=to_version, items=rows,
                       added=[row.item_id for row in rows if row.status == "added"],
                       removed=[row.item_id for row in rows if row.status == "removed"])


def downstream_packages(project_root: Path, novel_id: str, branch_id: str,
                        package_id: str) -> list[OutlinePackage]:
    """按父链找出所有下游包（全书 → 卷 → 篇章 → 章节）。"""

    repository = StoryOutlineRepository(project_root)
    prefix = _chain_prefix(novel_id, branch_id)
    all_rows: list[OutlinePackage] = []
    for level in LEVEL_ORDER:
        all_rows.extend(_latest_by_prefix(repository, level, prefix))
    children: dict[str, list[OutlinePackage]] = {}
    for row in all_rows:
        if row.parent_package_id:
            children.setdefault(row.parent_package_id, []).append(row)
    found: list[OutlinePackage] = []
    queue = list(children.get(package_id, []))
    seen: set[str] = set()
    while queue:
        current = queue.pop(0)
        if current.package_id in seen:
            continue
        seen.add(current.package_id)
        found.append(current)
        queue.extend(children.get(current.package_id, []))
    return found


def impact_of_change(project_root: Path, novel_id: str, *, branch_id: str,
                     package_id: str, item_id: str,
                     changes: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """改一个上层条目会影响哪些下游包；已发生事实只提示、不改写。"""

    repository = StoryOutlineRepository(project_root)
    level = None
    package = None
    for candidate_level in LEVEL_ORDER:
        try:
            package = repository.load(package_id, _latest_version(repository, candidate_level,
                                                                  package_id))
            level = candidate_level
            break
        except StoryOutlineError:
            continue
    if package is None or level is None:
        raise RevisionError("OUTLINE_NOT_FOUND", "找不到这个大纲包", target=package_id)
    item = next((row for row in package.items if row.item_id == item_id), None)
    if item is None:
        raise RevisionError("OUTLINE_ITEM_NOT_FOUND", "找不到这个大纲条目", target=item_id)
    affected = downstream_packages(project_root, novel_id, branch_id, package_id)
    happened: list[dict[str, str]] = []
    planned: list[dict[str, str]] = []
    for row in affected:
        for entry in row.items:
            kind = _item_kind(entry)
            record = {"package_id": row.package_id, "level": row.level.value,
                      "item_id": entry.item_id, "title": entry.title, "status": row.status.value}
            if kind == "happened":
                happened.append(record)
            else:
                planned.append({**record, "kind": kind})
    asked = {key: value for key, value in (changes or {}).items() if key in EDITABLE_FIELDS}
    protected = [key for key in (changes or {}) if key not in EDITABLE_FIELDS]
    return {"package_id": package_id, "level": level.value, "item_id": item_id,
            "item_kind": _item_kind(item), "changes": asked, "protected_fields": protected,
            "affected_downstream": [{"package_id": row.package_id, "level": row.level.value,
                                     "status": row.status.value, "items": len(row.items)}
                                    for row in affected],
            "affected_happened": happened, "affected_planned": planned,
            "note": "已发生事实不可改写；下游 planned 内容需要重新锻造才会更新"}


def _latest_version(repository: StoryOutlineRepository, level: OutlineLevel,
                    package_id: str) -> int:
    latest = repository.latest(level, package_id)
    if latest is None:
        raise StoryOutlineError("OUTLINE_NOT_FOUND", "找不到大纲包", package_id=package_id)
    return latest.version


def revise_item(project_root: Path, novel_id: str, *, branch_id: str, package_id: str,
                item_id: str, changes: Mapping[str, Any], expected_version: int) -> dict[str, Any]:
    """改写一个条目（只允许写作设计字段），并返回联动影响。"""

    invalid = [key for key in changes if key not in EDITABLE_FIELDS]
    if invalid:
        raise RevisionError("OUTLINE_FIELD_NOT_EDITABLE",
                            f"这些字段不属于写作设计，不能改：{'、'.join(invalid)}",
                            target=package_id)
    repository = StoryOutlineRepository(project_root)
    level = None
    for candidate_level in LEVEL_ORDER:
        try:
            _latest_version(repository, candidate_level, package_id)
            level = candidate_level
            break
        except StoryOutlineError:
            continue
    if level is None:
        raise RevisionError("OUTLINE_NOT_FOUND", "找不到这个大纲包", target=package_id)
    package = repository.load(package_id, expected_version)
    if package.status == OutlineStatus.NEEDS_REVIEW:
        raise RevisionError("OUTLINE_SOURCE_STALE", "来源已变化，请先重新锻造再改写",
                            target=package_id)
    impact = impact_of_change(project_root, novel_id, branch_id=branch_id,
                              package_id=package_id, item_id=item_id, changes=changes)
    items = [OutlineItem.model_validate({**row.model_dump(), **dict(changes)})
             if row.item_id == item_id else row for row in package.items]
    updated = package.model_copy(update={
        "items": items, "version": package.version + 1, "status": OutlineStatus.DRAFT,
        "confirmed_by_author": False})
    saved = repository.save(updated)
    return {"outline": saved.model_dump(mode="json"), "impact": impact}


def restore_version(project_root: Path, novel_id: str, *, package_id: str,
                    version: int) -> dict[str, Any]:
    """回退：把旧版本内容写成一个新版本（历史版本继续保留）。"""

    repository = StoryOutlineRepository(project_root)
    level = None
    for candidate_level in LEVEL_ORDER:
        try:
            _latest_version(repository, candidate_level, package_id)
            level = candidate_level
            break
        except StoryOutlineError:
            continue
    if level is None:
        raise RevisionError("OUTLINE_NOT_FOUND", "找不到这个大纲包", target=package_id)
    source = repository.load(package_id, version)
    latest = repository.load(package_id, _latest_version(repository, level, package_id))
    restored = source.model_copy(update={
        "version": latest.version + 1, "status": OutlineStatus.DRAFT,
        "confirmed_by_author": False,
        "pending_questions": list(source.pending_questions) + [f"由 V{version} 回退生成"]})
    return {"outline": repository.save(restored).model_dump(mode="json"),
            "restored_from": version}


def merge_versions(project_root: Path, novel_id: str, *, package_id: str,
                   base_version: int, source_version: int,
                   item_ids: Sequence[str] | None = None) -> dict[str, Any]:
    """把 source 版本里被选中的条目合并到 base 版本的新副本上（只追加版本）。"""

    repository = StoryOutlineRepository(project_root)
    level = None
    for candidate_level in LEVEL_ORDER:
        try:
            _latest_version(repository, candidate_level, package_id)
            level = candidate_level
            break
        except StoryOutlineError:
            continue
    if level is None:
        raise RevisionError("OUTLINE_NOT_FOUND", "找不到这个大纲包", target=package_id)
    base = repository.load(package_id, base_version)
    source = repository.load(package_id, source_version)
    wanted = set(item_ids or [])
    source_by_id = {row.item_id: row for row in source.items}
    merged_items: list[OutlineItem] = []
    applied: list[str] = []
    for row in base.items:
        replacement = source_by_id.get(row.item_id)
        if replacement is not None and (not wanted or row.item_id in wanted):
            merged_items.append(replacement)
            applied.append(row.item_id)
        else:
            merged_items.append(row)
    latest = repository.load(package_id, _latest_version(repository, level, package_id))
    merged = base.model_copy(update={
        "version": latest.version + 1, "status": OutlineStatus.DRAFT,
        "confirmed_by_author": False, "items": merged_items,
        "pending_questions": list(base.pending_questions) + [
            f"由 V{source_version} 合并 {len(applied)} 个条目"]})
    return {"outline": repository.save(merged).model_dump(mode="json"),
            "merged_items": applied, "from_version": source_version,
            "base_version": base_version}


def export_structured_json(project_root: Path, novel_id: str, *,
                           branch_id: str = "main") -> dict[str, Any]:
    """结构化 JSON 导出：四级大纲 + 路线来源 + 质量报告（供外部工具消费）。"""

    chain = load_forge_chain(project_root, novel_id, branch_id=branch_id)
    if chain["book"] is None:
        raise RevisionError("OUTLINE_NOT_FOUND", "这本小说还没有锻造过大纲")

    # NF-004：导出物里的作者可见字段必须是作者语言。participants 在领域模型里是
    # 角色 id（writing / 校验需要），导出时翻成角色名；item_id / source_ids 属于
    # artifact identity 与可追溯性字段，保留原样（它们不是「内容」）。
    labels = {}
    try:
        context = resolve_creator_context(project_root, novel_id)
        labels = naming_table(context.state, context.pack)
    except Exception:  # noqa: BLE001 - 名称表不可用时保留领域值，不阻断导出
        labels = {}

    def item_payload(item: OutlineItem) -> dict[str, Any]:
        payload = item.model_dump(mode="json")
        payload["participants"] = [labels.get(str(entry), str(entry))
                                   for entry in item.participants]
        return payload

    payload = {
        "novel_id": novel_id,
        "branch_id": branch_id,
        "fresh": chain["fresh"],
        "quality": chain["quality"],
        "levels": {
            "book": [item_payload(item) for item in chain["book"].items],
            "volume": [item_payload(item) for package in chain["volumes"]
                       for item in package.items],
            "arc": [item_payload(item) for package in chain["arcs"]
                    for item in package.items],
            "chapter": [item_payload(item) for package in chain["chapters"]
                        for item in package.items],
        },
        "packages": {
            "book": chain["book"].package_id,
            "volumes": [package.package_id for package in chain["volumes"]],
            "arcs": [package.package_id for package in chain["arcs"]],
            "chapters": [package.package_id for package in chain["chapters"]],
        },
        "route_source": dict(chain["book"].route_source),
    }
    return {"filename": f"剧情与大纲_{novel_id}_{branch_id}.json",
            "content": json.dumps(payload, ensure_ascii=False, indent=2)}


def export_docx(project_root: Path, novel_id: str, *, branch_id: str = "main") -> dict[str, Any]:
    """最小 DOCX 导出（无第三方依赖）：标题 + 段落，正文来自四级大纲条目。"""

    chain = load_forge_chain(project_root, novel_id, branch_id=branch_id)
    if chain["book"] is None:
        raise RevisionError("OUTLINE_NOT_FOUND", "这本小说还没有锻造过大纲")
    paragraphs: list[tuple[str, str]] = [("title", f"{chain['book'].design_sections.get('novel', novel_id)} 剧情与大纲")]
    paragraphs.append(("text", f"路线：{branch_id}；结构："
                               f"{chain['book'].design_sections.get('structure', '')}"))
    for package in [chain["book"], *chain["volumes"], *chain["arcs"], *chain["chapters"]]:
        for item in package.items:
            paragraphs.append(("heading", item.title))
            paragraphs.append(("text", item.summary))
            rows = [("目标", "；".join(item.goals)), ("核心冲突", "；".join(item.conflicts)),
                    ("转折", "；".join(item.major_turns)),
                    ("信息释放", "；".join(item.information_changes)),
                    ("代价 / 关系变化", "；".join(item.costs)),
                    ("结尾钩子", item.ending_hook),
                    ("来源", "；".join(_strip_source_prefix(row) for row in item.must_keep)),
                    ("不得违反", "；".join(item.must_avoid))]
            for label, value in rows:
                if value:
                    paragraphs.append(("text", f"{label}：{value}"))
    content = _docx_bytes(paragraphs)
    return {"filename": f"剧情与大纲_{novel_id}_{branch_id}.docx", "content": content}


def docx_bytes(paragraphs: Sequence[tuple[str, str]]) -> bytes:
    """写出一个最小但合法的 OOXML 文档（zip + document.xml）。"""

    body: list[str] = []
    for style, text in paragraphs:
        runs = (f'<w:rPr><w:b/><w:sz w:val="32"/></w:rPr>' if style == "title"
                else '<w:rPr><w:b/></w:rPr>' if style == "heading" else "")
        body.append(f'<w:p><w:pPr><w:spacing w:after="120"/></w:pPr>'
                    f'<w:r>{runs}<w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>')
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f'<w:body>{"".join(body)}<w:sectPr/></w:body></w:document>')
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '</Types>')
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        '</Relationships>')
    document_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>')
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("word/document.xml", document)
        archive.writestr("word/_rels/document.xml.rels", document_rels)
    return buffer.getvalue()


# 兼容旧调用点（M16 起作为共享 serializer 使用公开名）。
_docx_bytes = docx_bytes


def export_outline(project_root: Path, novel_id: str, *, branch_id: str = "main",
                   fmt: str = "markdown") -> dict[str, Any]:
    """统一导出入口：markdown / json / docx。"""

    normalized = (fmt or "markdown").lower()
    if normalized in ("markdown", "md"):
        rows = export_forge_markdown(project_root, novel_id, branch_id=branch_id)
        return {**rows, "format": "markdown"}
    if normalized == "json":
        return {**export_structured_json(project_root, novel_id, branch_id=branch_id),
                "format": "json"}
    if normalized == "docx":
        rows = export_docx(project_root, novel_id, branch_id=branch_id)
        return {"filename": rows["filename"], "format": "docx",
                "content_base64": base64.b64encode(rows["content"]).decode("ascii"),
                "size": len(rows["content"])}
    raise RevisionError("OUTLINE_EXPORT_FORMAT_UNSUPPORTED", f"不支持的导出格式：{fmt}")
