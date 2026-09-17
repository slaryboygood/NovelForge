"""统一 id / digest 工具（V4-01）。

只提供与业务无关的稳定构造：请求 id 与内容摘要。任何"作品 / 章节 / 节点"语义 id
仍然属于各自模块（domain 或 application），不进入 `core`。
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any


def new_request_id(prefix: str = "req") -> str:
    """生成一次操作的请求 id（用于 trace / 幂等 / 审计关联）。

    使用 uuid4 的自由形式（非可预测序列），避免多进程/多 Agent 并发下撞号。
    """

    cleaned = "".join(ch for ch in str(prefix or "req") if ch.isalnum() or ch in "_-")
    return f"{cleaned or 'req'}_{uuid.uuid4().hex}"


def digest_payload(payload: Any, *, length: int = 16) -> str:
    """稳定内容摘要（键排序 + UTF-8 + 不转义非 ASCII）。

    与 `story_engine` 现有的 `_digest()` 语义一致，供跨模块复用而不再重复实现。
    """

    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False,
                      default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:length]


__all__ = ["digest_payload", "new_request_id"]

