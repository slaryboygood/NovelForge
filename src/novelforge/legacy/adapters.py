"""Legacy adapters —— 对 frozen 能力的**只读**包装（V4-01）。

本模块只做两件事：

1. 暴露 frozen 能力清单（供服务层 / 文档 / 守卫测试查询）；
2. 对真正仍需要兼容的旧数据给出只读状态查询（例如旧旅程存档）。

禁止：通过本包写入任何数据、访问已删除的历史资产、把 frozen 能力接回产品写路径。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .manifest import FROZEN_MODULES, FrozenModule, frozen_module


class LegacyAdapterError(RuntimeError):
    """尝试通过 legacy 边界执行不被允许的操作。"""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


def describe_legacy_capabilities() -> dict[str, Any]:
    """只读：当前仍在原地保留的 frozen 能力清单。"""

    return {
        "count": len(FROZEN_MODULES),
        "modules": [
            {"module_id": item.module_id, "path": item.path,
             "capability": item.capability, "status": item.status,
             "used_by": list(item.used_by),
             "removal_condition": item.removal_condition}
            for item in FROZEN_MODULES
        ],
        "deleted_assets": [
            "已删除（V4-01）：旧正文 69 个 tracked 文件（原 novel/final 目录）",
            "已删除（V4-01）：570 章 historical 导出树（原 workspace/wasteland_001_exports）",
        ],
        "read_only": True,
    }


def legacy_adventure_status(project_root: Path | str, novel_id: str) -> dict[str, Any]:
    """只读：某作品是否存在旧旅程存档（rules_version 1 / 2）。

    只报告事实，不迁移、不转换、不写入；没有存档时返回 `exists: False`。
    """

    module = _require_module("story_builder.adventures")
    root = Path(project_root)
    folder = root / "novel" / "authoring" / "story_builder" / "adventures" / str(novel_id)
    files = sorted(folder.glob("v*.json")) if folder.is_dir() else []
    return {
        "novel_id": novel_id,
        "adapter": module.module_id,
        "exists": bool(files),
        "file_count": len(files),
        "source_ref": str(folder.relative_to(root)) if folder.is_dir() else "",
        "read_only": True,
        "note": "旧旅程存档为只读兼容；不会被转换成 StoryState。",
    }


def _require_module(module_id: str) -> FrozenModule:
    module = frozen_module(module_id)
    if module is None:
        raise LegacyAdapterError("LEGACY_MODULE_NOT_REGISTERED",
                                 f"{module_id} 未登记在 legacy manifest")
    return module


def forbid_write(operation: str) -> None:
    """供 frozen 模块或适配器显式拒绝写操作（结构上禁止 legacy 写路径）。"""

    raise LegacyAdapterError(
        "LEGACY_READ_ONLY",
        f"legacy 边界只允许只读操作：{operation} 被拒绝"
        "（frozen 能力不得接回产品写路径）")


__all__ = [
    "FROZEN_MODULES", "LegacyAdapterError", "describe_legacy_capabilities",
    "forbid_write", "legacy_adventure_status",
]
