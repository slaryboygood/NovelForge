from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from novelforge.models import StrictModel

from .catalog import StoryCatalogIndex
from .models import (
    STORY_STEP_ORDER,
    BlueprintSection,
    BlueprintStatus,
    BuilderStatus,
    ChoiceConflict,
    StoryBlueprint,
    StoryBuilderSession,
)
from .recommendations import DeterministicRecommendationEngine
from .sessions import StorySessionRepository
from .design_tree import design_view


DEFAULT_BLUEPRINTS_PATH = Path("novel/authoring/story_builder/blueprints")


class StoryBlueprintError(ValueError):
    def __init__(self, code: str, message: str, *, blueprint_id: str = "") -> None:
        self.code = code
        self.message = message
        self.blueprint_id = blueprint_id
        super().__init__(message)

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message, "blueprint_id": self.blueprint_id}


class StoredStoryBlueprint(StrictModel):
    schema_version: Literal[1] = 1
    blueprint: StoryBlueprint


class StoryBlueprintRepository:
    def __init__(self, project_root: Path, blueprints_path: Path | str = DEFAULT_BLUEPRINTS_PATH):
        self.project_root = project_root.resolve()
        relative = Path(blueprints_path)
        self.blueprints_dir = (
            relative.resolve() if relative.is_absolute() else (self.project_root / relative).resolve()
        )
        try:
            self.blueprints_dir.relative_to(self.project_root)
        except ValueError as exc:
            raise StoryBlueprintError("BLUEPRINT_PATH_OUTSIDE_PROJECT", "蓝图目录超出当前项目范围") from exc

    def save(self, blueprint: StoryBlueprint) -> StoryBlueprint:
        path = self.path_for(blueprint.blueprint_id, blueprint.version)
        if path.exists():
            current = self.load(blueprint.blueprint_id, blueprint.version)
            if current.status == BlueprintStatus.CONFIRMED and blueprint != current:
                raise StoryBlueprintError(
                    "BLUEPRINT_CONFIRMED_IMMUTABLE",
                    "已确认的故事蓝图不能被覆盖",
                    blueprint_id=blueprint.blueprint_id,
                )
        self._atomic_write(path, StoredStoryBlueprint(blueprint=blueprint))
        return blueprint

    def load(self, blueprint_id: str, version: int) -> StoryBlueprint:
        path = self.path_for(blueprint_id, version)
        if not path.is_file():
            raise StoryBlueprintError("BLUEPRINT_NOT_FOUND", "找不到故事蓝图", blueprint_id=blueprint_id)
        try:
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
            stored = StoredStoryBlueprint.model_validate(raw)
        except (OSError, UnicodeError, json.JSONDecodeError, ValidationError) as exc:
            raise StoryBlueprintError(
                "BLUEPRINT_READ_FAILED", "无法读取故事蓝图", blueprint_id=blueprint_id
            ) from exc
        blueprint = stored.blueprint
        if blueprint.blueprint_id != blueprint_id or blueprint.version != version:
            raise StoryBlueprintError(
                "BLUEPRINT_ID_MISMATCH", "蓝图文件名与内容不一致", blueprint_id=blueprint_id
            )
        return blueprint

    def latest(self, blueprint_id: str) -> StoryBlueprint | None:
        folder = self.blueprints_dir / blueprint_id
        versions = sorted(folder.glob("v*.json")) if folder.exists() else []
        return self.load(blueprint_id, int(versions[-1].stem[1:])) if versions else None

    def latest_for_session(self, session_id: str) -> StoryBlueprint | None:
        return self.latest(blueprint_id_for_session(session_id))

    def path_for(self, blueprint_id: str, version: int) -> Path:
        if version < 1:
            raise StoryBlueprintError("BLUEPRINT_VERSION_INVALID", "蓝图版本必须大于零", blueprint_id=blueprint_id)
        if not blueprint_id.startswith("bp_") or not blueprint_id.replace("_", "").isalnum():
            raise StoryBlueprintError("BLUEPRINT_ID_INVALID", "蓝图 ID 格式不正确", blueprint_id=blueprint_id)
        return self.blueprints_dir / blueprint_id / f"v{version:06d}.json"

    @staticmethod
    def _atomic_write(path: Path, document: StoredStoryBlueprint) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        payload = json.dumps(document.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise


class StoryBlueprintCompiler:
    def __init__(
        self,
        catalog: StoryCatalogIndex,
        sessions: StorySessionRepository,
        blueprints: StoryBlueprintRepository,
    ) -> None:
        self.catalog = catalog
        self.sessions = sessions
        self.blueprints = blueprints
        self.rules = DeterministicRecommendationEngine(catalog)

    def compile(self, session_id: str) -> StoryBlueprint:
        session = self.sessions.load(session_id)
        missing = [step for step in STORY_STEP_ORDER if step not in session.completed_steps]
        if missing:
            names = "、".join(self.catalog.require_step(step).title for step in missing)
            raise StoryBlueprintError("BLUEPRINT_STEPS_INCOMPLETE", f"请先完成这些构筑步骤：{names}")

        blueprint_id = blueprint_id_for_session(session_id)
        latest = self.blueprints.latest(blueprint_id)
        if latest and latest.source_selection_version == session.selection_version:
            return latest

        sections = [self._compile_section(session, step) for step in STORY_STEP_ORDER]
        conflicts = self._conflicts(session)
        blueprint = StoryBlueprint(
            blueprint_id=blueprint_id,
            project_id=session.project_id,
            source_session_id=session.session_id,
            source_selection_version=session.selection_version,
            version=(latest.version + 1) if latest else 1,
            premise=self._premise(sections),
            sections=sections,
            unresolved_conflicts=conflicts,
            design_choices=session.design_choices,
            design_effects={node["id"]: next((item["effects"] for item in node["options"]
                            if item["id"] == node["selection"]["option_id"]), {})
                            for node in design_view(self.catalog, session) if node["selection"] and not node["needs_review"]},
            design_summaries={node["id"]: node["title"] + "：" + (
                next((item["name"] + "。" + item["summary"] for item in node["options"]
                      if item["id"] == node["selection"]["option_id"]), node["selection"]["custom_text"])
            ) for node in design_view(self.catalog, session) if node["selection"] and not node["needs_review"]},
        )
        self.blueprints.save(blueprint)
        self.sessions.save(
            session.model_copy(update={"status": BuilderStatus.BLUEPRINT_DRAFT}),
            expected_selection_version=session.selection_version,
        )
        return blueprint

    def confirm(self, blueprint_id: str, version: int) -> StoryBlueprint:
        blueprint = self.blueprints.load(blueprint_id, version)
        session = self.sessions.load(blueprint.source_session_id)
        if session.selection_version != blueprint.source_selection_version:
            raise StoryBlueprintError("BLUEPRINT_SOURCE_STALE", "构筑选择已变化，请重新生成故事蓝图", blueprint_id=blueprint_id)
        if session.needs_review_steps or blueprint.unresolved_conflicts:
            raise StoryBlueprintError("BLUEPRINT_CONFLICTS_UNRESOLVED", "还有待复核选择，暂不能确认蓝图", blueprint_id=blueprint_id)
        confirmed = blueprint.model_copy(
            update={"status": BlueprintStatus.CONFIRMED, "confirmed_by_author": True}
        )
        self.blueprints.save(confirmed)
        self.sessions.save(
            session.model_copy(update={"status": BuilderStatus.BLUEPRINT_CONFIRMED}),
            expected_selection_version=session.selection_version,
        )
        return confirmed

    def _compile_section(self, session: StoryBuilderSession, step) -> BlueprintSection:
        selections = [item for item in session.selections if item.step == step]
        options = [self.catalog.require_option(item.option_id) for item in selections if item.option_id]
        custom = [item.custom_text for item in selections if item.custom_text]
        parts: list[str] = []
        if options:
            parts.append("选定：" + "、".join(item.name for item in options) + "。")
            parts.extend(item.summary for item in options)
            effects = [f"{name}：{value}" for item in options for name, value in item.effects.items()]
            if effects:
                parts.append("对故事的影响：" + "；".join(effects) + "。")
        if custom:
            parts.append("作者自定义：" + "；".join(custom) + "。")
        return BlueprintSection(
            step=step,
            summary="".join(parts),
            selected_option_ids=[item.option_id for item in selections if item.option_id],
            custom_inputs=custom,
            source_selection_ids=[item.selection_id for item in selections],
        )

    def _conflicts(self, session: StoryBuilderSession) -> list[ChoiceConflict]:
        option_ids = [item.option_id for item in session.selections if item.option_id]
        custom_counts = {
            step: sum(item.step == step and bool(item.custom_text) for item in session.selections)
            for step in STORY_STEP_ORDER
        }
        conflicts = list(self.rules.find_conflicts(option_ids, custom_counts))
        for node in design_view(self.catalog, session):
            if node["needs_review"]:
                conflicts.append(ChoiceConflict(code="DESIGN_NEEDS_REVIEW", message=f"“{node['title']}”的前置条件已改变，请复核或清除该选择"))
        for step in session.needs_review_steps:
            conflicts.append(
                ChoiceConflict(
                    code="STEP_NEEDS_REVIEW",
                    message=f"“{self.catalog.require_step(step).title}”需要根据新的前置选择重新确认",
                    option_ids=[
                        item.option_id for item in session.selections if item.step == step and item.option_id
                    ],
                )
            )
        return conflicts

    def _premise(self, sections: list[BlueprintSection]) -> str:
        by_step = {section.step: section for section in sections}

        def names(step) -> str:
            section = by_step[step]
            values = [self.catalog.require_option(item).name for item in section.selected_option_ids]
            values.extend(section.custom_inputs)
            return "、".join(values)

        return (
            f"以“{names(STORY_STEP_ORDER[0])}”为阅读承诺，"
            f"在“{names(STORY_STEP_ORDER[1])}”与“{names(STORY_STEP_ORDER[2])}”中，"
            f"让“{names(STORY_STEP_ORDER[3])}”经历“{names(STORY_STEP_ORDER[6])}”，"
            f"并通过“{names(STORY_STEP_ORDER[7])}”完成成长的长篇故事。"
        )


def blueprint_id_for_session(session_id: str) -> str:
    digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:20]
    return f"bp_{digest}"
