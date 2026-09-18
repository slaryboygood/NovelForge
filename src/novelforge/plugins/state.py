"""Plugin 状态 / 批准记录 / 审计（V4-09 §26–§30、§54、§56、§99–§100）。

```text
enablement（host 级）  plugins/enablement.json
audit（host 级）       plugins/audit.json
plugin state（作品级） plugins/state/<novel_id>/<plugin_id>/state.json
```

规则：

```text
· 路径全部经 persistence.paths（插件拿不到 project_root）
· state 按 (novel_id, plugin_id) 隔离：Plugin A 读不到 Plugin B / 其他作品
· state 永远不是 story truth（只能 cache / settings / plugin metadata）
· 不写 secret（manifest / state / audit / 错误响应都不写）
```
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Any, Mapping, MutableMapping

from novelforge.persistence.paths import (
    plugin_audit_path,
    plugin_enablement_path,
    plugin_state_dir,
)

from .errors import PluginError, PluginNotFoundError


def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


class PluginStateStore:
    """插件状态（按 novel_id + plugin_id 隔离）。"""

    def __init__(self, project_root: Path | str, novel_id: str, plugin_id: str) -> None:
        if not str(novel_id or "").strip():
            raise PluginError("PluginStateStore 需要显式 novel_id")
        if not str(plugin_id or "").strip():
            raise PluginError("PluginStateStore 需要显式 plugin_id")
        self.project_root = Path(project_root)
        self.novel_id = str(novel_id)
        self.plugin_id = str(plugin_id)

    @property
    def root(self) -> Path:
        return plugin_state_dir(self.project_root, self.novel_id, self.plugin_id)

    @property
    def state_path(self) -> Path:
        return self.root / "state.json"

    def load(self) -> dict[str, Any]:
        if not self.state_path.is_file():
            return {}
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def save(self, values: Mapping[str, Any]) -> Path:
        payload = {"plugin_id": self.plugin_id, "novel_id": self.novel_id,
                   "updated_at": utc_now(), "values": dict(values)}
        path = self.state_path
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1,
                                  sort_keys=True) + "\n",
                       encoding="utf-8", newline="\n")
        tmp.replace(path)
        return path

    def update(self, patch: Mapping[str, Any]) -> dict[str, Any]:
        merged: MutableMapping[str, Any] = dict(self.load().get("values") or {})
        merged.update(dict(patch))
        self.save(merged)
        return dict(merged)

    def as_dict(self) -> dict[str, Any]:
        return {"plugin_id": self.plugin_id, "novel_id": self.novel_id,
                "values": dict(self.load().get("values") or {})}


class EnablementStore:
    """approve / enable 记录（§54）：保存 approved_version + approved_permissions。"""

    def __init__(self, project_root: Path | str) -> None:
        self.project_root = Path(project_root)

    @property
    def path(self) -> Path:
        return plugin_enablement_path(self.project_root)

    def _read(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {"schema_version": 1, "plugins": {}}
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        payload.setdefault("plugins", {})
        return payload

    def _write(self, payload: Mapping[str, Any]) -> Path:
        body = {**dict(payload), "updated_at": utc_now()}
        path = self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(body, ensure_ascii=False, indent=1,
                                  sort_keys=True) + "\n",
                       encoding="utf-8", newline="\n")
        tmp.replace(path)
        return path

    def records(self) -> dict[str, dict[str, Any]]:
        return {str(key): dict(value)
                for key, value in (self._read().get("plugins") or {}).items()}

    def get(self, plugin_id: str) -> dict[str, Any]:
        return dict(self.records().get(str(plugin_id)) or {})

    def is_approved(self, plugin_id: str) -> bool:
        row = self.get(plugin_id)
        return bool(row.get("approved_version"))

    def is_enabled(self, plugin_id: str) -> bool:
        return bool(self.get(plugin_id).get("enabled"))

    def approve(self, plugin_id: str, *, version: str,
                permissions: Mapping[str, Any] | Any, package_digest: str = "",
                approved_by: str = "user", note: str = "") -> dict[str, Any]:
        payload = self._read()
        plugins = dict(payload.get("plugins") or {})
        row = dict(plugins.get(str(plugin_id)) or {})
        row.update({"plugin_id": str(plugin_id), "approved_version": str(version),
                    "approved_permissions": sorted(str(value) for value in permissions),
                    "package_digest": str(package_digest),
                    "approved_by": str(approved_by), "note": str(note)[:200],
                    "approved_at": utc_now(), "enabled": False})
        plugins[str(plugin_id)] = row
        self._write({**payload, "plugins": plugins})
        return row

    def set_enabled(self, plugin_id: str, enabled: bool) -> dict[str, Any]:
        payload = self._read()
        plugins = dict(payload.get("plugins") or {})
        row = dict(plugins.get(str(plugin_id)) or {})
        if not row.get("approved_version"):
            raise PluginNotFoundError(
                f"插件尚未批准：{plugin_id}",
                details={"plugin_id": str(plugin_id)})
        row["enabled"] = bool(enabled)
        row["enabled_at" if enabled else "disabled_at"] = utc_now()
        plugins[str(plugin_id)] = row
        self._write({**payload, "plugins": plugins})
        return row


class PluginAuditLog:
    """插件审计（§56）：discovered / approved / enabled / loaded / failed / disabled。"""

    def __init__(self, project_root: Path | str, *, max_records: int = 500) -> None:
        self.project_root = Path(project_root)
        self.max_records = max(1, int(max_records))

    @property
    def path(self) -> Path:
        return plugin_audit_path(self.project_root)

    def records(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return [dict(row) for row in (payload.get("records") or [])]

    def record(self, event: str, *, plugin_id: str = "", version: str = "",
               status: str = "", error_code: str = "", extra: Mapping[str, Any] | None = None
               ) -> dict[str, Any]:
        rows = self.records()
        row = {"event": str(event), "plugin_id": str(plugin_id),
               "version": str(version), "status": str(status),
               "error_code": str(error_code), "at": utc_now(),
               "extra": dict(extra or {})}
        rows.append(row)
        rows = rows[-self.max_records:]
        path = self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"schema_version": 1, "records": rows},
                                  ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                       encoding="utf-8", newline="\n")
        tmp.replace(path)
        return row


__all__ = ["EnablementStore", "PluginAuditLog", "PluginStateStore", "utc_now"]
