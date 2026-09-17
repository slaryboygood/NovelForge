"""Artifact path ownership（V4-01）。

设计约束（来自 V4-01 作者决策与 `docs/v4/V4_MODULE_BOUNDARIES.md` §3.3）：

1. 每个路径都必须显式携带 `project_id` / `novel_id` / `artifact_kind`
2. 禁止 `GLOBAL_CURRENT_NOVEL`、禁止默认作品、禁止扫描磁盘推断「当前作品」
3. 禁止「当前作品没有数据 → 回退到其他作品或已删除的历史数据」
4. 任何 artifact 的 novel_id 与请求的 novel_id 不一致时必须报错，不得静默使用

历史说明：V3 曾在产品代码里写死 `wasteland_001`（`RECON_DIR` / `PLANNING_INDEX` /
`canon/wasteland_001.sqlite` / `writer_v1`）。V4-01 删除这些废弃资产后，
本模块成为唯一的路径来源（对应缺陷 NR-002 的结构性修复）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# 与 story_engine.profile.NOVEL_ID_PATTERN 保持一致（同一个身份规则）
NOVEL_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_-]{2,95}$"

#: 允许通过本模块解析的 artifact 类别（显式枚举，避免"随手拼一个路径"）
ARTIFACT_KINDS: frozenset[str] = frozenset({
    "profile",
    "content_pack",
    "story_state",
    "canon",
    "writer_store",
    "planning",
    "session",
    "blueprint",
    "outline",
})

_NOVEL_ID_RE = re.compile(NOVEL_ID_PATTERN)


class OwnershipError(ValueError):
    """路径解析 / 归属校验失败（缺 context、id 非法、跨作品读取）。"""

    def __init__(self, code: str, message: str, *, novel_id: str = "") -> None:
        self.code = code
        self.message = message
        self.novel_id = novel_id
        super().__init__(message)

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message, "novel_id": self.novel_id}


def _validate_novel_id(novel_id: str) -> str:
    value = str(novel_id or "").strip()
    if not value:
        raise OwnershipError(
            "NOVEL_ID_REQUIRED",
            "artifact 路径必须显式携带 novel_id（不允许隐式当前作品）")
    if not _NOVEL_ID_RE.match(value):
        raise OwnershipError("NOVEL_ID_INVALID", f"novel_id 格式不正确：{value}",
                             novel_id=value)
    return value


@dataclass(frozen=True)
class ArtifactContext:
    """一次 artifact 访问的完整归属上下文。

    `project_id` 缺省时等价于 `novel_id`（V3 现状：sessions 用 project_id、
    profile/canon/writer 用 novel_id，二者同值；最终层级关系待 V4-08 定案）。
    """

    project_root: Path
    novel_id: str
    project_id: str = ""
    artifact_kind: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_root", Path(self.project_root).resolve())
        object.__setattr__(self, "novel_id", _validate_novel_id(self.novel_id))
        if self.project_id:
            _validate_novel_id(self.project_id)
        if self.artifact_kind and self.artifact_kind not in ARTIFACT_KINDS:
            raise OwnershipError(
                "ARTIFACT_KIND_UNKNOWN",
                f"未登记的 artifact_kind：{self.artifact_kind}"
                f"（允许值：{sorted(ARTIFACT_KINDS)}）",
                novel_id=self.novel_id)

    @property
    def owner_id(self) -> str:
        return self.project_id or self.novel_id

    def resolve(self, *parts: str) -> Path:
        """在项目根下解析路径，并保证结果不逃逸出项目根。"""

        target = self.project_root.joinpath(*parts).resolve()
        if target != self.project_root and self.project_root not in target.parents:
            raise OwnershipError("PATH_ESCAPES_PROJECT",
                                 f"路径逃逸出项目根：{target}", novel_id=self.novel_id)
        return target


def novel_context(project_root: Path | str, novel_id: str, *,
                  project_id: str = "", artifact_kind: str = "") -> ArtifactContext:
    """构造归属上下文。**novel_id 必填**，没有默认值。"""

    return ArtifactContext(project_root=Path(project_root), novel_id=novel_id,
                           project_id=project_id, artifact_kind=artifact_kind)


def require_same_novel(expected_novel_id: str, artifact_novel_id: str, *,
                       artifact_ref: str = "") -> None:
    """跨作品读取守卫：artifact 归属与请求作品不一致时直接报错。"""

    if _validate_novel_id(expected_novel_id) != _validate_novel_id(artifact_novel_id):
        raise OwnershipError(
            "CROSS_NOVEL_ACCESS",
            f"拒绝跨作品访问：请求 {expected_novel_id}，artifact 属于 {artifact_novel_id}"
            + (f"（{artifact_ref}）" if artifact_ref else ""),
            novel_id=expected_novel_id)


def profiles_path(project_root: Path | str, novel_id: str) -> Path:
    """作品档案文件：novel/authoring/story_engine/profiles/<novel_id>.json"""

    context = novel_context(project_root, novel_id, artifact_kind="profile")
    return context.resolve("novel", "authoring", "story_engine", "profiles",
                           f"{context.novel_id}.json")


def content_pack_path(project_root: Path | str, novel_id: str,
                      *, pack_id: str = "") -> Path:
    """内容包文件：novel/config/story_engine/<pack_id>.json（缺省 = <novel_id>_pack）"""

    context = novel_context(project_root, novel_id, artifact_kind="content_pack")
    resolved_pack = str(pack_id or f"{context.novel_id}_pack").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", resolved_pack):
        raise OwnershipError("PACK_ID_INVALID", f"内容包 id 不合法：{resolved_pack}",
                             novel_id=context.novel_id)
    return context.resolve("novel", "config", "story_engine", f"{resolved_pack}.json")


def story_state_dir(project_root: Path | str, novel_id: str) -> Path:
    """StoryState 根目录：novel/authoring/story_engine/state"""

    context = novel_context(project_root, novel_id, artifact_kind="story_state")
    return context.resolve("novel", "authoring", "story_engine", "state")


def canon_db_path(project_root: Path | str, novel_id: str) -> Path:
    """Canon SQLite：novel/authoring/story_engine/canon/<novel_id>.sqlite

    V3 曾把它写成 `canon/wasteland_001.sqlite` 常量出现在 4 个产品模块里；
    V4-01 起唯一入口在这里（按作品隔离，绝不回退到别的作品）。
    """

    context = novel_context(project_root, novel_id, artifact_kind="canon")
    return context.resolve("novel", "authoring", "story_engine", "canon",
                           f"{context.novel_id}.sqlite")


def writer_store_dir(project_root: Path | str, novel_id: str) -> Path:
    """Writer 存储根目录：novel/authoring/story_engine/writer"""

    context = novel_context(project_root, novel_id, artifact_kind="writer_store")
    return context.resolve("novel", "authoring", "story_engine", "writer")


def planning_dir(project_root: Path | str, novel_id: str) -> Path:
    """Planning IR 目录：novel/authoring/story_engine/planning/<novel_id>"""

    context = novel_context(project_root, novel_id, artifact_kind="planning")
    return context.resolve("novel", "authoring", "story_engine", "planning",
                           context.novel_id)


def planning_index_path(project_root: Path | str, novel_id: str) -> Path:
    """Planning IR index：planning/<novel_id>/index.json"""

    return planning_dir(project_root, novel_id) / "index.json"


__all__ = [
    "ARTIFACT_KINDS", "NOVEL_ID_PATTERN", "ArtifactContext", "OwnershipError",
    "canon_db_path", "content_pack_path", "novel_context", "planning_dir",
    "planning_index_path", "profiles_path", "require_same_novel", "story_state_dir",
    "writer_store_dir",
]

