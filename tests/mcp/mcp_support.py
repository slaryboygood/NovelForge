"""MCP 测试 fixture（零网络、in-process、StubProvider）。

复用 V4-04→V4-07 的 Golden fixture（`tests/delivery/delivery_support.py`），
并用同一份 stub gateway 注入 `application.services.facade.application_services`，
从而 MCP 的生成 / 改写工具在测试中也是离线的。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))


def _load(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


_delivery_support = _load("delivery_support_for_mcp",
                          ROOT / "tests" / "delivery" / "delivery_support.py")

delivery_stack = _delivery_support.delivery_stack
repaired_scene_payload = _delivery_support.repaired_scene_payload
repaired_chapter_payload = _delivery_support.repaired_chapter_payload
repair_script = _delivery_support.repair_script
current_payload = _delivery_support.current_payload
scripted = _delivery_support._editor_support.scripted
NOVEL_ID = _delivery_support.NOVEL_ID


def mcp_stack(tmp_path: Path, *, novel_id: str = NOVEL_ID, clean: bool = True,
              repairable: bool = True, script: Sequence[Any] | None = None
              ) -> dict[str, Any]:
    """交付 fixture + MCP dispatcher（Application Services 注入同一 stub gateway）。"""

    from novelforge.application.services.facade import application_services
    from novelforge.interfaces.mcp import create_dispatcher

    stack = delivery_stack(tmp_path, novel_id=novel_id, clean=clean,
                           repairable=repairable, script=script)

    def factory(root: Any, target_novel: str, *, gateway: Any = None,
                memory: Any = None, **kwargs: Any) -> Any:
        return application_services(root, target_novel,
                                    gateway=stack["gateway"],
                                    memory=stack["memory"])

    stack["dispatcher"] = create_dispatcher(tmp_path, services_factory=factory)
    stack["root_path"] = tmp_path
    return stack


def envelope(dispatcher: Any, tool: str, **arguments: Any) -> dict[str, Any]:
    return dispatcher.invoke_tool(tool, arguments)


def error_code(envelope: dict[str, Any]) -> str:
    errors = envelope.get("errors") or []
    return str(errors[0]["code"]) if errors else ""


__all__ = ["NOVEL_ID", "current_payload", "delivery_stack", "envelope", "error_code",
           "mcp_stack", "repair_script", "repaired_chapter_payload", "scripted",
           "repaired_scene_payload"]
