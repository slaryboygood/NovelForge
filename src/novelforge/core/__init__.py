"""Core Primitives（V4-01）。

`core` 只放**语义稳定、无模块所有权争议、不含故事业务规则**的 primitive
（见 `docs/v4/V4_MODULE_BOUNDARIES.md` §3.1 与 Master Plan §11）。

当前内容：

```text
core.ids       统一 id / digest 工具
core.revision  revision primitive（revision / expected_revision / parent_revision / conflict）
```

禁止：`core/utils.py`、`core/helpers.py`、`core/manager.py` 这类万能桶。
"""

from .ids import digest_payload, new_request_id
from .revision import (
    OperationContext,
    RevisionConflict,
    RevisionRef,
    check_expected_revision,
    new_revision,
)

__all__ = [
    "OperationContext", "RevisionConflict", "RevisionRef",
    "check_expected_revision", "digest_payload", "new_request_id", "new_revision",
]

