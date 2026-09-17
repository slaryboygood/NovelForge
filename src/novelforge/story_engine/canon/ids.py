"""Canon 稳定 ID 工具。

约束（Canon Infrastructure V1）：

- 稳定 ID 必须在**创建时确定**，之后不可修改；
- 禁止从可变文本（canonical_description / summary / 章节标题 / 正文）或
  可变序号（chapter number / effect_log order / route order）派生；
- 无法安全生成语义 key 时，生成并持久化随机 ID（ULID 风格），后续 rebuild 复用。
"""

from __future__ import annotations

import os
import re
import time

ID_PREFIXES = {"entity": "ENT", "fact": "FACT", "event": "EVENT", "knowledge": "KNW",
               "relationship": "REL", "foreshadow": "FS", "constraint": "CON"}

# 明显来自可变序号 / 渲染位置的非法 identity
FORBIDDEN_ID_PATTERN = re.compile(r"^(ch\d+|chapter[_-]?\d+|volume\d+[_-]?ch\d+|route[_-]?\d+)$", re.I)
KEY_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9_]{0,95}$")

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _encode(value: int, length: int) -> str:
    chars = []
    for _ in range(length):
        chars.append(_ALPHABET[value % len(_ALPHABET)])
        value //= len(_ALPHABET)
    return "".join(reversed(chars))


def new_random_key() -> str:
    """ULID 风格的可排序随机 key（单调时间前缀 + 随机后缀）。"""

    timestamp = int(time.time() * 1000)
    random_part = int.from_bytes(os.urandom(10), "big")
    return _encode(timestamp, 10) + _encode(random_part, 16)


def new_canon_id(kind: str, *, canonical_key: str = "") -> str:
    """生成 `FACT_<KEY>` / `EVENT_<KEY>`；无 key 时用持久化随机 key（调用方必须落库复用）。"""

    prefix = ID_PREFIXES[kind]
    key = (canonical_key or new_random_key()).upper()
    return f"{prefix}_{key}"


def validate_canon_id(value: str, kind: str | None = None) -> str:
    """校验 ID 形态；拒绝章节号/序号型 identity。"""

    if FORBIDDEN_ID_PATTERN.match(value or ""):
        raise ValueError(f"chapter/order 型编号不能作为 canon identity：{value}")
    if kind is not None:
        prefix = ID_PREFIXES[kind]
        if not value.startswith(prefix + "_"):
            raise ValueError(f"canon id 前缀必须是 {prefix}_：{value}")
        key = value[len(prefix) + 1:]
        if not KEY_PATTERN.match(key):
            raise ValueError(f"canon key 形态非法：{key}")
    return value


def validate_canonical_key(value: str) -> str:
    if not KEY_PATTERN.match(value or ""):
        raise ValueError(f"canonical_key 必须是不可变的机器 key（A-Z0-9_）：{value!r}")
    if FORBIDDEN_ID_PATTERN.match(value):
        raise ValueError(f"canonical_key 不得使用章节号/序号：{value}")
    return value
