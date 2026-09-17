"""模型调用 trace sink（V4-02，最小实现）。

只保存 `TraceRecord`（已是安全字段集：无 prompt / 无 secret），提供：

```text
InMemoryModelTraceStore  进程内环形缓冲（默认，测试与单进程运行时使用）
JsonlModelTraceStore     可选：按行落盘的 append-only trace（不含 prompt）
```
"""

from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from typing import Any, Iterable

from novelforge.ai.trace import TraceRecord


class InMemoryModelTraceStore:
    def __init__(self, *, max_records: int = 500) -> None:
        self.max_records = max(1, int(max_records))
        self._records: deque[TraceRecord] = deque(maxlen=self.max_records)

    def record(self, record: TraceRecord) -> None:
        self._records.append(record)

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = list(self._records)[-max(1, int(limit)):]
        return [item.as_dict() for item in rows]

    def filter_by_operation(self, operation: str) -> list[dict[str, Any]]:
        return [item.as_dict() for item in self._records
                if item.operation == operation]

    def clear(self) -> None:
        self._records.clear()

    def __len__(self) -> int:
        return len(self._records)


class JsonlModelTraceStore:
    """append-only JSONL trace（默认关闭；作者显式启用时才落盘）。"""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def record(self, record: TraceRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(record.as_dict(), ensure_ascii=False) + "\n")

    def read(self) -> Iterable[dict[str, Any]]:
        if not self.path.is_file():
            return []
        rows = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows


__all__ = ["InMemoryModelTraceStore", "JsonlModelTraceStore"]

