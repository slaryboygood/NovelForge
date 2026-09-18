"""NovelForge Package（`.nfpack` / ZIP）exporter（V4-07 §36–§38、§70–§72）。

```text
novelforge-package/
├── manifest.json
├── blueprint/blueprint.json（+ nodes/*.json，按 profile 决定）
├── quality/{summary,issues}.json
├── revisions/snapshot.json
├── provenance/provenance.json
├── editor/review-summary.json
└── exports/{blueprint.md, blueprint.docx}
```

规则：

```text
· 只包含明确选择的作品 / revision / 允许的 metadata（不是项目目录备份）
· 不包含 cache / .env / API key / provider secret / 完整 prompt / raw HTTP response
· ZIP 条目名不能用 ../ 或绝对路径（§70）
· 条目顺序与时间戳固定 → 产物 deterministic（§42）
```
"""

from __future__ import annotations

import io
import json
import zipfile
from typing import Any, Mapping, Sequence

from . import ExporterRegistry, ExporterSpec

EXPORTER_ID = "delivery.nfpack.v1"
EXPORTER_VERSION = 1

_FIXED_DATE = (1980, 1, 1, 0, 0, 0)

#: 绝不允许出现在 package 里的东西（§71）
FORBIDDEN_ENTRY_TOKENS: tuple[str, ...] = (
    ".env", "secret", "credential", "api_key", "apikey", "id_rsa", ".pem",
    "token", "cache", "logs", "node_modules", ".git",
)
FORBIDDEN_CONTENT_TOKENS: tuple[str, ...] = (
    "API_KEY", "api_key", "Authorization", "Bearer ", "sk-", "SECRET_KEY",
    "raw_response", "provider_config",
)


def _entry_name(path: str) -> str:
    text = str(path or "").replace("\\", "/").strip()
    if not text or text.startswith("/") or text.startswith("~") or ":" in text:
        raise ValueError(f"不安全的 package 条目名：{path!r}")
    parts = [part for part in text.split("/") if part]
    if not parts or any(part in ("..", ".") for part in parts):
        raise ValueError(f"不安全的 package 条目名：{path!r}")
    lowered = text.lower()
    if any(token in lowered for token in FORBIDDEN_ENTRY_TOKENS):
        raise ValueError(f"package 条目名命中禁区：{path!r}")
    return text


def _json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True)
            + "\n").encode("utf-8")


def package_entries(context: Mapping[str, Any]) -> list[tuple[str, bytes]]:
    """构造 package 条目（顺序固定 = 确定性前提）。"""

    blueprint = dict(context.get("blueprint") or {})
    entries: list[tuple[str, bytes]] = []
    manifest = dict(context.get("manifest") or {})
    entries.append(("manifest.json", _json_bytes(manifest)))
    entries.append(("blueprint/blueprint.json",
                    _json_bytes({"ordering": list(blueprint.get("ordering") or []),
                                 "node_count": int(blueprint.get("node_count") or 0),
                                 "node_revisions": dict(
                                     blueprint.get("node_revisions") or {}),
                                 "digest": str(blueprint.get("digest") or ""),
                                 "nodes": [dict(row) for row
                                           in (blueprint.get("nodes") or [])]})))
    if context.get("include_node_files"):
        for row in sorted(blueprint.get("nodes") or [],
                          key=lambda item: str(item.get("node_id"))):
            entries.append((f"blueprint/nodes/{row.get('node_id')}.json",
                            _json_bytes(row)))
    if context.get("quality"):
        entries.append(("quality/summary.json", _json_bytes(context.get("quality"))))
        entries.append(("quality/issues.json",
                        _json_bytes(context.get("quality_issues") or [])))
    entries.append(("revisions/snapshot.json",
                    _json_bytes(context.get("snapshot") or {})))
    if context.get("review"):
        entries.append(("editor/review-summary.json",
                        _json_bytes(context.get("review"))))
    if context.get("provenance"):
        entries.append(("provenance/provenance.json",
                        _json_bytes(context.get("provenance"))))
    if context.get("history"):
        entries.append(("revisions/history.json", _json_bytes(context.get("history"))))
    for extra in context.get("extra_exports") or []:
        path = str(extra.get("path") or "")
        data = extra.get("data") or b""
        if path:
            entries.append((path, bytes(data)))
    return entries


def build_zip(context: Mapping[str, Any]) -> bytes:
    entries = package_entries(context)
    seen: set[str] = set()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for raw_name, data in entries:
            name = _entry_name(raw_name)
            if name in seen:
                raise ValueError(f"package 条目重复：{name}")
            seen.add(name)
            info = zipfile.ZipInfo(name, date_time=_FIXED_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, bytes(data))
    return buffer.getvalue()


def scan_for_secrets(data: bytes) -> list[str]:
    """交付前扫描：package 二进制里不得出现 secret 类字符串（§71）。"""

    hits: list[str] = []
    try:
        text = data.decode("utf-8", errors="ignore")
    except Exception:  # noqa: BLE001 - 二进制内容只做粗扫描
        return hits
    for token in FORBIDDEN_CONTENT_TOKENS:
        if token in text:
            hits.append(token)
    return hits


def export(context: Mapping[str, Any]) -> bytes:
    return build_zip(context)


def register(registry: ExporterRegistry) -> ExporterSpec:
    return registry.register(ExporterSpec(
        format="nfpack", exporter_id=EXPORTER_ID, version=EXPORTER_VERSION,
        mime_type="application/zip", extension="nfpack", text=False,
        description="NovelForge Package（selected artifacts, not a repo backup）"),
        export)


__all__ = ["EXPORTER_ID", "EXPORTER_VERSION", "FORBIDDEN_CONTENT_TOKENS",
           "FORBIDDEN_ENTRY_TOKENS", "build_zip", "export", "package_entries",
           "register", "scan_for_secrets"]
