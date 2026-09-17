"""作者偏好（V4-03 §15–§16）。

作用域与优先级（deterministic merge）：

```text
Operation Override > Novel > Project > Global
```

规则：

```text
· 每条 preference 带 scope / key / value / source / created_at / updated_at
· 模型推断必须标记 inferred=True；不得静默写成作者明确偏好
· 同等作用域下 explicit（inferred=False）优先于 inferred
· 值必须可 JSON 序列化
· V4-03 只实现显式偏好（不做自动学习）
```
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable, Mapping

from novelforge.persistence.paths import memory_preferences_path

from ..contracts import utc_now
from ..errors import PreferenceScopeError

#: 优先级从低到高（merge 时后者覆盖前者）
PREFERENCE_SCOPE_ORDER: tuple[str, ...] = ("global", "project", "novel", "operation")


@dataclass(frozen=True)
class AuthorPreference:
    scope: str
    key: str
    value: Any
    scope_id: str = ""
    source: str = "author"
    inferred: bool = False
    note: str = ""
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        if self.scope not in PREFERENCE_SCOPE_ORDER:
            raise PreferenceScopeError(
                f"未知 preference 作用域：{self.scope}",
                details={"allowed": list(PREFERENCE_SCOPE_ORDER)})
        if not str(self.key or "").strip():
            raise PreferenceScopeError("preference 需要 key")
        if self.scope in ("project", "novel", "operation") and not str(
                self.scope_id or "").strip():
            raise PreferenceScopeError(
                f"{self.scope} 作用域必须提供 scope_id（否则无法隔离作品）")
        try:
            json.dumps(self.value, ensure_ascii=False)
        except TypeError as exc:
            raise PreferenceScopeError(
                f"preference 值必须可 JSON 序列化：{exc}") from exc
        stamp = utc_now()
        if not self.created_at:
            object.__setattr__(self, "created_at", stamp)
        if not self.updated_at:
            object.__setattr__(self, "updated_at", stamp)

    @property
    def precedence(self) -> int:
        return PREFERENCE_SCOPE_ORDER.index(self.scope)

    def as_dict(self) -> dict[str, Any]:
        return {"scope": self.scope, "scope_id": self.scope_id, "key": self.key,
                "value": self.value, "source": self.source,
                "inferred": self.inferred, "note": self.note,
                "created_at": self.created_at, "updated_at": self.updated_at}

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "AuthorPreference":
        return cls(scope=str(payload.get("scope") or ""),
                   scope_id=str(payload.get("scope_id") or ""),
                   key=str(payload.get("key") or ""),
                   value=payload.get("value"),
                   source=str(payload.get("source") or "author"),
                   inferred=bool(payload.get("inferred") or False),
                   note=str(payload.get("note") or ""),
                   created_at=str(payload.get("created_at") or ""),
                   updated_at=str(payload.get("updated_at") or ""))


class AuthorPreferenceService:
    """显式作者偏好的唯一读写入口（按 novel 隔离）。"""

    def __init__(self, novel_id: str, *, project_root: Path | str | None = None,
                 project_id: str = "", persist: bool = False) -> None:
        if not str(novel_id or "").strip():
            raise PreferenceScopeError("AuthorPreferenceService 需要显式 novel_id")
        self.novel_id = str(novel_id)
        self.project_id = str(project_id or novel_id)
        self.project_root = Path(project_root) if project_root else None
        self.persist = bool(persist and self.project_root is not None)
        self._items: dict[tuple[str, str, str], AuthorPreference] = {}
        if self.persist:
            self.load()

    # ------------------------------------------------------------------ 写入
    def set(self, scope: str, key: str, value: Any, *, scope_id: str = "",
            inferred: bool = False, source: str = "author",
            note: str = "") -> AuthorPreference:
        resolved_scope_id = str(scope_id or "")
        if scope == "project" and not resolved_scope_id:
            resolved_scope_id = self.project_id
        if scope == "novel" and not resolved_scope_id:
            resolved_scope_id = self.novel_id
        if scope == "operation" and not resolved_scope_id:
            raise PreferenceScopeError("operation 作用域必须提供 scope_id（操作名）")
        preference = AuthorPreference(scope=scope, scope_id=resolved_scope_id,
                                      key=str(key), value=value, source=source,
                                      inferred=bool(inferred), note=note)
        existing = self._items.get((scope, resolved_scope_id, preference.key))
        if existing is not None:
            preference = replace(preference, created_at=existing.created_at)
        self._items[(scope, resolved_scope_id, preference.key)] = preference
        return preference

    def add_many(self, rows: Iterable[Mapping[str, Any]]) -> int:
        count = 0
        for row in rows:
            self.set(str(row.get("scope") or "novel"), str(row.get("key") or ""),
                     row.get("value"), scope_id=str(row.get("scope_id") or ""),
                     inferred=bool(row.get("inferred") or False),
                     source=str(row.get("source") or "author"),
                     note=str(row.get("note") or ""))
            count += 1
        return count

    # ------------------------------------------------------------------ 读取
    def all(self) -> tuple[AuthorPreference, ...]:
        return tuple(sorted(self._items.values(),
                            key=lambda item: (item.precedence, item.scope_id,
                                              item.key)))

    def relevant(self, *, operation: str = "", scope: str = "") -> list[AuthorPreference]:
        rows = []
        for item in self.all():
            if scope and item.scope != scope:
                continue
            # operation override 只对**匹配的**操作生效；未指定 operation 时不参与
            if item.scope == "operation":
                if not operation or item.scope_id != operation:
                    continue
            if item.scope in ("project", "novel") and not self._in_scope(item):
                continue
            rows.append(item)
        return rows

    def _in_scope(self, item: AuthorPreference) -> bool:
        if item.scope == "project":
            return item.scope_id == self.project_id
        if item.scope == "novel":
            return item.scope_id == self.novel_id
        return True

    def resolve(self, *, operation: str = "") -> dict[str, dict[str, Any]]:
        """确定性 merge：高优先级覆盖低优先级；同级 explicit 优先于 inferred。"""

        merged: dict[str, dict[str, Any]] = {}
        for item in self.relevant(operation=operation):
            payload = {"value": item.value, "scope": item.scope,
                       "scope_id": item.scope_id, "source": item.source,
                       "inferred": item.inferred, "updated_at": item.updated_at}
            current = merged.get(item.key)
            if current is None:
                merged[item.key] = payload
                continue
            same_scope = (current["scope"] == item.scope
                          and current.get("scope_id", "") == item.scope_id)
            if same_scope:
                if bool(current["inferred"]) and not item.inferred:
                    merged[item.key] = payload
                continue
            if item.precedence >= PREFERENCE_SCOPE_ORDER.index(current["scope"]):
                merged[item.key] = payload
        return {key: merged[key] for key in sorted(merged)}

    def as_items(self, *, operation: str = "") -> list[dict[str, Any]]:
        """给 Context Builder 的 preference block（带 provenance）。"""

        rows = []
        for key, payload in self.resolve(operation=operation).items():
            rows.append({"key": key, "value": payload["value"],
                         "scope": payload["scope"], "source": payload["source"],
                         "inferred": payload["inferred"],
                         "updated_at": payload["updated_at"]})
        return rows

    # ------------------------------------------------------------------ 存储
    def path(self) -> Path | None:
        if self.project_root is None:
            return None
        return memory_preferences_path(self.project_root, self.novel_id)

    def save(self) -> Path | None:
        path = self.path()
        if path is None:
            return None
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"memory_schema_version": 1, "novel_id": self.novel_id,
                   "updated_at": utc_now(),
                   "preferences": [item.as_dict() for item in self.all()]}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8", newline="\n")
        return path

    def load(self) -> int:
        path = self.path()
        if path is None or not path.is_file():
            return 0
        payload = json.loads(path.read_text(encoding="utf-8"))
        self._items.clear()
        count = 0
        for row in payload.get("preferences") or []:
            preference = AuthorPreference.from_payload(row)
            self._items[(preference.scope, preference.scope_id,
                         preference.key)] = preference
            count += 1
        return count

    def clear(self) -> None:
        self._items.clear()


__all__ = ["PREFERENCE_SCOPE_ORDER", "AuthorPreference", "AuthorPreferenceService"]
