from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

import yaml
from pydantic import ValidationError

from .models import ChoiceOption, StoryBuilderStep, StoryChoiceCatalog, StoryStep


DEFAULT_CATALOG_PATH = Path("novel/config/story_builder/step_catalogs.yaml")


class StoryCatalogError(ValueError):
    """可直接交给 API 层转换的中文目录错误。"""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        path: Path | None = None,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.path = path
        self.details = details or []
        location = f"：{path}" if path else ""
        super().__init__(f"{message}{location}")

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "path": str(self.path) if self.path else "",
            "details": self.details,
        }


@dataclass(frozen=True, slots=True)
class StoryCatalogIndex:
    source_path: Path
    catalog: StoryChoiceCatalog
    steps_by_id: Mapping[StoryStep, StoryBuilderStep]
    options_by_id: Mapping[str, ChoiceOption]
    options_by_step: Mapping[StoryStep, tuple[ChoiceOption, ...]]

    def require_step(self, step: StoryStep | str) -> StoryBuilderStep:
        try:
            step_id = StoryStep(step)
        except ValueError as exc:
            raise StoryCatalogError("STEP_NOT_FOUND", f"选项目录中不存在步骤：{step}") from exc
        try:
            return self.steps_by_id[step_id]
        except KeyError as exc:
            raise StoryCatalogError("STEP_NOT_FOUND", f"选项目录中不存在步骤：{step_id.value}") from exc

    def require_option(self, option_id: str) -> ChoiceOption:
        try:
            return self.options_by_id[option_id]
        except KeyError as exc:
            raise StoryCatalogError("OPTION_NOT_FOUND", f"选项目录中不存在选项：{option_id}") from exc

    def options_for_step(self, step: StoryStep | str) -> tuple[ChoiceOption, ...]:
        step_id = self.require_step(step).step
        return self.options_by_step[step_id]


class StoryCatalogLoader:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()

    def load(self, catalog_path: Path | str = DEFAULT_CATALOG_PATH) -> StoryCatalogIndex:
        path = self._resolve_project_path(Path(catalog_path), code="CATALOG_OUTSIDE_PROJECT")
        if not path.is_file():
            raise StoryCatalogError("CATALOG_NOT_FOUND", "找不到故事选项目录", path=path)

        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError) as exc:
            raise StoryCatalogError("CATALOG_READ_FAILED", "无法读取故事选项目录", path=path) from exc
        except yaml.YAMLError as exc:
            raise StoryCatalogError(
                "CATALOG_YAML_INVALID",
                "故事选项目录不是有效的 YAML",
                path=path,
                details=[{"error": str(exc)}],
            ) from exc

        if not isinstance(raw, dict):
            raise StoryCatalogError(
                "CATALOG_ROOT_INVALID",
                "故事选项目录根节点必须是对象",
                path=path,
            )

        try:
            catalog = StoryChoiceCatalog.model_validate(raw)
        except ValidationError as exc:
            details = [
                {
                    "location": ".".join(str(part) for part in error["loc"]),
                    "message": error["msg"],
                    "type": error["type"],
                }
                for error in exc.errors(include_url=False, include_context=False)
            ]
            raise StoryCatalogError(
                "CATALOG_SCHEMA_INVALID",
                "故事选项目录内容不符合格式要求",
                path=path,
                details=details,
            ) from exc

        self._validate_source_refs(catalog, path)
        return self._build_index(catalog, path)

    def _resolve_project_path(self, path: Path, *, code: str) -> Path:
        resolved = path.resolve() if path.is_absolute() else (self.project_root / path).resolve()
        try:
            resolved.relative_to(self.project_root)
        except ValueError as exc:
            raise StoryCatalogError(code, "目录引用超出当前项目范围", path=resolved) from exc
        return resolved

    def _validate_source_refs(self, catalog: StoryChoiceCatalog, catalog_path: Path) -> None:
        for option in catalog.options:
            for source_ref in option.source_refs:
                try:
                    source_path = self._resolve_project_path(
                        Path(source_ref),
                        code="SOURCE_OUTSIDE_PROJECT",
                    )
                except StoryCatalogError as exc:
                    exc.details.append({"option_id": option.id, "source_ref": source_ref})
                    raise
                if not source_path.is_file():
                    raise StoryCatalogError(
                        "SOURCE_NOT_FOUND",
                        f"选项 {option.id} 引用的资料不存在",
                        path=catalog_path,
                        details=[{"option_id": option.id, "source_ref": source_ref}],
                    )

    @staticmethod
    def _build_index(catalog: StoryChoiceCatalog, path: Path) -> StoryCatalogIndex:
        steps_by_id = {step.step: step for step in catalog.steps}
        options_by_id = {option.id: option for option in catalog.options}
        options_by_step = {
            step.step: tuple(
                sorted(
                    (option for option in catalog.options if option.step == step.step),
                    key=lambda option: (-option.priority, option.id),
                )
            )
            for step in catalog.steps
        }
        return StoryCatalogIndex(
            source_path=path,
            catalog=catalog,
            steps_by_id=MappingProxyType(steps_by_id),
            options_by_id=MappingProxyType(options_by_id),
            options_by_step=MappingProxyType(options_by_step),
        )


def load_story_catalog(
    project_root: Path,
    catalog_path: Path | str = DEFAULT_CATALOG_PATH,
) -> StoryCatalogIndex:
    return StoryCatalogLoader(project_root).load(catalog_path)
