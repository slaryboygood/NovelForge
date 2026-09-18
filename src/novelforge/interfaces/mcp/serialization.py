"""序列化与安全（V4-08 §29、§31、§44–§46、§49–§50）。

```text
· 统一 envelope（ToolResult.as_dict）
· 敏感内容净化：secret / prompt / raw response / base_url / 绝对路径
· MIME：按格式给出正确 mime type，不全部标 text/plain
· 结构化优先：核心结果保持结构化字段，summary 只作补充
```
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

#: 永不外传的 key（§44）
FORBIDDEN_KEYS: tuple[str, ...] = (
    "api_key", "apikey", "authorization", "secret", "password", "token",
    "base_url", "api_base", "prompt", "system_prompt", "user_prompt",
    "raw_response", "raw_metadata", "provider_config", "env", "dotenv",
    "access_key", "credential", "private_key",
)

#: 绝对路径模式（§31：不暴露本机路径）
ABSOLUTE_PATH_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Windows 盘符路径（注意：不能误伤 URI，例如 novelforge://…）
    re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:\\[^\s\"']+"),
    re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/](?![\\/])[^\s\"']+"),
    re.compile(r"/(?:home|users|var|tmp|mnt|opt)/[^\s\"']+", re.IGNORECASE),
)

REDACTED = "[redacted]"

#: 格式 → MIME（§46）
MIME_TYPES: Mapping[str, str] = {
    "json": "application/json",
    "markdown": "text/markdown",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "nfpack": "application/zip",
    "text": "text/plain",
}

DEFAULT_MIME = "application/json"


def mime_for(fmt: str, *, fallback: str = DEFAULT_MIME) -> str:
    return MIME_TYPES.get(str(fmt), fallback)


def redact_text(text: str) -> str:
    """把绝对路径替换成占位符（保留字符串可读性）。"""

    resolved = str(text)
    for pattern in ABSOLUTE_PATH_PATTERNS:
        resolved = pattern.sub(REDACTED, resolved)
    return resolved


def sanitize(value: Any, *, depth: int = 0) -> Any:
    """递归净化：删除敏感 key，遮蔽绝对路径（§31、§44）。"""

    if depth > 12:
        return REDACTED
    if isinstance(value, Mapping):
        rows: dict[str, Any] = {}
        for key, item in value.items():
            name = str(key)
            if name.lower() in FORBIDDEN_KEYS:
                continue                      # 直接丢弃，不返回占位（避免客户端误解）
            rows[name] = sanitize(item, depth=depth + 1)
        return rows
    if isinstance(value, (list, tuple)):
        return [sanitize(item, depth=depth + 1) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, bytes):
        return REDACTED
    return value


def assert_no_secrets(payload: Any) -> list[str]:
    """交付 / 资源自检：返回命中的敏感 key 或路径（测试与运行期守卫共用）。"""

    hits: list[str] = []

    def walk(node: Any, depth: int = 0) -> None:
        if depth > 12:
            return
        if isinstance(node, Mapping):
            for key, item in node.items():
                name = str(key)
                if name.lower() in FORBIDDEN_KEYS:
                    hits.append(f"key:{name}")
                walk(item, depth + 1)
        elif isinstance(node, (list, tuple)):
            for item in node:
                walk(item, depth + 1)
        elif isinstance(node, str):
            if redact_text(node) != node:
                hits.append(f"path:{node[:80]}")

    walk(payload)
    return sorted(set(hits))


def structured(summary: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    """结构化结果 + 可选人类可读摘要（§49–§50：摘要不替代数据）。"""

    data = dict(payload)
    data.setdefault("summary", summary)
    return data


def content_blocks(envelope: Mapping[str, Any]) -> str:
    """把 envelope 序列化成 MCP 工具返回的文本块（JSON）。"""

    from .contracts import envelope_json

    return envelope_json(envelope)


__all__ = [
    "ABSOLUTE_PATH_PATTERNS", "DEFAULT_MIME", "FORBIDDEN_KEYS", "MIME_TYPES",
    "REDACTED", "assert_no_secrets", "content_blocks", "mime_for", "redact_text",
    "sanitize", "structured",
]
