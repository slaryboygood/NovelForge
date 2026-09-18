"""Delivery 契约（V4-07 §5–§11、§15、§19、§22、§39–§44、§51–§53）。

```text
DeliverySelection        这次交付选什么（mode / formats / profile / policy）
DeliveryPolicy           交付放行规则（accepted / quality / review / 内容完整性）
DeliverySnapshot         这次交付**钉住**了哪些 revision（不可歧义）
DeliveryManifest         交付清单（artifact / checksum / exporter 版本）
DeliveryIssue            交付问题（stable code）
DeliveryValidationResult preflight / post-build 结果
DeliveryRequest/Result   请求与统一结果
ExportArtifact           单个交付物
NovelForgePackage        .nfpack 结构描述
```

不变量（§5）：

```text
DELIVERY_READS_CANONICAL_ARTIFACTS  只读 blueprint / quality / editor metadata
DELIVERY_NEVER_INVENTS_STORY_CONTENT 不创作、不修复、不猜
DELIVERY_IS_REVISION_PINNED          snapshot 决定一切读取
DELIVERY_IS_NOVEL_ISOLATED           A 的交付不含 B 的任何数据
DELIVERY_IS_REPRODUCIBLE             同 snapshot + policy + exporter version → 同内容
DELIVERY_IS_VALIDATED_BEFORE_RELEASE preflight + post-build 双重校验
```
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from novelforge.core.ids import digest_payload, new_request_id

from .errors import DeliveryFormatError, DeliverySelectionError

#: 交付契约版本（与 BLUEPRINT_SCHEMA_VERSION 相互独立，§44）
DELIVERY_SCHEMA_VERSION = 1
PACKAGE_VERSION = 1

#: selection 模式（§8）
SELECTION_MODES: tuple[str, ...] = ("accepted", "explicit_revisions", "current")
DEFAULT_SELECTION_MODE = "accepted"

#: 导出 profile（§32）
EXPORT_PROFILES: tuple[str, ...] = ("reader", "author", "machine", "audit")
DEFAULT_PROFILE = "author"

#: 交付格式（§33）
EXPORT_FORMATS: tuple[str, ...] = ("json", "markdown", "docx", "nfpack")

#: profile → 默认包含项（可用 selection 覆盖）
PROFILE_DEFAULTS: Mapping[str, Mapping[str, bool]] = {
    "reader": {"include_quality_report": False, "include_provenance": False,
               "include_revision_history": False, "include_review_metadata": False},
    "author": {"include_quality_report": True, "include_provenance": True,
               "include_revision_history": False, "include_review_metadata": True},
    "machine": {"include_quality_report": True, "include_provenance": True,
                "include_revision_history": True, "include_review_metadata": True},
    "audit": {"include_quality_report": True, "include_provenance": True,
              "include_revision_history": True, "include_review_metadata": True},
}

#: 交付 issue 级别的 severity
DELIVERY_SEVERITIES: tuple[str, ...] = ("info", "warning", "blocker")


def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


@dataclass(frozen=True)
class DeliveryPolicy:
    """交付放行规则（§15）：不散落在 exporter 里。"""

    require_accepted: bool = True
    require_quality_pass: bool = True
    blocking_severities: tuple[str, ...] = ("blocker", "major")
    allow_unevaluated: bool = False
    allow_stale_quality: bool = False
    require_no_orphans: bool = True
    require_no_unpaid_required_setup: bool = True
    require_no_placeholders: bool = True
    require_no_pending_invalidation: bool = True
    partial_allowed: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {"require_accepted": self.require_accepted,
                "require_quality_pass": self.require_quality_pass,
                "blocking_severities": list(self.blocking_severities),
                "allow_unevaluated": self.allow_unevaluated,
                "allow_stale_quality": self.allow_stale_quality,
                "require_no_orphans": self.require_no_orphans,
                "require_no_unpaid_required_setup":
                    self.require_no_unpaid_required_setup,
                "require_no_placeholders": self.require_no_placeholders,
                "require_no_pending_invalidation":
                    self.require_no_pending_invalidation,
                "partial_allowed": self.partial_allowed}

    @property
    def digest(self) -> str:
        return digest_payload(self.as_dict())

    @classmethod
    def relaxed(cls) -> "DeliveryPolicy":
        """current 导出 / 草稿预览用（明确放宽，不隐藏风险）。"""

        return cls(require_accepted=False, require_quality_pass=False,
                   allow_unevaluated=True, allow_stale_quality=True,
                   require_no_pending_invalidation=False)


@dataclass(frozen=True)
class DeliverySelection:
    """这次交付选什么（§7–§8）。"""

    novel_id: str
    selection_mode: str = DEFAULT_SELECTION_MODE
    explicit_revisions: Mapping[str, int] = field(default_factory=dict)
    include_node_types: tuple[str, ...] = ()
    formats: tuple[str, ...] = ("json", "markdown")
    profile: str = DEFAULT_PROFILE
    include_quality_report: bool | None = None
    include_provenance: bool | None = None
    include_revision_history: bool | None = None
    include_review_metadata: bool | None = None
    package_includes_node_files: bool = False
    created_by: str = "author"
    request_id: str = ""
    policy: DeliveryPolicy = field(default_factory=DeliveryPolicy)

    def __post_init__(self) -> None:
        if not str(self.novel_id or "").strip():
            raise DeliverySelectionError("DeliverySelection 需要显式 novel_id")
        if self.selection_mode not in SELECTION_MODES:
            raise DeliverySelectionError(
                f"未知 selection_mode：{self.selection_mode}",
                details={"known": list(SELECTION_MODES)})
        if self.profile not in EXPORT_PROFILES:
            raise DeliverySelectionError(f"未知 profile：{self.profile}",
                                         details={"known": list(EXPORT_PROFILES)})
        if self.selection_mode == "explicit_revisions" and not self.explicit_revisions:
            raise DeliverySelectionError(
                "explicit_revisions 模式必须提供 node_id → revision")
        if not self.formats:
            raise DeliveryFormatError("至少需要一种导出格式")
        unknown = [str(fmt) for fmt in self.formats if str(fmt) not in EXPORT_FORMATS]
        if unknown:
            raise DeliveryFormatError(f"不支持的导出格式：{unknown}",
                                      details={"supported": list(EXPORT_FORMATS)})
        if not self.request_id:
            object.__setattr__(self, "request_id", new_request_id("delivery"))

    # ------------------------------------------------------------- profile
    def resolve_include(self, key: str) -> bool:
        explicit = getattr(self, key, None)
        if explicit is not None:
            return bool(explicit)
        return bool(PROFILE_DEFAULTS[self.profile].get(key, False))

    @property
    def include_quality(self) -> bool:
        return self.resolve_include("include_quality_report")

    @property
    def provenance_included(self) -> bool:
        return self.resolve_include("include_provenance")

    @property
    def history_included(self) -> bool:
        return self.resolve_include("include_revision_history")

    @property
    def review_included(self) -> bool:
        return self.resolve_include("include_review_metadata")

    @property
    def digest(self) -> str:
        return digest_payload({
            "novel": self.novel_id, "mode": self.selection_mode,
            "explicit": {str(key): int(value)
                         for key, value in sorted(self.explicit_revisions.items())},
            "types": sorted(self.include_node_types),
            "formats": sorted({str(fmt) for fmt in self.formats}),
            "profile": self.profile, "policy": self.policy.digest,
            "includes": [self.include_quality, self.provenance_included,
                         self.history_included, self.review_included,
                         self.package_includes_node_files]})

    def as_dict(self) -> dict[str, Any]:
        return {"novel_id": self.novel_id, "selection_mode": self.selection_mode,
                "explicit_revisions": {str(key): int(value) for key, value
                                       in sorted(self.explicit_revisions.items())},
                "include_node_types": list(self.include_node_types),
                "formats": [str(fmt) for fmt in self.formats],
                "profile": self.profile,
                "include_quality_report": self.include_quality,
                "include_provenance": self.provenance_included,
                "include_revision_history": self.history_included,
                "include_review_metadata": self.review_included,
                "package_includes_node_files": self.package_includes_node_files,
                "created_by": self.created_by, "request_id": self.request_id,
                "delivery_schema_version": DELIVERY_SCHEMA_VERSION,
                "policy": self.policy.as_dict(), "digest": self.digest}


@dataclass(frozen=True)
class DeliveryIssue:
    code: str
    severity: str
    message: str
    node_ids: tuple[str, ...] = ()
    revision: int = 0
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.severity not in DELIVERY_SEVERITIES:
            raise DeliveryFormatError(f"未知 delivery severity：{self.severity}")

    @property
    def blocking(self) -> bool:
        return self.severity == "blocker"

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "severity": self.severity,
                "message": self.message, "node_ids": list(self.node_ids),
                "revision": int(self.revision), "evidence": dict(self.evidence)}


@dataclass(frozen=True)
class DeliveryValidationResult:
    novel_id: str
    phase: str                     # preflight | post_build
    ok: bool
    issues: tuple[DeliveryIssue, ...] = ()
    warnings: tuple[DeliveryIssue, ...] = ()
    selected_revisions: Mapping[str, int] = field(default_factory=dict)
    quality_summary: Mapping[str, Any] = field(default_factory=dict)
    blocking_reason: str = ""

    @property
    def blockers(self) -> tuple[DeliveryIssue, ...]:
        return tuple(row for row in self.issues if row.blocking)

    def as_dict(self) -> dict[str, Any]:
        return {"novel_id": self.novel_id, "phase": self.phase, "ok": self.ok,
                "issues": [row.as_dict() for row in self.issues],
                "warnings": [row.as_dict() for row in self.warnings],
                "selected_revisions": {str(key): int(value) for key, value
                                       in sorted(self.selected_revisions.items())},
                "quality_summary": dict(self.quality_summary),
                "blocking_reason": self.blocking_reason}


@dataclass(frozen=True)
class DeliverySnapshot:
    """这次交付钉住哪些 revision（§22–§25）。"""

    snapshot_id: str
    novel_id: str
    node_revisions: Mapping[str, int] = field(default_factory=dict)
    selection_mode: str = DEFAULT_SELECTION_MODE
    profile: str = DEFAULT_PROFILE
    formats: tuple[str, ...] = ()
    quality_refs: Mapping[str, str] = field(default_factory=dict)
    review_refs: Mapping[str, str] = field(default_factory=dict)
    excluded: tuple[Mapping[str, Any], ...] = ()
    policy: Mapping[str, Any] = field(default_factory=dict)
    selection_digest: str = ""
    schema_version: int = DELIVERY_SCHEMA_VERSION
    created_at: str = ""
    request_id: str = ""
    node_types: Mapping[str, str] = field(default_factory=dict)
    input_digest: str = ""

    def __post_init__(self) -> None:
        if not str(self.snapshot_id or "").strip():
            raise DeliverySelectionError("DeliverySnapshot 需要 snapshot_id")
        if not str(self.novel_id or "").strip():
            raise DeliverySelectionError("DeliverySnapshot 需要显式 novel_id")
        if not self.created_at:
            object.__setattr__(self, "created_at", utc_now())
        if not self.input_digest:
            object.__setattr__(self, "input_digest", self.compute_input_digest())

    def compute_input_digest(self) -> str:
        """内容可复现性锚点：snapshot 的语义输入（不含时间戳）。"""

        return digest_payload({
            "novel": self.novel_id, "schema": self.schema_version,
            "selection": self.selection_digest,
            "revisions": {str(key): int(value)
                          for key, value in sorted(self.node_revisions.items())},
            "quality_refs": dict(sorted(self.quality_refs.items())),
            "review_refs": dict(sorted(self.review_refs.items()))})

    @property
    def node_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self.node_revisions))

    def as_dict(self) -> dict[str, Any]:
        return {"snapshot_id": self.snapshot_id, "novel_id": self.novel_id,
                "selection_mode": self.selection_mode, "profile": self.profile,
                "formats": [str(fmt) for fmt in self.formats],
                "node_revisions": {str(key): int(value) for key, value
                                   in sorted(self.node_revisions.items())},
                "node_types": dict(sorted(self.node_types.items())),
                "quality_refs": dict(sorted(self.quality_refs.items())),
                "review_refs": dict(sorted(self.review_refs.items())),
                "excluded": [dict(row) for row in self.excluded],
                "policy": dict(self.policy),
                "selection_digest": self.selection_digest,
                "schema_version": self.schema_version,
                "created_at": self.created_at, "request_id": self.request_id,
                "input_digest": self.input_digest}


@dataclass(frozen=True)
class ExportArtifact:
    format: str
    filename: str
    relative_path: str
    mime_type: str
    size: int
    checksum: str
    exporter_id: str
    exporter_version: int
    content: bytes = b""
    text: bool = True

    def as_dict(self, *, with_content: bool = False) -> dict[str, Any]:
        row: dict[str, Any] = {"format": self.format, "filename": self.filename,
                               "path": self.relative_path,
                               "mime_type": self.mime_type, "size": self.size,
                               "checksum": self.checksum,
                               "exporter_id": self.exporter_id,
                               "exporter_version": self.exporter_version,
                               "text": self.text}
        if with_content:
            if self.text:
                row["content"] = self.content.decode("utf-8")
            else:
                import base64

                row["content_base64"] = base64.b64encode(self.content).decode("ascii")
        return row


@dataclass(frozen=True)
class DeliveryManifest:
    manifest_id: str
    novel_id: str
    project_id: str
    snapshot_id: str
    created_at: str
    blueprint_schema_version: int
    delivery_schema_version: int
    package_version: int
    selected_revisions: Mapping[str, int]
    formats: tuple[str, ...]
    exporters: tuple[Mapping[str, Any], ...]
    quality_policy: Mapping[str, Any]
    quality_summary: Mapping[str, Any]
    review_policy: Mapping[str, Any]
    source_ids: tuple[str, ...]
    artifacts: tuple[Mapping[str, Any], ...]
    excluded: tuple[Mapping[str, Any], ...] = ()
    input_digest: str = ""
    schema_version: int = DELIVERY_SCHEMA_VERSION
    extra: Mapping[str, Any] = field(default_factory=dict)

    @property
    def checksums(self) -> dict[str, str]:
        return {str(row["path"]): str(row["checksum"]) for row in self.artifacts}

    @property
    def digest(self) -> str:
        return digest_payload(self.as_dict())

    def as_dict(self) -> dict[str, Any]:
        return {"manifest_id": self.manifest_id, "package_version": self.package_version,
                "delivery_schema_version": self.delivery_schema_version,
                "blueprint_schema_version": self.blueprint_schema_version,
                "novel_id": self.novel_id, "project_id": self.project_id,
                "snapshot_id": self.snapshot_id, "created_at": self.created_at,
                "selected_revisions": {str(key): int(value) for key, value
                                       in sorted(self.selected_revisions.items())},
                "formats": [str(fmt) for fmt in self.formats],
                "exporters": [dict(row) for row in self.exporters],
                "quality_policy": dict(self.quality_policy),
                "quality_summary": dict(self.quality_summary),
                "review_policy": dict(self.review_policy),
                "source_ids": list(self.source_ids),
                "artifacts": [dict(row) for row in self.artifacts],
                "excluded": [dict(row) for row in self.excluded],
                "input_digest": self.input_digest,
                "schema_version": self.schema_version,
                "extra": dict(self.extra)}


@dataclass(frozen=True)
class DeliveryRequest:
    selection: DeliverySelection
    idempotency_key: str = ""
    dry_run: bool = False

    @property
    def novel_id(self) -> str:
        return self.selection.novel_id


@dataclass(frozen=True)
class DeliveryResult:
    request_id: str
    novel_id: str
    snapshot_id: str
    status: str                      # delivered | dry_run | blocked | partial
    validation: DeliveryValidationResult
    artifacts: tuple[ExportArtifact, ...] = ()
    manifest: DeliveryManifest | None = None
    post_validation: DeliveryValidationResult | None = None
    warnings: tuple[DeliveryIssue, ...] = ()
    package_path: str = ""
    idempotent: bool = False
    usage: Mapping[str, Any] = field(default_factory=dict)
    notes: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.status == "delivered"

    @property
    def checksums(self) -> dict[str, str]:
        return {row.relative_path: row.checksum for row in self.artifacts}

    def as_dict(self, *, with_content: bool = False) -> dict[str, Any]:
        return {"request_id": self.request_id, "novel_id": self.novel_id,
                "snapshot_id": self.snapshot_id, "status": self.status,
                "ok": self.ok, "idempotent": self.idempotent,
                "validation": self.validation.as_dict(),
                "post_validation": (self.post_validation.as_dict()
                                    if self.post_validation is not None else None),
                "artifacts": [row.as_dict(with_content=with_content)
                              for row in self.artifacts],
                "manifest": (self.manifest.as_dict()
                             if self.manifest is not None else None),
                "checksums": self.checksums,
                "warnings": [row.as_dict() for row in self.warnings],
                "package_path": self.package_path,
                "usage": dict(self.usage), "notes": list(self.notes),
                "llm_calls": 0}


@dataclass(frozen=True)
class NovelForgePackage:
    """`.nfpack` 的结构描述（§36–§37）：交付物，不是项目目录备份。"""

    novel_id: str
    snapshot_id: str
    package_version: int = PACKAGE_VERSION
    node_count: int = 0
    entries: Sequence[str] = ()
    includes_node_files: bool = False
    total_bytes: int = 0

    FORBIDDEN_ENTRY_TOKENS: tuple[str, ...] = (
        "..", "/", "\\", ":", ".env", "secret", "credential", "id_rsa",
    )

    @property
    def digest(self) -> str:
        return digest_payload({"novel": self.novel_id, "snapshot": self.snapshot_id,
                               "version": self.package_version,
                               "entries": list(self.entries)})

    def as_dict(self) -> dict[str, Any]:
        return {"novel_id": self.novel_id, "snapshot_id": self.snapshot_id,
                "package_version": self.package_version,
                "node_count": self.node_count,
                "includes_node_files": self.includes_node_files,
                "total_bytes": self.total_bytes,
                "entries": list(self.entries), "digest": self.digest}


def profile_defaults(profile: str) -> Mapping[str, bool]:
    if profile not in PROFILE_DEFAULTS:
        raise DeliveryFormatError(f"未知 profile：{profile}")
    return PROFILE_DEFAULTS[profile]


__all__ = [
    "DEFAULT_PROFILE", "DEFAULT_SELECTION_MODE", "DELIVERY_SCHEMA_VERSION",
    "DELIVERY_SEVERITIES", "EXPORT_FORMATS", "EXPORT_PROFILES", "PACKAGE_VERSION",
    "PROFILE_DEFAULTS", "SELECTION_MODES", "DeliveryIssue", "DeliveryManifest",
    "DeliveryPolicy", "DeliveryRequest", "DeliveryResult", "DeliverySelection",
    "DeliverySnapshot", "DeliveryValidationResult", "ExportArtifact",
    "NovelForgePackage", "profile_defaults", "utc_now",
]
