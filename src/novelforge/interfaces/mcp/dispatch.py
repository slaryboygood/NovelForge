"""MCP dispatch（V4-08 §2、§29–§36、§41–§42、§55、§68–§69）。

```text
invoke_tool(name, arguments)   参数校验 → Application Service → Result Envelope
read_resource(uri)             URI 解析 → Application Service → 只读载荷（MIME 明确）
```

铁律：

```text
· MCP 只调用 application.services（由宿主注入 services_factory）
· 每个请求显式携带 novel_id（不做"当前作品"推断）
· 业务错误 → 稳定 MCP code（cause 保留原始业务 code），不泄漏 traceback / 路径
· 读操作 0 LLM 调用；mutation 的 revision / idempotency / dry_run 语义由业务层保证
```
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable, Mapping

from .contracts import ResourceSpec, ToolResult, ToolSpec
from .errors import (
    MCPDeliveryBlocked,
    MCPError,
    MCPInvalidArgument,
    MCPInternalError,
    MCPLLMUnavailable,
    MCPNodeNotFound,
    MCPOperationRejected,
    MCPOwnershipMismatch,
    MCPPreserveViolation,
    MCPQualityBlocked,
    MCPRequiresReview,
    MCPResourceNotFound,
    MCPRevisionConflict,
    InvocationRecord,
)
from .registry import MCPResourceRegistry, MCPToolRegistry
from .payloads import ResourcePayload
from .serialization import assert_no_secrets, sanitize
from .uri import ResourceTarget, parse_uri

#: 业务 error code → 稳定 MCP 错误类（duck typing：接口层不 import 业务错误类，§60）
_BUSINESS_CODE_MAP: Mapping[str, type[MCPError]] = {
    # core / blueprint
    "REVISION_CONFLICT": MCPRevisionConflict,
    "BLUEPRINT_NODE_NOT_FOUND": MCPNodeNotFound,
    "BLUEPRINT_OWNERSHIP_VIOLATION": MCPOwnershipMismatch,
    "BLUEPRINT_VALIDATION_FAILED": MCPInvalidArgument,
    "BLUEPRINT_STATUS_INVALID": MCPOperationRejected,
    # editor
    "EDITOR_NODE_NOT_FOUND": MCPNodeNotFound,
    "EDITOR_REVISION_CONFLICT": MCPRevisionConflict,
    "EDITOR_OWNERSHIP_MISMATCH": MCPOwnershipMismatch,
    "EDITOR_PRESERVE_VIOLATION": MCPPreserveViolation,
    "EDITOR_VALIDATION_FAILED": MCPInvalidArgument,
    "EDITOR_OPERATION_REJECTED": MCPOperationRejected,
    # generation
    "GENERATION_UNAVAILABLE": MCPLLMUnavailable,
    "GENERATION_VALIDATION_FAILED": MCPInvalidArgument,
    "REWRITE_PRESERVE_VIOLATION": MCPPreserveViolation,
    # quality / repair
    "QUALITY_SCOPE_INVALID": MCPOwnershipMismatch,
    "QUALITY_POLICY_INVALID": MCPInvalidArgument,
    "REPAIR_PLAN_INVALID": MCPInvalidArgument,
    "REPAIR_CONTRACT_CONFLICT": MCPRequiresReview,
    "REPAIR_NOT_ALLOWED": MCPRequiresReview,
    "REPAIR_ROUND_LIMIT": MCPRequiresReview,
    # delivery
    "DELIVERY_OWNERSHIP_MISMATCH": MCPOwnershipMismatch,
    "DELIVERY_SELECTION_INVALID": MCPInvalidArgument,
    "DELIVERY_FORMAT_UNSUPPORTED": MCPInvalidArgument,
    "DELIVERY_VALIDATION_FAILED": MCPDeliveryBlocked,
    "DELIVERY_EXPORT_FAILED": MCPDeliveryBlocked,
}

#: 允许出现在客户端错误详情里的 key（避免把内部细节透出去）
SAFE_DETAIL_KEYS: tuple[str, ...] = (
    "node_id", "node_ids", "revision", "expected_revision", "actual_revision",
    "artifact_id", "issue_id", "issue_ids", "code", "status", "reason",
    "fields", "structural_fields", "protected_fields", "violating_fields",
    "conflict_diff", "blocking_reason", "missing", "selection_mode", "formats",
)

#: 已知业务异常基类名（未列出的异常视为内部错误，不冒充业务拒绝，§31）
KNOWN_BUSINESS_ERROR_NAMES: tuple[str, ...] = (
    "EditorError", "BlueprintError", "GenerationError", "QualityError",
    "DeliveryError", "MemoryIsolationError", "StoryOutlineError",
    "EditorOperationRejected", "BlueprintStatusError", "RepairPlanError",
)


def map_error(exc: BaseException, *, novel_id: str = "",
              request_id: str = "") -> MCPError:
    """把业务异常映射为稳定 MCP 错误（保留原始 code 到 cause，§68）。"""

    if isinstance(exc, MCPError):
        if not exc.cause:
            exc.cause = exc.code          # 接口层错误的 cause 即自身 code（稳定链）
        if novel_id and not exc.details.get("novel_id"):
            exc.details.setdefault("novel_id", novel_id)
        return exc
    business_code = str(getattr(exc, "code", "") or "")
    name = type(exc).__name__
    mapped = _BUSINESS_CODE_MAP.get(business_code)
    if mapped is None:
        if name in ("RevisionConflict", "EditorConflictError"):
            mapped = MCPRevisionConflict
        elif "Ownership" in name or "Isolation" in name:
            mapped = MCPOwnershipMismatch
        elif "Preserve" in name:
            mapped = MCPPreserveViolation
        elif "NotFound" in name:
            mapped = MCPNodeNotFound
        elif name in ("ValidationError", "ValueError"):
            mapped = MCPInvalidArgument
        elif "Unavailable" in name:
            mapped = MCPLLMUnavailable
        elif name in KNOWN_BUSINESS_ERROR_NAMES or \
                any(name.startswith(prefix) for prefix in
                    ("Editor", "Blueprint", "Generation", "Quality", "Delivery",
                     "Repair")):
            mapped = MCPOperationRejected
        else:
            mapped = MCPInternalError
    raw_details = dict(getattr(exc, "details", {}) or {})
    details = {key: raw_details[key] for key in SAFE_DETAIL_KEYS
               if key in raw_details}
    if novel_id:
        details.setdefault("novel_id", novel_id)
    message = str(getattr(exc, "message", "") or exc)[:400]
    if mapped is MCPInternalError and not business_code:
        message = f"内部错误（{name}）：{message[:200]}"
    if business_code and business_code not in message:
        message = f"{message}（{business_code}）"
    return mapped(message, cause=business_code, details=details,
                  request_id=request_id)


class MCPDispatcher:
    """协议无关的调用入口（in-process 测试与 SDK adapter 共用）。"""

    def __init__(self, project_root: Path | str, *,
                 services_factory: Callable[..., Any] | None = None,
                 tools: MCPToolRegistry | None = None,
                 resources: MCPResourceRegistry | None = None,
                 max_records: int = 500) -> None:
        from .resources import build_resource_registry
        from .tools import build_tool_registry

        self.project_root = Path(project_root)
        self.services_factory = services_factory
        self.tools = tools or build_tool_registry()
        self.resources = resources or build_resource_registry(
            spec_source=self._spec_tables)
        self._services: dict[str, Any] = {}
        self._records: list[InvocationRecord] = []
        self._max_records = max(1, int(max_records))

    # ------------------------------------------------------------------ 服务
    def services_for(self, novel_id: str, **kwargs: Any) -> Any:
        """按 novel_id 惰性构造 Application 能力束（§42：不预加载全部作品）。"""

        key = str(novel_id or "").strip()
        if not key:
            raise MCPInvalidArgument("必须显式提供 novel_id（不允许隐式当前作品）")
        if key not in self._services:
            if self.services_factory is None:
                raise MCPOperationRejected("MCP server 未注入 services_factory")
            self._services[key] = self.services_factory(self.project_root, key,
                                                        **kwargs)
        return self._services[key]

    def forget_services(self) -> None:
        """丢弃缓存的能力束（测试 / 长驻服务释放资源用）。"""

        self._services.clear()

    # ------------------------------------------------------------------ 工具
    def invoke_tool(self, name: str, arguments: Mapping[str, Any] | None = None,
                    *, request_id: str = "") -> dict[str, Any]:
        started = time.perf_counter()
        args = dict(arguments or {})
        novel_id = str(args.get("novel_id") or "")
        status, error_code, cause = "ok", "", ""
        try:
            registration = self.tools.get(name)
            context = self.services_for(novel_id)
            result = registration.handler(context, args)
            envelope = self._envelope(registration.spec, result,
                                      novel_id=novel_id, request_id=request_id)
        except BaseException as exc:  # noqa: BLE001 - 统一映射，绝不外泄 traceback
            error = map_error(exc, novel_id=novel_id, request_id=request_id)
            status, error_code, cause = "error", error.code, error.cause
            envelope = ToolResult(operation=str(name), ok=False, novel_id=novel_id,
                                  request_id=request_id or error.request_id,
                                  errors=(error.as_dict(),)).as_dict()
        self._record(InvocationRecord(
            request_id=str(envelope.get("request_id") or ""), kind="tool",
            name=str(name), novel_id=novel_id, operation=str(name), status=status,
            error_code=error_code, cause=cause,
            latency_ms=int((time.perf_counter() - started) * 1000),
            extra={"mutation": bool(getattr(self.tools.get(name).spec, "mutation", True))
                   if status == "ok" else False}))
        return envelope

    # ------------------------------------------------------------------ 资源
    def read_resource(self, uri: str) -> ResourcePayload:
        started = time.perf_counter()
        target = parse_uri(uri)
        novel_id = target.novel_id
        status, error_code, cause = "ok", "", ""
        try:
            registration = self.resources.resolve(target)
            context = (self.services_for(novel_id) if novel_id else None)
            payload = registration.handler(context, target)
            if not isinstance(payload, ResourcePayload):
                raise MCPOperationRejected(
                    f"资源处理器返回了非法类型：{type(payload).__name__}")
            return self._clean(payload)
        except BaseException as exc:  # noqa: BLE001
            error = map_error(exc, novel_id=novel_id)
            status, error_code, cause = "error", error.code, error.cause
            if isinstance(error, MCPResourceNotFound):
                raise
            raise MCPResourceNotFound(error.message, cause=error.cause,
                                      details=error.details) from exc
        finally:
            self._record(InvocationRecord(
                request_id="", kind="resource", name=str(uri), novel_id=novel_id,
                operation=target.kind, status=status, error_code=error_code,
                cause=cause,
                latency_ms=int((time.perf_counter() - started) * 1000)))

    # ------------------------------------------------------------------ 内部
    @staticmethod
    def _envelope(spec: ToolSpec, result: Any, *, novel_id: str,
                  request_id: str) -> dict[str, Any]:
        if isinstance(result, ToolResult):
            envelope = result.as_dict()
            if novel_id and not envelope.get("novel_id"):
                envelope["novel_id"] = novel_id
            if request_id and not result.request_id:
                envelope["request_id"] = request_id
        elif isinstance(result, Mapping):
            envelope = ToolResult(operation=spec.name, novel_id=novel_id,
                                  request_id=request_id,
                                  result=dict(result)).as_dict()
        else:
            raise MCPOperationRejected(
                f"tool {spec.name} 返回了非法类型：{type(result).__name__}")
        envelope["tool_version"] = spec.version
        envelope["read_only"] = spec.read_only
        return sanitize(envelope)

    @staticmethod
    def _clean(payload: ResourcePayload) -> ResourcePayload:
        if isinstance(payload.content, bytes):
            return payload                       # 二进制（交付 artifact）按 MIME 原样返回
        cleaned = sanitize(payload.content)
        import json

        hits = assert_no_secrets(json.loads(cleaned) if cleaned.strip().startswith(("{", "["))
                                 else cleaned)
        notes = payload.notes
        if hits:
            notes = (*notes, f"redacted:{len(hits)}")
        return ResourcePayload(uri=payload.uri, content=cleaned,
                               mime_type=payload.mime_type, spec=payload.spec,
                               notes=notes)

    def _record(self, record: InvocationRecord) -> None:
        self._records.append(record)
        if len(self._records) > self._max_records:
            del self._records[: len(self._records) - self._max_records]

    def invocations(self) -> list[dict[str, Any]]:
        """接口层 observability（§69）：内存记录，不含敏感内容。"""

        return [row.as_dict() for row in self._records]

    def clear_invocations(self) -> None:
        self._records.clear()

    def tool_specs(self) -> tuple[ToolSpec, ...]:
        return self.tools.specs()

    def resource_specs(self) -> tuple[ResourceSpec, ...]:
        return self.resources.specs()

    def _spec_tables(self) -> dict[str, Any]:
        """接口自描述资源的数据源（§54）。"""

        return {"tools": self.tools.specs(), "resources": self.resources.specs()}


__all__ = ["MCPDispatcher", "ResourcePayload", "SAFE_DETAIL_KEYS", "map_error"]
