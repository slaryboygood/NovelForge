"""NovelForge `delivery` —— Delivery, Export & NovelForge Package（V4-07）。

Public Contract（精简，§19）：

```text
DeliveryService / delivery_service        交付编排（selection → snapshot → validate → export）
DeliveryStore                             交付快照 / manifest / artifact 落盘（原子发布）
DeliveryRequest / DeliveryResult          请求与统一结果
DeliveryPolicy / DeliverySelection        放行规则与选择策略
DeliverySnapshot / DeliveryManifest       钉住的 revision 与交付清单
DeliveryValidationResult / DeliveryIssue  preflight / post-build 结论与稳定 issue code
ExportArtifact / ExportFormat / profiles  交付物与格式 / profile
NovelForgePackage                         .nfpack 结构描述
ExporterRegistry / ExporterSpec           exporter 注册表（可扩展，插件留给 V4-09）
DeliveryError 家族
```

内部实现（compiler / selection / validators 细节、具体 exporter 模块）不全部公开。

边界（§82–§83）：

```text
delivery  → blueprint / quality Public Contract / editor metadata（全部只读）/ core / persistence
禁止      → LLM 调用、memory retrieval、修改 Blueprint / Canon / StoryState、修 Quality issue
禁止      → delivery import api / application；反向依赖（core…editor → delivery）也禁止
Application → application.services.ExportService 是唯一 facade
```

不变量（§5）：

```text
DELIVERY_READS_CANONICAL_ARTIFACTS / DELIVERY_NEVER_INVENTS_STORY_CONTENT /
DELIVERY_IS_REVISION_PINNED / DELIVERY_IS_NOVEL_ISOLATED /
DELIVERY_IS_REPRODUCIBLE / DELIVERY_IS_VALIDATED_BEFORE_RELEASE
```
"""

from .compiler import (
    INTERNAL_FIELDS,
    NODE_TYPE_ORDER,
    VISIBLE_FIELDS,
    BlueprintCompiler,
    CompiledBlueprint,
    CompiledNode,
    payload_of,
    visible_payload,
)
from .contracts import (
    DEFAULT_PROFILE,
    DEFAULT_SELECTION_MODE,
    DELIVERY_SCHEMA_VERSION,
    DELIVERY_SEVERITIES,
    EXPORT_FORMATS,
    EXPORT_PROFILES,
    PACKAGE_VERSION,
    PROFILE_DEFAULTS,
    SELECTION_MODES,
    DeliveryIssue,
    DeliveryManifest,
    DeliveryPolicy,
    DeliveryRequest,
    DeliveryResult,
    DeliverySelection,
    DeliverySnapshot,
    DeliveryValidationResult,
    ExportArtifact,
    NovelForgePackage,
    profile_defaults,
)
from .errors import (
    DeliveryError,
    DeliveryExportError,
    DeliveryFormatError,
    DeliveryOwnershipError,
    DeliverySelectionError,
    DeliveryValidationFailed,
)
from .exporters import ExporterRegistry, ExporterSpec, build_default_registry
from .manifest import build_manifest, sha256_hex
from .selection import NodeQualityState, RevisionSelector, SelectionOutcome
from .service import DeliveryService, delivery_service
from .store import DeliveryStore
from .validation import ISSUE_CODES, DeliveryValidator

__all__ = [
    # service / store
    "DeliveryService", "delivery_service", "DeliveryStore",
    # contracts
    "DeliveryRequest", "DeliveryResult", "DeliveryPolicy", "DeliverySelection",
    "DeliverySnapshot", "DeliveryManifest", "DeliveryValidationResult",
    "DeliveryIssue", "ExportArtifact", "NovelForgePackage",
    "DEFAULT_PROFILE", "DEFAULT_SELECTION_MODE", "DELIVERY_SCHEMA_VERSION",
    "DELIVERY_SEVERITIES", "EXPORT_FORMATS", "EXPORT_PROFILES", "PACKAGE_VERSION",
    "PROFILE_DEFAULTS", "SELECTION_MODES", "profile_defaults",
    # compiler
    "BlueprintCompiler", "CompiledBlueprint", "CompiledNode", "INTERNAL_FIELDS",
    "NODE_TYPE_ORDER", "VISIBLE_FIELDS", "payload_of", "visible_payload",
    # selection / validation / manifest
    "RevisionSelector", "SelectionOutcome", "NodeQualityState",
    "DeliveryValidator", "ISSUE_CODES", "build_manifest", "sha256_hex",
    # exporters
    "ExporterRegistry", "ExporterSpec", "build_default_registry",
    # errors
    "DeliveryError", "DeliveryExportError", "DeliveryFormatError",
    "DeliveryOwnershipError", "DeliverySelectionError", "DeliveryValidationFailed",
]
