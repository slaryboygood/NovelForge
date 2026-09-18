"""V4-09 §9–§18、§22、§26、§55–§57：插件契约（manifest / id / 状态 / 贡献 / 错误）。"""

from __future__ import annotations

import pytest

from novelforge.plugins import (
    CONTRIBUTION_TYPES,
    PLUGIN_API_VERSION,
    PLUGIN_ENTRY_POINT_GROUP,
    PLUGIN_PERMISSIONS,
    PLUGIN_STATUSES,
    PLUGIN_TRANSITIONS,
    RESERVED_NAMESPACES,
    TRUST_MODEL,
    TRUST_MODEL_NOTE,
    PluginConflictError,
    PluginContribution,
    PluginDescriptor,
    PluginExecutionError,
    PluginManifest,
    PluginManifestError,
    PluginNotFoundError,
    PluginPermissionError,
    PluginResult,
    assert_transition,
    can_transition,
    lifecycle_table,
    next_statuses,
    permission_note,
    plugin_namespace,
    validate_plugin_id,
)
from novelforge.plugins.contracts import contribution_error

VALID_ID = "com.example.plugin"


def _manifest(**overrides) -> PluginManifest:
    payload = {"plugin_id": VALID_ID, "name": "Example", "version": "1.0.0",
               "entry_point": "example_module:register",
               "capabilities": ("exporter",), "permissions": ("delivery.export",)}
    payload.update(overrides)
    return PluginManifest(**payload)


# ------------------------------------------------------------------ plugin_id
def test_plugin_id_requires_namespace() -> None:
    assert validate_plugin_id(VALID_ID) == VALID_ID
    assert validate_plugin_id("org.author.thing-1_2") == "org.author.thing-1_2"
    for bad in ("plugin1", "test", "new_plugin", "com", ""):
        with pytest.raises(PluginManifestError):
            validate_plugin_id(bad)


def test_plugin_id_rejects_reserved_namespace_and_bad_segments() -> None:
    assert RESERVED_NAMESPACES == ("novelforge", "core")
    for bad in ("novelforge.plugin", "core.plugin", "com.Example.plugin",
                "com..plugin"):
        with pytest.raises(PluginManifestError):
            validate_plugin_id(bad)


def test_plugin_namespace_is_stable() -> None:
    assert plugin_namespace(VALID_ID) == f"plugin.{VALID_ID}"
    assert plugin_namespace(VALID_ID) == plugin_namespace(VALID_ID)


# ------------------------------------------------------------------- manifest
def test_manifest_requires_core_fields() -> None:
    for missing in ("name", "version", "entry_point"):
        with pytest.raises(PluginManifestError):
            _manifest(**{missing: ""})


def test_manifest_rejects_unknown_permission_and_capability() -> None:
    with pytest.raises(PluginManifestError):
        _manifest(permissions=("delivery.export", "root.everything"))
    with pytest.raises(PluginManifestError):
        _manifest(capabilities=("exporter", "core_override"))


def test_manifest_rejects_invalid_api_version() -> None:
    with pytest.raises(PluginManifestError):
        _manifest(plugin_api_version=0)


def test_manifest_roundtrip_and_digest() -> None:
    manifest = _manifest(description="说明", author="作者", homepage="https://x")
    assert PluginManifest.from_dict(manifest.as_dict()) == manifest
    assert manifest.digest == _manifest(description="说明", author="作者",
                                        homepage="https://x").digest
    assert manifest.digest != _manifest(version="1.0.1").digest
    assert manifest.namespace == f"plugin.{VALID_ID}"


def test_descriptor_exposes_ui_contract_fields() -> None:
    descriptor = PluginDescriptor(manifest=_manifest(), source="manifest_path",
                                  locator="com.example.plugin.json",
                                  status="compatible",
                                  manifest_digest=_manifest().digest)
    row = descriptor.as_dict()
    for key in ("plugin_id", "name", "version", "plugin_api_version", "description",
                "capabilities", "permissions", "author", "homepage", "entry_point",
                "status", "compatibility", "manifest_digest"):
        assert key in row
    assert row["plugin_id"] == VALID_ID


# --------------------------------------------------------------- contribution
def test_contribution_validates_type_id_factory_and_permissions() -> None:
    factory = lambda: None  # noqa: E731 - 测试用占位
    ok = PluginContribution(type="exporter", contribution_id="plain", factory=factory,
                            permissions_required=("delivery.export",))
    assert ok.namespaced_id(VALID_ID) == f"plugin.{VALID_ID}.plain"
    with pytest.raises(PluginManifestError):
        PluginContribution(type="unknown", contribution_id="x", factory=factory)
    with pytest.raises(PluginManifestError):
        PluginContribution(type="exporter", contribution_id="", factory=factory)
    with pytest.raises(PluginManifestError):
        PluginContribution(type="exporter", contribution_id="x", factory=None)
    with pytest.raises(PluginManifestError):
        PluginContribution(type="exporter", contribution_id="x", factory=factory,
                           permissions_required=("root",))


def test_contribution_types_and_permissions_are_small_and_explicit() -> None:
    assert CONTRIBUTION_TYPES == ("exporter", "quality_evaluator", "mcp_tool",
                                  "mcp_resource")
    assert PLUGIN_PERMISSIONS == ("delivery.export", "quality.evaluate", "mcp.extend",
                                  "ai.invoke", "blueprint.read", "editor.mutate",
                                  "network.request", "plugin.state")
    assert PLUGIN_ENTRY_POINT_GROUP == "novelforge.plugins"
    assert PLUGIN_API_VERSION == 1


# ---------------------------------------------------------------- lifecycle
def test_lifecycle_statuses_and_transitions_are_consistent() -> None:
    assert PLUGIN_STATUSES == ("discovered", "compatible", "incompatible", "approved",
                               "enabled", "loaded", "active", "disabled", "failed")
    for status, targets in PLUGIN_TRANSITIONS.items():
        assert status in PLUGIN_STATUSES
        assert all(target in PLUGIN_STATUSES for target in targets)
    assert can_transition("discovered", "compatible")
    assert not can_transition("compatible", "active")     # 不能跳过 approve / enable
    assert not can_transition("discovered", "loaded")
    assert next_statuses("approved")[0] == "enabled"
    assert set(lifecycle_table()) == set(PLUGIN_STATUSES)
    assert assert_transition("active", "disabled") == "disabled"
    with pytest.raises(Exception):
        assert_transition("disabled", "active")


# ------------------------------------------------------------------- trust
def test_trust_model_is_honest_about_no_sandbox() -> None:
    assert TRUST_MODEL == "trusted_in_process"
    assert "sandbox" in TRUST_MODEL_NOTE
    note = permission_note()
    assert "sandbox" in note and "governance" in note


# ------------------------------------------------------------------ result
def test_plugin_result_carries_provenance() -> None:
    result = PluginResult(plugin_id=VALID_ID, plugin_version="2.0.0",
                          contribution_id="text-list", value={"ok": True})
    assert result.provenance == {"plugin_id": VALID_ID, "plugin_version": "2.0.0",
                                 "plugin_api_version": 1,
                                 "contribution_id": "text-list"}
    assert result.as_dict()["provenance"]["plugin_id"] == VALID_ID


def test_contribution_error_maps_to_stable_code_without_leaking_paths() -> None:
    result = contribution_error(VALID_ID, "1.0.0", "text-list",
                                RuntimeError(r"崩了：C:\Users\alice\a.py"))
    assert result.ok is False
    assert result.error_code == "PLUGIN_EXECUTION_FAILED"
    assert "C:" not in result.message and "<path>" in result.message
    assert result.provenance["plugin_version"] == "1.0.0"


# -------------------------------------------------------------- error codes
def test_error_classes_expose_stable_codes() -> None:
    from novelforge.plugins import (
        PluginCompatibilityError,
        PluginConfigError,
        PluginError,
        PluginLoadError,
        PluginNotApprovedError,
        PluginRegistrationError,
    )

    expected = {
        PluginError: "PLUGIN_ERROR",
        PluginManifestError: "PLUGIN_MANIFEST_INVALID",
        PluginCompatibilityError: "PLUGIN_INCOMPATIBLE",
        PluginPermissionError: "PLUGIN_PERMISSION_DENIED",
        PluginNotApprovedError: "PLUGIN_NOT_APPROVED",
        PluginLoadError: "PLUGIN_LOAD_FAILED",
        PluginRegistrationError: "PLUGIN_REGISTRATION_FAILED",
        PluginConflictError: "PLUGIN_REGISTRATION_CONFLICT",
        PluginExecutionError: "PLUGIN_EXECUTION_FAILED",
        PluginNotFoundError: "PLUGIN_NOT_FOUND",
        PluginConfigError: "PLUGIN_CONFIG_INVALID",
    }
    for klass, code in expected.items():
        assert klass.code == code
        assert klass("boom", plugin_id=VALID_ID).as_dict()["code"] == code


def test_error_message_redacts_path_and_secret() -> None:
    from novelforge.plugins.errors import redact_message

    text = redact_message(r"失败 C:\Users\alice\x.json api_key=sk-abcdef123456")
    assert "C:\\Users" not in text and "<path>" in text
    assert "sk-abcdef123456" not in text


# ----------------------------------------------------------- public contract
def test_public_contract_is_small_and_explicit() -> None:
    import novelforge.plugins as plugins

    exported = set(plugins.__all__)
    required = {"PluginManager", "PluginRegistry", "PluginRecord", "PluginManifest",
                "PluginDescriptor", "PluginContribution", "PluginConfig",
                "PluginResult", "PLUGIN_API_VERSION", "PLUGIN_PERMISSIONS",
                "PLUGIN_STATUSES", "PLUGIN_TRANSITIONS", "TRUST_MODEL",
                "build_adapters", "PluginError", "can_transition",
                "check_compatibility", "EnablementStore", "PluginStateStore",
                "PluginAuditLog"}
    assert required <= exported
    assert not [name for name in exported if name.startswith("_")]
    # SDK / adapters 细节不进入包级 Public Contract（插件作者只依赖 sdk）
    assert "PluginContext" not in exported
    assert "ExporterAdapter" not in exported
    assert "PluginHost" not in exported      # composition root 在 plugins.host
