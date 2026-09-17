"""作品级管理：重命名与删除（NF-011）。

为什么单独放在 story_builder 而不是 story_engine：

* 重命名只改 NovelProfile.title（作者可见名字），不改任何事实；
* 删除**不是**「删掉 profile 文件」——那样会在磁盘上留下孤儿大纲 / StoryState /
  内容包 / 写作草稿。这里把这本书的全部产物**整体归档**到一个 gitignored 的
  归档目录，保证：

  ```text
  没有孤儿文件（所有产物一起移动）
  可恢复（归档目录保留原样，只是不再出现在作品列表里）
  不进入版本控制（归档目录位于 gitignored 的 workspace/ 下）
  ```

边界：本模块不修改 Canon / StoryState 的内容，只移动文件位置；不做「部分删除」。
"""

from __future__ import annotations

import datetime as _dt
import shutil
from pathlib import Path
from typing import Any

from novelforge.story_engine.profile import NovelProfile, NovelProfileRepository

ARCHIVE_DIR = "workspace/archived_novels"


class NovelAdminError(ValueError):
    def __init__(self, code: str, message: str, *, novel_id: str = "") -> None:
        self.code = code
        self.message = message
        self.novel_id = novel_id
        super().__init__(message)

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message, "novel_id": self.novel_id}


def novel_artifact_paths(project_root: Path | str, novel_id: str) -> list[Path]:
    """这本书的全部产物路径（真实存在才返回；用于删除时的完整性检查）。"""

    root = Path(project_root).resolve()
    candidates = [
        root / "novel" / "authoring" / "story_engine" / "profiles" / f"{novel_id}.json",
        root / "novel" / "config" / "story_engine" / f"{novel_id}_pack.json",
        root / "novel" / "authoring" / "story_engine" / "state" / f"runtime_{novel_id}",
        root / "novel" / "authoring" / "story_engine" / "writer" / novel_id,
    ]
    outlines = root / "novel" / "authoring" / "story_builder" / "outlines"
    if outlines.is_dir():
        for level_dir in outlines.iterdir():
            if level_dir.is_dir():
                candidates.extend(sorted(level_dir.glob(f"ol_*{novel_id}*")))
    return [path for path in candidates if path.exists()]


def rename_novel(project_root: Path | str, novel_id: str, title: str
                 ) -> dict[str, Any]:
    """改作者可见的作品名（只改 profile.title，不动任何事实）。"""

    cleaned = " ".join(str(title or "").split())
    if not cleaned:
        raise NovelAdminError("NOVEL_TITLE_EMPTY", "作品名不能为空", novel_id=novel_id)
    if len(cleaned) > 120:
        raise NovelAdminError("NOVEL_TITLE_TOO_LONG", "作品名不能超过 120 个字",
                              novel_id=novel_id)
    repository = NovelProfileRepository(Path(project_root))
    if not repository.exists(novel_id):
        raise NovelAdminError("PROFILE_NOT_FOUND", "找不到这本小说的配置",
                              novel_id=novel_id)
    profile: NovelProfile = repository.load(novel_id)
    saved = repository.save(profile.model_copy(update={"title": cleaned}))
    return {"novel_id": novel_id, "title": saved.title, "updated_at":
            saved.updated_at.isoformat(), "read_only": False}


def archive_novel(project_root: Path | str, novel_id: str, *,
                  reason: str = "") -> dict[str, Any]:
    """删除作品＝把它的全部产物整体归档（可恢复，不留孤儿）。"""

    root = Path(project_root).resolve()
    repository = NovelProfileRepository(root)
    if not repository.exists(novel_id):
        raise NovelAdminError("PROFILE_NOT_FOUND", "找不到这本小说的配置",
                              novel_id=novel_id)
    paths = novel_artifact_paths(root, novel_id)
    if not paths:
        raise NovelAdminError("NOVEL_ARTIFACTS_MISSING",
                              "这本书没有任何可归档的产物", novel_id=novel_id)
    stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = root / ARCHIVE_DIR / f"{novel_id}_{stamp}"
    if target.exists():
        raise NovelAdminError("NOVEL_ARCHIVE_EXISTS", "归档目录已经存在",
                              novel_id=novel_id)
    target.mkdir(parents=True, exist_ok=False)
    moved: list[dict[str, str]] = []
    for index, path in enumerate(paths, start=1):
        slot = target / f"{index:02d}_{path.name}"
        shutil.move(str(path), str(slot))
        moved.append({"from": str(path.relative_to(root)).replace("\\", "/"),
                      "to": str(slot.relative_to(root)).replace("\\", "/"),
                      "kind": "dir" if slot.is_dir() else "file"})
    manifest = {
        "novel_id": novel_id, "archived_at": _dt.datetime.now(
            _dt.timezone.utc).isoformat(),
        "reason": str(reason or ""), "archive_dir": str(target.relative_to(root))
        .replace("\\", "/"),
        "moved": moved, "recoverable": True,
        "note": ("删除＝整体归档：所有大纲 / StoryState / 内容包 / 写作草稿一起移动，"
                 "不会留下孤儿文件；归档目录可以直接移回原位恢复。"),
    }
    (target / "ARCHIVE_MANIFEST.json").write_text(
        __import__("json").dumps(manifest, ensure_ascii=False, indent=1),
        encoding="utf-8", newline="\n")
    return manifest


__all__ = [
    "ARCHIVE_DIR", "NovelAdminError", "archive_novel", "novel_artifact_paths",
    "rename_novel",
]
