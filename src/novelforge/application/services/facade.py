"""ApplicationServices —— 按 novel_id 绑定的业务能力束（V4-08 §6、§42、§58、§59）。

接口层（REST / MCP / Agent / UI）只通过本模块拿到 Application Service；
MCP 因此**永远不需要** import blueprint / quality / editor / delivery / generation。

```text
application.services.facade
  ApplicationServices      一个作品的业务能力束（blueprint / review / editor / export /
                           journey / project）
  application_services()   按 (project_root, novel_id) 构造（惰性，不扫描磁盘、不打开模型）
```

边界：本模块属于 application 层，可以依赖下层模块；接口层只依赖本模块。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from novelforge.blueprint import BlueprintRepository
from novelforge.delivery import DeliveryPolicy, DeliveryStore
from novelforge.editor import BlueprintEditorService, EditorStore
from novelforge.generation import BlueprintGenerationService
from novelforge.quality import QualityPolicy, QualityService

from .blueprint import BlueprintService
from .editor import EditorService
from .export import ExportService
from .journey import JourneyService
from .project import ProjectService
from .review import ReviewService

#: 接口层可用的最小错误（避免接口层 import 下层模块的错误类型）
class MCPFacadeUnavailable(RuntimeError):
    code = "MCP_CAPABILITY_UNAVAILABLE"


@dataclass(frozen=True)
class ApplicationServices:
    """一个作品的全部 Application 能力（接口层的唯一依赖）。"""

    novel_id: str
    project_root: Path
    project: ProjectService
    journey: JourneyService
    blueprint: BlueprintService | None
    review: ReviewService | None
    editor: EditorService | None
    export: ExportService | None
    ai_available: bool = False

    # ------------------------------------------------------------------ 摘要
    def summary(self) -> dict[str, Any]:
        """作品摘要（读操作，0 LLM 调用）：元数据 + 进度 + Blueprint / 质量 / 交付计数。"""

        payload: dict[str, Any] = {"novel_id": self.novel_id,
                                   "project_id": self.novel_id,
                                   "ai_available": bool(self.ai_available)}
        try:
            payload["profile"] = self.project.get_novel(self.novel_id)
        except Exception:  # noqa: BLE001 - 摘要不因缺少 profile 失败
            payload["profile"] = {}
        try:
            payload["journey"] = self.journey.projection()
        except Exception:  # noqa: BLE001
            payload["journey"] = {}
        if self.blueprint is not None:
            try:
                payload["blueprint"] = self.blueprint.stats()
            except Exception:  # noqa: BLE001
                payload["blueprint"] = {}
        if self.review is not None:
            try:
                payload["quality"] = self.review.stats()
            except Exception:  # noqa: BLE001
                payload["quality"] = {}
        if self.export is not None:
            try:
                payload["delivery"] = self.export.delivery().stats()
            except Exception:  # noqa: BLE001
                payload["delivery"] = {}
        return payload

    def interface_metadata(self) -> dict[str, Any]:
        """服务元数据（不含任何作品数据），供 `novelforge://interface` 使用。"""

        return {"server": "novelforge", "novel_id": self.novel_id,
                "ai_available": bool(self.ai_available),
                "project_id": self.novel_id}

    def delivery_store(self) -> DeliveryStore:
        return DeliveryStore(self.project_root, self.novel_id)

    def delivery_selection(self, *, selection_mode: str = "accepted",
                           profile: str = "author",
                           formats: Sequence[str] = ("json",),
                           include_node_types: Sequence[str] = (),
                           require_accepted: bool = True,
                           require_quality_pass: bool = True,
                           allow_unevaluated: bool = False,
                           allow_stale_quality: bool = False,
                           include_quality_report: bool | None = None,
                           include_provenance: bool | None = None,
                           include_revision_history: bool | None = None,
                           package_includes_node_files: bool = False) -> Any:
        """构造 DeliverySelection（接口层只传协议参数，不 import delivery，§7/§60）。"""

        if self.export is None:
            raise MCPFacadeUnavailable("export 能力不可用")
        policy = DeliveryPolicy(
            require_accepted=require_accepted,
            require_quality_pass=require_quality_pass,
            allow_unevaluated=allow_unevaluated,
            allow_stale_quality=allow_stale_quality)
        return self.export.delivery_selection(
            selection_mode=selection_mode, profile=profile,
            formats=tuple(formats), policy=policy,
            include_node_types=tuple(include_node_types),
            include_quality_report=include_quality_report,
            include_provenance=include_provenance,
            include_revision_history=include_revision_history,
            package_includes_node_files=package_includes_node_files)


def application_services(project_root: Path | str, novel_id: str, *,
                         gateway: Any = None, memory: Any = None,
                         policy: QualityPolicy | None = None,
                         with_ai: bool | None = None,
                         exporter_registry: Any = None,
                         evaluator_registry: Any = None) -> ApplicationServices:
    """构造一个作品的 Application 能力束。

    ```text
    · 不扫描磁盘、不自动打开"当前作品"（显式 novel_id）
    · 未注入 gateway 时不构造生成能力（AI 相关的 tool 会返回 MCP_LLM_UNAVAILABLE）
    ```
    """

    root = Path(project_root)
    repository = BlueprintRepository(root, novel_id)
    resolved_policy = policy or QualityPolicy()
    generation: BlueprintGenerationService | None = None
    resolved_memory = memory
    if gateway is not None and (with_ai is not False):
        if resolved_memory is None:
            try:
                from novelforge.memory import build_default_service

                resolved_memory = build_default_service(novel_id, root)
            except Exception:  # noqa: BLE001 - 没有作者数据时 AI 能力不可用
                resolved_memory = None
        if resolved_memory is not None:
            generation = BlueprintGenerationService(root, novel_id, gateway=gateway,
                                                    memory=resolved_memory,
                                                    repository=repository)
    blueprint = (BlueprintService(root, novel_id, generation=generation,
                                  repository=repository)
                 if generation is not None else None)
    quality = QualityService(root, novel_id, repository=repository, memory=memory,
                             registry=evaluator_registry)
    review = ReviewService(root, novel_id, quality=quality, generation=generation,
                           repository=repository, policy=resolved_policy)
    editor = EditorService(root, novel_id,
                           editor=BlueprintEditorService(
                               root, novel_id, repository=repository,
                               generation=generation, store=EditorStore(root, novel_id)),
                           quality=quality, review=review, generation=generation,
                           repository=repository, policy=resolved_policy)
    export = ExportService(root, novel_id, exporter_registry=exporter_registry)
    return ApplicationServices(
        novel_id=novel_id, project_root=root, project=ProjectService(root),
        journey=JourneyService(root, novel_id), blueprint=blueprint, review=review,
        editor=editor, export=export, ai_available=generation is not None)


__all__ = ["ApplicationServices", "MCPFacadeUnavailable", "application_services"]
