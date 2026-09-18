"""Quality evaluator 扩展（V4-09 §35–§37、§78–§79、§96）。

插件只能**追加** evaluator；执行顺序 / policy / gate / evidence / report 仍由
`QualityService` 负责。默认：插件 evaluator 不参与（除非 policy 显式启用），
且默认 non-blocking（不因安装插件而阻断 Delivery）。
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..contracts import PLUGIN_PERMISSIONS, PluginContribution
from ..errors import PluginRegistrationError
from . import BaseAdapter


class QualityEvaluatorAdapter(BaseAdapter):
    type = "quality_evaluator"
    permission = "quality.evaluate"

    def core_ids(self) -> tuple[str, ...]:
        if hasattr(self.registry, "evaluators"):
            return tuple(str(spec.evaluator_id) for spec in self.registry.evaluators())
        return ()

    def register(self, *, plugin_id: str, plugin_version: str,
                 contribution: PluginContribution,
                 approved_permissions: Sequence[str] = ()) -> str:
        metadata = dict(contribution.metadata or {})
        gate = str(metadata.get("gate") or "").strip()
        if not gate:
            raise PluginRegistrationError(
                "quality evaluator 贡献缺少 gate",
                details={"plugin_id": plugin_id,
                         "contribution_id": contribution.contribution_id})
        factory = contribution.factory
        if not callable(factory):
            raise PluginRegistrationError(
                "quality evaluator 贡献的 factory 必须可调用",
                details={"plugin_id": plugin_id, "gate": gate})
        from novelforge.quality import EvaluatorSpec

        self._declare_issue_codes(plugin_id=plugin_id, gate=gate, metadata=metadata)
        evaluator_id = self.namespaced(plugin_id, contribution.contribution_id)
        self.check_core_conflict(evaluator_id, core_ids=self.core_ids())
        spec = EvaluatorSpec(
            evaluator_id=evaluator_id, version=int(contribution.version),
            gate=gate,
            # 插件 evaluator 由 policy 显式启用；kind 仍是 deterministic（插件代码同步执行）
            kind=str(metadata.get("kind") or "deterministic"),
            supported_node_types=tuple(str(value) for value in
                                       (metadata.get("supported_node_types") or ())),
            required_context=("blueprint_nodes",),
            description=str(metadata.get("description")
                            or f"plugin evaluator（{plugin_id}@{plugin_version}）"),
            owner_type="plugin", owner_id=plugin_id)
        self.registry.register(spec, self._wrap(plugin_id, factory))
        return evaluator_id

    @staticmethod
    def _declare_issue_codes(*, plugin_id: str, gate: str,
                             metadata: Mapping[str, Any]) -> tuple[str, ...]:
        """注册贡献声明的 issue code（§36、§72）。

        插件必须在 `quality_contribution(issue_codes=...)` 里声明它要用到的 code；
        Host 在注册时把它注册成 `plugin.<plugin_id>.<CODE>`（禁止 Core code）。
        """

        from novelforge.quality.codes import is_registered, register_plugin_code

        declared: list[str] = []
        for entry in metadata.get("issue_codes") or ():
            if isinstance(entry, Mapping):
                raw = str(entry.get("code") or "")
                severity = str(entry.get("severity") or "minor")
                description = str(entry.get("description") or "")
                repairable = bool(entry.get("repairable", False))
            else:
                raw, severity, description, repairable = str(entry), "minor", "", False
            code = raw if raw.startswith("plugin.") else f"plugin.{plugin_id}.{raw}"
            if not is_registered(code):
                register_plugin_code(code, gate=gate, severity=severity,
                                     plugin_id=plugin_id,
                                     description=description, repairable=repairable)
            declared.append(code)
        return tuple(declared)

    @staticmethod
    def _wrap(plugin_id: str, factory: Any) -> Any:
        """包装插件 evaluator：强制 issue code namespace + 动态注册（§36、§72）。"""

        def evaluate(context: Any) -> Any:
            from novelforge.quality import QualityIssue
            from novelforge.quality.codes import register_plugin_code

            rows = factory(context) or ()
            resolved = []
            for row in rows:
                if isinstance(row, QualityIssue):
                    if not str(row.code).startswith(f"plugin.{plugin_id}."):
                        raise PluginRegistrationError(
                            f"插件 issue code 未 namespaced：{row.code}",
                            plugin_id=plugin_id,
                            details={"code": str(row.code),
                                     "expected_prefix": f"plugin.{plugin_id}."})
                    resolved.append(row)
                    continue
                if isinstance(row, Mapping):
                    code = str(row.get("code") or "")
                    register_plugin_code(code, gate=str(row.get("gate") or "Q8"),
                                         severity=str(row.get("severity") or "minor"),
                                         plugin_id=plugin_id,
                                         description=str(row.get("reason") or ""))
                    from novelforge.plugins.sdk.quality import quality_issue

                    resolved.append(quality_issue(
                        context, code=code, reason=str(row.get("reason") or ""),
                        node_ids=tuple(row.get("node_ids") or ()),
                        severity=str(row.get("severity") or "minor"),
                        explanation=str(row.get("explanation") or ""),
                        excerpt=str(row.get("excerpt") or "")))
                    continue
                raise PluginRegistrationError(
                    f"插件 evaluator 返回了非法对象：{type(row).__name__}",
                    plugin_id=plugin_id)
            return tuple(resolved)

        return evaluate

    def unregister(self, *, plugin_id: str) -> int:
        from novelforge.quality.codes import unregister_plugin_codes

        unregister_plugin_codes(str(plugin_id))
        return super().unregister(plugin_id=plugin_id)


__all__ = ["QualityEvaluatorAdapter"]
