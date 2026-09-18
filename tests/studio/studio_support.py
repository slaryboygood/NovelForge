"""Story Studio API 测试 fixture（V4-10）。

复用 V4-04→V4-09 的 Golden fixture：

```text
tests/delivery/delivery_support.delivery_stack   已接受 + 质量通过的 Blueprint
tests/generation/gen_support                      StubProvider（零网络生成）
tests/plugins/plugins_support                     PluginHost（fixture 插件）
```

零网络、零真实模型：所有 app 都用注入的 stub gateway 构造。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))


def _load(module_name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


_delivery = _load("delivery_support_for_studio",
                  ROOT / "tests" / "delivery" / "delivery_support.py")
_gen = _load("gen_support_for_studio",
             ROOT / "tests" / "generation" / "gen_support.py")
_plugins = _load("plugins_support_for_studio",
                 ROOT / "tests" / "plugins" / "plugins_support.py")

delivery_stack = _delivery.delivery_stack
repaired_scene_payload = _delivery.repaired_scene_payload
repaired_chapter_payload = _delivery.repaired_chapter_payload
repair_script = _delivery.repair_script
NOVEL_ID = _delivery.NOVEL_ID

build_novel = _gen.build_novel
service_for = _gen.service_for
stub_gateway = _gen.stub_gateway
premise_payload = _gen.premise_payload
world_payload = _gen.world_payload
character_payload = _gen.character_payload
character_arc_payload = _gen.character_arc_payload
story_arc_payload = _gen.story_arc_payload
unit_payload = _gen.unit_payload
chapter_payload = _gen.chapter_payload
scene_payload = _gen.scene_payload

plugin_host = _plugins.plugin_host
exporter_manifest = _plugins.exporter_manifest
write_manifest = _plugins.write_manifest
active_plugin = _plugins.active_plugin
EXPORTER_PLUGIN = _plugins.EXPORTER_PLUGIN


def studio_app(root: Path, *, gateway: Any = None, memory: Any = None,
               plugin_host_obj: Any = None) -> Any:
    """构造 REST 应用（只含 current V4 路由；legacy router 已整体退休）。"""

    from fastapi.testclient import TestClient

    from novelforge.api.app import create_app

    app = create_app(root, gateway=gateway, memory=memory,
                     plugin_host=plugin_host_obj)
    return TestClient(app)


def clean_studio(tmp_path: Path, *, novel_id: str = NOVEL_ID,
                 plugin_formats: bool = False) -> dict[str, Any]:
    """已接受 + 质量通过的 Studio（可选：装配插件 exporter 格式）。"""

    stack = delivery_stack(tmp_path, novel_id=novel_id)
    host = None
    if plugin_formats:
        host = plugin_host(tmp_path, manifests=[exporter_manifest(tmp_path)],
                           novel_id=novel_id)
        host.discover()
        active_plugin(host, EXPORTER_PLUGIN)
    client = studio_app(tmp_path, gateway=stack["gateway"],
                        memory=stack["memory"], plugin_host_obj=host)
    stack.update({"client": client, "plugin_host": host, "root": tmp_path})
    return stack


def empty_studio(tmp_path: Path, *, novel_id: str = "studio_empty",
                 script: Sequence[Any] = ()) -> dict[str, Any]:
    """没有任何 Blueprint 的新作品（空态 / 首次生成）。"""

    build_novel(tmp_path, novel_id, title="Studio 空作品",
                fact_text="工作室规则：供电优先级高于个人装备。")
    gateway, provider = stub_gateway(list(script))
    client = studio_app(tmp_path, gateway=gateway)
    return {"root": tmp_path, "novel_id": novel_id, "client": client,
            "gateway": gateway, "provider": provider}


__all__ = [
    "EXPORTER_PLUGIN", "NOVEL_ID", "ROOT", "active_plugin", "build_novel",
    "chapter_payload", "clean_studio", "character_payload", "delivery_stack",
    "character_arc_payload", "story_arc_payload", "unit_payload",
    "empty_studio", "exporter_manifest", "plugin_host", "premise_payload",
    "repair_script", "repaired_chapter_payload", "repaired_scene_payload",
    "scene_payload", "stub_gateway", "studio_app", "world_payload",
    "write_manifest",
]
