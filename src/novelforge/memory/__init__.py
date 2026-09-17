"""NovelForge `memory` —— Story Memory & Context Builder（V4-03）。

Public Contract（**刻意保持精简**，§10）：

```text
MemoryService        唯一检索 / 重建入口
MemoryQuery/Result/Item/Scope/Source/RetrievalPolicy   检索契约
ContextBuilder / ContextRequest / ContextBundle        上下文选择契约
AuthorPreferenceService / AuthorPreference             作者偏好
build_default_service(novel_id, project_root)          默认装配（Canon + StoryState）
MEMORY_SCHEMA_VERSION / MemoryError 家族                 版本与错误
```

内部实现（`memory/retrieval-like` 细节、`episodic/`、`semantic/`、`context/` 的具体
store / index / scorer / compressor、embedding 实现）**不**全部公开。

核心原则（§3）：

```text
Memory is not the database / not Canon / not StoryState.
派生记忆必须可重建、可失效、可追溯 source_ids、可判断 revision。
```
"""

from .context import (
    BLOCK_PRIORITY_ORDER,
    CONTEXT_BUNDLE_SCHEMA_VERSION,
    ContextBlock,
    ContextBuilder,
    ContextBundle,
    ContextRequest,
    DeterministicTokenEstimator,
    DeterministicTruncatingCompressor,
    GatewayCompressor,
    NullCompressor,
    TokenEstimator,
)
from .contracts import (
    MEMORY_SCHEMA_VERSION,
    MemoryItem,
    MemoryQuery,
    MemoryResult,
    MemoryScope,
    MemorySource,
    RetrievalPolicy,
)
from .errors import (
    MemoryError,
    MemoryIsolationError,
    MemorySourceError,
    PreferenceScopeError,
    StaleMemoryError,
)
from .preferences import (
    PREFERENCE_SCOPE_ORDER,
    AuthorPreference,
    AuthorPreferenceService,
)
from .service import MemoryService, build_default_service

__all__ = [
    # service
    "MemoryService", "build_default_service",
    # retrieval contract
    "MemoryItem", "MemoryQuery", "MemoryResult", "MemoryScope", "MemorySource",
    "RetrievalPolicy",
    # context builder
    "ContextBlock", "ContextBuilder", "ContextBundle", "ContextRequest",
    "CONTEXT_BUNDLE_SCHEMA_VERSION", "BLOCK_PRIORITY_ORDER",
    "DeterministicTokenEstimator", "TokenEstimator",
    # preferences
    "AuthorPreference", "AuthorPreferenceService", "PREFERENCE_SCOPE_ORDER",
    # compression（可选注入）
    "DeterministicTruncatingCompressor", "GatewayCompressor", "NullCompressor",
    # version / errors
    "MEMORY_SCHEMA_VERSION", "MemoryError", "MemoryIsolationError",
    "MemorySourceError", "PreferenceScopeError", "StaleMemoryError",
]

