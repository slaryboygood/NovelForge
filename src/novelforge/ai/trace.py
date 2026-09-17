"""Trace 记录（V4-02 §18）。

隐私底线：

```text
默认不保存：完整 system prompt / user prompt / API key / 敏感 headers / 完整小说上下文
允许保存  ：context digest、context size、contract id、schema id、usage 摘要
```
"""

from __future__ import annotations

import datetime as _dt
import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol


@dataclass(frozen=True)
class TraceRecord:
    request_id: str
    operation: str
    provider: str
    model: str
    contract_id: str
    contract_version: int
    status: str                      # ok | error | cache_hit
    latency_ms: int
    attempt_count: int
    timeout_s: float
    usage: Mapping[str, Any] = field(default_factory=dict)
    error_code: str = ""
    #: 终态错误的根因（例如 RetryExhaustedError 包装的最后一个 provider 错误码）
    error_chain: str = ""
    context_digest: str = ""
    context_size: int = 0
    schema_id: str = ""
    cache_key: str = ""
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            object.__setattr__(self, "created_at",
                               _dt.datetime.now(_dt.timezone.utc).isoformat())

    def as_dict(self) -> dict[str, Any]:
        return {"request_id": self.request_id, "operation": self.operation,
                "provider": self.provider, "model": self.model,
                "contract_id": self.contract_id,
                "contract_version": self.contract_version,
                "status": self.status, "latency_ms": self.latency_ms,
                "attempt_count": self.attempt_count, "timeout_s": self.timeout_s,
                "usage": dict(self.usage), "error_code": self.error_code,
                "error_chain": self.error_chain,
                "context_digest": self.context_digest,
                "context_size": self.context_size, "schema_id": self.schema_id,
                "cache_key": self.cache_key, "created_at": self.created_at}


class TraceSink(Protocol):
    def record(self, record: TraceRecord) -> None: ...


class NullTraceSink:
    """默认 sink：丢弃 trace（显式选择"不留痕"时使用）。"""

    def record(self, record: TraceRecord) -> None:  # pragma: no cover - trivial
        return None


def context_digest(context: Mapping[str, Any]) -> str:
    """上下文摘要（用于 cache key 与 trace；不保存原文）。"""

    from novelforge.core.ids import digest_payload

    return digest_payload(context)


def context_size(context: Mapping[str, Any]) -> int:
    """上下文字节量级（用于 trace 的体积观测，不保存内容）。"""

    return len(json.dumps(context, ensure_ascii=False, default=str).encode("utf-8"))


__all__ = ["NullTraceSink", "TraceRecord", "TraceSink", "context_digest",
           "context_size"]
