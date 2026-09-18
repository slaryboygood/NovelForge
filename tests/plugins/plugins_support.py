"""Plugin Platform 测试 fixture（V4-09 §68–§69、§93–§99）。

```text
· 测试插件只放在 tests/plugins/fixtures/，不进入生产 discovery（§69）
· manifest 一律写入 tmp_path；entry point 指向 fixture 模块（显式，不扫描目录）
· 复用 V4-04→V4-07 的 Golden fixture（delivery_stack）保证"插件仍走正常管线"
```
"""

from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"

for _candidate in (ROOT / "src", HERE, FIXTURES):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

OTHER_NOVEL_ID = "beta"
HOST_VERSION = "4.9"
MANIFEST_FILE_NAME = "novelforge-plugin.json"

#: fixture 插件身份（测试里不要手写字符串）
EXPORTER_PLUGIN = "com.example.exporter"
EXPORTER_MODULE = "example_exporter_plugin"
QUALITY_PLUGIN = "com.example.qualitycheck"
QUALITY_MODULE = "example_quality_plugin"
MCP_PLUGIN = "com.example.mcpext"
MCP_MODULE = "example_mcp_plugin"
BROKEN_MODULE = "broken_plugin"
CONFLICT_MODULE = "conflict_plugin"
PARTIAL_MODULE = "partial_conflict_plugin"
PERMISSION_MODULE = "permission_plugin"
CRASHING_MODULE = "crashing_export_plugin"
LEAKY_MODULE = "leaky_plugin"


# --------------------------------------------------------------------- 基础
def manifest_payload(plugin_id: str, *, module: str, name: str = "",
                     version: str = "1.0.0", plugin_api_version: int = 1,
                     capabilities: Sequence[str] = (),
                     permissions: Sequence[str] = (),
                     **extra: Any) -> dict[str, Any]:
    """构造 manifest payload（entry_point = `<module>:register`）。"""

    payload: dict[str, Any] = {
        "plugin_id": plugin_id, "name": name or plugin_id, "version": version,
        "plugin_api_version": int(plugin_api_version),
        "entry_point": f"{module}:register",
        "capabilities": list(capabilities), "permissions": list(permissions),
        "description": f"test plugin {plugin_id}", "author": "novelforge-tests",
    }
    payload.update(extra)
    return payload


def write_manifest(tmp_path: Path, plugin_id: str, *,
                   directory: Path | None = None, **kwargs: Any) -> Path:
    """把 manifest 写到 tmp_path（显式路径，不是目录扫描，§61）。"""

    payload = manifest_payload(plugin_id, **kwargs)
    target_dir = Path(directory or tmp_path)
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{plugin_id}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                    encoding="utf-8")
    return path


def exporter_manifest(tmp_path: Path, plugin_id: str = EXPORTER_PLUGIN,
                      module: str = EXPORTER_MODULE, **kwargs: Any) -> Path:
    return write_manifest(tmp_path, plugin_id, module=module,
                          capabilities=("exporter",),
                          permissions=("delivery.export",), **kwargs)


def quality_manifest(tmp_path: Path, plugin_id: str = QUALITY_PLUGIN,
                     module: str = QUALITY_MODULE, **kwargs: Any) -> Path:
    return write_manifest(tmp_path, plugin_id, module=module,
                          capabilities=("quality_evaluator",),
                          permissions=("quality.evaluate",), **kwargs)


def mcp_manifest(tmp_path: Path, plugin_id: str = MCP_PLUGIN,
                 module: str = MCP_MODULE, **kwargs: Any) -> Path:
    return write_manifest(tmp_path, plugin_id, module=module,
                          capabilities=("mcp_tool", "mcp_resource"),
                          permissions=("mcp.extend", "blueprint.read"), **kwargs)


@dataclass
class FakeDist:
    """distribution metadata（只提供 read_text，符合 §15 的 metadata 读取）。"""

    manifest: Mapping[str, Any] | None = None
    files: Mapping[str, str] = field(default_factory=dict)

    def read_text(self, name: str) -> str | None:
        if name in self.files:
            return self.files[name]
        if self.manifest is not None and name == MANIFEST_FILE_NAME:
            return json.dumps(dict(self.manifest), ensure_ascii=False)
        return None


@dataclass(frozen=True)
class FakeEntryPoint:
    """importlib.metadata EntryPoint 的最小替身（name / value / dist）。"""

    name: str
    value: str
    dist: Any = None


def entry_point(plugin_id: str, module: str, *, manifest: bool = True,
                **kwargs: Any) -> FakeEntryPoint:
    payload = manifest_payload(plugin_id, module=module, **kwargs) if manifest else None
    return FakeEntryPoint(name=plugin_id, value=f"{module}:register",
                          dist=FakeDist(manifest=payload))


# ------------------------------------------------------------------- PluginHost
def plugin_host(tmp_path: Path, *, manifests: Sequence[Path] = (),
                entries: Sequence[Any] | None = None, novel_id: str = "",
                host_version: str = HOST_VERSION, **kwargs: Any) -> Any:
    """构造 PluginHost（composition root；不扫描目录、不执行插件代码）。"""

    from novelforge.plugins.host import PluginHost

    return PluginHost(tmp_path, novel_id=novel_id or NOVEL_ID,
                      host_version=host_version,
                      entry_points=list(entries) if entries is not None else [],
                      manifest_paths=list(manifests), **kwargs)


def install(host: Any, plugin_id: str, *,
            permissions: Sequence[str] | None = None) -> dict[str, Any]:
    """approve + enable（Host 控制的显式启用，§17）。"""

    host.service.approve(plugin_id, permissions=permissions)
    return host.service.enable(plugin_id)


def active_plugin(host: Any, plugin_id: str, **kwargs: Any) -> dict[str, Any]:
    record = install(host, plugin_id, **kwargs)
    assert record["status"] == "active", record
    return record


# ------------------------------------------------------------------ 交付 fixture
def _load(module_name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


_delivery_support = _load("delivery_support_for_plugins",
                          ROOT / "tests" / "delivery" / "delivery_support.py")

delivery_stack = _delivery_support.delivery_stack
#: 与 V4-04→V4-07 Golden fixture 一致的 novel_id（不要在测试里手写）
NOVEL_ID = _delivery_support.NOVEL_ID
repaired_scene_payload = _delivery_support.repaired_scene_payload
repaired_chapter_payload = _delivery_support.repaired_chapter_payload
repair_script = _delivery_support.repair_script
current_payload = _delivery_support.current_payload
scripted = _delivery_support._editor_support.scripted


def plugin_delivery_stack(tmp_path: Path, plugin_ids: Sequence[str], *,
                          novel_id: str = "", **kwargs: Any) -> dict[str, Any]:
    """交付 Golden fixture + 已启用的插件（同一 project_root）。"""

    stack = delivery_stack(tmp_path, novel_id=novel_id or NOVEL_ID, **kwargs)
    stack["plugin_ids"] = tuple(plugin_ids)
    return stack


__all__ = [
    "BROKEN_MODULE", "CONFLICT_MODULE", "CRASHING_MODULE", "EXPORTER_MODULE",
    "EXPORTER_PLUGIN", "FIXTURES", "FakeDist", "FakeEntryPoint", "HERE",
    "HOST_VERSION", "LEAKY_MODULE", "MANIFEST_FILE_NAME", "MCP_MODULE",
    "MCP_PLUGIN", "NOVEL_ID", "OTHER_NOVEL_ID", "PARTIAL_MODULE",
    "PERMISSION_MODULE", "QUALITY_MODULE", "QUALITY_PLUGIN", "ROOT",
    "active_plugin", "current_payload", "delivery_stack", "entry_point",
    "exporter_manifest", "install", "mcp_manifest", "plugin_delivery_stack",
    "plugin_host", "quality_manifest", "repair_script", "repaired_chapter_payload",
    "repaired_scene_payload", "scripted", "write_manifest",
]
