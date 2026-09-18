"""V4-09 §56、§58、§62、§100：没有 secret / traceback / 私有路径泄漏。"""

from __future__ import annotations

import ast
import json
from pathlib import Path

from novelforge.interfaces.mcp.serialization import assert_no_secrets
from novelforge.persistence.paths import plugin_audit_path, plugin_enablement_path

from plugins_support import (
    EXPORTER_PLUGIN,
    LEAKY_MODULE,
    NOVEL_ID,
    active_plugin,
    exporter_manifest,
    install,
    plugin_host,
    write_manifest,
)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def test_no_secrets_in_manifest_enablement_state_or_audit(tmp_path: Path) -> None:
    host = plugin_host(tmp_path, manifests=[exporter_manifest(tmp_path)])
    host.discover()
    record = install(host, EXPORTER_PLUGIN)
    context = host.manager.context(EXPORTER_PLUGIN)
    context._state.save({"note": "plugin cache"})      # type: ignore[union-attr]

    enablement = _read_json(plugin_enablement_path(tmp_path))
    audit = _read_json(plugin_audit_path(tmp_path))
    state = _read_json(tmp_path / "novel" / "authoring" / "story_engine" /
                       "plugins" / "state" / NOVEL_ID / EXPORTER_PLUGIN /
                       "state.json")
    for payload in (enablement, audit, state, record):
        assert assert_no_secrets(payload) == [], assert_no_secrets(payload)
    text = json.dumps(enablement, ensure_ascii=False) + \
        json.dumps(audit, ensure_ascii=False) + json.dumps(state, ensure_ascii=False)
    for token in ("API_KEY", "api_key", "Authorization", "Bearer ", "sk-"):
        assert token not in text


def test_plugin_error_message_does_not_leak_path_or_secret(tmp_path: Path) -> None:
    """§58：失败插件的 error_message 不得带出绝对路径 / secret / traceback。"""

    manifest = write_manifest(tmp_path, "com.example.leaky", module=LEAKY_MODULE,
                              capabilities=("exporter",),
                              permissions=("delivery.export",))
    host = plugin_host(tmp_path, manifests=[manifest])
    host.discover()
    active_plugin(host, "com.example.leaky")
    result = host.manager.execute("com.example.leaky", "leaky")
    assert result.ok is False
    assert result.error_code == "PLUGIN_EXECUTION_FAILED"
    message = result.message
    assert "C:\\" not in message and "sk-live" not in message
    assert "Traceback" not in message
    record = host.service.get_plugin("com.example.leaky")
    assert "C:\\" not in record.get("error_message", "")
    audit_text = json.dumps(host.service.audit(), ensure_ascii=False)
    assert "C:\\\\Users" not in audit_text


def test_studio_trust_note_matches_plugin_contract() -> None:
    """UI（api/studio_routes）与插件平台必须对作者说同一句信任声明。"""

    from novelforge.api.studio_routes import TRUST_MODEL, TRUST_MODEL_NOTE
    from novelforge.plugins import TRUST_MODEL as PLUGIN_TRUST_MODEL
    from novelforge.plugins import permission_note

    assert TRUST_MODEL == PLUGIN_TRUST_MODEL
    assert TRUST_MODEL_NOTE == permission_note()


def test_no_automatic_remote_install_surface() -> None:
    """§16：V4-09 不提供 marketplace / 下载 / pip install 能力。"""

    import novelforge.plugins as plugins

    names = {name.lower() for name in plugins.__all__}
    for token in ("install_plugin", "uninstall", "download", "marketplace",
                  "fetch", "upgrade", "pip"):
        assert not [name for name in names if token in name], token
    package = Path(plugins.__file__).resolve().parent
    for path in sorted(package.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                imported = [node.module or ""]
            else:
                continue
            for name in imported:
                assert not name.startswith(("urllib", "httpx", "requests",
                                            "subprocess", "pip"))


def test_delivery_package_has_no_plugin_secret_leak(tmp_path: Path) -> None:
    """§100：交付包里不出现 plugin secret / 私有路径。"""

    from plugins_support import delivery_stack

    stack = delivery_stack(tmp_path)
    host = plugin_host(tmp_path, manifests=[exporter_manifest(tmp_path)])
    host.discover()
    active_plugin(host, EXPORTER_PLUGIN)
    services = host.services(NOVEL_ID, gateway=stack["gateway"],
                             memory=stack["memory"])
    selection = services.export.delivery_selection(
        selection_mode="accepted", profile="author", formats=("tlist",))
    from novelforge.delivery import DeliveryRequest

    result = services.export.delivery().deliver(DeliveryRequest(selection=selection))
    assert result.status == "delivered"
    artifact = result.artifacts[0]
    assert str(tmp_path) not in artifact.content.decode("utf-8")
    assert assert_no_secrets(result.manifest.as_dict()) == []
