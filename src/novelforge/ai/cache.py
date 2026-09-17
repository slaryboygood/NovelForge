"""Cache Contract（V4-02 §20–21）。

保守默认：只有 contract 显式声明 `cacheable=True` 才写入缓存
（创意类 / StoryState 驱动生成默认不缓存）。

Cache key 只使用 digest，**不直接把正文 / prompt / 人物隐私作为 key**。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from novelforge.core.ids import digest_payload


@dataclass(frozen=True)
class CacheKey:
    provider: str
    model: str
    contract_id: str
    contract_version: int
    context_digest: str
    policy_digest: str
    revision: int | None = None

    def as_string(self) -> str:
        parts = [self.provider, self.model, self.contract_id,
                 f"v{self.contract_version}", self.context_digest,
                 self.policy_digest]
        if self.revision is not None:
            parts.append(f"r{self.revision}")
        return "|".join(parts)


def build_cache_key(*, provider: str, model: str, contract_id: str,
                    contract_version: int, context: Mapping[str, Any],
                    policy_fields: Mapping[str, Any],
                    revision: int | None = None) -> CacheKey:
    return CacheKey(provider=provider, model=model, contract_id=contract_id,
                    contract_version=int(contract_version),
                    context_digest=digest_payload(context),
                    policy_digest=digest_payload(dict(policy_fields)),
                    revision=revision)


class InMemoryCache:
    """进程内缓存（测试 / 单进程运行时使用）。"""

    def __init__(self, *, max_entries: int = 256) -> None:
        self.max_entries = max(1, int(max_entries))
        self._entries: dict[str, Any] = {}
        self.hits = 0
        self.misses = 0

    def get(self, key: CacheKey) -> Any | None:
        if key.as_string() in self._entries:
            self.hits += 1
            return self._entries[key.as_string()]
        self.misses += 1
        return None

    def put(self, key: CacheKey, value: Any) -> None:
        if len(self._entries) >= self.max_entries:
            oldest = next(iter(self._entries))
            self._entries.pop(oldest, None)
        self._entries[key.as_string()] = value

    def clear(self) -> None:
        self._entries.clear()
        self.hits = 0
        self.misses = 0

    def stats(self) -> dict[str, int]:
        return {"entries": len(self._entries), "hits": self.hits,
                "misses": self.misses}


def cache_allowed(*, contract_cacheable: bool, generation_mode: str) -> bool:
    """缓存准入：contract 必须显式声明可缓存（creative 默认关闭）。"""

    if not contract_cacheable:
        return False
    return generation_mode in ("structured_json", "text")


__all__ = ["CacheKey", "InMemoryCache", "build_cache_key", "cache_allowed"]

