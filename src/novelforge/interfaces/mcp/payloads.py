"""资源载荷（V4-08 §45–§46）：只读 + 明确 MIME。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contracts import ResourceSpec
from .serialization import DEFAULT_MIME


@dataclass(frozen=True)
class ResourcePayload:
    uri: str
    content: str | bytes
    mime_type: str = DEFAULT_MIME
    spec: ResourceSpec | None = None
    notes: tuple[str, ...] = ()

    @property
    def size(self) -> int:
        return len(self.content)

    @property
    def is_binary(self) -> bool:
        return isinstance(self.content, bytes)


def as_payload(uri: str, content: str | bytes, *,
               mime_type: str = DEFAULT_MIME, spec: ResourceSpec | None = None,
               notes: tuple[str, ...] = ()) -> ResourcePayload:
    return ResourcePayload(uri=uri, content=content, mime_type=mime_type,
                           spec=spec, notes=notes)


def json_payload(uri: str, data: Any, *, spec: ResourceSpec | None = None,
                 notes: tuple[str, ...] = ()) -> ResourcePayload:
    import json

    return ResourcePayload(uri=uri,
                           content=json.dumps(data, ensure_ascii=False, indent=1,
                                              sort_keys=True, default=_json_default),
                           mime_type=DEFAULT_MIME, spec=spec, notes=notes)


def _json_default(value: Any) -> Any:
    """把业务对象降级成 JSON 安全形状（协议层只做序列化，不改语义）。"""

    for method in ("as_dict", "model_dump", "to_dict"):
        handler = getattr(value, method, None)
        if callable(handler):
            try:
                return handler()
            except Exception:  # noqa: BLE001 - 继续尝试下一种
                continue
    if hasattr(value, "__dict__"):
        return {key: item for key, item in vars(value).items()
                if not str(key).startswith("_")}
    return str(value)


__all__ = ["ResourcePayload", "as_payload", "json_payload"]
