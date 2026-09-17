"""StoryState 持久化（主计划 T08d-02 前置）。

约束来自迁移要求：**不新增 Adventure 专用字段**。
因此引擎状态单独存放在：

    novel/authoring/story_engine/state/{blueprint_id}/v{version}[_{branch}].json

旧 Adventure 存档保持原样可读；两份文件一一对应同一 blueprint + revision 分支，
首次读取时由 `load_or_migrate` 从旧存档迁移出等价的初始 StoryState。
"""

from __future__ import annotations

import json
import os
import re
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from novelforge.models import StrictModel

from .state import StoryState, from_legacy_adventure, story_state_from_payload

DEFAULT_STATE_PATH = Path("novel/authoring/story_engine/state")
_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_-]{2,95}$"
_BRANCH_PATTERN = r"^(main|branch_[a-f0-9]{32})$"


class StoryStateStorageError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


class StoredStoryState(StrictModel):
    schema_version: int = 1
    story_state: StoryState


class StoryStateRepository:
    def __init__(self, project_root: Path, states_path: Path | str = DEFAULT_STATE_PATH) -> None:
        self.project_root = project_root.resolve()
        relative = Path(states_path)
        self.states_dir = (
            relative.resolve() if relative.is_absolute() else (self.project_root / relative).resolve()
        )
        try:
            self.states_dir.relative_to(self.project_root)
        except ValueError as exc:
            raise StoryStateStorageError("STORY_STATE_PATH_OUTSIDE_PROJECT", "引擎状态目录超出当前项目范围") from exc

    def path_for(self, blueprint_id: str, version: int, branch_id: str = "main") -> Path:
        if not re.fullmatch(_ID_PATTERN, blueprint_id):
            raise StoryStateStorageError("STORY_STATE_ID_INVALID", "蓝图编号格式不正确")
        if version < 1:
            raise StoryStateStorageError("STORY_STATE_VERSION_INVALID", "版本号必须大于零")
        if not re.fullmatch(_BRANCH_PATTERN, branch_id):
            raise StoryStateStorageError("STORY_STATE_BRANCH_INVALID", "路线编号格式不正确")
        suffix = "" if branch_id == "main" else f"_{branch_id}"
        return self.states_dir / blueprint_id / f"v{version:06d}{suffix}.json"

    def exists(self, blueprint_id: str, version: int, branch_id: str = "main") -> bool:
        return self.path_for(blueprint_id, version, branch_id).is_file()

    def save(self, state: StoryState, blueprint_id: str, version: int, branch_id: str = "main") -> StoryState:
        target = self.path_for(blueprint_id, version, branch_id)
        self._atomic_write(target, StoredStoryState(story_state=state))
        return state

    def load(self, blueprint_id: str, version: int, branch_id: str = "main") -> StoryState:
        path = self.path_for(blueprint_id, version, branch_id)
        if not path.is_file():
            raise StoryStateStorageError("STORY_STATE_NOT_FOUND", "找不到这条路线的引擎状态")
        try:
            stored = StoredStoryState.model_validate(json.loads(path.read_text(encoding="utf-8-sig")))
        except (OSError, UnicodeError, json.JSONDecodeError, ValidationError) as exc:
            raise StoryStateStorageError("STORY_STATE_READ_FAILED", "无法读取引擎状态") from exc
        return stored.story_state

    def load_or_migrate(self, legacy: Mapping[str, Any] | None, blueprint_id: str, version: int,
                        branch_id: str = "main", *, novel_id: str = "") -> tuple[StoryState, bool]:
        """读取引擎状态；不存在时从旧 Adventure 存档迁移出初始状态。"""

        if self.exists(blueprint_id, version, branch_id):
            return self.load(blueprint_id, version, branch_id), False
        payload = dict(legacy or {})
        state = from_legacy_adventure(payload, novel_id=novel_id) if payload else StoryState(novel_id=novel_id)
        return state, True

    def delete(self, blueprint_id: str, version: int, branch_id: str = "main") -> bool:
        path = self.path_for(blueprint_id, version, branch_id)
        if not path.is_file():
            return False
        path.unlink()
        return True

    def branches(self, blueprint_id: str, version: int) -> list[str]:
        """列出该蓝图版本已有的分支（main 永远存在，其它按文件后缀）。"""

        main_path = self.path_for(blueprint_id, version, "main")
        found = ["main"] if main_path.is_file() else []
        folder = main_path.parent
        if folder.is_dir():
            prefix = f"v{version:06d}_"
            for item in sorted(folder.glob(f"{prefix}*.json")):
                branch = item.stem[len(prefix):]
                if re.fullmatch(_BRANCH_PATTERN, branch) and branch not in found:
                    found.append(branch)
        return found

    def fork(self, blueprint_id: str, version: int, *, source_branch: str = "main",
             target_branch: str) -> StoryState:
        """把某个分支的当前事实深拷贝到新分支；源分支与目标分支都必须合法，且目标不存在时更安全。"""

        if source_branch == target_branch:
            raise StoryStateStorageError("STORY_STATE_FORK_SAME_BRANCH", "源分支与目标分支不能相同")
        if self.exists(blueprint_id, version, target_branch):
            raise StoryStateStorageError("STORY_STATE_BRANCH_EXISTS", "目标分支已经存在")
        state = self.load(blueprint_id, version, source_branch)
        forked = state.model_copy(deep=True)
        self.save(forked, blueprint_id, version, target_branch)
        return forked

    @staticmethod
    def _atomic_write(path: Path, stored: StoredStoryState) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        payload = json.dumps(stored.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
