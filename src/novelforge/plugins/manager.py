"""PluginManager（V4-09 §17–§19、§48–§53、§63、§81）：发现 / 批准 / 启用 / 加载 / 禁用。

```text
discover（manifest only）→ validate → compatibility → approval → enable → load
→ inspect contributions → validate → register atomically → active
```

铁律：

```text
· 只有显式 approve + enable 的插件才会被 import（§17、§21、§91）
· 发现阶段不执行插件代码（§14）；不扫描项目目录（§61）；不做远程安装（§16）
· 一个插件加载失败 → status=failed，Core 与其它插件继续（§19、§81）
· 注册是原子的：任一贡献失败 → 回滚已注册项（§49）
```
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from .compatibility import check_compatibility
from .contracts import (
    PLUGIN_API_VERSION,
    TRUST_MODEL,
    TRUST_MODEL_NOTE,
    PluginConfig,
    PluginContribution,
    PluginDescriptor,
    PluginManifest,
    PluginResult,
)
from .discovery import (
    annotate_compatibility,
    dedupe_descriptors,
    discover_installed,
    discover_manifest_paths,
)
from .errors import (
    PluginCompatibilityError,
    PluginConflictError,
    PluginExecutionError,
    PluginLoadError,
    PluginNotApprovedError,
    PluginPermissionError,
    redact_message,
)
from .permissions import (
    check_approval,
    declared_permissions,
    requires_reapproval,
)
from .registry import PluginRecord, PluginRegistry
from .sdk.context import PluginContext
from .state import EnablementStore, PluginAuditLog, PluginStateStore

#: Host 支持的 capability（= 本阶段开放的 3 个扩展点 + 声明性能力）
SUPPORTED_CAPABILITIES: tuple[str, ...] = (
    "exporter", "quality_evaluator", "mcp_tool", "mcp_resource",
)


class PluginManager:
    """插件的唯一生命周期入口（Application 层的 PluginService 包装它）。"""

    def __init__(self, project_root: Path | str, *,
                 adapters: Mapping[str, Any] | None = None,
                 host_version: str = "4.9",
                 plugin_api_version: int = PLUGIN_API_VERSION,
                 novel_id: str = "",
                 entry_points: Sequence[Any] | None = None,
                 manifest_paths: Iterable[Path | str] = (),
                 trust_model: str = TRUST_MODEL) -> None:
        self.project_root = Path(project_root)
        self.adapters = dict(adapters or {})
        self.host_version = str(host_version)
        self.plugin_api_version = int(plugin_api_version)
        self.novel_id = str(novel_id)
        self.entry_points = entry_points
        self.manifest_paths = tuple(Path(value) for value in manifest_paths)
        self.trust_model = str(trust_model)
        self.registry = PluginRegistry()
        self.enablement = EnablementStore(self.project_root)
        self.audit = PluginAuditLog(self.project_root)
        self._contexts: dict[str, PluginContext] = {}

    # ================================================================= discover
    def discover(self) -> list[dict[str, Any]]:
        """发现插件并标注兼容性（**不执行插件代码**，§14）。"""

        descriptors: list[PluginDescriptor] = []
        if self.entry_points is not None:
            descriptors.extend(discover_installed(entries=self.entry_points))
        else:
            descriptors.extend(discover_installed())
        if self.manifest_paths:
            descriptors.extend(discover_manifest_paths(self.manifest_paths))
        annotated = annotate_compatibility(
            dedupe_descriptors(descriptors), host_api_version=self.plugin_api_version,
            host_version=self.host_version,
            supported_capabilities=SUPPORTED_CAPABILITIES)
        for descriptor in annotated:
            existing = self.registry.find(descriptor.plugin_id)
            record = self.registry.add(descriptor)
            if existing is None:
                record.status = descriptor.status      # 已加载插件保留自己的生命周期状态
            self.audit.record("discovered", plugin_id=descriptor.plugin_id,
                              version=descriptor.version, status=record.status,
                              extra={"source": descriptor.source,
                                     "compatible": descriptor.status == "compatible"})
        return self.registry.list_discovered()

    # ================================================================== approve
    def approve(self, plugin_id: str, *, permissions: Sequence[str] | None = None,
                approved_by: str = "user", note: str = "") -> dict[str, Any]:
        """用户显式批准：记录版本 + 权限集合（§54、§92）。"""

        record = self.registry.get(plugin_id)
        if record.status == "incompatible":
            raise PluginCompatibilityError(
                f"插件不兼容，不能批准：{record.descriptor.compatibility.get('reason')}",
                plugin_id=plugin_id,
                details=dict(record.descriptor.compatibility))
        approved = tuple(permissions) if permissions is not None else \
            declared_permissions(record.manifest)
        check_approval(record.manifest, approved_permissions=approved,
                       requested=approved)
        self.enablement.approve(plugin_id, version=record.manifest.version,
                                permissions=approved,
                                package_digest=record.manifest.package_digest,
                                approved_by=approved_by, note=note)
        record.approved_version = record.manifest.version
        record.approved_permissions = tuple(sorted(approved))
        record.status = "approved"
        self.audit.record("approved", plugin_id=plugin_id,
                          version=record.manifest.version, status=record.status,
                          extra={"permissions": list(record.approved_permissions)})
        return record.as_dict()

    # =================================================================== enable
    def enable(self, plugin_id: str) -> dict[str, Any]:
        """批准 + 启用 + 加载（§17：discovered 不能直接 active）。"""

        record = self.registry.get(plugin_id)
        # §13 / §81：不兼容的插件绝不进入 load（即使曾被批准）
        compatibility = dict(record.descriptor.compatibility or {})
        if record.status == "incompatible" or compatibility.get("ok") is False:
            raise PluginCompatibilityError(
                f"插件与当前 Host 不兼容，不能启用：{compatibility.get('reason', '')}",
                plugin_id=plugin_id, details=compatibility)
        approval = self.enablement.get(plugin_id)
        if not approval.get("approved_version"):
            raise PluginNotApprovedError(
                f"插件尚未批准：{plugin_id}", plugin_id=plugin_id)
        needs, diff = requires_reapproval(
            approved_version=str(approval.get("approved_version") or ""),
            current_version=record.manifest.version,
            approved=approval.get("approved_permissions") or (),
            declared=declared_permissions(record.manifest),
            approved_digest=str(approval.get("package_digest") or ""),
            current_digest=record.manifest.package_digest)
        if needs and "permission_added" in diff["reasons"]:
            raise PluginPermissionError(
                f"插件升级新增了未批准 permission：{diff['permission_diff']['added']}",
                plugin_id=plugin_id,
                details={"reasons": diff["reasons"],
                         "permission_diff": diff["permission_diff"]})
        if needs:
            # 版本 / digest 变化：需要重新批准（保守）
            raise PluginNotApprovedError(
                f"插件内容已变化，需要重新批准：{diff['reasons']}",
                plugin_id=plugin_id, details=dict(diff))
        self.enablement.set_enabled(plugin_id, True)
        record.approved_permissions = tuple(approval.get("approved_permissions") or ())
        record.approved_version = str(approval.get("approved_version") or "")
        record.enabled = True
        record.status = "enabled"
        self.audit.record("enabled", plugin_id=plugin_id,
                          version=record.manifest.version, status=record.status)
        self.load(plugin_id)
        return record.as_dict()

    # =================================================================== disable
    def disable(self, plugin_id: str, *, reason: str = "") -> dict[str, Any]:
        """逻辑禁用：卸载该插件的贡献（Core 不受影响，§50、§74–§75）。"""

        record = self.registry.get(plugin_id)
        removed = self._unregister(record)
        self.enablement.set_enabled(plugin_id, False)
        self._contexts.pop(plugin_id, None)
        record.enabled = False
        record.status = "disabled"
        record.registered_ids = ()
        record.loaded = False
        self.audit.record("disabled", plugin_id=plugin_id,
                          version=record.manifest.version, status=record.status,
                          extra={"unregistered": removed, "reason": reason[:200],
                                 "restart_required": False})
        return record.as_dict()

    # ====================================================================== load
    def load(self, plugin_id: str) -> dict[str, Any]:
        """解析 entry point → 收集贡献 → 原子注册（§48–§49）。"""

        record = self.registry.get(plugin_id)
        if record.status not in ("enabled", "loaded", "active", "approved"):
            raise PluginNotApprovedError(
                f"插件未启用，不能加载：{record.status}", plugin_id=plugin_id)
        compatibility = dict(record.descriptor.compatibility or {})
        if compatibility.get("ok") is False:
            self._fail(record, PluginCompatibilityError(
                "插件不兼容当前 Host",
                plugin_id=plugin_id, details=compatibility))
            return record.as_dict()
        try:
            target = self._resolve_entry_point(record.manifest)
            # entry_point 既可以是 `module:register`（直接指向回调），
            # 也可以是 `module`（此时约定模块暴露 `register(context)`）
            factory = target if callable(target) else getattr(target, "register", None)
            if not callable(factory):
                raise PluginLoadError(
                    "插件模块必须提供 register(context) -> 贡献列表",
                    plugin_id=plugin_id)
            context = self._build_context(record)
            raw = factory(context) or ()
            contributions = tuple(row.as_host_contribution()
                                  if hasattr(row, "as_host_contribution") else row
                                  for row in raw)
            for row in contributions:
                if not isinstance(row, PluginContribution):
                    raise PluginLoadError(
                        f"插件返回了非 contribution 对象：{type(row).__name__}",
                        plugin_id=plugin_id)
                check_approval(record.manifest,
                               approved_permissions=record.approved_permissions,
                               requested=row.permissions_required)
        except BaseException as exc:  # noqa: BLE001 - 失败隔离（§19、§58）
            self._fail(record, exc, default_code="PLUGIN_LOAD_FAILED")
            return record.as_dict()
        try:
            registered = self._register(record, contributions)
        except BaseException as exc:  # noqa: BLE001 - 注册阶段失败（§49）
            self._fail(record, exc, default_code="PLUGIN_REGISTRATION_FAILED")
            return record.as_dict()
        record.contributions = contributions
        record.registered_ids = tuple(registered)
        record.loaded = True
        record.status = "active"
        self.audit.record("loaded", plugin_id=plugin_id,
                          version=record.manifest.version, status=record.status,
                          extra={"contributions": len(contributions),
                                 "registered": list(registered)})
        return record.as_dict()

    # ================================================================== 运行时
    def execute(self, plugin_id: str, contribution_id: str,
                *args: Any, **kwargs: Any) -> PluginResult:
        """在 Host 控制下执行插件贡献（失败映射为 PLUGIN_EXECUTION_FAILED，§58）。"""

        record = self.registry.get(plugin_id)
        if not record.active:
            raise PluginNotApprovedError(
                f"插件未激活：{plugin_id}（status={record.status}）",
                plugin_id=plugin_id)
        contribution = next((row for row in record.contributions
                             if row.contribution_id == contribution_id), None)
        if contribution is None:
            raise PluginExecutionError(
                f"未知贡献：{contribution_id}", plugin_id=plugin_id,
                details={"contribution_id": contribution_id})
        try:
            value = contribution.factory(*args, **kwargs)
        except BaseException as exc:  # noqa: BLE001 - 不泄漏 traceback
            result = PluginResult(
                plugin_id=plugin_id, plugin_version=record.manifest.version,
                contribution_id=contribution_id, ok=False,
                error_code="PLUGIN_EXECUTION_FAILED",
                message=redact_message(f"{type(exc).__name__}: {exc}"))
            self.audit.record("execution_failed", plugin_id=plugin_id,
                              version=record.manifest.version, status="failed",
                              error_code=result.error_code,
                              extra={"contribution_id": contribution_id})
            return result
        return PluginResult(plugin_id=plugin_id, plugin_version=record.manifest.version,
                            contribution_id=contribution_id, ok=True, value=value)

    # ===================================================================== 查询
    def list_discovered(self) -> list[dict[str, Any]]:
        return self.registry.list_discovered()

    def list_enabled(self) -> list[dict[str, Any]]:
        return self.registry.list_enabled()

    def get(self, plugin_id: str) -> dict[str, Any]:
        return self.registry.get(plugin_id).as_dict()

    def context(self, plugin_id: str) -> PluginContext | None:
        """Host 侧持有 / 检视插件上下文（least privilege，§24–§25）。

        未加载的插件没有上下文；返回值是 Host 注入给该插件的**同一个**窄对象。
        """

        self.registry.get(plugin_id)          # 未知插件 → PluginNotFoundError
        return self._contexts.get(plugin_id)

    def contributions(self, *, type: str = "") -> list[dict[str, Any]]:
        return self.registry.contributions(type=type)

    def status(self) -> dict[str, Any]:
        return {**self.registry.status(), "trust_model": self.trust_model,
                "trust_note": TRUST_MODEL_NOTE,
                "enablement": self.enablement.records()}

    def audit_records(self) -> list[dict[str, Any]]:
        return self.audit.records()

    # ==================================================================== 内部
    def _resolve_entry_point(self, manifest: PluginManifest) -> Any:
        module_name, _, attribute = str(manifest.entry_point).partition(":")
        if not module_name:
            raise PluginLoadError("entry_point 必须形如 module:attribute",
                                  plugin_id=manifest.plugin_id)
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:  # noqa: BLE001
            raise PluginLoadError(
                f"插件模块无法导入：{module_name}（{type(exc).__name__}）",
                plugin_id=manifest.plugin_id,
                details={"module": module_name}) from exc
        if not attribute:
            return module
        target: Any = module
        for part in attribute.split("."):
            target = getattr(target, part, None)
            if target is None:
                raise PluginLoadError(
                    f"entry_point 属性不存在：{attribute}",
                    plugin_id=manifest.plugin_id)
        return target

    def _build_context(self, record: PluginRecord) -> PluginContext:
        state = (PluginStateStore(self.project_root, self.novel_id, record.plugin_id)
                 if self.novel_id else None)
        context = PluginContext(
            plugin_id=record.plugin_id, plugin_version=record.manifest.version,
            approved_permissions=tuple(record.approved_permissions),
            config=PluginConfig(plugin_id=record.plugin_id,
                                values=self._config_values(record.plugin_id)),
            _state=state, metadata={"host_version": self.host_version,
                                    "trust_model": self.trust_model})
        self._contexts[record.plugin_id] = context
        return context

    def _config_values(self, plugin_id: str) -> dict[str, Any]:
        payload = self.enablement.get(plugin_id)
        return dict(payload.get("config") or {})

    def _register(self, record: PluginRecord,
                  contributions: Sequence[PluginContribution]) -> list[str]:
        """原子注册：任一贡献失败 → 回滚（§49）。"""

        registered: list[str] = []
        try:
            for contribution in contributions:
                adapter = self.adapters.get(contribution.type)
                if adapter is None:
                    raise PluginConflictError(
                        f"Host 未开放该扩展点：{contribution.type}",
                        plugin_id=record.plugin_id,
                        details={"type": contribution.type})
                registered.append(adapter.register(
                    plugin_id=record.plugin_id,
                    plugin_version=record.manifest.version,
                    approved_permissions=record.approved_permissions,
                    contribution=contribution))
        except BaseException:
            self._unregister(record)
            raise
        return registered

    def _unregister(self, record: PluginRecord) -> int:
        removed = 0
        for adapter in self.adapters.values():
            if hasattr(adapter, "unregister"):
                removed += int(adapter.unregister(plugin_id=record.plugin_id))
        return removed

    def _fail(self, record: PluginRecord, exc: BaseException, *,
              default_code: str = "PLUGIN_LOAD_FAILED") -> None:
        record.status = "failed"
        record.loaded = False
        record.registered_ids = ()
        # 稳定 code（§57）：只暴露宿主定义的 code，绝不把 Python 类名当稳定码
        code = str(getattr(exc, "code", "") or "") or str(default_code)
        record.error_code = code
        record.error_message = redact_message(str(getattr(exc, "message", "") or exc))
        self.audit.record("failed", plugin_id=record.plugin_id,
                          version=record.manifest.version, status="failed",
                          error_code=code,
                          extra={"message": record.error_message})


__all__ = ["SUPPORTED_CAPABILITIES", "PluginManager"]
