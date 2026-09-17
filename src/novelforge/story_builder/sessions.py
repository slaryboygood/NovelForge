from __future__ import annotations

import json
import os
import re
import uuid
import threading
from functools import wraps
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import ValidationError

from novelforge.models import StrictModel

from .catalog import StoryCatalogIndex
from .models import (
    STORY_STEP_ORDER,
    BuilderStatus,
    SelectionSource,
    StoryBuilderSession,
    StorySelection,
    StoryStep,
)
from .recommendations import DeterministicRecommendationEngine


SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{2,95}$")
DEFAULT_SESSIONS_PATH = Path("novel/authoring/story_builder/sessions")
_SESSION_IO_LOCK = threading.RLock()


def _serialized_io(method):
    @wraps(method)
    def guarded(*args, **kwargs):
        with _SESSION_IO_LOCK:
            return method(*args, **kwargs)
    return guarded


class StorySessionError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        session_id: str = "",
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.session_id = session_id
        self.details = details or []
        suffix = f"：{session_id}" if session_id else ""
        super().__init__(f"{message}{suffix}")

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "session_id": self.session_id,
            "details": self.details,
        }


class StoredStorySession(StrictModel):
    schema_version: Literal[1] = 1
    session: StoryBuilderSession


class StorySessionRepository:
    def __init__(
        self,
        project_root: Path,
        sessions_path: Path | str = DEFAULT_SESSIONS_PATH,
    ) -> None:
        self.project_root = project_root.resolve()
        relative = Path(sessions_path)
        self.sessions_dir = (
            relative.resolve() if relative.is_absolute() else (self.project_root / relative).resolve()
        )
        try:
            self.sessions_dir.relative_to(self.project_root)
        except ValueError as exc:
            raise StorySessionError("SESSION_PATH_OUTSIDE_PROJECT", "会话目录超出当前项目范围") from exc

    @_serialized_io
    def create(
        self,
        project_id: str,
        *,
        session_id: str | None = None,
        entry_step: StoryStep = StoryStep.READER_EXPERIENCE,
    ) -> StoryBuilderSession:
        entry_step = StoryStep(entry_step)
        if entry_step not in {StoryStep.READER_EXPERIENCE, StoryStep.WORLDVIEW, StoryStep.PROTAGONIST, StoryStep.MAJOR_EVENTS}:
            raise StorySessionError("ENTRY_STEP_INVALID", "请选择读者体验、世界观、人物或开场事件作为起点")
        resolved_id = session_id or self._new_session_id()
        self._validate_id(resolved_id, "SESSION_ID_INVALID", "会话 ID 格式不正确")
        self._validate_id(project_id, "PROJECT_ID_INVALID", "项目 ID 格式不正确")
        path = self.path_for(resolved_id)
        if path.exists():
            raise StorySessionError("SESSION_ALREADY_EXISTS", "构筑会话已经存在", session_id=resolved_id)
        now = datetime.now(timezone.utc)
        session = StoryBuilderSession(
            session_id=resolved_id,
            project_id=project_id,
            status=BuilderStatus.CREATED,
            current_step=entry_step,
            created_at=now,
            updated_at=now,
        )
        self._atomic_write(path, StoredStorySession(session=session))
        return session

    def load(self, session_id: str) -> StoryBuilderSession:
        path = self.path_for(session_id)
        if not path.is_file():
            raise StorySessionError("SESSION_NOT_FOUND", "找不到构筑会话", session_id=session_id)
        return self._read_document(path, session_id).session

    @_serialized_io
    def save(
        self,
        session: StoryBuilderSession,
        *,
        expected_selection_version: int,
    ) -> StoryBuilderSession:
        path = self.path_for(session.session_id)
        if not path.is_file():
            raise StorySessionError(
                "SESSION_NOT_FOUND",
                "不能保存尚未创建的构筑会话",
                session_id=session.session_id,
            )
        current = self._read_document(path, session.session_id).session
        if current.project_id != session.project_id:
            raise StorySessionError(
                "SESSION_PROJECT_MISMATCH",
                "会话所属项目不能修改",
                session_id=session.session_id,
            )
        if current.selection_version != expected_selection_version:
            raise StorySessionError(
                "SESSION_VERSION_CONFLICT",
                "会话已在其他位置更新，请刷新后重试",
                session_id=session.session_id,
                details=[
                    {
                        "expected_selection_version": expected_selection_version,
                        "actual_selection_version": current.selection_version,
                    }
                ],
            )
        if session.selection_version not in {
            current.selection_version,
            current.selection_version + 1,
        }:
            raise StorySessionError(
                "SESSION_VERSION_SEQUENCE_INVALID",
                "会话选择版本只能保持不变或递增一版",
                session_id=session.session_id,
            )
        payload = session.model_dump(mode="python")
        payload["updated_at"] = datetime.now(timezone.utc)
        saved = StoryBuilderSession.model_validate(payload)
        if saved.selection_version > current.selection_version:
            self._archive(current)
        self._atomic_write(path, StoredStorySession(session=saved))
        return saved

    def latest_for_project(self, project_id: str) -> StoryBuilderSession | None:
        sessions = self.list_for_project(project_id)
        return sessions[0] if sessions else None

    def list_for_project(self, project_id: str) -> list[StoryBuilderSession]:
        self._validate_id(project_id, "PROJECT_ID_INVALID", "项目 ID 格式不正确")
        if not self.sessions_dir.exists():
            return []
        sessions: list[StoryBuilderSession] = []
        for path in self.sessions_dir.glob("*.json"):
            session_id = path.stem
            session = self._read_document(path, session_id).session
            if session.project_id == project_id:
                sessions.append(session)
        return sorted(
            sessions,
            key=lambda item: (item.updated_at, item.session_id),
            reverse=True,
        )

    def history_for(self, session_id: str, *, include_current: bool = True) -> list[StoryBuilderSession]:
        self._validate_id(session_id, "SESSION_ID_INVALID", "会话 ID 格式不正确")
        history_dir = self.sessions_dir / "history" / session_id
        versions: list[StoryBuilderSession] = []
        if history_dir.exists():
            for path in sorted(history_dir.glob("selection_*.json")):
                versions.append(self._read_document(path, session_id).session)
        if include_current:
            versions.append(self.load(session_id))
        return sorted(versions, key=lambda item: item.selection_version)

    def path_for(self, session_id: str) -> Path:
        self._validate_id(session_id, "SESSION_ID_INVALID", "会话 ID 格式不正确")
        return self.sessions_dir / f"{session_id}.json"

    @_serialized_io
    def _read_document(self, path: Path, session_id: str) -> StoredStorySession:
        try:
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError) as exc:
            raise StorySessionError(
                "SESSION_READ_FAILED",
                "无法读取构筑会话",
                session_id=session_id,
            ) from exc
        except json.JSONDecodeError as exc:
            raise StorySessionError(
                "SESSION_JSON_INVALID",
                "构筑会话文件不是有效的 JSON",
                session_id=session_id,
            ) from exc
        try:
            document = StoredStorySession.model_validate(raw)
        except ValidationError as exc:
            details = [
                {
                    "location": ".".join(str(part) for part in error["loc"]),
                    "message": error["msg"],
                    "type": error["type"],
                }
                for error in exc.errors(include_url=False, include_context=False)
            ]
            raise StorySessionError(
                "SESSION_SCHEMA_INVALID",
                "构筑会话内容不符合格式要求",
                session_id=session_id,
                details=details,
            ) from exc
        if document.session.session_id != session_id:
            raise StorySessionError(
                "SESSION_ID_MISMATCH",
                "会话文件名与文件内容不一致",
                session_id=session_id,
            )
        return document

    def _atomic_write(self, path: Path, document: StoredStorySession) -> None:
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

    def _archive(self, session: StoryBuilderSession) -> None:
        path = (
            self.sessions_dir
            / "history"
            / session.session_id
            / f"selection_{session.selection_version:06d}.json"
        )
        document = StoredStorySession(session=session)
        if path.exists():
            archived = self._read_document(path, session.session_id)
            if archived != document:
                raise StorySessionError(
                    "SESSION_HISTORY_CONFLICT",
                    "同一选择版本存在不同的历史内容",
                    session_id=session.session_id,
                )
            return
        self._atomic_write(path, document)

    @staticmethod
    def _validate_id(value: str, code: str, message: str) -> None:
        if not SESSION_ID_PATTERN.fullmatch(value):
            raise StorySessionError(code, message, session_id=value if code == "SESSION_ID_INVALID" else "")

    @staticmethod
    def _new_session_id() -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        return f"sb_{timestamp}_{uuid.uuid4().hex[:8]}"


class StorySessionManager:
    def __init__(self, repository: StorySessionRepository, catalog: StoryCatalogIndex) -> None:
        self.repository = repository
        self.catalog = catalog
        self.rules = DeterministicRecommendationEngine(catalog)

    def set_step_selections(
        self,
        session_id: str,
        step: StoryStep | str,
        *,
        option_ids: list[str] | None = None,
        custom_texts: list[str] | None = None,
        expected_selection_version: int,
        option_source: SelectionSource = SelectionSource.AUTHOR,
    ) -> StoryBuilderSession:
        session = self.repository.load(session_id)
        self._require_version(session, expected_selection_version)
        target = self.catalog.require_step(step)
        option_ids = option_ids or []
        custom_texts = self._clean_custom_texts(custom_texts or [])
        if len(option_ids) != len(set(option_ids)):
            raise StorySessionError("SELECTION_DUPLICATE", "同一步骤不能重复选择同一选项")
        for option_id in option_ids:
            option = self.catalog.require_option(option_id)
            if option.step != target.step:
                raise StorySessionError(
                    "SELECTION_STEP_MISMATCH",
                    f"选项“{option.name}”不属于步骤“{target.title}”",
                    session_id=session_id,
                )
        count = len(option_ids) + len(custom_texts)
        if count < target.min_selections or count > target.max_selections:
            raise StorySessionError(
                "SELECTION_COUNT_INVALID",
                f"步骤“{target.title}”需要选择 {target.min_selections} 至 {target.max_selections} 项",
                session_id=session_id,
            )

        remaining = [selection for selection in session.selections if selection.step != target.step]
        remaining_ids = [selection.option_id for selection in remaining if selection.option_id]
        remaining_custom = self._custom_counts(remaining)
        accessible = set(self.rules.unlocked_steps(remaining_ids, remaining_custom))
        if not session.selections and target.step == session.current_step:
            accessible.add(target.step)
        if target.step not in accessible and target.step not in session.completed_steps:
            raise StorySessionError(
                "STEP_NOT_ACCESSIBLE",
                f"步骤“{target.title}”尚未解锁",
                session_id=session_id,
            )

        earlier_ids = [
            option_id
            for option_id in remaining_ids
            if STORY_STEP_ORDER.index(self.catalog.require_option(option_id).step)
            < STORY_STEP_ORDER.index(target.step)
        ]
        direct_ids = [*earlier_ids, *option_ids]
        direct_custom = {
            key: value
            for key, value in remaining_custom.items()
            if STORY_STEP_ORDER.index(key) < STORY_STEP_ORDER.index(target.step)
        }
        direct_custom[target.step] = len(custom_texts)
        direct_conflicts = self.rules.find_conflicts(direct_ids, direct_custom)
        if any(conflict.blocking for conflict in direct_conflicts):
            raise StorySessionError(
                "SELECTION_CONFLICT",
                "当前选择与前置选择冲突",
                session_id=session_id,
                details=[conflict.model_dump(mode="json") for conflict in direct_conflicts],
            )

        new_version = session.selection_version + 1
        replacements = [
            StorySelection(
                selection_id=self._new_selection_id(new_version),
                step=target.step,
                option_id=option_id,
                source=option_source,
                revision=new_version,
            )
            for option_id in option_ids
        ]
        replacements.extend(
            StorySelection(
                selection_id=self._new_selection_id(new_version),
                step=target.step,
                custom_text=text,
                source=SelectionSource.CUSTOM,
                revision=new_version,
            )
            for text in custom_texts
        )
        all_selections = [*remaining, *replacements]
        all_selections.sort(
            key=lambda item: (STORY_STEP_ORDER.index(item.step), item.selection_id)
        )
        selected_ids = [item.option_id for item in all_selections if item.option_id]
        custom_counts = self._custom_counts(all_selections)
        all_conflicts = self.rules.find_conflicts(selected_ids, custom_counts)
        changed_index = STORY_STEP_ORDER.index(target.step)
        downstream_with_selections = {
            item.step
            for item in remaining
            if STORY_STEP_ORDER.index(item.step) > changed_index
        }
        needs_review = set(session.needs_review_steps)
        needs_review.discard(target.step)
        needs_review.update(downstream_with_selections)
        for conflict in all_conflicts:
            if not conflict.blocking:
                continue
            for option_id in conflict.option_ids:
                if option_id in selected_ids:
                    needs_review.add(self.catalog.require_option(option_id).step)

        completed = self._completed_steps(all_selections)
        next_step = target.next_steps[0] if target.next_steps else target.step
        # 从后面的灵感起步后，先补齐此前缺少的设定，不替作者填默认值。
        for prerequisite in STORY_STEP_ORDER[:changed_index]:
            if prerequisite not in completed or prerequisite in needs_review:
                next_step = prerequisite
                break
        status = BuilderStatus.NEEDS_REVIEW if needs_review else BuilderStatus.CONFIGURING
        changed = session.model_copy(
            update={
                "status": status,
                "current_step": next_step,
                "completed_steps": completed,
                "selections": all_selections,
                "needs_review_steps": self._ordered_steps(needs_review),
                "selection_version": new_version,
                "recommendation_version": 0,
            }
        )
        return self.repository.save(
            changed,
            expected_selection_version=expected_selection_version,
        )

    def go_back(
        self,
        session_id: str,
        target_step: StoryStep | str,
        *,
        expected_selection_version: int,
    ) -> StoryBuilderSession:
        session = self.repository.load(session_id)
        self._require_version(session, expected_selection_version)
        target = self.catalog.require_step(target_step).step
        if STORY_STEP_ORDER.index(target) > STORY_STEP_ORDER.index(session.current_step) and target not in session.completed_steps:
            raise StorySessionError(
                "BACK_TARGET_INVALID",
                "只能返回当前步骤或更早的步骤",
                session_id=session_id,
            )
        changed = session.model_copy(update={"current_step": target})
        return self.repository.save(
            changed,
            expected_selection_version=expected_selection_version,
        )

    def _completed_steps(self, selections: list[StorySelection]) -> list[StoryStep]:
        result: list[StoryStep] = []
        for step in STORY_STEP_ORDER:
            config = self.catalog.require_step(step)
            count = sum(item.step == step for item in selections)
            if config.min_selections <= count <= config.max_selections:
                result.append(step)
        return result

    @staticmethod
    def _custom_counts(selections: list[StorySelection]) -> dict[StoryStep, int]:
        return {
            step: sum(item.step == step and bool(item.custom_text) for item in selections)
            for step in STORY_STEP_ORDER
        }

    @staticmethod
    def _clean_custom_texts(values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values if value.strip()]
        if len(cleaned) != len(set(text.casefold() for text in cleaned)):
            raise StorySessionError("CUSTOM_SELECTION_DUPLICATE", "自定义选择不能重复")
        return cleaned

    @staticmethod
    def _require_version(session: StoryBuilderSession, expected: int) -> None:
        if session.selection_version != expected:
            raise StorySessionError(
                "SESSION_VERSION_CONFLICT",
                "会话已在其他位置更新，请刷新后重试",
                session_id=session.session_id,
            )

    @staticmethod
    def _new_selection_id(version: int) -> str:
        return f"sel_{version:06d}_{uuid.uuid4().hex[:8]}"

    @staticmethod
    def _ordered_steps(steps: set[StoryStep]) -> list[StoryStep]:
        return [step for step in STORY_STEP_ORDER if step in steps]
