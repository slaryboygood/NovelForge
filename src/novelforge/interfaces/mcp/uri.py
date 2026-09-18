"""MCP Resource URI 规范（V4-08 §11–§13、§78）—— URI 的唯一 SSOT。

```text
novelforge://interface                       服务元数据（版本 / 工具表 / 资源表）
novelforge://novels/{novel_id}               作品摘要
novelforge://novels/{novel_id}/blueprint     有序 Blueprint（分页）
novelforge://novels/{novel_id}/blueprint/nodes/{node_id}
novelforge://novels/{novel_id}/blueprint/nodes/{node_id}/revisions/{revision}
novelforge://novels/{novel_id}/scenes        场景列表（分页）
novelforge://novels/{novel_id}/quality       质量摘要
novelforge://novels/{novel_id}/quality/issues 质量 issue 列表（分页）
novelforge://novels/{novel_id}/review        编辑 / 评审摘要
novelforge://novels/{novel_id}/delivery      交付快照列表
novelforge://novels/{novel_id}/delivery/{snapshot_id}
novelforge://novels/{novel_id}/delivery/{snapshot_id}/manifest
novelforge://novels/{novel_id}/delivery/{snapshot_id}/artifacts/{artifact_path}

V4-09（additive，插件扩展点）：

novelforge://plugins/{plugin_id}/{path}    插件资源（kind = plugin_resource:<plugin_id>）
```

查询参数：`limit` / `cursor`（分页）、`mode`（current | accepted）。
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass, field
from typing import Any, Mapping
from urllib.parse import parse_qs, unquote, urlsplit

from .errors import MCPInvalidArgument, MCPResourceNotFound

SCHEME = "novelforge"

#: V4-09（additive）：插件资源 namespace（URI 形状的唯一 SSOT）
PLUGINS_HEAD = "plugins"
PLUGIN_RESOURCE_KIND_PREFIX = "plugin_resource:"

#: 分页上限（§47：不要一次返回整本大型作品的全部历史）
DEFAULT_LIMIT = 50
MAX_LIMIT = 200

_SEGMENT_KINDS: tuple[tuple[str, str], ...] = (
    ("novels", "novel"),
    ("blueprint", "blueprint"),
    ("nodes", "node"),
    ("revisions", "revision"),
    ("scenes", "scenes"),
    ("quality", "quality"),
    ("issues", "issues"),
    ("review", "review"),
    ("delivery", "delivery"),
    ("manifest", "manifest"),
    ("artifacts", "artifact"),
)


@dataclass(frozen=True)
class ResourceTarget:
    """解析后的资源目标（协议层形状，不含业务逻辑）。"""

    kind: str                                  # novel | blueprint | node | revision | ...
    novel_id: str = ""
    node_id: str = ""
    revision: int = 0
    snapshot_id: str = ""
    artifact_path: str = ""
    #: V4-09：插件资源（`novelforge://plugins/<plugin_id>/<path>`）
    plugin_id: str = ""
    resource_path: str = ""
    mode: str = "current"
    limit: int = DEFAULT_LIMIT
    cursor: int = 0
    uri: str = ""
    params: Mapping[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "novel_id": self.novel_id,
                "node_id": self.node_id, "revision": self.revision,
                "snapshot_id": self.snapshot_id,
                "artifact_path": self.artifact_path, "mode": self.mode,
                "plugin_id": self.plugin_id, "resource_path": self.resource_path,
                "limit": self.limit, "cursor": self.cursor, "uri": self.uri}


def encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(str(max(0, int(offset))).encode("ascii")).decode("ascii")


def decode_cursor(cursor: str) -> int:
    if not str(cursor or "").strip():
        return 0
    try:
        raw = base64.urlsafe_b64decode(str(cursor).encode("ascii")).decode("ascii")
        return max(0, int(raw))
    except (binascii.Error, ValueError, UnicodeDecodeError) as exc:
        raise MCPInvalidArgument("cursor 无法解析", details={"cursor": cursor}) from exc


def _query(params: Mapping[str, list[str] | str]) -> dict[str, str]:
    resolved: dict[str, str] = {}
    for key, value in params.items():
        resolved[str(key)] = value[0] if isinstance(value, list) and value else str(value)
    return resolved


def parse_uri(uri: str) -> ResourceTarget:
    """解析资源 URI → `ResourceTarget`（未知形状 → MCP_RESOURCE_NOT_FOUND）。"""

    text = str(uri or "").strip()
    parts = urlsplit(text)
    if parts.scheme != SCHEME or not parts.netloc:
        raise MCPResourceNotFound(f"未知资源 URI：{text}",
                                  details={"uri": text, "scheme": parts.scheme})
    segments = [unquote(segment) for segment in parts.path.split("/") if segment]
    query = _query(parse_qs(parts.query))
    limit = int(query.get("limit") or DEFAULT_LIMIT)
    if limit < 1 or limit > MAX_LIMIT:
        raise MCPInvalidArgument(f"limit 必须在 1..{MAX_LIMIT}",
                                 details={"limit": limit})
    mode = str(query.get("mode") or "current")
    if mode not in ("current", "accepted"):
        raise MCPInvalidArgument("mode 只支持 current / accepted",
                                 details={"mode": mode})
    cursor = decode_cursor(query.get("cursor", ""))
    base = {"uri": text, "mode": mode, "limit": limit, "cursor": cursor,
            "params": query}
    head = parts.netloc
    if head == "interface":
        return ResourceTarget(kind="interface", **base)
    if head == PLUGINS_HEAD:
        # V4-09：插件资源 namespace（`novelforge://plugins/<plugin_id>/<path>`）
        if len(segments) < 2:
            raise MCPResourceNotFound(f"未知插件资源 URI：{text}",
                                      details={"uri": text})
        plugin_id = segments[0]
        return ResourceTarget(kind=plugin_resource_kind(plugin_id),
                              plugin_id=plugin_id,
                              resource_path="/".join(segments[1:]), **base)
    if head != "novels" or not segments:
        raise MCPResourceNotFound(f"未知资源 URI：{text}", details={"uri": text})
    novel_id = segments[0]
    if len(segments) == 1:
        return ResourceTarget(kind="novel", novel_id=novel_id, **base)
    section = segments[1]
    if section == "blueprint":
        if len(segments) == 2:
            return ResourceTarget(kind="blueprint", novel_id=novel_id, **base)
        if segments[2] == "nodes" and len(segments) >= 4:
            node_id = segments[3]
            if len(segments) == 4:
                return ResourceTarget(kind="node", novel_id=novel_id,
                                      node_id=node_id, **base)
            if len(segments) == 6 and segments[4] == "revisions":
                return ResourceTarget(kind="revision", novel_id=novel_id,
                                      node_id=node_id,
                                      revision=int(segments[5]), **base)
        raise MCPResourceNotFound(f"未知资源 URI：{text}", details={"uri": text})
    if section == "scenes" and len(segments) == 2:
        return ResourceTarget(kind="scenes", novel_id=novel_id, **base)
    if section == "quality":
        if len(segments) == 2:
            return ResourceTarget(kind="quality", novel_id=novel_id, **base)
        if len(segments) == 3 and segments[2] == "issues":
            return ResourceTarget(kind="issues", novel_id=novel_id, **base)
        raise MCPResourceNotFound(f"未知资源 URI：{text}", details={"uri": text})
    if section == "review" and len(segments) == 2:
        return ResourceTarget(kind="review", novel_id=novel_id, **base)
    if section == "delivery":
        if len(segments) == 2:
            return ResourceTarget(kind="delivery", novel_id=novel_id, **base)
        snapshot_id = segments[2]
        if len(segments) == 3:
            return ResourceTarget(kind="delivery_snapshot", novel_id=novel_id,
                                  snapshot_id=snapshot_id, **base)
        if len(segments) == 4 and segments[3] == "manifest":
            return ResourceTarget(kind="manifest", novel_id=novel_id,
                                  snapshot_id=snapshot_id, **base)
        if len(segments) >= 5 and segments[3] == "artifacts":
            artifact_path = "/".join(segments[4:])
            return ResourceTarget(kind="artifact", novel_id=novel_id,
                                  snapshot_id=snapshot_id,
                                  artifact_path=artifact_path, **base)
        raise MCPResourceNotFound(f"未知资源 URI：{text}", details={"uri": text})
    raise MCPResourceNotFound(f"未知资源 URI：{text}", details={"uri": text})


def novel_uri(novel_id: str) -> str:
    return f"{SCHEME}://novels/{novel_id}"


def plugin_resource_kind(plugin_id: str) -> str:
    """插件资源 kind：按 plugin_id 区分，保证 resolve 精确命中（V4-09 §38–§42）。"""

    return f"{PLUGIN_RESOURCE_KIND_PREFIX}{plugin_id}"


def plugin_resource_uri(plugin_id: str, path: str) -> str:
    """插件资源 URI：`novelforge://plugins/<plugin_id>/<path>`（namespaced）。"""

    cleaned = str(path or "").split("://")[-1].strip("/")
    return f"{SCHEME}://{PLUGINS_HEAD}/{plugin_id}/{cleaned}"


def blueprint_uri(novel_id: str) -> str:
    return f"{novel_uri(novel_id)}/blueprint"


def node_uri(novel_id: str, node_id: str) -> str:
    return f"{blueprint_uri(novel_id)}/nodes/{node_id}"


def revision_uri(novel_id: str, node_id: str, revision: int) -> str:
    return f"{node_uri(novel_id, node_id)}/revisions/{int(revision)}"


def scenes_uri(novel_id: str) -> str:
    return f"{novel_uri(novel_id)}/scenes"


def quality_uri(novel_id: str) -> str:
    return f"{novel_uri(novel_id)}/quality"


def issues_uri(novel_id: str) -> str:
    return f"{quality_uri(novel_id)}/issues"


def review_uri(novel_id: str) -> str:
    return f"{novel_uri(novel_id)}/review"


def delivery_uri(novel_id: str) -> str:
    return f"{novel_uri(novel_id)}/delivery"


def manifest_uri(novel_id: str, snapshot_id: str) -> str:
    return f"{delivery_uri(novel_id)}/{snapshot_id}/manifest"


def artifact_uri(novel_id: str, snapshot_id: str, artifact_path: str) -> str:
    return f"{delivery_uri(novel_id)}/{snapshot_id}/artifacts/{artifact_path}"


def paginate(rows: list[Any], *, limit: int, cursor: int) -> dict[str, Any]:
    """通用分页（§47）：返回当前页 + next_cursor。"""

    start = max(0, int(cursor))
    page = rows[start:start + int(limit)]
    next_offset = start + len(page)
    return {"items": page, "count": len(page), "total": len(rows),
            "limit": int(limit), "offset": start,
            "next_cursor": encode_cursor(next_offset) if next_offset < len(rows) else "",
            "has_more": next_offset < len(rows)}


__all__ = [
    "DEFAULT_LIMIT", "MAX_LIMIT", "PLUGIN_RESOURCE_KIND_PREFIX", "PLUGINS_HEAD",
    "SCHEME", "ResourceTarget", "artifact_uri", "blueprint_uri", "decode_cursor",
    "delivery_uri", "encode_cursor", "issues_uri", "manifest_uri", "node_uri",
    "novel_uri", "paginate", "parse_uri", "plugin_resource_kind",
    "plugin_resource_uri", "quality_uri", "review_uri", "revision_uri",
    "scenes_uri",
]
